# SOURCE: NOT IN PAPERS. Own helpers for the profile and medicine history pages.
"""Values computed from what the person entered. None when an input is missing; nothing is guessed."""
from __future__ import annotations

from datetime import date
from typing import Literal

CourseStatus = Literal["current", "past", "upcoming", "not_stated"]


def age(dob: date | None, today: date) -> int | None:
    if dob is None or dob > today:
        return None
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def bmi(height_cm: float | None, weight_kg: float | None) -> float | None:
    if not height_cm or not weight_kg:
        return None
    m = height_cm / 100
    return round(weight_kg / (m * m), 1)


def course_status(start: date | None, end: date | None, today: date) -> CourseStatus:
    """current while today is inside [start, end] (end None = ongoing); no start date = not_stated."""
    if start is None:
        return "not_stated"
    if start > today:
        return "upcoming"
    if end is not None and end < today:
        return "past"
    return "current"


def course_days(start: date | None, end: date | None, today: date) -> int | None:
    """Length of the course in days, counting both ends. An ongoing course counts up to today."""
    if start is None:
        return None
    last = end if end is not None else today
    if last < start:
        return None
    return (last - start).days + 1
