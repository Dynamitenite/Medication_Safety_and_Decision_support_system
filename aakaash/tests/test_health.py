# SOURCE: NOT IN PAPERS. FIXTURES ONLY: dates below are hand-written to hit boundaries.
from datetime import date

from medsafe import health

TODAY = date(2026, 6, 15)


def test_age_before_and_after_birthday():
    assert health.age(date(2000, 6, 15), TODAY) == 26      # birthday today
    assert health.age(date(2000, 6, 16), TODAY) == 25      # birthday tomorrow
    assert health.age(date(2000, 1, 1), TODAY) == 26
    assert health.age(date(2000, 12, 31), TODAY) == 25


def test_age_missing_or_future_dob_is_none():
    assert health.age(None, TODAY) is None
    assert health.age(date(2030, 1, 1), TODAY) is None


def test_bmi_rounding_and_missing():
    assert health.bmi(170, 70) == 24.2          # 70 / 1.7^2 = 24.22
    assert health.bmi(180, 81) == 25.0
    assert health.bmi(None, 70) is None and health.bmi(170, None) is None and health.bmi(0, 70) is None


def test_course_status_ongoing_ended_upcoming():
    assert health.course_status(date(2026, 6, 1), None, TODAY) == "current"                 # ongoing
    assert health.course_status(date(2026, 6, 1), date(2026, 6, 30), TODAY) == "current"    # inside
    assert health.course_status(date(2026, 6, 1), date(2026, 6, 15), TODAY) == "current"    # ends today
    assert health.course_status(date(2026, 6, 1), date(2026, 6, 14), TODAY) == "past"       # ended yesterday
    assert health.course_status(date(2026, 6, 15), None, TODAY) == "current"                # starts today
    assert health.course_status(date(2026, 6, 16), None, TODAY) == "upcoming"
    assert health.course_status(date(2026, 6, 16), date(2026, 7, 1), TODAY) == "upcoming"


def test_course_status_without_start_is_not_stated():
    assert health.course_status(None, None, TODAY) == "not_stated"
    assert health.course_status(None, date(2026, 1, 1), TODAY) == "not_stated"


def test_course_days_counts_both_ends():
    assert health.course_days(date(2026, 6, 1), date(2026, 6, 30), TODAY) == 30
    assert health.course_days(date(2026, 6, 15), date(2026, 6, 15), TODAY) == 1
    assert health.course_days(date(2026, 6, 1), None, TODAY) == 15      # ongoing, up to today
    assert health.course_days(date(2026, 6, 16), None, TODAY) is None   # upcoming, not started
    assert health.course_days(None, None, TODAY) is None
