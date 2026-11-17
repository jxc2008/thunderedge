"""Match / map level analysis frames built from data/valorant_stats.db research tables.

Market probability sources (column `mkt_src`):
  two_sided    Thunderpick both prices from a Wayback pre-match snapshot (exact de-vig)
  winner_only  only the winner's post-match Thunderpick price; the loser is reconstructed with
               an ASSUMED overround V. Because the observed side is the winner, any error in V
               moves p_fair toward/away from the realised outcome -> regressions that use p_fair
               as a feature on these rows are reported only as V-sensitivity bands.
ROI at actual odds is exact on winner-only rows: a winning bet's price is always the
observed one, a losing bet costs 1 unit whatever its price.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

DB = Path(__file__).resolve().parent.parent / "data" / "valorant_stats.db"
TEST_SEASONS = (2024, 2025, 2026)  # 2023 is scraped only as the churn baseline


def _con(db: Path | str = DB) -> sqlite3.Connection:
    return sqlite3.connect(db)


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def overround_table(db=DB) -> pd.DataFrame:
    """Two-sided Thunderpick snapshots: overround and hours before start."""
    q = """SELECT match_id, MAX(hours_before) hours_before, SUM(1.0/odds) overround, COUNT(*) n
           FROM prematch_odds WHERE book='thunderpick' GROUP BY match_id HAVING n=2"""
    return pd.read_sql(q, _con(db))


def lineups(db=DB) -> pd.DataFrame:
    """One modal starting five per (match, team)."""
    lu = pd.read_sql("""SELECT l.match_id, l.team_id, l.p1,l.p2,l.p3,l.p4,l.p5, m.date_utc,
                               m.event_id, m.season
                        FROM lineups l JOIN research_matches m USING(match_id)""", _con(db))
    lu["five"] = list(map(tuple, lu[["p1", "p2", "p3", "p4", "p5"]].values))
    g = (lu.groupby(["match_id", "team_id", "date_utc", "event_id", "season"])["five"]
         .agg(lambda s: Counter(s).most_common(1)[0][0]).reset_index())
    return g.sort_values("date_utc")


def churn(db=DB) -> pd.DataFrame:
    """churn_season: share of the five not in the team's LAST lineup of the previous season.
    churn_event: same vs the team's last lineup at its previous event."""
    g = lineups(db)
    rows = []
    for tid, t in g.groupby("team_id"):
        t = t.sort_values("date_utc")
        last_by_season = t.groupby("season").tail(1).set_index("season")["five"].to_dict()
        hist = []  # (date, event_id, five)
        for r in t.itertuples():
            prev_s = last_by_season.get(r.season - 1)
            cs = (1 - len(set(r.five) & set(prev_s)) / 5) if prev_s else np.nan
            prev_ev = [h for h in hist if h[1] != r.event_id]
            ce = (1 - len(set(r.five) & set(prev_ev[-1][2])) / 5) if prev_ev else np.nan
            rows.append((r.match_id, tid, cs, ce))
            hist.append((r.date_utc, r.event_id, r.five))
    return pd.DataFrame(rows, columns=["match_id", "team_id", "churn_season", "churn_event"])


def matches(db=DB, overround: float = 1.06) -> pd.DataFrame:
    con = _con(db)
    m = pd.read_sql("""SELECT m.*, e.slug event_slug, t1.home_region home1, t2.home_region home2
                       FROM research_matches m JOIN events e USING(event_id)
                       JOIN teams t1 ON t1.team_id=m.team1_id JOIN teams t2 ON t2.team_id=m.team2_id
                       WHERE m.winner_id IS NOT NULL""", con)
    m = m[m.home1.notna() & m.home2.notna()].copy()  # drop showmatch / all-star sides
    m["y1"] = (m.winner_id == m.team1_id).astype(int)
    ts = pd.read_sql("""SELECT match_id, team_id, odds, hours_before FROM prematch_odds
                        WHERE book='thunderpick'""", con)
    ts = ts.groupby("match_id").filter(lambda d: len(d) == 2)
    wo = pd.read_sql("""SELECT match_id, team_id, odds FROM match_odds
                        WHERE book='thunderpick' AND observed_side='winner'""", con)
    m = m.merge(wo.rename(columns={"team_id": "wo_team", "odds": "winner_odds"}), on="match_id", how="left")
    o1 = ts.merge(m[["match_id", "team1_id"]], left_on=["match_id", "team_id"],
                  right_on=["match_id", "team1_id"])[["match_id", "odds", "hours_before"]]
    o2 = ts.merge(m[["match_id", "team2_id"]], left_on=["match_id", "team_id"],
                  right_on=["match_id", "team2_id"])[["match_id", "odds"]]
    m = m.merge(o1.rename(columns={"odds": "ts_o1"}), on="match_id", how="left")
    m = m.merge(o2.rename(columns={"odds": "ts_o2"}), on="match_id", how="left")
    m = add_market(m, overround)
    ch = churn(db)
    for k in (1, 2):
        m = m.merge(ch.rename(columns={"team_id": f"team{k}_id", "churn_season": f"churn_season{k}",
                                       "churn_event": f"churn_event{k}"}),
                    on=["match_id", f"team{k}_id"], how="left")
    m["churn_max"] = m[["churn_season1", "churn_season2"]].max(axis=1, skipna=False)
    m["churn_event_max"] = m[["churn_event1", "churn_event2"]].max(axis=1, skipna=False)
    m["wk_bucket"] = pd.cut(m.weeks_since_season_start, [-1, 6, 16, 1e9], labels=["0-6", "7-16", "17+"])
    return m


