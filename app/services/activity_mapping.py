"""Map allocated periods back to the syllabus learning activities.

A specific competence (SubTopic) usually spans several weeks and contains
several learning activities (Objectives). Each activity owns a share of the
competence's periods - its own ``periods`` value when the syllabus gives one,
otherwise an equal share. When the allocator scales a competence to fit the
calendar, the shares are scaled with it.

These helpers let the scheme of work show only the activities taught in a
given week, and let each lesson plan target the activity of its period.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AllocationAssignment, Objective


def ordered_objectives(assignment: AllocationAssignment) -> list[Objective]:
    return sorted(assignment.sub_topic.objectives, key=lambda o: o.order)


def _boundaries(objectives: list[Objective], total: int) -> list[int]:
    """Start position of each objective (plus final end) within ``total`` periods."""
    if all(o.periods for o in objectives):
        weights = [o.periods for o in objectives]
    else:
        weights = [1] * len(objectives)
    w_total = sum(weights) or 1
    bounds, cum = [0], 0
    for w in weights:
        cum += w
        bounds.append(round(cum * total / w_total))
    return bounds


def assignment_span(assignment: AllocationAssignment, db: Session) -> tuple[int, int, int]:
    """Return (start, end, total) period positions of this part within its sub-topic."""
    base = db.query(AllocationAssignment).filter(
        AllocationAssignment.syllabus_id == assignment.syllabus_id,
        AllocationAssignment.calendar_id == assignment.calendar_id,
        AllocationAssignment.sub_topic_id == assignment.sub_topic_id,
    )
    before = (
        base.filter(AllocationAssignment.split_index < (assignment.split_index or 1))
        .with_entities(func.coalesce(func.sum(AllocationAssignment.periods), 0))
        .scalar()
    )
    total = base.with_entities(func.coalesce(func.sum(AllocationAssignment.periods), 0)).scalar()
    return int(before), int(before) + assignment.periods, int(total) or assignment.periods


def objectives_for_assignment(assignment: AllocationAssignment, db: Session) -> list[Objective]:
    """Learning activities taught during this assignment (one week's part)."""
    objectives = ordered_objectives(assignment)
    if len(objectives) <= 1:
        return objectives
    start, end, total = assignment_span(assignment, db)
    bounds = _boundaries(objectives, total)
    selected = []
    for i, obj in enumerate(objectives):
        lo, hi = bounds[i], bounds[i + 1]
        if lo < hi:
            if lo < end and hi > start:
                selected.append(obj)
        else:
            # Zero-width activity (more activities than periods): attach to the
            # period where it would start (or the last period).
            pos = min(lo, total - 1)
            if start <= pos < end:
                selected.append(obj)
    return selected or objectives[:1]


def objective_for_period(
    assignment: AllocationAssignment, period_number: int, db: Session
) -> Objective | None:
    """Learning activity for a given period number of the week."""
    objectives = ordered_objectives(assignment)
    if not objectives:
        return None
    if len(objectives) == 1:
        return objectives[0]
    start, _end, total = assignment_span(assignment, db)
    pos = start + (period_number - (assignment.first_period or 1))
    bounds = _boundaries(objectives, total)
    for i in range(len(objectives)):
        if bounds[i] <= pos < bounds[i + 1]:
            return objectives[i]
    return objectives[-1]
