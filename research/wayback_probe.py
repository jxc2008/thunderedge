"""Estimate Wayback coverage of PRE-MATCH vlr.gg snapshots (two-sided odds).
Usage: python -m research.wayback_probe N  (random sample of N tier-1 matches)
Writes research/cache/wayback_probe.json. archive.org only; >=1.5s spacing.
"""
import json, random, sys, time
from datetime import datetime
import requests
from research import vlr_fetch as v, parse_match as P
CDX = "http://web.archive.org/cdx/search/cdx"
n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
d = json.load(open(v.ROOT / "cache" / "tier1_matches.json"))
ms = [m for x in d.values() for m in x if v.cached(m)]
random.seed(7); sample = random.sample(ms, min(n, len(ms)))
out = []
for m in sample:
    mid = m.strip("/").split("/")[0]
    info = P.parse(v.get(m), m)
    start = info["date_utc"]
    try:
        r = requests.get(CDX, params={"url": f"vlr.gg/{mid}/*", "output": "json",
                         "fl": "timestamp,statuscode", "filter": "statuscode:200"}, timeout=60)
        rows = r.json()[1:] if r.text.strip() else []
    except Exception as e:
        rows, start = [], start; print("ERR", mid, e)
    pre = [t for t, _ in rows if start and datetime.strptime(t, "%Y%m%d%H%M%S") < datetime.strptime(start, "%Y-%m-%d %H:%M:%S")]
    out.append({"match": m, "start": start, "n_snaps": len(rows), "n_pre": len(pre), "last_pre": max(pre) if pre else None})
    print(mid, start, len(rows), len(pre), flush=True)
    time.sleep(1.5)
json.dump(out, open(v.ROOT / "cache" / "wayback_probe.json", "w"), indent=1)
k = sum(1 for o in out if o["n_pre"]); print(f"pre-match snapshot coverage: {k}/{len(out)}")
