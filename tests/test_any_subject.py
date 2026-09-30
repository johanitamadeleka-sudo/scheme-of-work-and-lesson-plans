"""Tests for subject-agnostic generation: PDF parsing, periods/week and fit-to-calendar."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.services.allocation import effective_week_budgets, scale_periods
from app.services.syllabus_pdf_parser import normalise_form, parse_syllabus_pdf

SYLLABUS_DIR = Path(__file__).resolve().parent.parent / "assets" / "syllabus"
PHYSICS_PDF = SYLLABUS_DIR / "PHYSICS SYLLABUS - O Level 2023.pdf"
GEOGRAPHY_PDF = SYLLABUS_DIR / "GEOGRAPHY SYLLABUS - O Level 2023.pdf"


# ----------------------------------------------------------------- helpers


def _syllabus(periods, ppw=None, objectives=None):
    return {
        "subject": "Physics",
        "form": "Form I",
        "periods_per_week": ppw,
        "topics": [
            {
                "order": 1,
                "topic_id_code": "1.0",
                "title": "Apply knowledge of Physics",
                "sub_topics": [
                    {
                        "order": i + 1,
                        "sub_topic_id_code": f"1.{i + 1}",
                        "title": f"Competence {i + 1}",
                        "planned_periods": p,
                        "objectives": (objectives or {}).get(i, [{"order": 1, "text": f"(a) Activity {i + 1}"}]),
                    }
                    for i, p in enumerate(periods)
                ],
            }
        ],
    }


def _calendar(weeks=4, budget=5):
    return {
        "academic_year": "2026",
        "terms": [
            {
                "order": 1,
                "term_id_code": "T1",
                "title": "Term 1",
                "weeks": [
                    {
                        "week_number": n + 1,
                        "start_date": (date(2026, 1, 5) + timedelta(weeks=n)).isoformat(),
                        "classification": "teaching",
                        "period_budget": budget,
                        "label": f"January Week {n + 1}",
                    }
                    for n in range(weeks)
                ],
            }
        ],
    }


def _setup(client, syllabus, calendar):
    sid = client.post("/api/syllabus/", json=syllabus).json()["id"]
    cid = client.post("/api/calendar/", json=calendar).json()["id"]
    return sid, cid


# ----------------------------------------------------------------- unit tests


def test_scale_periods_sums_to_target_and_keeps_every_item():
    assert sum(scale_periods([22, 11, 14, 16], 30)) == 30
    assert all(p >= 1 for p in scale_periods([100, 1, 1], 10))
    assert scale_periods([5, 5], 10) == [5, 5]


def test_effective_budget_scales_short_weeks():
    class W:
        def __init__(self, i, b):
            self.id, self.period_budget = i, b

    budgets = effective_week_budgets([W(1, 5), W(2, 2), W(3, 0)], 3)
    assert budgets == {1: 3, 2: 1, 3: 0}


@pytest.mark.parametrize(
    "value,expected",
    [("Form I", "Form I"), ("form 2", "Form II"), ("F3", "Form III"), ("4", "Form IV"), ("IV", "Form IV")],
)
def test_normalise_form(value, expected):
    assert normalise_form(value) == expected


# ----------------------------------------------------------------- allocation


def test_periods_per_week_from_syllabus_limits_weekly_budget(client):
    sid, cid = _setup(client, _syllabus([6], ppw=3), _calendar(weeks=4, budget=5))
    data = client.post("/api/allocate", json={"syllabus_id": sid, "calendar_id": cid}).json()
    assert [a["periods"] for a in data["assignments"]] == [3, 3]
    assert data["capacity"] == 12
    assert all(a["week_budget"] == 3 for a in data["assignments"])


def test_request_periods_per_week_overrides_syllabus(client):
    sid, cid = _setup(client, _syllabus([4], ppw=3), _calendar(weeks=4, budget=5))
    data = client.post(
        "/api/allocate", json={"syllabus_id": sid, "calendar_id": cid, "periods_per_week": 2}
    ).json()
    assert [a["periods"] for a in data["assignments"]] == [2, 2]


def test_fit_scale_fills_calendar_exactly(client):
    sid, cid = _setup(client, _syllabus([10, 20], ppw=3), _calendar(weeks=4, budget=5))
    data = client.post(
        "/api/allocate", json={"syllabus_id": sid, "calendar_id": cid, "fit": "scale"}
    ).json()
    assert data["total_planned"] == 30
    assert data["total_allocated"] == data["capacity"] == 12


def test_fit_shrink_keeps_periods_when_they_fit(client):
    sid, cid = _setup(client, _syllabus([3, 3], ppw=3), _calendar(weeks=4, budget=5))
    data = client.post(
        "/api/allocate", json={"syllabus_id": sid, "calendar_id": cid, "fit": "shrink"}
    ).json()
    assert data["total_allocated"] == 6


def test_invalid_fit_rejected(client):
    sid, cid = _setup(client, _syllabus([3]), _calendar())
    resp = client.post("/api/allocate", json={"syllabus_id": sid, "calendar_id": cid, "fit": "bogus"})
    assert resp.status_code == 422


# ----------------------------------------------------------------- activity mapping


def test_scheme_shows_only_the_weeks_activities_with_syllabus_details(client):
    objectives = {
        0: [
            {"order": 1, "text": "(a) Explain physics", "periods": 3,
             "teaching_methods": "Brainstorming", "resources": "Charts",
             "assessment_criteria": "Physics is explained"},
            {"order": 2, "text": "(b) Measure length", "periods": 3,
             "teaching_methods": "Experimentation", "resources": "Metre rule",
             "assessment_criteria": "Length is measured"},
        ]
    }
    sid, cid = _setup(client, _syllabus([6], ppw=3, objectives=objectives), _calendar(weeks=2))
    client.post("/api/allocate", json={"syllabus_id": sid, "calendar_id": cid})
    entries = client.get(f"/api/scheme/{sid}/{cid}").json()["entries"]
    assert entries[0]["objectives"] == ["(a) Explain physics"]
    assert entries[0]["teaching_methods"] == "Brainstorming"
    assert entries[0]["assessment"] == "Physics is explained"
    assert entries[1]["objectives"] == ["(b) Measure length"]
    assert "Metre rule" in entries[1]["teaching_resources"]

    plans = client.get(f"/api/lesson-plan/{sid}/{cid}/week/2").json()
    assert all(p["learning_activity"] == "(b) Measure length" for p in plans)
    assert "Experimentation" in plans[0]["teacher_activities"].title()


# ----------------------------------------------------------------- PDF parsing


@pytest.fixture(scope="module")
def physics():
    return parse_syllabus_pdf(str(PHYSICS_PDF))


def test_parse_physics_forms_and_periods_per_week(physics):
    assert physics.subject == "Physics"
    assert physics.form_names() == ["Form I", "Form II", "Form III", "Form IV"]
    assert physics.periods_per_week == {"Form I": 3, "Form II": 3, "Form III": 4, "Form IV": 4}


def test_parse_physics_form_one_matrix(physics):
    data = physics.to_syllabus_input("Form I")
    codes = [st["sub_topic_id_code"] for t in data["topics"] for st in t["sub_topics"]]
    assert [t["topic_id_code"] for t in data["topics"]] == ["1.0", "2.0", "3.0"]
    assert codes == ["1.1", "1.2", "1.3", "2.1", "2.2", "3.1", "3.2"]
    periods = [st["planned_periods"] for t in data["topics"] for st in t["sub_topics"]]
    assert periods == [22, 11, 14, 16, 15, 15, 16]
    first = data["topics"][0]["sub_topics"][0]
    assert len(first["objectives"]) == 7  # activities (a)-(g)
    assert first["objectives"][0]["text"].startswith("(a) Explain the concept of Physics")
    assert "Brainstorming" in first["objectives"][0]["teaching_methods"]
    assert sum(o["periods"] for o in first["objectives"]) == 22


def test_parse_per_activity_periods_layout():
    """Geography prints periods per learning activity rather than per competence."""
    geo = parse_syllabus_pdf(str(GEOGRAPHY_PDF))
    data = geo.to_syllabus_input("Form I")
    first = data["topics"][0]["sub_topics"][0]
    assert [o["periods"] for o in first["objectives"]] == [9, 80]
    assert geo.periods_per_week["Form I"] == 3


def test_upload_pdf_endpoint_creates_syllabus_and_full_scheme(client):
    with open(PHYSICS_PDF, "rb") as fh:
        resp = client.post(
            "/api/syllabus/from-pdf",
            files={"file": ("physics.pdf", fh, "application/pdf")},
            data={"form": "Form II"},
        )
    assert resp.status_code == 201, resp.text
    syl = resp.json()
    assert syl["subject"] == "Physics" and syl["form"] == "Form II"
    assert syl["periods_per_week"] == 3

    cid = client.post("/api/calendar/", json=_calendar(weeks=35, budget=5)).json()["id"]
    alloc = client.post(
        "/api/allocate", json={"syllabus_id": syl["id"], "calendar_id": cid, "fit": "scale"}
    ).json()
    assert alloc["total_allocated"] == alloc["capacity"] == 105
    docx = client.get(f"/api/scheme/{syl['id']}/{cid}/docx")
    assert docx.status_code == 200 and docx.content[:2] == b"PK"


def test_upload_rejects_non_pdf(client):
    resp = client.post(
        "/api/syllabus/from-pdf", files={"file": ("x.pdf", b"hello", "application/pdf")}
    )
    assert resp.status_code == 400
