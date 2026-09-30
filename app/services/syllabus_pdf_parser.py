"""Generic parser for TIE (2023) Ordinary Secondary syllabus PDFs.

Every 2023 TIE O-Level syllabus (Physics, Geography, Biology, Computer Science,
Mathematics, History, ...) presents its teaching content as the same 7-column
matrix::

    Main competence | Specific competence | Learning activities |
    Suggested teaching & learning methods | Assessment criteria |
    Suggested resources | Number of periods

This module turns that matrix into the JSON structure accepted by
``POST /api/syllabus/`` (see :class:`app.schemas.SyllabusInput`), one syllabus
per Form. Mapping:

* main competence      -> Topic
* specific competence  -> SubTopic (``planned_periods`` = sum of its periods)
* learning activity    -> Objective (with its own methods, resources,
  assessment criteria and periods)

Periods in TIE syllabi are printed either once per specific competence (e.g.
Physics) or once per learning activity (e.g. Geography). Both layouts are
handled: explicit per-activity numbers are kept and any remaining periods of a
specific competence are shared evenly among the activities without a number.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import BinaryIO, Optional, Union

import pdfplumber

FORM_NUMERALS = ["I", "II", "III", "IV"]
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

_FORM_TOKEN = r"(IV|III|II|I|One|Two|Three|Four)"
_FORM_WORDS = {"ONE": "I", "TWO": "II", "THREE": "III", "FOUR": "IV"}
_FORM_HEADING_RE = re.compile(
    r"^\s*(?:Table\s+\d+\s*:\s*)?(?:Detailed\s+Contents?\s+for\s+)?Form\s+" + _FORM_TOKEN + r"\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_CODE_RE = re.compile(r"^\s*(\d+\.\d+)\s*(.*)$", re.DOTALL)
_ACTIVITY_RE = re.compile(r"^\s*\(([a-z]{1,3})\)\s*(.*)$", re.DOTALL)
_PPW_NUMBER_RE = re.compile(r"\b(\w+)\s*(?:\(\d+\))?\s+periods?\b", re.IGNORECASE)
_PPW_FORMS_RE = re.compile(
    r"Forms?\s+" + _FORM_TOKEN + r"(?:\s*(?:[-–]|and|&|to)\s*" + _FORM_TOKEN + r")?", re.IGNORECASE
)


def _form_numeral(token: str) -> str:
    t = token.upper()
    return _FORM_WORDS.get(t, t)


# ---------------------------------------------------------------------------
# Intermediate structures
# ---------------------------------------------------------------------------


@dataclass
class _Activity:
    text: str
    methods: str = ""
    assessment: str = ""
    resources: str = ""
    periods: Optional[int] = None


@dataclass
class _Specific:
    code: str
    title: str
    periods: int = 0
    activities: list[_Activity] = field(default_factory=list)


@dataclass
class _Main:
    code: str
    title: str
    specifics: list[_Specific] = field(default_factory=list)


@dataclass
class ParsedSyllabus:
    """Result of parsing a syllabus PDF."""

    subject: str
    source_note: str
    periods_per_week: dict[str, int]
    forms: dict[str, list[_Main]]

    def form_names(self) -> list[str]:
        return list(self.forms.keys())

    def to_syllabus_input(self, form: str, subject: Optional[str] = None) -> dict:
        """Return a dict matching ``SyllabusInput`` for the given form."""
        form = normalise_form(form)
        if form not in self.forms:
            raise KeyError(f"{form} not found in syllabus (available: {self.form_names()})")
        topics = []
        for t_order, main in enumerate(self.forms[form], start=1):
            sub_topics = []
            for s_order, spec in enumerate(main.specifics, start=1):
                periods = _distribute_activity_periods(spec)
                objectives = [
                    {
                        "order": i,
                        "text": act.text,
                        "periods": periods[i - 1],
                        "teaching_methods": act.methods or None,
                        "resources": act.resources or None,
                        "assessment_criteria": act.assessment or None,
                    }
                    for i, act in enumerate(spec.activities, start=1)
                ]
                sub_topics.append(
                    {
                        "order": s_order,
                        "sub_topic_id_code": spec.code,
                        "title": spec.title,
                        "planned_periods": sum(periods) if periods else spec.periods,
                        "competences": [a.text for a in spec.activities],
                        "objectives": objectives,
                    }
                )
            topics.append(
                {
                    "order": t_order,
                    "topic_id_code": main.code,
                    "title": main.title,
                    "sub_topics": sub_topics,
                }
            )
        return {
            "subject": subject or self.subject,
            "form": form,
            "source_note": self.source_note,
            "periods_per_week": self.periods_per_week.get(form),
            "topics": topics,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalise_form(form: str) -> str:
    """Normalise 'form 1', 'F1', 'Form I', 'i' ... to 'Form I'."""
    s = re.sub(r"^(FORM|F)\s*", "", form.strip().upper()).strip()
    s = {"1": "I", "2": "II", "3": "III", "4": "IV"}.get(s, s)
    if s not in FORM_NUMERALS:
        raise ValueError(f"Unrecognised form: {form!r}")
    return f"Form {s}"


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"(\w)-\n(\w)", r"\1-\2", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _join(a: str, b: str) -> str:
    return f"{a} {b}".strip() if a else b


_LABEL_TAILS = {
    "work", "learning", "discussion", "approach", "method", "methods", "study",
    "visit", "trip", "session", "experiment", "strategy", "simulation", "simulations",
}


def _method_labels(raw: Optional[str]) -> str:
    """Extract the bold method labels ('Brainstorming', 'Group discussion').

    TIE cells read like ``Brainstorming: Guide students ... Group discussion:
    Organise ...``; a label is the text between the previous sentence end and
    a colon, and may wrap across lines.
    """
    if not raw:
        return ""
    raw = raw.replace("\u00a0", " ")
    # Candidate label starts: beginning of a line or of a sentence
    starts = sorted({0, *[m.end() for m in re.finditer(r"\n|[.;]\s+", raw)]})
    labels = []
    prev_colon = 0
    for colon in [m.start() for m in re.finditer(r":", raw)]:
        candidates = [
            st for st in starts
            if prev_colon <= st < colon and raw[st:st + 1].isupper()
        ]
        prev_colon = colon + 1
        if not candidates:
            continue
        label = _clean(raw[candidates[-1]:colon]).strip(" ,")
        # "Practical\nWork:" - a lone generic tail word belongs to the line above
        if label.lower() in _LABEL_TAILS and len(candidates) > 1:
            longer = _clean(raw[candidates[-2]:colon]).strip(" ,")
            if len(longer.split()) <= 4 and "." not in longer:
                label = longer
        if "." in label or not 1 <= len(label.split()) <= 8:
            continue
        if label.lower() in {"note", "e.g", "i.e"}:
            continue
        labels.append(re.sub(r"\s*-\s*", "-", label))
    if not labels:
        # No "Label:" formatting - fall back to the first sentence fragment
        return _clean(raw).split(".")[0][:120]
    return ", ".join(dict.fromkeys(labels))


def _to_int(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def _distribute_activity_periods(spec: _Specific) -> list[int]:
    """Give every activity a period count that sums to the competence total."""
    acts = spec.activities
    if not acts:
        return []
    explicit = [a.periods for a in acts]
    known = sum(p for p in explicit if p)
    total = max(spec.periods, known)
    unknown_idx = [i for i, p in enumerate(explicit) if not p]
    result = [p or 0 for p in explicit]
    remaining = total - known
    if unknown_idx:
        if remaining <= 0:
            # No budget left: give each unnumbered activity at least one period
            for i in unknown_idx:
                result[i] = 1
        else:
            base, extra = divmod(remaining, len(unknown_idx))
            for n, i in enumerate(unknown_idx):
                result[i] = base + (1 if n < extra else 0)
    # Guarantee every activity gets >= 1 period so it appears in the scheme
    return [max(1, p) for p in result]


def _detect_subject(first_pages_text: str) -> str:
    m = re.search(r"([A-Z][A-Z &'’\-]{2,60}?)\s+SYLLABUS\s+FOR", first_pages_text)
    if m:
        return m.group(1).strip().title()
    m = re.search(r"([A-Z][A-Z &'’\-]{2,60}?)\s+SYLLABUS", first_pages_text)
    return m.group(1).strip().title() if m else "Unknown Subject"


def _detect_periods_per_week(text: str) -> dict[str, int]:
    """Read section 10.0 'Number of periods' into {'Form I': 3, ...}."""
    flat = re.sub(r"\s+", " ", text)
    sections = [
        m.group(1)
        for m in re.finditer(r"Number of Periods(.*?)(?:11\.0|$)", flat, re.IGNORECASE)
        if "week" in m.group(1).lower()
    ]
    section = sections[-1] if sections else flat
    clauses = re.split(r",|;|\bwhile\b|\band\s+(?=\w+\s*(?:\(\d+\))?\s+periods)", section)
    result: dict[str, int] = {}
    default: Optional[int] = None
    for clause in clauses:
        nm = _PPW_NUMBER_RE.search(clause)
        if not nm:
            continue
        word = nm.group(1).lower()
        n = NUMBER_WORDS.get(word) or (int(word) if word.isdigit() else None)
        if not n:
            continue
        fm = _PPW_FORMS_RE.search(clause)
        if not fm:
            default = default or n
            continue
        start = FORM_NUMERALS.index(_form_numeral(fm.group(1)))
        end = FORM_NUMERALS.index(_form_numeral(fm.group(2))) if fm.group(2) else start
        for i in range(start, end + 1):
            result.setdefault(f"Form {FORM_NUMERALS[i]}", n)
    if default:
        for f in FORM_NUMERALS:
            result.setdefault(f"Form {f}", default)
    return result


def _is_header(row: list[str]) -> bool:
    cells = [re.sub(r"\s+", " ", c or "").lower() for c in row]
    return (
        "main competence" in cells[0]
        or "specific competence" in cells[1]
        or cells[2].startswith("learning activit")
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def parse_syllabus_pdf(source: Union[str, bytes, BinaryIO]) -> ParsedSyllabus:
    """Parse a TIE O-Level syllabus PDF into structured competences per Form."""
    if isinstance(source, bytes):
        source = io.BytesIO(source)

    forms: dict[str, list[_Main]] = {}
    current_form: Optional[str] = None
    main: Optional[_Main] = None
    spec: Optional[_Specific] = None
    act: Optional[_Activity] = None
    intro_text = []

    with pdfplumber.open(source) as pdf:
        for page_no, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if page_no < 25:
                intro_text.append(text)

            tables = page.extract_tables()
            m = _FORM_HEADING_RE.search(text) if tables else None
            if m:
                new_form = f"Form {_form_numeral(m.group(1))}"
                # Forms only move forward; ignore stray "Form III" mentions in cells
                if current_form is None or FORM_NUMERALS.index(new_form[5:]) > FORM_NUMERALS.index(current_form[5:]):
                    current_form = new_form
                    forms.setdefault(current_form, [])
                    main = spec = act = None

            for table in tables:
                for raw_row in table:
                    row = _compact(raw_row)
                    if row is None or _is_header([c or "" for c in row]):
                        continue
                    if current_form is None:
                        current_form = "Form I"
                        forms.setdefault(current_form, [])

                    c_main, c_spec, c_act, c_meth, c_assess, c_res, c_per = row
                    main_txt, spec_txt, act_txt = _clean(c_main), _clean(c_spec), _clean(c_act)
                    periods = _to_int(c_per)

                    mm = _CODE_RE.match(main_txt)
                    if mm and mm.group(1).endswith(".0"):
                        main = _Main(code=mm.group(1), title=_clean(mm.group(2)))
                        forms[current_form].append(main)
                        spec = act = None
                    elif main_txt and main is not None and not spec_txt and not act_txt:
                        main.title = _join(main.title, main_txt)

                    sm = _CODE_RE.match(spec_txt)
                    if sm and not sm.group(1).endswith(".0"):
                        if main is None:
                            main = _Main(code=sm.group(1).split(".")[0] + ".0", title="")
                            forms[current_form].append(main)
                        spec = _Specific(code=sm.group(1), title=_clean(sm.group(2)))
                        main.specifics.append(spec)
                        act = None
                    elif spec_txt and spec is not None and not act_txt:
                        spec.title = _join(spec.title, spec_txt)

                    if spec is None:
                        continue

                    am = _ACTIVITY_RE.match(act_txt)
                    if am:
                        act = _Activity(text=act_txt)
                        spec.activities.append(act)
                    elif act_txt and act is not None:
                        act.text = _join(act.text, act_txt)
                    elif act_txt and act is None:
                        act = _Activity(text=act_txt)
                        spec.activities.append(act)

                    if act is not None:
                        labels = _method_labels(c_meth)
                        if labels:
                            act.methods = ", ".join(dict.fromkeys(filter(None, [*act.methods.split(", "), *labels.split(", ")])))
                        act.assessment = _join(act.assessment, _clean(c_assess))
                        act.resources = _join(act.resources, _clean(c_res))

                    if periods:
                        if am and (spec.periods or len(spec.activities) > 1):
                            # Per-activity layout (a second number within a competence)
                            act.periods = periods
                            spec.periods += periods
                        elif am:
                            act.periods = None
                            spec.periods = periods
                            spec._first_activity_period = periods  # type: ignore[attr-defined]
                        else:
                            spec.periods += periods

    # Resolve the "first activity number" ambiguity: if a competence had only one
    # number on its first activity it is the competence total (Physics layout);
    # if later activities also had numbers, the first one was per-activity too.
    for mains in forms.values():
        for mn in mains:
            for sp in mn.specifics:
                first = getattr(sp, "_first_activity_period", None)
                if first is not None and any(a.periods for a in sp.activities[1:]):
                    sp.activities[0].periods = first
                    sp.periods = sum(a.periods or 0 for a in sp.activities)
    # Drop empty forms / competences
    forms = {
        f: [mn for mn in mains if mn.specifics]
        for f, mains in forms.items()
        if any(mn.specifics for mn in mains)
    }

    intro = "\n".join(intro_text)
    subject = _detect_subject(intro[:3000])
    return ParsedSyllabus(
        subject=subject,
        source_note=f"TIE (2023), {subject} Syllabus for Ordinary Secondary Education Form I-IV",
        periods_per_week=_detect_periods_per_week(intro),
        forms=forms,
    )


def _compact(raw_row: list[Optional[str]]) -> Optional[list[Optional[str]]]:
    """Return the 7 content cells of a matrix row, or None for non-matrix rows."""
    if len(raw_row) == 7:
        return list(raw_row)
    cells = [c for c in raw_row if c is not None]
    if len(cells) == 7 and any((c or "").strip() for c in cells):
        return cells
    return None