def add_market(m: pd.DataFrame, overround: float) -> pd.DataFrame:
    """p1 (team1 fair prob), favourite identity and payout bookkeeping for a given V."""
    m = m.copy()
    two = m.ts_o1.notna() & m.ts_o2.notna()
    i1, i2 = 1 / m.ts_o1, 1 / m.ts_o2
    p_two = i1 / (i1 + i2)
    pw = (1 / m.winner_odds) / overround
    p_wo = np.where(m.wo_team == m.team1_id, pw, 1 - pw)
    m["p1"] = np.where(two, p_two, np.where(m.winner_odds.notna(), p_wo, np.nan))
    m["mkt_src"] = np.where(two, "two_sided", np.where(m.winner_odds.notna(), "winner_only", "none"))
    # favourite: two-sided -> lower price; winner-only -> winner was fav iff o_w < 2/V.
    # Ambiguous band: o_w in (2/1.08, 2/1.04) flips with any plausible V -> excluded from fav/dog tests.
    amb = (~two) & m.winner_odds.between(2 / 1.08, 2 / 1.04)
    m["fav_ambiguous"] = amb
    m["fav_is_1"] = m.p1 > 0.5
    m["p_fav"] = np.where(m.fav_is_1, m.p1, 1 - m.p1)
    m["y_fav"] = np.where(m.fav_is_1, m.y1, 1 - m.y1).astype(float)
    m.loc[m.p1.isna(), ["p_fav", "y_fav"]] = np.nan
    for c in ("p1", "p_fav", "y_fav"):
        m[c] = m[c].astype(float)
    return m


def bet_pnl(m: pd.DataFrame, on_team1: pd.Series) -> pd.Series:
    """Flat 1-unit stake P&L at the actual (post-match = closing) Thunderpick price.
    Exact: if our side won, its price is the observed winner price; else -1."""
    won = np.where(on_team1, m.y1 == 1, m.y1 == 0)
    return pd.Series(np.where(won, m.winner_odds - 1.0, -1.0), index=m.index).where(m.winner_odds.notna())


def maps_frame(db=DB, overround: float = 1.06) -> pd.DataFrame:
    mt = matches(db, overround)
    mp = pd.read_sql("SELECT * FROM map_results WHERE team1_score IS NOT NULL", _con(db))
    mp = mp.merge(mt, on="match_id", suffixes=("", "_m"))
    mp["rd1"] = mp.team1_score - mp.team2_score
    mp["ot"] = (mp.team1_score + mp.team2_score) > 24
    return mp


def cluster_boot(df: pd.DataFrame, fn, n: int = 2000, seed: int = 0, cluster: str = "event_id"):
    """Percentile CI for fn(df) resampling clusters (events) with replacement."""
    rng = np.random.default_rng(seed)
    groups = {k: g for k, g in df.groupby(cluster)}
    keys = np.array(list(groups))
    est = fn(df)
    draws = []
    for _ in range(n):
        pick = rng.choice(keys, size=len(keys), replace=True)
        try:
            draws.append(fn(pd.concat([groups[k] for k in pick], ignore_index=True)))
        except Exception:  # noqa: BLE001 — degenerate resample (e.g. singular fit)
            continue
    d = np.array(draws, dtype=float)
    if d.ndim == 1:
        d = d[np.isfinite(d)]
        return est, float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5)), len(d)
    lo, hi = np.nanpercentile(d, 2.5, axis=0), np.nanpercentile(d, 97.5, axis=0)
    return est, lo, hi, len(d)
