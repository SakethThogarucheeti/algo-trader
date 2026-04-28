"""
Month review report.

Usage
-----
    uv run month-report            # current month
    uv run month-report 2025-04    # specific month (YYYY-MM)
    uv run month-report 2025-04-15 # month containing this date
"""

from __future__ import annotations

import asyncio
import calendar
import sys
from datetime import UTC, date, datetime

from trading.reports.engine import run_report


def _month_window(for_date: date) -> tuple[datetime, datetime]:
    first = date(for_date.year, for_date.month, 1)
    last_day = calendar.monthrange(for_date.year, for_date.month)[1]
    after_last = date(for_date.year, for_date.month, last_day)
    # end is exclusive: midnight of first day of next month
    if for_date.month == 12:
        next_first = date(for_date.year + 1, 1, 1)
    else:
        next_first = date(for_date.year, for_date.month + 1, 1)
    return (
        datetime(first.year, first.month, first.day, tzinfo=UTC),
        datetime(next_first.year, next_first.month, next_first.day, tzinfo=UTC),
    )


def _parse_arg(arg: str) -> date:
    # Accept YYYY-MM or YYYY-MM-DD
    if len(arg) == 7:
        try:
            return date.fromisoformat(arg + "-01")
        except ValueError:
            pass
    try:
        return date.fromisoformat(arg)
    except ValueError:
        sys.exit(f"ERROR: Invalid date {arg!r}. Expected YYYY-MM or YYYY-MM-DD.")


def main() -> None:
    for_date = _parse_arg(sys.argv[1]) if len(sys.argv) > 1 else date.today()

    start, end = _month_window(for_date)
    title = f"MONTH REVIEW — {start.strftime('%B %Y')}"

    asyncio.run(run_report(start, end, title))


if __name__ == "__main__":
    main()
