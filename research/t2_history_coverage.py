"""Player-history coverage from the tier-2 scrape (REPORT_v4 §3).

For every 2026 tier-1 series (by first map), count lineup slots whose player had (i) any earlier tier-1 map
and (ii) any earlier tier-2 map. Players with tier-2 history but no tier-1 history are the ones the
tier-2 data gives a prior to. Usage: python -m research.t2_history_coverage
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
T1, T2 = ROOT.parent / "data" / "valorant_stats.db", ROOT.parent / "data" / "valorant_tier2.db"


def slots(db: Path) -> list[tuple[str, int, int, int]]:
    con = sqlite3.connect(db)
    q = """SELECT m.date_utc, m.season, m.match_id, l.p1, l.p2, l.p3, l.p4, l.p5
           FROM lineups l JOIN research_matches m USING(match_id)"""
    return [(d, s, mid, p) for d, s, mid, *ps in con.execute(q) for p in ps if p is not None]


def main() -> None:
    a, b = slots(T1), slots(T2)
    first1: dict[int, str] = {}
    for d, _s, _m, p in sorted(a):
        first1.setdefault(p, d)
    first2: dict[int, str] = {}
    for d, _s, _m, p in sorted(b):
        first2.setdefault(p, d)
    test: dict[tuple[int, int], str] = {}
    for d, s, mid, p in a:
        if s == 2026:
            test[(mid, p)] = min(d, test.get((mid, p), d))
    n = len(test)
    has1 = sum(1 for (_m, p), d in test.items() if first1.get(p, "9") < d)
    has2 = sum(1 for (_m, p), d in test.items() if first2.get(p, "9") < d)
    only2 = sum(1 for (_m, p), d in test.items() if first2.get(p, "9") < d and not first1.get(p, "9") < d)
    neither = sum(1 for (_m, p), d in test.items() if not first2.get(p, "9") < d and not first1.get(p, "9") < d)
    players = {p for _m, p in test}
    out = {"n_slots_2026_t1": n, "n_players": len(players), "with_prior_t1": has1, "with_prior_t2": has2,
           "t2_only": only2, "neither": neither,
           "players_t2_only": len({p for (_m, p), d in test.items() if first2.get(p, "9") < d
                                   and not first1.get(p, "9") < d})}
    (ROOT / "out" / "t2_history_coverage.json").write_text(json.dumps(out, indent=1))
    print(out)


if __name__ == "__main__":
    main()
