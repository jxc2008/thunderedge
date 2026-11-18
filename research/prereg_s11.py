"""Frozen evaluation for PREREG_KICKOFF2027.md §11: paper-trade Kalshi taking against Pinnacle (k = 5 pts).
Do not edit after the code freeze except for logged bug fixes (prereg §9).

Rule (§11). At each Kalshi observation time t before the start (an odds-logger poll whose book request
succeeded, or an event-driven book snapshot), for the vlr-team-1 KXVALORANTGAME market:
  fair  = Pinnacle de-vigged probability (PRIMARY_DEVIG) from the latest Pinnacle record at or before t;
          the record must be active, valid for the method, and at most MAX_PIN_AGE old;
  ask   = best YES ask (1 - best NO bid) for the YES side, 1 - best YES bid for the NO side;
  size  = displayed contracts at that ask (top level only);
  enter when fair - ask > K, 0.01 <= ask <= 0.99 and size >= 1; first entry per match x side; contracts
  C = min(UNIT, floor(size)); fee = ceil(100 * 0.07 * C * ask * (1 - ask)) / 100 dollars (Kalshi
  quadratic fee, series multiplier 1, rounded up per order).
Primary metric: net CLV, pts = 100 * (Pinnacle close for the side - ask) - 100 * fee / C, one value per
trade, Pinnacle close = last active valid PRIMARY_DEVIG record before the start. Match-level bootstrap.
Secondary: settlement P&L (per contract and per trade at C contracts), the ask < 0.30 slice, the other
de-vig methods, CLV vs Kalshi close mid, and counts of signals blocked by Pinnacle age / displayed size.

Modes:
  python -m research.prereg_s11 --season 2027 --look 1 [--fetch]  # frozen evaluation on logged data
  python -m research.prereg_s11 --backtest-2026                    # same rule on 2026 candles (no
         displayed size: size treated as UNIT; observation times sampled every 15 min) -> power inputs
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SNAP = ROOT.parent / "data" / "odds_snapshots.db"
K = 0.05
UNIT = 100                       # contracts
MAX_PIN_AGE = timedelta(minutes=15)
FEE_RATE, FEE_MULT = 0.07, 1.0
PRIMARY_DEVIG = "shin"           # fixed by the §11 rule on 2026 data (Shin fails on <= 5% of markets): REPORT_v6 §1
OTHER_DEVIG = ("mult", "power")
CHEAP = 0.30
LOOK_END = {1: datetime(2027, 6, 30, tzinfo=timezone.utc),   # matches starting up to this date
            2: datetime(2027, 10, 31, tzinfo=timezone.utc)}  # pooled with look 1 (whole 2027 season)
ALPHA = {1: 0.01, 2: 0.04}
MIN_TRADES = {1: 20, 2: 30}
PIN_HOST = "oddspapi_s11"        # ledger host / cap in research/hist_fetch.py (PREREG §4, §11)
NBOOT = 10_000
CADENCE_BACKTEST = timedelta(minutes=15)


def fee_dollars(c: int, ask: float) -> float:
    return math.ceil(100 * FEE_RATE * FEE_MULT * c * ask * (1 - ask) - 1e-9) / 100


def pin_close(s, start: datetime) -> float | None:
    for t, p, a, ok in zip(reversed(s.t), reversed(s.p1), reversed(s.active), reversed(s.ok), strict=True):
        if t < start and a and ok:
            return p
    return None


def entries(times: list[datetime], book_at, s, start: datetime, k: float = K) -> tuple[list[dict], dict]:
    """The §11 decision. book_at(t) -> (yes_bid, yes_bid_size, yes_ask, yes_ask_size) or None; sizes may be
    None (unknown = UNIT, backtest only). s = pinnacle.Series for vlr team 1 with .ok."""
    out, done = [], set()
    blocked = defaultdict(int)
    for t in times:
        if t >= start or len(done) == 2:
            break
        i = bisect.bisect_right(s.t, t) - 1
        if i < 0:
            continue
        b = book_at(t)
        if b is None:
            continue
        yb, ybs, ya, yas = b
        for side, fair, ask, size in (("yes", s.p1[i], ya, yas), ("no", 1 - s.p1[i], None if yb is None else 1 - yb, ybs)):
            if side in done or ask is None or not 0.01 <= ask <= 0.99 or fair - ask <= k:
                continue
            if not s.active[i] or not s.ok[i]:
                blocked["pinnacle_inactive_or_invalid"] += 1
                continue
            if t - s.t[i] > MAX_PIN_AGE:
                blocked["pinnacle_older_than_15min"] += 1
                continue
            c = UNIT if size is None else min(UNIT, int(math.floor(size)))
            if c < 1:
                blocked["no_displayed_size"] += 1
                continue
            out.append({"t": t.isoformat(), "side": side, "ask": ask, "fair": fair, "contracts": c,
                        "fee": fee_dollars(c, ask), "pin_age_min": (t - s.t[i]).total_seconds() / 60})
            done.add(side)
    return out, dict(blocked)


def score(trades: list[dict], s_by_method: dict, start: datetime, y: float | None, kal_close_mid: float | None) -> None:
    for x in trades:
        for m, s in s_by_method.items():
            pc = pin_close(s, start) if s is not None else None
            side_pc = None if pc is None else (pc if x["side"] == "yes" else 1 - pc)
            x[f"clv_pin_{m}_pts"] = None if side_pc is None else 100 * (side_pc - x["ask"])
            x[f"net_clv_{m}_pts"] = None if side_pc is None else 100 * (side_pc - x["ask"]) - 100 * x["fee"] / x["contracts"]
        if kal_close_mid is not None:
            cm = kal_close_mid if x["side"] == "yes" else 1 - kal_close_mid
            x["clv_kalshi_pts"] = 100 * (cm - x["ask"])
        if y is not None:
            won = (y == 1.0) == (x["side"] == "yes")
            x["pnl_per_contract_c"] = 100 * ((1.0 if won else 0.0) - x["ask"]) - 100 * x["fee"] / x["contracts"]
            x["pnl_trade_dollars"] = x["contracts"] * ((1.0 if won else 0.0) - x["ask"]) - x["fee"]


def boot(rows: list[dict], key: str, alpha: float, cluster: str = "match_id", seed: int = 0) -> dict:
    rows = [r for r in rows if r.get(key) is not None]
    if not rows:
        return {"n": 0}
    cl = sorted({r[cluster] for r in rows})
    by = defaultdict(list)
    for r in rows:
        by[r[cluster]].append(r[key])
    rng = np.random.default_rng(seed)
    sums = np.array([sum(by[c]) for c in cl])
    cnts = np.array([len(by[c]) for c in cl])
    idx = rng.integers(0, len(cl), size=(NBOOT, len(cl)))
    draws = sums[idx].sum(1) / cnts[idx].sum(1)
    x = np.array([r[key] for r in rows])
    return {"n": len(rows), "n_matches": len(cl), "mean": float(x.mean()), "sd": float(x.std(ddof=1)) if len(x) > 1 else None,
            "lower_one_sided": float(np.quantile(draws, alpha)),
            "ci95": [float(np.quantile(draws, .025)), float(np.quantile(draws, .975))]}


def summarize(trades: list[dict], blocked: dict, look: int) -> dict:
    p = f"net_clv_{PRIMARY_DEVIG}_pts"
    prim = boot(trades, p, ALPHA[look])
    n = prim.get("n", 0)
    if n < MIN_TRADES[look]:
        decision = (f"void (fewer than {MIN_TRADES[look]} trades) - continue to look 2" if look == 1
                    else f"inconclusive (fewer than {MIN_TRADES[look]} trades)")
    elif prim["lower_one_sided"] > 0:
        decision = "confirm"
    elif prim["mean"] <= 0:
        decision = "abandon"
    else:
        decision = "continue to look 2" if look == 1 else "abandon"
    cheap = [x for x in trades if x["ask"] < CHEAP]
    return {"look": look, "primary_devig": PRIMARY_DEVIG, "k": K, "primary_net_clv_pts": prim, "decision": decision,
            "secondary": {
                "settlement_pnl_per_contract_c": boot(trades, "pnl_per_contract_c", 0.05),
                "settlement_pnl_per_trade_dollars": boot(trades, "pnl_trade_dollars", 0.05),
                "ask_below_0.30": {"n": len(cheap), "net_clv": boot(cheap, p, 0.05)},
                "other_devig": {m: boot(trades, f"net_clv_{m}_pts", 0.05) for m in OTHER_DEVIG},
                "gross_clv_primary": boot(trades, f"clv_pin_{PRIMARY_DEVIG}_pts", 0.05),
                "clv_vs_kalshi_close": boot(trades, "clv_kalshi_pts", 0.05),
                "mean_contracts": float(np.mean([x["contracts"] for x in trades])) if trades else None,
                "blocked_signals": blocked}}


# ------------------------------------------------------------------------------ 2027 (logged data)
def logged_markets(con: sqlite3.Connection) -> dict[str, dict]:
    """Kalshi KXVALORANTGAME tickers seen by the logger: ticker -> {event, team, start, times}."""
    out: dict = {}
    for ts, ev, ticker, start, team in con.execute(
            """SELECT ts_utc, match_key, match_url, start_utc, team FROM odds_snapshots
               WHERE source='kalshi' AND event='KXVALORANTGAME'"""):
        d = out.setdefault(ticker, {"event": ev, "team": team, "start": start, "times": set()})
        d["times"].add(ts)
    bad = {ts for ts, err in con.execute("SELECT ts_utc, errors FROM poll_log WHERE errors LIKE '%kalshi books%'")}
    for ticker, ts in con.execute("SELECT ticker, ts_utc FROM kalshi_books WHERE trigger IS NOT NULL"):
        if ticker in out:
            out[ticker]["times"].add(ts)
    for d in out.values():
        d["times"] = sorted(datetime.fromisoformat(t) for t in d["times"] if t not in bad)
    return out


def book_reader(con: sqlite3.Connection, ticker: str):
    rows = [(datetime.fromisoformat(ts), json.loads(y), json.loads(n)) for ts, y, n in con.execute(
        "SELECT ts_utc, yes_bids, no_bids FROM kalshi_books WHERE ticker=? ORDER BY ts_utc", (ticker,))]
    ts = [r[0] for r in rows]

    def at(t: datetime):
        i = bisect.bisect_right(ts, t) - 1
        if i < 0:
            return None
        _, yes, no = rows[i]
        yb, ybs = (yes[0][0], yes[0][1]) if yes else (None, None)
        ya, yas = (1 - no[0][0], no[0][1]) if no else (None, None)
        return yb, ybs, ya, yas
    return at


def run_2027(season: int, look: int, fetch: bool) -> dict:
    from research import hist_fetch as H  # noqa: PLC0415
    from research import odds_logger as LG  # noqa: PLC0415
    from research import pinnacle as PN  # noqa: PLC0415
    from research.pinnacle_open_poll import NOT_TIER1, STATE  # noqa: PLC0415
    from research.timeutil import vlr_to_utc  # noqa: PLC0415
    con = sqlite3.connect(f"file:{SNAP}?mode=ro", uri=True)
    vlr = []
    for key, event, t1, t2 in con.execute("SELECT match_key, event, team1, team2 FROM match_status"):
        if not LG.TIER1.search(event or "") or NOT_TIER1.search(event or ""):
            continue
        r = con.execute("SELECT max(start_utc) FROM odds_snapshots WHERE match_key=? AND source='vlr'", (key,)).fetchone()
        if r and r[0] and vlr_to_utc(r[0]).year == season:
            vlr.append({"match_id": int(key.split(":")[1]), "start": vlr_to_utc(r[0]), "a": 1, "b": 2,
                        "names": {1: {H.norm(t1)}, 2: {H.norm(t2)}}, "t1": t1, "t2": t2})
    if not vlr:
        return {"look": look, "decision": "no data", "n_matches": 0}
    season_start = min(m["start"] for m in vlr)
    end = LOOK_END[look]
    vlr = [m for m in vlr if m["start"] <= end]
    # fixtures: the live Pinnacle-open poll's mapping first (no cost), then cached / fetched fixture lists
    fmap: dict = {}
    if STATE.exists():
        for fid, v in json.loads(STATE.read_text()).get("fixtures", {}).items():
            fmap[v["match_key"].split(":")[1]] = {"fixtureId": fid, "p1_is_team1": v["p1_is_team1"]}
    rest = [m for m in vlr if str(m["match_id"]) not in fmap]
    fx = H.fixtures(False)
    if fetch and rest:
        fx += H.fixture_windows([m["start"] for m in rest], PIN_HOST)
    fmap = {**H.map_fixtures(rest, fx), **fmap}
    mk = logged_markets(con)
    by_event = defaultdict(list)
    for tk, d in mk.items():
        by_event[d["event"]].append((tk, d))
    trades, blocked = [], defaultdict(int)
    settle_tickers = []
    for m in vlr:
        f = fmap.get(str(m["match_id"]))
        if f is None:
            continue
        if fetch:
            H.fetch_history(f["fixtureId"], PIN_HOST)
        h = PN.load(f["fixtureId"])
        if not h:
            continue
        s_by = {meth: PN.series(h, f["p1_is_team1"], method=meth) for meth in (PRIMARY_DEVIG, *OTHER_DEVIG)}
        s = s_by[PRIMARY_DEVIG]
        cand = [(tk, d) for ev in by_event.values() for tk, d in ev
                if H.team_hit(d["team"], m["names"][1]) and abs((datetime.fromisoformat(d["start"].replace("Z", "+00:00"))
                                                                 - m["start"]).total_seconds()) < 36 * 3600]
        if s is None or not cand:
            continue
        tk, d = cand[0]
        at = book_reader(con, tk)
        tr, bl = entries(d["times"], at, s, m["start"])
        for k_, v in bl.items():
            blocked[k_] += v
        last = at(m["start"] - timedelta(seconds=1))
        mid = (last[0] + last[2]) / 2 if last and last[0] is not None and last[2] is not None else None
        for x in tr:
            x.update(match_id=m["match_id"], ticker=tk)
        score(tr, s_by, m["start"], None, mid)
        trades += tr
        settle_tickers.append(tk)
    res = {}
    if fetch and settle_tickers:
        for i in range(0, len(settle_tickers), 100):
            r = H.get("kalshi_prereg", H.KALSHI + "/markets", {"tickers": ",".join(settle_tickers[i:i + 100]), "limit": 100})
            for x in r.json().get("markets", []):
                if x.get("result") in ("yes", "no"):
                    res[x["ticker"]] = 1.0 if x["result"] == "yes" else 0.0
        (ROOT / "cache" / f"s11_settlements_{season}.json").write_text(json.dumps(res))
    elif (ROOT / "cache" / f"s11_settlements_{season}.json").exists():
        res = json.loads((ROOT / "cache" / f"s11_settlements_{season}.json").read_text())
    for x in trades:
        y = res.get(x["ticker"])
        if y is not None:
            won = (y == 1.0) == (x["side"] == "yes")
            x["pnl_per_contract_c"] = 100 * ((1.0 if won else 0.0) - x["ask"]) - 100 * x["fee"] / x["contracts"]
            x["pnl_trade_dollars"] = x["contracts"] * ((1.0 if won else 0.0) - x["ask"]) - x["fee"]
    out = summarize(trades, dict(blocked), look)
    out.update(n_matches=len(vlr), n_mapped=len(fmap), season_start=season_start.isoformat(), window_end=end.isoformat())
    return {"summary": out, "trades": trades}


# ------------------------------------------------------------------------------ 2026 backtest (power inputs)
def run_backtest_2026() -> dict:
    from research import pinnacle as PN  # noqa: PLC0415
    from research import stale_hist as SH  # noqa: PLC0415
    ms, _, kal = SH.load_all()
    mp = json.loads((SH.H.CACHE / "mapping.json").read_text())
    trades, blocked = [], defaultdict(int)
    for m in ms:
        f, kq = mp["oddspapi"].get(str(m["match_id"])), kal.get(m["match_id"])
        h = PN.load(f["fixtureId"]) if f else None
        if not h or kq is None or not kq.t:
            continue
        s_by = {meth: PN.series(h, f["p1_is_team1"], method=meth) for meth in (PRIMARY_DEVIG, *OTHER_DEVIG)}
        s = s_by[PRIMARY_DEVIG]
        if s is None:
            continue
        t0 = max(kq.t[0], s.t[0]).replace(second=0, microsecond=0)
        times, t = [], t0
        while t < m["start"]:
            times.append(t)
            t += CADENCE_BACKTEST

        def at(t, kq=kq):
            b, a = kq.at(t)
            return (b, None, a, None) if b is not None and a is not None and 0 < b < a <= 1 else None
        tr, bl = entries(times, at, s, m["start"])
        for k_, v in bl.items():
            blocked[k_] += v
        for x in tr:
            x.update(match_id=m["match_id"], event=m["event"], start=m["start"].isoformat())
        score(tr, s_by, m["start"], m["y"], kq.mid(m["start"] - timedelta(minutes=1)))
        trades += tr
    out = summarize(trades, dict(blocked), 1)
    out["note"] = "2026 backtest: candle quotes sampled every 15 min, displayed size unknown (treated as UNIT)"
    out["by_window"] = {}
    starts = sorted(datetime.fromisoformat(x["start"]) for x in trades)
    out["season_start_2026"] = min(m["start"] for m in ms).isoformat()
    ss = min(m["start"] for m in ms)
    out["n_trades_first_42_days"] = sum(1 for t in starts if t <= ss + timedelta(days=42))
    out["n_trades_to_jun30"] = sum(1 for t in starts if t <= datetime(2026, 6, 30, tzinfo=timezone.utc))
    out["n_events"] = len({x["event"] for x in trades})
    out["event_boot_primary"] = SH.boot([x for x in trades if x[f"net_clv_{PRIMARY_DEVIG}_pts"] is not None],
                                        lambda rs: float(np.mean([r[f"net_clv_{PRIMARY_DEVIG}_pts"] for r in rs])))
    return {"summary": out, "trades": trades}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2027)
    ap.add_argument("--look", type=int, choices=(1, 2), default=1)
    ap.add_argument("--fetch", action="store_true", help="OddsPapi fixtures/history (cap oddspapi_prereg) + Kalshi settlement")
    ap.add_argument("--backtest-2026", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.backtest_2026:
        res = run_backtest_2026()
        out = Path(a.out or ROOT / "out" / "s11_backtest_2026.json")
    else:
        res = run_2027(a.season, a.look, a.fetch)
        out = Path(a.out or ROOT / "out" / f"prereg_s11_{a.season}_look{a.look}.json")
    out.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res.get("summary", res), indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
