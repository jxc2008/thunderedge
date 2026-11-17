"""Frozen evaluation for research/PREREG_KICKOFF2027.md. Do not edit after the code freeze except
for logged bug fixes (prereg §9).

Part 1 (§3-§5): early-season churn underdog rule — paper bets, ROI, decision at look 1 / look 2.
Part 2 (§10):   stale-line study — after each result, the logger snapshots the same teams'
                upcoming matches (trigger='post_result'). Reference = Pinnacle's de-vigged price at
                the snapshot time (OddsPapi history); signal = Pinnacle - stale de-vigged Thunderpick
                price; paper bet the signalled side at the stale price; CLV vs Thunderpick's close.
                Where Pinnacle is missing or pulled, model (a) is the reference and those rows are
                reported separately (amendment 2026-11-17, PREREG §9).
Strata: tier 1 (primary) and tier 2 (separately reported) via events.tier.

Inputs: data/valorant_stats.db (results/lineups, rebuilt with the 2027 pages), data/odds_snapshots.db
(odds logger), roster_snapshots table (research/fetch_rosters.py), and the frozen rating model:
valorant-pricing-model/src/rating + research/out/rating_eval.json (params + head (a)).

Usage:
  python -m research.prereg_kickoff2027 --season 2027 --fetch-pinnacle   # network: OddsPapi only (PREREG §4)
  python -m research.prereg_kickoff2027 --season 2027 [--look 1|2] --out research/out/prereg_2027.json
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
PRICING = REPO.parent / "valorant-pricing-model"
DB = REPO / "data" / "valorant_stats.db"
SNAP = REPO / "data" / "odds_snapshots.db"
FROZEN = ROOT / "out" / "rating_eval.json"

# ---- pre-registered constants (PREREG §2-§5, §10)
WEEKS_MAX = 6.0
CHURN_MIN = 0.6
BET_LEAD = timedelta(minutes=60)
BET_MAX_AGE = timedelta(hours=6)
ROSTER_WINDOW = (timedelta(hours=48), timedelta(hours=2))
MIN_BETS_LOOK1 = 20
ALPHA = {1: 0.01, 2: 0.04}
NBOOT = 10_000
STALE_MIN_SIGNAL = 0.02          # |reference - stale price| needed for a stale-line paper bet
PIN_HOST = "oddspapi_prereg"     # ledger label / cap in research/hist_fetch.py
SURPRISE_BINS = (0.0, 0.3, 0.6, 1.01)
BOOK = "thunderpick"


def _pricing():
    """Import the frozen rating engine from the pricing repo (its `scripts` package must win
    over this repo's top-level scripts/ folder)."""
    sys.path.insert(0, str(PRICING))
    from scripts import rating_eval as R  # noqa: PLC0415
    from scripts.walkforward_eval import series_p  # noqa: PLC0415
    from src.rating.dp_table import MapTable  # noqa: PLC0415
    from src.rating.engine import Engine, EngineParams, Team  # noqa: PLC0415
    assert Path(R.__file__).resolve().is_relative_to(PRICING), R.__file__
    return R, series_p, MapTable, Engine, EngineParams, Team


def _dt(s: str) -> datetime:
    s = s.replace("Z", "+00:00").replace(" ", "T")
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _boot_mean(x: np.ndarray, alpha: float, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    if len(x) == 0:
        return {"n": 0}
    draws = rng.choice(x, size=(NBOOT, len(x)), replace=True).mean(1)
    return {"n": int(len(x)), "mean": float(x.mean()), "lower_one_sided": float(np.quantile(draws, alpha)),
            "ci95": [float(np.quantile(draws, .025)), float(np.quantile(draws, .975))]}


# ------------------------------------------------------------------------------- odds access
class Odds:
    def __init__(self, snap_db: Path, name_to_id: dict[str, int]) -> None:
        self.con = sqlite3.connect(f"file:{snap_db}?mode=ro", uri=True)
        self.ids = name_to_id

    def two_sided(self, mid: int, lo: datetime | None, hi: datetime, trigger: str | None = None
                  ) -> tuple[datetime, dict[int, float]] | None:
        """Latest snapshot in (lo, hi] with exactly two 'pre' prices from BOOK, keyed by team id."""
        q = """SELECT ts_utc, team, odds_decimal FROM odds_snapshots WHERE source='vlr' AND match_key=?
               AND book=? AND status='pre' AND odds_decimal > 1.0""" + (" AND trigger=?" if trigger else "")
        by_ts: dict = defaultdict(dict)
        for ts, team, o in self.con.execute(q, (f"vlr:{mid}", BOOK, *([trigger] if trigger else []))):
            t = _dt(ts)
            if t <= hi and (lo is None or t > lo):
                tid = self.ids.get((team or "").lower())
                if tid is not None:
                    by_ts[t][tid] = o
        for t in sorted(by_ts, reverse=True):
            if len(by_ts[t]) == 2:
                return t, by_ts[t]
        return None


def devig(p: dict[int, float], tid: int) -> float:
    inv = {k: 1 / v for k, v in p.items()}
    return inv[tid] / sum(inv.values())


# ------------------------------------------------------------------------------- data
def load(db: Path, season: int):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    name_to_id: dict[str, int] = {}
    for tid, name, tag in con.execute("SELECT team_id, name, tag FROM teams"):
        for k in (name, tag):
            if k:
                name_to_id.setdefault(k.lower(), tid)
    for alias, tid in con.execute("SELECT alias, team_id FROM team_aliases"):
        name_to_id.setdefault(alias.lower(), tid)
    matches = con.execute("""SELECT m.match_id, m.date_utc, m.season, m.team1_id, m.team2_id, m.winner_id,
                                    m.weeks_since_season_start, m.event_id, e.tier, m.is_international,
                                    m.best_of, m.map_pool
                             FROM research_matches m JOIN events e USING(event_id)
                             WHERE m.date_utc IS NOT NULL ORDER BY m.date_utc""").fetchall()
    five: dict = {}
    for mid, tid, f in con.execute("""SELECT match_id, team_id, p1||','||p2||','||p3||','||p4||','||p5
                                      FROM lineups ORDER BY game_id"""):
        five.setdefault((mid, tid), tuple(sorted(int(x) for x in f.split(","))))
    rosters: dict = defaultdict(list)
    if con.execute("SELECT name FROM sqlite_master WHERE name='roster_snapshots'").fetchone():
        for tid, ts, *ps in con.execute("SELECT team_id, captured_ts, p1, p2, p3, p4, p5 FROM roster_snapshots"):
            rosters[tid].append((_dt(ts), tuple(sorted(int(p) for p in ps))))
    return con, name_to_id, matches, five, rosters


# ------------------------------------------------------------------------------- part 1
def churn_bets(season: int, odds: Odds, matches, five, rosters) -> tuple[list[dict], dict]:
    excl: dict = defaultdict(int)
    last_prev_season: dict = {}
    prev_in_season: dict = {}
    bets = []
    for (mid, date, s, t1, t2, win, wk, ev, tier, intl, bo, pool) in matches:
        T = _dt(date)
        if s == season - 1:
            for t in (t1, t2):
                if (mid, t) in five:
                    last_prev_season[t] = five[(mid, t)]
            continue
        if s != season:
            continue
        expect = {}
        for t in (t1, t2):
            if t in prev_in_season:
                expect[t] = prev_in_season[t]
            else:
                snaps = [f for ts, f in rosters.get(t, []) if T - ROSTER_WINDOW[0] <= ts <= T - ROSTER_WINDOW[1]]
                expect[t] = snaps[-1] if snaps else None
        realized = {t: five.get((mid, t)) for t in (t1, t2)}
        for t in (t1, t2):
            if realized[t]:
                prev_in_season[t] = realized[t]
        in_window = wk is not None and wk <= WEEKS_MAX
        if win is None:
            excl["not_completed_or_forfeit"] += int(in_window)
            continue
        if t1 not in last_prev_season or t2 not in last_prev_season:
            excl["no_previous_season_lineup"] += int(in_window)
            continue
        churn_real = (max(1 - len(set(realized[t]) & set(last_prev_season[t])) / 5 for t in (t1, t2))
                      if realized[t1] and realized[t2] else None)
        if expect[t1] is None or expect[t2] is None:
            excl["no_expected_five"] += int(in_window)
            churn = None
        else:
            churn = max(1 - len(set(expect[t]) & set(last_prev_season[t])) / 5 for t in (t1, t2))
        qualifies = bool(in_window and churn is not None and churn >= CHURN_MIN)
        row = {"match_id": mid, "tier": tier, "weeks": wk, "in_window": in_window, "churn_max": churn,
               "churn_max_realized": churn_real, "qualifies": qualifies}
        # every match with a price gets a hypothetical underdog bet so the §6 complement slices and
        # the realised-lineup variant use the same pricing rule; only `qualifies` rows are the test
        snap = odds.two_sided(mid, T - BET_MAX_AGE - BET_LEAD, T - BET_LEAD)
        if snap is None:
            excl["no_price"] += int(qualifies)
            row["no_price"] = True
            bets.append(row)
            continue
        ts, px = snap
        if px[t1] == px[t2]:
            excl["equal_prices"] += int(qualifies)
            bets.append(row)
            continue
        dog = t1 if px[t1] > px[t2] else t2
        close = odds.two_sided(mid, None, T)
        row.update(bet_ts=ts.isoformat(), dog=dog, price=px[dog], pnl=(px[dog] - 1) if win == dog else -1.0,
                   clv=math.log(px[dog] / close[1][dog]) if close else None)
        bets.append(row)
    return bets, dict(excl)


# ------------------------------------------------------------------------------- part 2
def _trigger_rows(odds: Odds) -> list[tuple]:
    return odds.con.execute("""SELECT match_key, ref_match, MIN(ts_utc) FROM odds_snapshots
                               WHERE trigger='post_result' AND book=? GROUP BY match_key, ref_match""",
                            (BOOK,)).fetchall()


def pinnacle_series(season: int, mids: set[int], fetch: bool) -> dict:
    """match_id -> pinnacle.Series for vlr team 1. Network only when ``fetch``; otherwise cache."""
    from research import hist_fetch as H, pinnacle as PN  # noqa: PLC0415
    ms = [m for m in H.vlr_matches(season) if m["match_id"] in mids]
    if fetch:
        fx = H.fixture_windows([m["start"] for m in ms], PIN_HOST)
    else:
        fx = []
        for fp in H.CACHE.glob("op_fixtures_*.json"):
            d = json.loads(fp.read_text() or "[]")
            fx += d if isinstance(d, list) else d.get("data", [])
    mp = H.map_fixtures(ms, fx)
    out = {}
    for mid, f in mp.items():
        if fetch:
            H.fetch_history(f["fixtureId"], PIN_HOST)
        h = PN.load(f["fixtureId"])
        sr = PN.series(h, f["p1_is_team1"]) if h else None
        if sr is not None:
            out[int(mid)] = sr
    return out


def stale_line(season: int, odds: Odds, matches, frozen: dict, pin: dict | None = None) -> list[dict]:
    pin = pin or {}
    R, series_p, MapTable, Engine, EngineParams, Team = _pricing()
    D = R.load(str(DB))
    table = MapTable()
    pa, pb = EngineParams(**frozen["params_a"]), EngineParams(**frozen["params_b"])
    beta = np.array(frozen["head_a_beta"])
    info = {m[0]: m for m in matches}
    trig = _trigger_rows(odds)
    out = []
    for key, ref, ts0 in trig:
        mid, rid = int(key.split(":")[1]), int(ref.split(":")[1])
        if mid not in info or rid not in info or info[mid][2] != season:
            continue
        _, date, _, t1, t2, win, _, _, tier, intl, bo, pool = info[mid]
        t0 = _dt(ts0)
        stale = odds.two_sided(mid, t0 - timedelta(minutes=1), t0 + timedelta(minutes=30), trigger="post_result")
        close = odds.two_sided(mid, None, _dt(date))
        if stale is None or close is None or win is None:
            continue
        pin_now = pin[mid].at(t0) if mid in pin else None
        if pin_now is not None and pin_now[1]:
            p_ref, ref_type = pin_now[0], "pinnacle"
        else:  # Pinnacle missing or line pulled at t0 -> model (a), reported separately
            p_ref = _model_prob(R, series_p, table, Engine, Team, pa, D, t1, t2, t0, bo or 3, beta, intl)
            ref_type = "model_a"
        ref_m = info[rid]
        pin_ref = pin[rid].at(_dt(ref_m[1])) if rid in pin else None
        if pin_ref is not None and pin_ref[1]:
            p_pre_ref, surprise_src = pin_ref[0], "pinnacle"
        else:
            p_pre_ref = _model_prob(R, series_p, table, Engine, Team, pb, D, ref_m[3], ref_m[4], _dt(ref_m[1]),
                                    ref_m[10] or 3, None, ref_m[9], pool_json=ref_m[11])
            surprise_src = "model_b"
        y_ref = 1.0 if ref_m[5] == ref_m[3] else 0.0
        p_stale = devig(stale[1], t1)
        sig = p_ref - p_stale
        row = {"match_id": mid, "ref_match": rid, "tier": tier, "ref_type": ref_type, "signal": sig,
               "p_ref": p_ref, "p_stale": p_stale, "p_close": devig(close[1], t1),
               "surprise": abs(y_ref - p_pre_ref), "surprise_src": surprise_src, "stale_ts": stale[0].isoformat()}
        if abs(sig) >= STALE_MIN_SIGNAL:
            side = t1 if sig > 0 else t2
            row.update(side=side, clv=math.log(stale[1][side] / close[1][side]),
                       pnl=(stale[1][side] - 1) if win == side else -1.0)
        out.append(row)
    return out


def _model_prob(R, series_p, table, Engine, Team, params, D, a, b, t_cut: datetime, bo, beta, intl,
                pool_json: str | None = None) -> float:
    """Engine state from every map of matches strictly before t_cut; predict a vs b."""
    from scripts.rebuild_half_win_rates import _days  # noqa: PLC0415  (pricing repo, already on path)
    cut = _days(t_cut.strftime("%Y-%m-%d %H:%M:%S"))
    eng = Engine(params)
    last_five: dict = {}
    pools: dict = defaultdict(int)
    for m in D["matches"]:
        if m["t"] >= cut:
            break
        ra, rb = D["region"].get(m["a"]), D["region"].get(m["b"])
        for g, mp, (k1, n1, k2, n2) in m["games"]:
            f1, f2 = D["fives"].get((g, m["a"])), D["fives"].get((g, m["b"]))
            if cut - m["t"] <= 120:
                pools[mp] += 1
            if f1 and f2 and ra and rb and n1 + n2 > 0:
                eng.update_map(Team(m["a"], f1, ra), Team(m["b"], f2, rb), mp, m["t"], m["season"], (k1, n1), (k2, n2))
                last_five[m["a"]], last_five[m["b"]] = f1, f2
    if a not in last_five or b not in last_five:
        return float("nan")
    A, B = Team(a, last_five[a], D["region"][a]), Team(b, last_five[b], D["region"][b])
    pool = tuple(json.loads(pool_json)) if pool_json else tuple(sorted(pools, key=lambda k: -pools[k])[:7])
    season = max(m["season"] for m in D["matches"] if m["t"] < cut)
    pm = [table.map_p(*eng.predict_map(A, B, mp, cut, season)[:3]) for mp in pool]
    ps = series_p(pm, bo) if pool_json else series_p([float(np.mean(pm))] * bo, bo)
    if beta is None:
        return ps
    x = math.log(ps / (1 - ps))
    return 1 / (1 + math.exp(-(beta[0] + beta[1] * x + beta[3] * x * intl)))  # lineup_change assumed 0


# ------------------------------------------------------------------------------- summary
def summarize(bets: list[dict], stale: list[dict], excl: dict, look: int) -> dict:
    res: dict = {"look": look, "exclusions": excl}
    for tier in (1, 2):
        b = [x for x in bets if x["tier"] == tier and x.get("qualifies") and "pnl" in x]
        pnl = np.array([x["pnl"] for x in b])
        blk = {"n_qualifying": sum(1 for x in bets if x["tier"] == tier and x.get("qualifies")),
               "n_bets": len(b), "roi": _boot_mean(pnl, ALPHA[look]),
               "clv": _boot_mean(np.array([x["clv"] for x in b if x.get("clv") is not None]), 0.05)}
        priced = [x for x in bets if x["tier"] == tier and "pnl" in x]
        blk["secondary_roi"] = {
            "realised_lineup_variant": _boot_mean(np.array([x["pnl"] for x in priced if x["in_window"]
                                                            and (x["churn_max_realized"] or 0) >= CHURN_MIN]), 0.05),
            "window_churn_below_0.6": _boot_mean(np.array([x["pnl"] for x in priced if x["in_window"]
                                                           and x["churn_max"] is not None and x["churn_max"] < CHURN_MIN]), 0.05),
            "after_window_churn_ge_0.6": _boot_mean(np.array([x["pnl"] for x in priced if not x["in_window"]
                                                              and (x["churn_max"] or 0) >= CHURN_MIN]), 0.05)}
        if tier == 1:
            if look == 1 and len(b) < MIN_BETS_LOOK1:
                blk["decision"] = "void (fewer than 20 priced bets) - rerun as look 1 in 2028"
            elif len(b) and blk["roi"]["lower_one_sided"] > 0:
                blk["decision"] = "confirm"
            elif look == 1 and len(b) and blk["roi"]["mean"] <= 0:
                blk["decision"] = "abandon"
            else:
                blk["decision"] = "continue to 2028" if look == 1 else "abandon"
        else:
            blk["decision"] = "descriptive stratum (no decision)"
        res[f"churn_rule_tier{tier}"] = blk
        for ref_type in ("pinnacle", "model_a"):
            res[f"stale_line_tier{tier}_{ref_type}"] = _stale_block(
                [x for x in stale if x["tier"] == tier and x["ref_type"] == ref_type],
                decide=(tier == 1 and ref_type == "pinnacle"))
    return res


def _stale_block(rows: list[dict], decide: bool) -> dict:
    if True:
        s = [x for x in rows if "clv" in x]
        clv = np.array([x["clv"] for x in s])
        sur = np.array([x["surprise"] for x in s])
        sblk = {"n_snapshots": len(rows), "n_bets": len(s), "clv": _boot_mean(clv, 0.05),
                "roi_at_stale_price": _boot_mean(np.array([x["pnl"] for x in s]), 0.05)}
        if len(s) >= 10 and np.std(sur) > 0:
            rng = np.random.default_rng(1)
            slope = float(np.polyfit(sur, clv, 1)[0])
            bs = []
            for _ in range(NBOOT // 5):
                i = rng.integers(0, len(s), len(s))
                if np.std(sur[i]) > 0:
                    bs.append(np.polyfit(sur[i], clv[i], 1)[0])
            sblk["slope_clv_on_surprise"] = {"est": slope, "lower_one_sided": float(np.quantile(bs, 0.05))}
            sblk["by_surprise"] = {f"{lo}-{hi}": _boot_mean(clv[(sur >= lo) & (sur < hi)], 0.05)
                                   for lo, hi in zip(SURPRISE_BINS[:-1], SURPRISE_BINS[1:], strict=True)}
            mv = np.array([x["p_close"] - x["p_stale"] for x in rows])
            sg = np.array([x["signal"] for x in rows])
            sblk["move_on_signal_slope"] = float(np.polyfit(sg, mv, 1)[0]) if len(sg) > 2 and np.std(sg) > 0 else None
            ok = sblk["clv"]["lower_one_sided"] > 0 and sblk["slope_clv_on_surprise"]["est"] > 0
            sblk["decision"] = (("success" if ok and sblk["slope_clv_on_surprise"]["lower_one_sided"] > 0
                                 else "partial (CLV > 0, slope not established)" if ok
                                 else "not supported") if decide else "descriptive (no decision)")
        return sblk


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2027)
    ap.add_argument("--look", type=int, choices=(1, 2), default=1)
    ap.add_argument("--db", default=str(DB))
    ap.add_argument("--snap", default=str(SNAP))
    ap.add_argument("--out", default=str(ROOT / "out" / "prereg_2027.json"))
    ap.add_argument("--fetch-pinnacle", action="store_true", help="download Pinnacle history, then exit")
    a = ap.parse_args()
    frozen = json.loads(FROZEN.read_text())
    _, name_to_id, matches, five, rosters = load(Path(a.db), a.season)
    odds = Odds(Path(a.snap), name_to_id)
    seasons = (a.season,) if a.look == 1 else (a.season - 1, a.season)
    trig_ids = {int(x.split(":")[1]) for k, r, _ in _trigger_rows(odds) for x in (k, r)}
    if a.fetch_pinnacle:
        for s in seasons:
            pinnacle_series(s, trig_ids, fetch=True)
        print("pinnacle history cached")
        return
    bets, excl, stale = [], {}, []
    for s in seasons:
        b, e = churn_bets(s, odds, matches, five, rosters)
        bets += b
        for k, v in e.items():
            excl[k] = excl.get(k, 0) + v
        stale += stale_line(s, odds, matches, frozen, pinnacle_series(s, trig_ids, fetch=False))
    res = summarize(bets, stale, excl, a.look)
    Path(a.out).write_text(json.dumps({"summary": res, "bets": bets, "stale": stale}, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
