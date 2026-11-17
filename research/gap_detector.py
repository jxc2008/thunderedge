"""Missed-poll detector for the two 15-minute jobs; rewrites the gap section of research/STATUS.md.

Sources: data/odds_snapshots.db poll_log (odds logger) and
valorant-pricing-model/data/shadow_quotes.db (distinct shadow-quote pass times).
A gap is any interval between consecutive runs > GAP_MIN minutes; missed polls = gap // 15 - 1.
Runs at the end of every odds-logger invocation (research/odds_logger_task.cmd), so a gap is
recorded at the first poll after it ends. Usage: python -m research.gap_detector
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATUS = ROOT / "STATUS.md"
SOURCES = {
    "odds logger": (ROOT.parent / "data" / "odds_snapshots.db", "SELECT ts_utc FROM poll_log"),
    "shadow quotes": (ROOT.parent.parent / "valorant-pricing-model" / "data" / "shadow_quotes.db",
                      "SELECT DISTINCT ts_utc FROM shadow_quotes"),
}
CADENCE_MIN, GAP_MIN, WINDOW_DAYS = 15, 20, 14
START, END = "<!-- gaps:start -->", "<!-- gaps:end -->"


def _ts(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def gaps(db: Path, q: str, since: datetime) -> tuple[int, list[tuple[datetime, datetime, int]]]:
    if not db.exists():
        return 0, []
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    ts = sorted(t for t in (_ts(r[0]) for r in con.execute(q)) if t >= since)
    out = []
    for a, b in zip(ts, ts[1:], strict=False):
        mins = (b - a).total_seconds() / 60
        if mins > GAP_MIN:
            out.append((a, b, int(mins // CADENCE_MIN) - 1))
    now = datetime.now(timezone.utc)
    if ts and (now - ts[-1]).total_seconds() / 60 > GAP_MIN:  # still down
        out.append((ts[-1], now, int((now - ts[-1]).total_seconds() / 60 // CADENCE_MIN) - 1))
    return len(ts), out


def render() -> str:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=WINDOW_DAYS)
    L = [START, "", f"_Auto-updated {now:%Y-%m-%d %H:%M} UTC by `research/gap_detector.py` (last {WINDOW_DAYS} days; "
         f"a gap = > {GAP_MIN} min between runs)._", "",
         "| Job | runs | gaps | missed polls | longest gap |", "|---|---|---|---|---|"]
    detail = []
    for name, (db, q) in SOURCES.items():
        n, g = gaps(db, q, since)
        longest = max(g, key=lambda x: x[1] - x[0]) if g else None
        L.append(f"| {name} | {n} | {len(g)} | {sum(x[2] for x in g)} | "
                 + (f"{(longest[1] - longest[0])} ({longest[0]:%m-%d %H:%M}Z)" if longest else "—") + " |")
        detail += [(name, a, b, m) for a, b, m in g]
    if detail:
        L += ["", "| Job | from (UTC) | to (UTC) | missed |", "|---|---|---|---|"]
        for name, a, b, m in sorted(detail, key=lambda x: x[1], reverse=True)[:20]:
            L.append(f"| {name} | {a:%Y-%m-%d %H:%M} | {b:%Y-%m-%d %H:%M} | {m} |")
    L += ["", END]
    return "\n".join(L)


def main() -> None:
    s = STATUS.read_text(encoding="utf-8")
    block = render()
    if START in s and END in s:
        s = s[: s.index(START)] + block + s[s.index(END) + len(END):]
    else:
        s = s.rstrip() + "\n\n## Missed polls\n\n" + block + "\n"
    STATUS.write_text(s, encoding="utf-8")


if __name__ == "__main__":
    main()
