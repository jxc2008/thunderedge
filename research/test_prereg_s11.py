"""PREREG §11 frozen code, offline: fee rounding, the entry rule, and an end-to-end run on a synthetic logger DB."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

from research import odds_logger as L
from research import pinnacle as PN
from research import pinnacle_open_poll as P
from research import prereg_s11 as S
from research.timeutil import utc_to_vlr

T0 = datetime(2027, 1, 20, 12, tzinfo=timezone.utc)


def test_fee_rounds_up_per_order():
    assert S.fee_dollars(100, 0.5) == 1.75
    assert S.fee_dollars(1, 0.5) == 0.02
    assert S.fee_dollars(10, 0.2) == 0.12  # 0.07*10*0.16 = 0.112 -> 0.12


def _series(times, p1, ok=True):
    return PN.Series(list(times), list(p1), [True] * len(times), [ok] * len(times))


def test_entry_rule_threshold_age_size():
    start = T0 + timedelta(hours=10)
    s = _series([T0, T0 + timedelta(hours=2)], [0.60, 0.60])
    times = [T0 + timedelta(minutes=10), T0 + timedelta(hours=1), T0 + timedelta(hours=2, minutes=5)]
    # yes ask 0.54 (edge 6 > 5) at every time; size 3 contracts
    tr, bl = S.entries(times, lambda t: (0.50, 10.0, 0.54, 3.0), s, start)
    assert len(tr) == 1 and tr[0]["t"] == times[0].isoformat() and tr[0]["contracts"] == 3
    # Pinnacle record 60 min old at the second time -> blocked; first time only 10 min old -> entry
    tr2, bl2 = S.entries(times[1:2], lambda t: (0.50, 10.0, 0.54, 3.0), s, start)
    assert tr2 == [] and bl2["pinnacle_older_than_15min"] == 1
    # edge exactly 5 pts -> no entry (strict >)
    assert S.entries(times[:1], lambda t: (0.50, 10.0, 0.55, 3.0), s, start)[0] == []
    # no displayed size -> blocked
    tr3, bl3 = S.entries(times[:1], lambda t: (0.50, 10.0, 0.54, 0.0), s, start)
    assert tr3 == [] and bl3["no_displayed_size"] == 1


def test_run_2027_end_to_end(tmp_path, monkeypatch):
    db = tmp_path / "snap.db"
    con = sqlite3.connect(db)
    con.executescript(L.SCHEMA)
    for c in ("trigger", "ref_match"):
        con.execute(f"ALTER TABLE odds_snapshots ADD COLUMN {c} TEXT")
    start = T0 + timedelta(hours=24)
    con.execute("INSERT INTO match_status(match_key,url,event,team1,team2,status) VALUES ('vlr:9','/9/x',"
                "'VCT 2027: EMEA Kickoff','Team Heretics','Fnatic','upcoming')")
    con.execute("INSERT INTO odds_snapshots(ts_utc,source,match_key,start_utc) VALUES (?,?,?,?)",
                (T0.isoformat(), "vlr", "vlr:9", utc_to_vlr(start).strftime("%Y-%m-%d %H:%M:%S")))
    polls = [T0 + timedelta(minutes=15 * i) for i in range(8)]
    for t in polls:
        ts = t.isoformat(timespec="seconds")
        con.execute("INSERT INTO poll_log VALUES (?,?,?,?,?,?)", (ts, 1, 5, 1, 1, None))
        con.execute("INSERT INTO odds_snapshots(ts_utc,source,match_key,match_url,event,start_utc,team) VALUES (?,?,?,?,?,?,?)",
                    (ts, "kalshi", "kalshi:KXVALORANTGAME-27JAN21TH", "KXVALORANTGAME-27JAN21TH-TH", "KXVALORANTGAME",
                     start.isoformat().replace("+00:00", "Z"), "Team Heretics"))
    # book: best NO bid 0.48 x 40 -> YES ask 0.52; YES bid 0.47 (stored once, change-only)
    con.execute("INSERT INTO kalshi_books VALUES (?,?,?,?,?,?,?)", (polls[0].isoformat(timespec="seconds"),
                "KXVALORANTGAME-27JAN21TH-TH", "KXVALORANTGAME-27JAN21TH", "KXVALORANTGAME", None,
                json.dumps([[0.47, 25.0]]), json.dumps([[0.48, 40.0]])))
    con.commit()
    # Pinnacle: records every 10 min, team 1 at odds 1.55 / 2.55 (Shin ~ 0.62), close the same
    hist_dir = tmp_path / "hist"
    hist_dir.mkdir()
    recs = [T0 - timedelta(hours=1) + timedelta(minutes=10 * i) for i in range(160)]

    def side(price):
        return [{"createdAt": t.isoformat().replace("+00:00", "Z"), "price": price, "limit": 500, "active": True}
                for t in recs]
    hist = {"bookmakers": {"pinnacle": {"markets": {"611": {"outcomes": {"611": {"players": {"0": side(1.55)}},
                                                                         "612": {"players": {"0": side(2.55)}}}}}}}}
    (hist_dir / "op_hist_FX1.json").write_text(json.dumps(hist))
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"fixtures": {"FX1": {"match_key": "vlr:9", "p1_is_team1": True, "tournamentId": 1}}}))
    monkeypatch.setattr(S, "SNAP", db)
    monkeypatch.setattr(PN, "CACHE", hist_dir)
    monkeypatch.setattr(P, "STATE", state)
    monkeypatch.setattr("research.hist_fetch.fixtures", lambda fetch: [])
    res = S.run_2027(2027, 1, fetch=False)
    tr = res["trades"]
    assert len(tr) == 1 and tr[0]["side"] == "yes" and abs(tr[0]["ask"] - 0.52) < 1e-9 and tr[0]["contracts"] == 40
    p_close = tr[0]["fair"]
    assert abs(tr[0]["net_clv_shin_pts"] - (100 * (p_close - 0.52) - 100 * S.fee_dollars(40, 0.52) / 40)) < 1e-9
    assert res["summary"]["n_matches"] == 1 and res["summary"]["primary_net_clv_pts"]["n"] == 1
