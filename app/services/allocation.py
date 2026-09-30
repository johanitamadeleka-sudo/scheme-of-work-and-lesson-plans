"""Allocation engine: greedy sequential bin-packing of sub-topics into teaching weeks.

The engine is subject-agnostic. Two knobs make one academic calendar reusable
for every subject:

* **periods_per_week** - weekly periods for the subject (e.g. Physics Form I = 3,
  Mathematics = 5). Taken from the request, else from ``Syllabus.periods_per_week``,
  else the calendar's own ``Week.period_budget``. Short weeks (budget below the
  calendar's normal week) are scaled proportionally.
* **fit** - how syllabus periods are reconciled with calendar capacity:

  - ``none``   keep syllabus periods as-is (overflow is left unallocated)
  - ``shrink`` scale down proportionally only when the syllabus overflows
  - ``scale``  scale up or down so the scheme exactly fills the calendar

  Scaling uses the largest-remainder method and gives every sub-topic at least
  one period, so no competence disappears from the scheme.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    AllocationAssignment,
    CalendarData,
    SubTopic,
    Syllabus,
    Term,
    Topic,
    Week,
    WeekClassification,
)

FIT_MODES = ("none", "shrink", "scale")


@dataclass
class AllocationSummary:
    """Summary numbers for an allocation run."""

    total_planned: int
    total_allocated: int
    capacity: int
    fit: str


def effective_week_budgets(
    weeks: list[Week], periods_per_week: Optional[int]
) -> dict[int, int]:
    """Return {week_id: budget} applying a subject's periods-per-week."""
    if not periods_per_week:
        return {w.id: w.period_budget or 0 for w in weeks}
    normal = max((w.period_budget or 0) for w in weeks) if weeks else 0
    budgets: dict[int, int] = {}
    for w in weeks:
        base = w.period_budget or 0
        if base <= 0:
            budgets[w.id] = 0
        elif normal <= 0 or base >= normal:
            budgets[w.id] = periods_per_week
        else:
            budgets[w.id] = max(1, round(base * periods_per_week / normal))
    return budgets


def scale_periods(planned: list[int], target: int) -> list[int]:
    """Scale ``planned`` so it sums to ``target`` (largest remainder, min 1 each)."""
    total = sum(planned)
    n = len(planned)
    if n == 0 or total <= 0:
        return list(planned)
    if target < n:
        # Not enough room for one period each: keep the first `target` items only
        return [1 if i < target else 0 for i in range(n)]
    # Reserve one period per item, distribute the rest proportionally
    spare = target - n
    raw = [max(p, 0) / total * spare for p in planned]
    base = [math.floor(r) for r in raw]
    leftover = spare - sum(base)
    order = sorted(range(n), key=lambda i: (raw[i] - base[i], planned[i]), reverse=True)
    for i in order[:leftover]:
        base[i] += 1
    return [b + 1 for b in base]


def run_allocation(
    syllabus_id: int,
    calendar_id: int,
    db: Session,
    periods_per_week: Optional[int] = None,
    fit: str = "none",
) -> list[AllocationAssignment]:
    """Run the allocation and return the created assignments."""
    assignments, _ = run_allocation_with_summary(
        syllabus_id, calendar_id, db, periods_per_week=periods_per_week, fit=fit
    )
    return assignments


def run_allocation_with_summary(
    syllabus_id: int,
    calendar_id: int,
    db: Session,
    periods_per_week: Optional[int] = None,
    fit: str = "none",
) -> tuple[list[AllocationAssignment], AllocationSummary]:
    """
    Run the greedy sequential bin-packing algorithm.

    Iterates sub-topics in syllabus order (topic.order, sub_topic.order).
    For each sub-topic, assigns its (possibly scaled) periods to teaching weeks
    respecting the effective weekly budget. Splits across weeks when needed.
    """
    if fit not in FIT_MODES:
        raise ValueError(f"fit must be one of {FIT_MODES}, got {fit!r}")

    syllabus = db.query(Syllabus).filter(Syllabus.id == syllabus_id).first()
    if not syllabus:
        raise ValueError(f"Syllabus with id {syllabus_id} not found")

    calendar = db.query(CalendarData).filter(CalendarData.id == calendar_id).first()
    if not calendar:
        raise ValueError(f"Calendar with id {calendar_id} not found")

    sub_topics = (
        db.query(SubTopic)
        .join(Topic)
        .filter(Topic.syllabus_id == syllabus_id)
        .order_by(Topic.order, SubTopic.order)
        .all()
    )

    # Delete any existing allocation for this pair (idempotent re-run)
    db.query(AllocationAssignment).filter(
        AllocationAssignment.syllabus_id == syllabus_id,
        AllocationAssignment.calendar_id == calendar_id,
    ).delete(synchronize_session="fetch")

    teaching_weeks = (
        db.query(Week)
        .join(Term)
        .filter(
            Term.calendar_id == calendar_id,
            Week.classification == WeekClassification.teaching,
            Week.period_budget > 0,
        )
        .order_by(Term.order, Week.week_number)
        .all()
    )

    ppw = periods_per_week or syllabus.periods_per_week
    budgets = effective_week_budgets(teaching_weeks, ppw)
    capacity = sum(budgets.values())

    planned = [max(st.planned_periods or 0, 0) for st in sub_topics]
    total_planned = sum(planned)
    if fit == "scale" or (fit == "shrink" and total_planned > capacity):
        targets = scale_periods(planned, capacity)
    else:
        targets = planned

    if not teaching_weeks:
        db.commit()
        return [], AllocationSummary(total_planned, 0, 0, fit)

    week_capacity_used: dict[int, int] = {w.id: 0 for w in teaching_weeks}
    week_slot_counter: dict[int, int] = {w.id: 0 for w in teaching_weeks}

    all_assignments: list[AllocationAssignment] = []
    week_index = 0

    for sub_topic, target in zip(sub_topics, targets):
        remaining = target
        if remaining <= 0:
            continue

        parts: list[AllocationAssignment] = []
        split_index = 1

        while remaining > 0 and week_index < len(teaching_weeks):
            week = teaching_weeks[week_index]
            budget = budgets[week.id]
            available = budget - week_capacity_used[week.id]

            if available <= 0:
                week_index += 1
                continue

            take = min(remaining, available)
            first_period = week_capacity_used[week.id] + 1
            last_period = week_capacity_used[week.id] + take

            week_slot_counter[week.id] += 1

            assignment = AllocationAssignment(
                syllabus_id=syllabus_id,
                calendar_id=calendar_id,
                week_id=week.id,
                sub_topic_id=sub_topic.id,
                slot=week_slot_counter[week.id],
                first_period=first_period,
                last_period=last_period,
                periods=take,
                split_index=split_index,
                split_total=1,  # updated after loop
                week_budget=budget,
            )
            parts.append(assignment)
            all_assignments.append(assignment)

            week_capacity_used[week.id] += take
            remaining -= take
            split_index += 1

            if week_capacity_used[week.id] >= budget:
                week_index += 1

        for part in parts:
            part.split_total = len(parts)

    db.add_all(all_assignments)
    db.commit()
    for assignment in all_assignments:
        db.refresh(assignment)

    summary = AllocationSummary(
        total_planned=total_planned,
        total_allocated=sum(a.periods for a in all_assignments),
        capacity=capacity,
        fit=fit,
    )
    return all_assignments, summary
