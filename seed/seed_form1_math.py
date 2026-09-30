"""
Seed script for Form I Mathematics data.

Populates the database with the complete Form I Mathematics syllabus
(extracted from the Tanzania O-Level Mathematics Syllabus 2023),
the 2026 academic calendar (matching the sample scheme dates),
textbook entries, and runs the allocation engine.

Usage:
    cd /projects/sandbox/scheme-of-work-and-lesson-plans
    .venv/bin/python seed/seed_form1_math.py
"""

import json
import sys
from pathlib import Path

# Ensure the project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


# ---------------------------------------------------------------------------
# Form I Mathematics Syllabus Data (from pages 14-24 of the syllabus)
# Total: 175 periods (30 + 36 + 34 + 45 + 30)
# ---------------------------------------------------------------------------

SYLLABUS_DATA = {
    "subject": "Basic Mathematics",
    "form": "Form I",
    "source_note": "TIE (2023), Mathematics Syllabus for Ordinary Secondary Education Form I-IV",
    "topics": [
        {
            "order": 1,
            "topic_id_code": "1.0",
            "title": "Demonstrate mastery of mathematical language",
            "sub_topics": [
                {
                    "order": 1,
                    "sub_topic_id_code": "1.1",
                    "title": "Use numerical skills in different contexts",
                    "planned_periods": 30,
                    "competences": [
                        "Explain the basic concepts of Mathematics",
                        "Explain the concept of rational, irrational, and real numbers",
                        "Represent rational numbers on a number line",
                        "Explain the concept of inequalities and absolute values of real numbers",
                        "Describe the importance of numbers in real-life situations",
                    ],
                    "objectives": [
                        {
                            "order": 1,
                            "text": (
                                "(a) Explain the basic concepts of Mathematics "
                                "(Meaning of mathematics, branches of mathematics, "
                                "relationship between mathematics and other subjects, "
                                "importance of mathematics)"
                            ),
                        },
                        {
                            "order": 2,
                            "text": (
                                "(b) Explain the concept of rational, irrational, "
                                "and real numbers"
                            ),
                        },
                        {
                            "order": 3,
                            "text": (
                                "(c) Represent rational numbers on a number line"
                            ),
                        },
                        {
                            "order": 4,
                            "text": (
                                "(d) Explain the concept of inequalities and "
                                "absolute values of real numbers"
                            ),
                        },
                        {
                            "order": 5,
                            "text": (
                                "(e) Describe the importance of numbers in "
                                "real-life situations"
                            ),
                        },
                    ],
                },
                {
                    "order": 2,
                    "sub_topic_id_code": "1.2",
                    "title": "Use ratios and proportions in daily life",
                    "planned_periods": 36,
                    "competences": [
                        "Explain the concept of ratios and proportions",
                        "Solve ratio and proportion problems",
                    ],
                    "objectives": [
                        {
                            "order": 1,
                            "text": (
                                "(a) Explain the concept of ratios and proportions"
                            ),
                        },
                        {
                            "order": 2,
                            "text": (
                                "(b) Solve ratio and proportion problems"
                            ),
                        },
                    ],
                },
            ],
        },
        {
            "order": 2,
            "topic_id_code": "2.0",
            "title": "Demonstrate mastery of basic concepts in geometry and algebra",
            "sub_topics": [
                {
                    "order": 1,
                    "sub_topic_id_code": "2.1",
                    "title": (
                        "Use geometry, approximations, relations and functions "
                        "in various contexts"
                    ),
                    "planned_periods": 34,
                    "competences": [
                        "Explain the concept of approximations",
                        "Round off numbers and estimate values of expressions",
                        "Approximate numbers to the required significant figures and decimal places",
                        "Use approximations in computations and measurements of quantities in various contexts",
                    ],
                    "objectives": [
                        {
                            "order": 1,
                            "text": (
                                "(a) Explain the concept of approximations "
                                "(rounding off, significant figures, and decimal places)"
                            ),
                        },
                        {
                            "order": 2,
                            "text": (
                                "(b) Round off numbers and estimate values of expressions"
                            ),
                        },
                        {
                            "order": 3,
                            "text": (
                                "(c) Approximate numbers to the required significant "
                                "figures and decimal places"
                            ),
                        },
                        {
                            "order": 4,
                            "text": (
                                "(d) Use approximations in computations and measurements "
                                "of quantities in various contexts"
                            ),
                        },
                    ],
                },
                {
                    "order": 2,
                    "sub_topic_id_code": "2.2",
                    "title": "Use algebra and matrices in problem solving",
                    "planned_periods": 45,
                    "competences": [
                        "Explore the basic tenets of algebra",
                        "Use algebraic expressions to model situations",
                        "Solve simultaneous equations using substitution and elimination methods",
                        "Solve inequalities in one unknown",
                    ],
                    "objectives": [
                        {
                            "order": 1,
                            "text": (
                                "(a) Explore the basic tenets of algebra "
                                "(algebraic expressions and equations, linear "
                                "simultaneous equations of two unknowns, "
                                "inequalities in one unknown)"
                            ),
                        },
                        {
                            "order": 2,
                            "text": (
                                "(b) Use algebraic expressions to model situations "
                                "(word problems into algebraic expressions and equations)"
                            ),
                        },
                        {
                            "order": 3,
                            "text": (
                                "(c) Solve simultaneous equations using substitution "
                                "and elimination methods"
                            ),
                        },
                        {
                            "order": 4,
                            "text": (
                                "(d) Solve inequalities in one unknown"
                            ),
                        },
                    ],
                },
            ],
        },
        {
            "order": 3,
            "topic_id_code": "3.0",
            "title": (
                "Demonstrate mastery of basic concepts in coordinate geometry, "
                "trigonometry, circles, vectors, probability and statistics"
            ),
            "sub_topics": [
                {
                    "order": 1,
                    "sub_topic_id_code": "3.1",
                    "title": (
                        "Use basic coordinate geometry, trigonometry and vectors "
                        "skills in daily life"
                    ),
                    "planned_periods": 30,
                    "competences": [
                        "Explore the basic tenets of coordinate geometry",
                        "Find the gradient/slope of a line",
                        "Determine the equation of a straight line and draw its graph",
                        "Solve linear simultaneous equations graphically",
                        "Use mathematical software to solve and draw graphs of simultaneous equations",
                    ],
                    "objectives": [
                        {
                            "order": 1,
                            "text": (
                                "(a) Explore the basic tenets of coordinate geometry "
                                "(gradient and equations of a straight line, graphs "
                                "of linear equations)"
                            ),
                        },
                        {
                            "order": 2,
                            "text": (
                                "(b) Find the gradient/slope of a line"
                            ),
                        },
                        {
                            "order": 3,
                            "text": (
                                "(c) Determine the equation of a straight line "
                                "and draw its graph"
                            ),
                        },
                        {
                            "order": 4,
                            "text": (
                                "(d) Solve linear simultaneous equations graphically"
                            ),
                        },
                        {
                            "order": 5,
                            "text": (
                                "(e) Use mathematical software to solve and draw "
                                "graphs of simultaneous equations"
                            ),
                        },
                    ],
                },
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# 2026 Academic Calendar (matching the sample scheme dates)
# 5 periods per week, 35 teaching weeks needed for 175 periods
# Term 1: 15 teaching weeks (March - June 2026)
# Term 2: 20 teaching weeks (July - November 2026)
# ---------------------------------------------------------------------------

# 2026 calendar shared by every subject (see data/calendars/)
CALENDAR_PATH = PROJECT_ROOT / "data" / "calendars" / "tanzania_secondary_2026.json"
CALENDAR_DATA = json.loads(CALENDAR_PATH.read_text())

# Textbook reference used throughout the sample scheme
TEXTBOOK_REFERENCE = "TIE (2023), Basic Mathematics for Secondary Schools Book 1, TIE-DSM"


def run_seed():
    """Run the seed process using FastAPI TestClient."""
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    client = TestClient(app)

    print("=" * 60)
    print("  SEED: Form I Mathematics 2026")
    print("=" * 60)

    # ---- Step 1: Create Syllabus ----
    print("\n[1/4] Creating syllabus...")
    resp = client.post("/api/syllabus/", json=SYLLABUS_DATA)
    if resp.status_code != 201:
        print(f"  ERROR creating syllabus: {resp.status_code} - {resp.text}")
        sys.exit(1)
    syllabus = resp.json()
    syllabus_id = syllabus["id"]
    topic_count = len(syllabus["topics"])
    sub_topic_count = sum(len(t["sub_topics"]) for t in syllabus["topics"])
    total_periods = sum(
        st["planned_periods"]
        for t in syllabus["topics"]
        for st in t["sub_topics"]
    )
    print(f"  Created syllabus id={syllabus_id}")
    print(f"  Topics: {topic_count}, Sub-topics: {sub_topic_count}")
    print(f"  Total planned periods: {total_periods}")

    # ---- Step 2: Create Calendar ----
    print("\n[2/4] Creating calendar...")
    resp = client.post("/api/calendar/", json=CALENDAR_DATA)
    if resp.status_code != 201:
        print(f"  ERROR creating calendar: {resp.status_code} - {resp.text}")
        sys.exit(1)
    calendar = resp.json()
    calendar_id = calendar["id"]
    term_count = len(calendar["terms"])
    teaching_weeks = sum(
        1
        for t in calendar["terms"]
        for w in t["weeks"]
        if w["classification"] == "teaching"
    )
    total_budget = sum(
        w["period_budget"] or 0
        for t in calendar["terms"]
        for w in t["weeks"]
        if w["classification"] == "teaching"
    )
    print(f"  Created calendar id={calendar_id}")
    print(f"  Terms: {term_count}, Teaching weeks: {teaching_weeks}")
    print(f"  Total period budget: {total_budget}")

    # ---- Step 3: Create Textbook Entries ----
    print("\n[3/4] Creating textbook entries...")
    # Collect all sub-topic IDs
    sub_topic_ids = [
        st["id"]
        for t in syllabus["topics"]
        for st in t["sub_topics"]
    ]
    textbook_entries = [
        {
            "sub_topic_id": st_id,
            "book_title": TEXTBOOK_REFERENCE,
            "start_page": None,
            "end_page": None,
            "note": None,
        }
        for st_id in sub_topic_ids
    ]
    resp = client.post("/api/textbook/", json=textbook_entries)
    if resp.status_code != 201:
        print(f"  ERROR creating textbook entries: {resp.status_code} - {resp.text}")
        sys.exit(1)
    textbooks = resp.json()
    print(f"  Created {len(textbooks)} textbook entries")

    # ---- Step 4: Run Allocation ----
    print("\n[4/4] Running allocation...")
    resp = client.post(
        "/api/allocate",
        json={"syllabus_id": syllabus_id, "calendar_id": calendar_id},
    )
    if resp.status_code != 200:
        print(f"  ERROR running allocation: {resp.status_code} - {resp.text}")
        sys.exit(1)
    allocation = resp.json()
    assignment_count = len(allocation["assignments"])
    total_allocated = sum(a["periods"] for a in allocation["assignments"])
    print(f"  Created {assignment_count} allocation assignments")
    print(f"  Total periods allocated: {total_allocated}")

    # ---- Summary ----
    print("\n" + "=" * 60)
    print("  SEED COMPLETE")
    print("=" * 60)
    print(f"  Syllabus:    id={syllabus_id} ({topic_count} topics, {sub_topic_count} sub-topics)")
    print(f"  Calendar:    id={calendar_id} ({term_count} terms, {teaching_weeks} teaching weeks)")
    print(f"  Textbooks:   {len(textbooks)} entries")
    print(f"  Allocation:  {assignment_count} assignments ({total_allocated}/{total_periods} periods)")
    if total_allocated == total_periods:
        print("  Status:      ALL periods allocated successfully!")
    else:
        print(f"  WARNING:     {total_periods - total_allocated} periods unallocated!")
    print("=" * 60)

    return {
        "syllabus_id": syllabus_id,
        "calendar_id": calendar_id,
        "assignments": assignment_count,
        "total_allocated": total_allocated,
        "total_planned": total_periods,
    }


if __name__ == "__main__":
    run_seed()
