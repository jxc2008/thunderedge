"""Parse a cached vlr.gg match overview page into plain dicts.

Team names and ids come from the match header (``/team/<id>/<slug>``), never
from the URL slug — the slug-derived names were the source of contamination
like "Furia Champions Tour 2024 Amer" in the old moneyline table.
"""
from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup, Tag

_TEAM_RE = re.compile(r"^/team/(\d+)/")
_PLAYER_RE = re.compile(r"^/player/(\d+)/")
_EVENT_RE = re.compile(r"^/event/(\d+)/([^/?#]+)")


def _txt(el: Tag | None) -> str:
    return el.get_text(" ", strip=True) if el else ""


def _num(s: str) -> float | None:
    s = s.replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _side_val(cell: Tag | None, side: str = "mod-both") -> float | None:
    if cell is None:
        return None
    el = cell.select_one(f".side.{side}") or cell
    return _num(_txt(el))


def parse(html: str, match_url: str) -> dict:
    s = BeautifulSoup(html, "lxml")
    out: dict = {"match_url": match_url, "match_id": int(match_url.strip("/").split("/")[0])}

    ev = s.select_one("a.match-header-event")
    m = _EVENT_RE.match(ev["href"]) if ev else None
    out["event_id"] = int(m[1]) if m else None
    out["event_slug"] = m[2] if m else None
    out["series_text"] = re.sub(r"\s+", " ", _txt(s.select_one(".match-header-event-series")))
    ts = s.select_one(".match-header-date .moment-tz-convert[data-utc-ts]")
    out["date_utc"] = ts["data-utc-ts"] if ts else None

    teams = []
    for a in s.select(".match-header-vs a.match-header-link")[:2]:
        tm = _TEAM_RE.match(a.get("href", ""))
        name = _txt(a.select_one(".wf-title-med")) or _txt(a)
        # Sponsored names carry the base name in parentheses:
        # "VISA KRÜ (KRÜ Esports)", "JD Mall JDG Esports (JD Gaming)".
        pm = re.match(r"^(.*?)\s*\(([^()]+)\)\s*$", name or "")
        teams.append({"id": int(tm[1]) if tm else None, "name": name,
                      "alt": pm[2].strip() if pm else None})
    while len(teams) < 2:
        teams.append({"id": None, "name": None})
    out["team1"], out["team2"] = teams

    sc = re.search(r"(\d+)\s*:\s*(\d+)", _txt(s.select_one(".match-header-vs-score .js-spoiler"))
                   or _txt(s.select_one(".match-header-vs-score")))
    out["team1_maps"], out["team2_maps"] = (int(sc[1]), int(sc[2])) if sc else (None, None)
    # Veto: "NRG ban Split; LOUD ban Ascent; NRG pick Abyss; ...; Lotus remains".
    # Pre-match map pool (play order) = picks in order, then the remaining decider.
    veto = " ".join(_txt(n) for n in s.select(".match-header-note"))
    out["veto_text"] = veto or None
    pool = re.findall(r"\bpick ([A-Za-z]+)", veto) + re.findall(r"([A-Za-z]+) remains", veto)
    out["map_pool"] = pool or None
    notes = [_txt(n) for n in s.select(".match-header-vs-note")]
    out["status"] = notes[0].lower() if notes else None
    bo = next((n for n in notes if re.match(r"Bo\d", n)), None)
    out["best_of"] = int(bo[2:]) if bo else None
    if out["team1_maps"] is not None and out["team1_maps"] != out["team2_maps"]:
        out["winner"] = 1 if out["team1_maps"] > out["team2_maps"] else 2
    else:
        out["winner"] = None

    # Odds widget. Post-match pages show only the winner's price ("mod-post-odds").
    odds = []
    for b in s.select("a.match-bet-item"):
        txt = _txt(b)
        if "odds" not in txt:
            continue
        img = b.select_one("img")
        book = None
        if img is not None:
            cls = [c for c in img.get("class", []) if c.startswith("mod-")]
            book = cls[0][4:] if cls else (img.get("src", "").rsplit("/", 1)[-1].split(".")[0] or None)
        team = _txt(b.select_one(".match-bet-item-return-msg .match-bet-item-teamzzz"))
        val = _txt(b.select_one(".match-bet-item-return-short .match-bet-item-odds"))
        odds.append({
            "book": book,
            "team_name": team or None,
            "odds": _num(val) if val else None,
            "post": "mod-post-odds" in b.get("class", []),
            "raw": txt[:200],
        })
    out["odds"] = odds

    maps = []
    for g in s.select(".vm-stats-game"):
        gid = g.get("data-game-id")
        if not gid or gid == "all":
            continue
        hdr = g.select_one(".vm-stats-game-header")
        if hdr is None:
            continue
        mp = hdr.select_one(".map-name span") or hdr.select_one(".map")
        map_name = (mp.find(string=True, recursive=False) or "").strip() if mp else ""
        pick = hdr.select_one(".picked")
        picked_by = None
        if pick is not None:
            picked_by = 1 if "mod-1" in pick.get("class", []) else 2 if "mod-2" in pick.get("class", []) else None
        tdivs = hdr.select(".team")
        side_scores = []
        for td in tdivs[:2]:
            d = {k: None for k in ("t", "ct", "ot")}
            for k in d:
                el = td.select_one(f"span.mod-{k}")
                d[k] = int(_txt(el)) if el and _txt(el).isdigit() else None
            side_scores.append(d)
        scores = [int(_txt(x)) if _txt(x).isdigit() else None for x in hdr.select(".score")[:2]]
        rounds = []
        for col in g.select(".vlr-rounds-row-col"):
            num = col.select_one(".rnd-num")
            if num is None or not _txt(num).isdigit():
                continue
            sq = col.select(".rnd-sq")
            if len(sq) < 2:
                continue
            w = 1 if "mod-win" in sq[0].get("class", []) else 2 if "mod-win" in sq[1].get("class", []) else None
            if w is None:
                continue
            wcls = sq[w - 1].get("class", [])
            side = "atk" if "mod-t" in wcls else "def" if "mod-ct" in wcls else None
            rounds.append({"round": int(_txt(num)), "winner": w, "winner_side": side})
        players = []
        for ti, tb in enumerate(g.select(".ovw-table")[:2], start=1):
            for row in tb.select(".ovw-row"):
                if "mod-head" in row.get("class", []):
                    continue
                a = row.select_one('a[href^="/player/"]')
                if a is None:
                    continue
                pm = _PLAYER_RE.match(a["href"])
                ag = row.select_one(".mod-agents img")
                cell = {c.get("data-col"): c for c in row.select("[data-col]")}
                players.append({
                    "team_idx": ti,
                    "player_id": int(pm[1]) if pm else None,
                    "player_name": _txt(a.select_one(".ovw-player-name")) or _txt(a),
                    "team_tag": _txt(a.select_one(".ovw-player-tag")),
                    "agent": ag.get("alt") if ag else None,
                    **{k: _side_val(cell.get(k)) for k in
                       ("rating2", "acs", "kills", "deaths", "assists", "kast", "adr", "fb", "fd")},
                })
        maps.append({
            "game_id": int(gid), "map_name": map_name, "picked_by": picked_by,
            "team1_score": scores[0] if scores else None,
            "team2_score": scores[1] if len(scores) > 1 else None,
            "team1_sides": side_scores[0] if side_scores else {},
            "team2_sides": side_scores[1] if len(side_scores) > 1 else {},
            "rounds": rounds, "players": players,
        })
    out["maps"] = maps
    return out


def team1_start_side(m: dict) -> str | None:
    """'atk'/'def' for team1 on round 1, inferred from the round-1 winner's side."""
    r1 = next((r for r in m["rounds"] if r["round"] == 1), None)
    if r1 is None or r1["winner_side"] is None:
        return None
    if r1["winner"] == 1:
        return r1["winner_side"]
    return "def" if r1["winner_side"] == "atk" else "atk"


if __name__ == "__main__":
    import json
    import sys

    from research import vlr_fetch as v

    url = sys.argv[1]
    d = parse(v.get(url), url)
    for mp in d["maps"]:
        mp["n_rounds"] = len(mp.pop("rounds"))
        mp["n_players"] = len(mp.pop("players"))
    print(json.dumps(d, indent=1, default=str)[:3000])
    _ = datetime
