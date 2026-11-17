"""Post-result trigger of the odds logger, offline (synthetic pages, no network)."""
from pathlib import Path

import requests

from research import odds_logger as L

FX = Path(__file__).parent / "fixtures"


def _list(items):
    body = "".join(
        f'<a class="match-item" href="/{mid}/x"><div class="match-item-vs-team-name"><div class="text-of">{t1}</div></div>'
        f'<div class="match-item-vs-team-name"><div class="text-of">{t2}</div></div>'
        f'<div class="ml-status">{st}</div><div class="match-item-event">VCT 2027: Test Kickoff</div></a>'
        for mid, t1, t2, st in items)
    return f"<html><body>{body}</body></html>"


class _Resp:
    def __init__(self, text):
        self.text = text


def test_post_result_trigger(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "DB", tmp_path / "snap.db")
    monkeypatch.setattr(L, "MIN_INTERVAL", 0.0)
    pages = {}
    match_html = (FX / "synthetic_prematch_current.html").read_text(encoding="utf-8")

    def fake_get(self, url, **kw):
        self.n += 1
        if "/matches" in url:
            return _Resp(pages["list"])
        return _Resp(match_html)

    def no_kalshi(*a, **k):
        raise requests.ConnectionError("offline test")

    monkeypatch.setattr(L.Fetcher, "get", fake_get)
    monkeypatch.setattr(L.requests, "get", no_kalshi)
    pages["list"] = _list([(1001, "Alpha Squad", "Beta Club", "LIVE"), (1002, "Beta Club", "Gamma Five", "Upcoming"),
                           (1003, "Delta Unit", "Omega", "Upcoming")])
    L.poll()
    pages["list"] = _list([(1002, "Beta Club", "Gamma Five", "Upcoming"), (1003, "Delta Unit", "Omega", "Upcoming")])
    L.poll()
    import sqlite3
    con = sqlite3.connect(L.DB)
    done = con.execute("SELECT match_key FROM match_status WHERE completed_ts IS NOT NULL").fetchall()
    assert done == [("vlr:1001",)]
    trig = con.execute("""SELECT DISTINCT match_key, ref_match FROM odds_snapshots
                          WHERE trigger='post_result'""").fetchall()
    assert trig == [("vlr:1002", "vlr:1001")]  # Beta Club's next match, not Delta's
