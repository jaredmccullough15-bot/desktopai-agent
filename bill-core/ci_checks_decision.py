from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from zoneinfo import ZoneInfo

_COMMON_DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%m/%d/%y",
    "%m-%d-%y",
    "%b %d, %Y",
    "%B %d, %Y",
]


def _parse_paid_through_date(value: object) -> date | None:
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    raw = str(value).strip()
    if not raw:
        return None

    # Try ISO datetime/date first.
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        pass

    for fmt in _COMMON_DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    return None


def _current_month_end(now: datetime, timezone_name: str | None = None) -> date:
    if timezone_name:
        try:
            now = now.astimezone(ZoneInfo(timezone_name))
        except Exception:
            pass

    year = now.year
    month = now.month
    last_day = monthrange(year, month)[1]
    return date(year, month, last_day)


def evaluate_paid_through_date(
    paid_through_date: object,
    *,
    now: datetime | None = None,
    timezone_name: str | None = None,
) -> dict[str, object]:
    now_dt = now or datetime.now()
    month_end = _current_month_end(now_dt, timezone_name=timezone_name)
    parsed_date = _parse_paid_through_date(paid_through_date)

    result: dict[str, object] = {
        "paid_through_date_raw": paid_through_date,
        "paid_through_date": parsed_date.isoformat() if parsed_date else None,
        "current_month_end_date": month_end.isoformat(),
        "payment_status": "needs_review",
        "decision_reason": "missing_or_unparseable_date",
    }

    if parsed_date is None:
        return result

    if parsed_date >= month_end:
        result["payment_status"] = "good"
        result["decision_reason"] = "paid_through_on_or_after_month_end"
        return result

    result["payment_status"] = "bad"
    result["decision_reason"] = "paid_through_before_month_end"
    return result
