"""Windowed Pinnacle-open poll: pending-window logic and the 30-day ledger cap, offline."""
import sqlite3
from datetime import datetime, timezone

from research import hist_fetch as H
from research import odds_logger as L
from research import pinnacle_open_poll as P
from research.timeutil import utc_to_vlr


def test_pending_window(tmp_path):
    con = sqlite3.connect(tmp_path / "s.db")
    con.executescript(L.SCHEMA)
    for c in ("trigger", "ref_match"):
        con.execute(f"ALTER TABLE odds_snapshots ADD COLUMN {c} TEXT")
    now = datetime(2027, 1, 10, 12, tzinfo=timezone.utc)
    starts = {"vlr:1": 20, "vlr:2": 40, "vlr:3": 3, "vlr:4": 30, "vlr:5": 20}  # hours from now
    for k, h in starts.items():
        ev = "VCT 2027: Americas Kickoff - Brazil Qualifier" if k == "vlr:5" else "VCT 2027: EMEA Kickoff"
        con.execute("INSERT INTO match_status(match_key,url,event,team1,team2,status) VALUES (?,?,?,?,?, 'upcoming')",
                    (k, "/" + k[4:], ev, "A", "B"))
        t = datetime.fromtimestamp(now.timestamp() + h * 3600, timezone.utc)
        con.execute("INSERT INTO odds_snapshots(ts_utc,source,match_key,start_utc) VALUES (?,?,?,?)",
                    (now.isoformat(), "vlr", k, utc_to_vlr(t).strftime("%Y-%m-%d %H:%M:%S")))
    got = P.pending_matches(con, now, 36, 6, caught={"vlr:4"})
    assert set(got) == {"vlr:1"}  # 2 too far, 3 past the late edge, 4 caught, 5 qualifier


def test_live_cap_is_rolling_30d(tmp_path, monkeypatch):
    led = tmp_path / "ledger.csv"
    old = "2020-01-01T00:00:00+00:00"
    new = datetime.now(timezone.utc).isoformat(timespec="seconds")
    led.write_text("".join(f"{old},oddspapi_live,u,200\n" for _ in range(500)) + f"{new},oddspapi_live,u,200\n")
    monkeypatch.setattr(H, "LEDGER", led)
    assert H.used_30d("oddspapi_live") == 1
    assert H.used("oddspapi_live") == 501
