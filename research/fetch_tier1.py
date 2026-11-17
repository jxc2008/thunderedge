"""Fetch (cache-only) all tier-1 2024-2026 match pages listed in cache/tier1_matches.json."""
import json, sys
from research import vlr_fetch as v
d = json.load(open(v.ROOT / "cache" / "tier1_matches.json"))
todo = [m for ms in d.values() for m in ms if not v.cached(m)]
print(f"{len(todo)} to fetch; used {v.live_requests_used()}", flush=True)
for i, m in enumerate(todo):
    try:
        v.get(m)
    except v.BudgetExceeded as e:
        print("STOP", e); sys.exit(1)
    except Exception as e:
        print("ERR", m, e, flush=True)
    if i % 100 == 0:
        print(i, v.live_requests_used(), flush=True)
print("done; used", v.live_requests_used())
