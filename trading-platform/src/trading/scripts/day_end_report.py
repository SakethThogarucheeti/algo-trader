"""
Day-end review report.

Usage
-----
    uv run day-end-report              # today
    uv run day-end-report 2025-04-24   # specific date (YYYY-MM-DD)
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, date, datetime, timedelta

from trading.reports.engine import run_report


def main() -> None:
    if len(sys.argv) > 1:
        try:
            for_date = date.fromisoformat(sys.argv[1])
        except ValueError:
            sys.exit(f"ERROR: Invalid date {sys.argv[1]!r}. Expected YYYY-MM-DD.")
    else:
        for_date = date.today()

    start = datetime(for_date.year, for_date.month, for_date.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    title = f"DAY-END REVIEW — {for_date.strftime('%A, %d %B %Y')}"

    asyncio.run(run_report(start, end, title))


if __name__ == "__main__":
    main()
