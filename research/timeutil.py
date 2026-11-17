"""vlr.gg times are US Eastern local time, not UTC.

vlr's `data-utc-ts` attribute (stored as research_matches.date_utc and odds_snapshots.start_utc)
is America/New_York wall-clock time. Verified 2026-11-17: OddsPapi trueStartTime minus vlr time
has median +3.92 h (n=24, p10-p90 3.78-4.05 h) in EDT months, and +5 h in EST months
(e.g. 2026-03-01 12:00 vlr = 17:00Z). Kalshi tickers (ET) agree with vlr's wall-clock times.
Relative quantities (weeks since season start, ordering) are unaffected; absolute comparisons
with UTC timestamps (odds logger, OddsPapi, Kalshi, Wayback) must convert first.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def vlr_to_utc(s: str | datetime) -> datetime:
    """vlr wall-clock time (naive 'YYYY-MM-DD HH:MM:SS' or naive datetime) -> aware UTC."""
    d = datetime.fromisoformat(s.replace("T", " ").replace("Z", "")) if isinstance(s, str) else s
    if d.tzinfo is not None:
        raise ValueError("vlr times are naive wall-clock ET; got an aware datetime")
    return d.replace(tzinfo=ET).astimezone(timezone.utc)


def utc_to_vlr(d: datetime) -> datetime:
    """Aware UTC -> naive ET wall-clock (the time axis of research_matches.date_utc)."""
    return d.astimezone(ET).replace(tzinfo=None)
