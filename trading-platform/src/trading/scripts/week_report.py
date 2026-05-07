"""
Week review report.

Usage
-----
    uv run week-report           # current week (Mon–Sun containing today)
    uv run week-report 2025-04-21  # week containing this date
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, date, datetime, timedelta

from trading.reports.engine import run_report


def _week_window(for_date: date) -> tuple[datetime, datetime]:
    monday = for_date - timedelta(days=for_date.weekday())
    sunday = monday + timedelta(days=7)
    return (
        datetime(monday.year, monday.month, monday.day, tzinfo=UTC),
        datetime(sunday.year, sunday.month, sunday.day, tzinfo=UTC),
    )


def main() -> None:
    if len(sys.argv) > 1:
        try:
            for_date = date.fromisoformat(sys.argv[1])
        except ValueError:
            sys.exit(f"ERROR: Invalid date {sys.argv[1]!r}. Expected YYYY-MM-DD.")
    else:
        for_date = date.today()

    start, end = _week_window(for_date)
    week_num = start.isocalendar()[1]
    end_str = (end - timedelta(days=1)).strftime('%d %b %Y')
    title = f"WEEK REVIEW — Week {week_num}, {start.strftime('%d %b')}–{end_str}"

    asyncio.run(run_report(start, end, title))


if __name__ == "__main__":
    main()
