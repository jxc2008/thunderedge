"""Unit tests for the odds bookkeeping every result depends on. Run: python -m pytest research"""
import math

import numpy as np
import pandas as pd

from research import features as F
from research.odds_logger import parse_match_odds
from pathlib import Path


def _frame(**cols):
    base = dict(team1_id=[1], team2_id=[2], y1=[1], ts_o1=[np.nan], ts_o2=[np.nan],
                winner_odds=[np.nan], wo_team=[np.nan])
    base.update(cols)
    return pd.DataFrame(base)


def test_two_sided_devig():
    m = F.add_market(_frame(ts_o1=[2.40], ts_o2=[1.53], y1=[0], winner_odds=[1.53], wo_team=[2]), 1.06)
    i1, i2 = 1 / 2.40, 1 / 1.53
    assert math.isclose(m.p1[0], i1 / (i1 + i2))
    assert m.mkt_src[0] == "two_sided" and not m.fav_is_1[0] and m.y_fav[0] == 1.0


def test_winner_only_reconstruction_uses_overround():
    m = F.add_market(_frame(winner_odds=[1.50], wo_team=[1]), 1.06)
    assert math.isclose(m.p1[0], (1 / 1.50) / 1.06)
    m2 = F.add_market(_frame(winner_odds=[3.00], wo_team=[2], y1=[0]), 1.06)
    assert math.isclose(m2.p1[0], 1 - (1 / 3.0) / 1.06)
    assert m2.fav_is_1[0] and m2.y_fav[0] == 0.0  # the dog won


def test_ambiguity_band():
    for o, amb in ((1.80, False), (1.88, True), (1.95, False)):
        assert bool(F.add_market(_frame(winner_odds=[o], wo_team=[1]), 1.06).fav_ambiguous[0]) is amb


def test_bet_pnl_exact():
    m = F.add_market(_frame(winner_odds=[3.30], wo_team=[2], y1=[0]), 1.06)
    assert F.bet_pnl(m, pd.Series([False]))[0] == 3.30 - 1  # backed team2, it won at 3.30
    assert F.bet_pnl(m, pd.Series([True]))[0] == -1.0        # backed team1, it lost


def test_prematch_fixture_parses_two_sided():
    html = (Path(__file__).parent / "fixtures" / "synthetic_prematch_current.html").read_text(encoding="utf-8")
    _, rows = parse_match_odds(html)
    tp = {r["team"]: r["odds"] for r in rows if r["book"] == "thunderpick" and r["status"] == "pre"}
    assert tp == {"Alpha Squad": 2.40, "Beta Club": 1.53}


def test_old_layout_prematch_and_post():
    fx = Path(__file__).parent / "fixtures"
    _, rows = parse_match_odds((fx / "synthetic_prematch_old.html").read_text(encoding="utf-8"))
    gg = {r["team"]: r["odds"] for r in rows if r["book"] == "ggbet" and r["status"] == "pre"}
    assert gg == {"Gamma Five": 1.76, "Delta Unit": 1.99}
    _, rows = parse_match_odds((fx / "synthetic_post_old.html").read_text(encoding="utf-8"))
    assert [(r["team"], r["odds"], r["status"]) for r in rows] == [("Epsilon Esports", 2.00, "post")]
