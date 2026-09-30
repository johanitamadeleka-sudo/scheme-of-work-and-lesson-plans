"""
Generate a Scheme of Work (and optionally Lesson Plans) for ANY subject.

Give it an official TIE 2023 O-Level syllabus PDF (or a syllabus JSON produced
by this script / the API) and a Form; it parses the competence matrix, fits
the periods to the academic calendar and writes the .docx files.

Examples:
    # Physics Form I, 3 periods/week read from the syllabus, scheme fills the year
    venv/bin/python seed/generate_scheme.py \
        --syllabus "assets/syllabus/PHYSICS SYLLABUS - O Level 2023.pdf" --form "Form I"

    # Every form of Geography, schemes only, override weekly periods
    venv/bin/python seed/generate_scheme.py \
        --syllabus "assets/syllabus/GEOGRAPHY SYLLABUS - O Level 2023.pdf" --form all \
        --periods-per-week 3 --no-lesson-plans

    # Just extract the syllabus to editable JSON (one file per form)
    venv/bin/python seed/generate_scheme.py --syllabus some.pdf --form all --export-json data/syllabi

Uses an in-memory database, so it never touches sow_generator.db.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.syllabus_pdf_parser import normalise_form, parse_syllabus_pdf  # noqa: E402

DEFAULT_CALENDAR = PROJECT_ROOT / "data" / "calendars" / "tanzania_secondary_2026.json"


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


def load_syllabi(path: Path, form: str, subject: str | None) -> list[dict]:
    """Return SyllabusInput dicts for the requested form(s)."""
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        items = data if isinstance(data, list) else [data]
        if subject:
            for item in items:
                item["subject"] = subject
        if form != "all":
            items = [i for i in items if normalise_form(i["form"]) == normalise_form(form)]
        return items

    parsed = parse_syllabus_pdf(str(path))
    if not parsed.forms:
        sys.exit(f"No competence matrix found in {path}")
    forms = parsed.form_names() if form == "all" else [normalise_form(form)]
    return [parsed.to_syllabus_input(f, subject) for f in forms]


def _client() -> TestClient:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def generate(
    syllabus: dict,
    calendar: dict,
    out_dir: Path,
    periods_per_week: int | None,
    fit: str,
    lesson_plans: bool,
    textbook: str | None,
) -> None:
    client = _client()
    if periods_per_week:
        syllabus["periods_per_week"] = periods_per_week

    resp = client.post("/api/syllabus/", json=syllabus)
    resp.raise_for_status()
    syl = resp.json()
    resp = client.post("/api/calendar/", json=calendar)
    resp.raise_for_status()
    cal = resp.json()

    if textbook:
        entries = [
            {"sub_topic_id": st["id"], "book_title": textbook}
            for t in syl["topics"]
            for st in t["sub_topics"]
        ]
        client.post("/api/textbook/", json=entries).raise_for_status()

    resp = client.post(
        "/api/allocate",
        json={"syllabus_id": syl["id"], "calendar_id": cal["id"], "fit": fit},
    )
    resp.raise_for_status()
    alloc = resp.json()

    name = f"{_slug(syl['subject'])}_{_slug(syl['form'])}_{_slug(cal['academic_year'])}"
    out_dir.mkdir(parents=True, exist_ok=True)

    resp = client.get(f"/api/scheme/{syl['id']}/{cal['id']}/docx")
    resp.raise_for_status()
    scheme_path = out_dir / f"Scheme_of_Work_{name}.docx"
    scheme_path.write_bytes(resp.content)

    print(f"\n{syl['subject']} {syl['form']}  ({syl.get('periods_per_week') or 'calendar'} periods/week)")
    print(
        f"  syllabus periods: {alloc['total_planned']}  calendar capacity: {alloc['capacity']}"
        f"  allocated: {alloc['total_allocated']}  (fit={alloc['fit']})"
    )
    print(f"  -> {scheme_path.relative_to(PROJECT_ROOT) if scheme_path.is_relative_to(PROJECT_ROOT) else scheme_path}")

    if lesson_plans:
        resp = client.get(f"/api/lesson-plan/{syl['id']}/{cal['id']}/docx")
        resp.raise_for_status()
        lp_path = out_dir / f"Lesson_Plans_{name}.docx"
        lp_path.write_bytes(resp.content)
        print(f"  -> {lp_path.relative_to(PROJECT_ROOT) if lp_path.is_relative_to(PROJECT_ROOT) else lp_path}")

    app.dependency_overrides.clear()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--syllabus", required=True, type=Path, help="TIE syllabus PDF or syllabus JSON")
    ap.add_argument("--form", default="Form I", help="'Form I'..'Form IV', 'F2', '3' or 'all'")
    ap.add_argument("--subject", help="Override the subject name detected from the PDF")
    ap.add_argument("--calendar", type=Path, default=DEFAULT_CALENDAR, help="Calendar JSON")
    ap.add_argument("--periods-per-week", type=int, help="Override weekly periods from the syllabus")
    ap.add_argument(
        "--fit",
        choices=["none", "shrink", "scale"],
        default="scale",
        help="scale: fill the calendar exactly (default); shrink: only scale down; none: keep syllabus periods",
    )
    ap.add_argument("--textbook", help="Textbook title to cite for every competence")
    ap.add_argument("--out", type=Path, default=PROJECT_ROOT / "examples")
    ap.add_argument("--no-lesson-plans", action="store_true")
    ap.add_argument("--export-json", type=Path, help="Write parsed syllabus JSON here and exit")
    args = ap.parse_args()

    syllabi = load_syllabi(args.syllabus, args.form, args.subject)

    if args.export_json:
        args.export_json.mkdir(parents=True, exist_ok=True)
        for s in syllabi:
            path = args.export_json / f"{_slug(s['subject']).lower()}_{_slug(s['form']).lower()}.json"
            path.write_text(json.dumps(s, indent=2, ensure_ascii=False))
            print(f"wrote {path}")
        return

    calendar = json.loads(args.calendar.read_text())
    for s in syllabi:
        generate(
            s,
            calendar,
            args.out,
            args.periods_per_week,
            args.fit,
            not args.no_lesson_plans,
            args.textbook,
        )


if __name__ == "__main__":
    main()
