from __future__ import annotations

from datetime import datetime

from ci_checks_decision import evaluate_paid_through_date


def test_evaluate_paid_through_date_good_when_on_or_after_month_end() -> None:
    result = evaluate_paid_through_date("2026-02-28", now=datetime(2026, 2, 10, 12, 0, 0))
    assert result["payment_status"] == "good"
    assert result["decision_reason"] == "paid_through_on_or_after_month_end"


def test_evaluate_paid_through_date_bad_when_before_month_end() -> None:
    result = evaluate_paid_through_date("2026-02-10", now=datetime(2026, 2, 20, 12, 0, 0))
    assert result["payment_status"] == "bad"
    assert result["decision_reason"] == "paid_through_before_month_end"


def test_evaluate_paid_through_date_needs_review_for_unparseable() -> None:
    result = evaluate_paid_through_date("not-a-date", now=datetime(2026, 2, 20, 12, 0, 0))
    assert result["payment_status"] == "needs_review"
    assert result["decision_reason"] == "missing_or_unparseable_date"
