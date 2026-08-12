"""Data freshness monitor: alert if the signals lake is more than N hours stale.

Run after the nightly pipeline (see daily_update.sh). Exits 0 always so a
stale-data alert never blocks the rest of the update script.

Usage:
    poetry run python crypto_signal_station/freshness_check.py
    poetry run python crypto_signal_station/freshness_check.py --max-age-hours 48
"""

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

DEFAULT_MAX_AGE_HOURS = 36
CATEGORIES = ("crypto", "stocks")
TIMEFRAME = "1d"


def _latest_signal_date() -> datetime | None:
    """Return the most recent Date value across all signal parquets, or None."""
    latest = None
    for cat in CATEGORIES:
        df = db.scan_signals_lake(cat, TIMEFRAME, columns=["Date"])
        if df.empty:
            continue
        ts = df["Date"].max()
        if ts is None or (hasattr(ts, "isnull") and ts.isnull()):
            continue
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        if latest is None or ts > latest:
            latest = ts
    return latest


def check_freshness(max_age_hours: int = DEFAULT_MAX_AGE_HOURS) -> bool:
    """Return True if data is fresh, False if stale (and send an alert)."""
    latest = _latest_signal_date()
    now = datetime.now(timezone.utc)

    if latest is None:
        msg = "No signal data found in the lake — pipeline may not have run yet."
        print(f"[freshness] WARNING: {msg}")
        _alert("SignalStack: no data", msg)
        return False

    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)

    age_hours = (now - latest).total_seconds() / 3600
    latest_str = latest.strftime("%Y-%m-%d %H:%M UTC")

    if age_hours > max_age_hours:
        msg = (
            f"Most recent signal data is {age_hours:.1f}h old "
            f"(latest bar: {latest_str}). "
            f"Threshold: {max_age_hours}h. Pipeline may have failed."
        )
        print(f"[freshness] STALE: {msg}")
        _alert("SignalStack: stale data", msg)
        return False

    print(f"[freshness] OK: data is {age_hours:.1f}h old (latest: {latest_str})")
    return True


def _alert(title: str, message: str):
    try:
        from notify import send_notification
        send_notification(title, message, priority="high")
    except Exception as e:
        print(f"[freshness] could not send alert: {e}")


def main():
    parser = argparse.ArgumentParser(description="Check signal data freshness")
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=DEFAULT_MAX_AGE_HOURS,
        help=f"Alert if data is older than this many hours (default: {DEFAULT_MAX_AGE_HOURS})",
    )
    args = parser.parse_args()
    check_freshness(args.max_age_hours)
    sys.exit(0)


if __name__ == "__main__":
    main()
