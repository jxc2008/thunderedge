"""
Live Score Poller for VCT Eco/Anti-Eco Trading Strategy.

Data source (confirmed working):
  GET api.bo3.gg/api/v1/matches/{slug}  →  response.live_updates

live_updates fields (confirmed from live Challengers match 117117):
  team_1:
    side:             "DEFENDER" | "ATTACKER"
    game_score:       int  (rounds won this map)
    match_score:      int  (maps won this series)
    economy_level:    str | null  (e.g. "ECO", "SEMI_ECO", "FULL_BUY" — sometimes null)
    equipment_value:  int  (credit value of current loadout)
  team_2:  (same fields)
  map_name:     str  (e.g. "lotus")
  game_number:  int  (map number in series: 1, 2, 3)
  round_number: int  (current round, 1-indexed)
  round_phase:  str  ("BUY_TIME" | "COMBAT" | "END_OF_ROUND" | "GAME_ENDED")
  game_ended:   bool

Match discovery:
  VLR.gg /matches page → LIVE badge → team names + date
  → construct bo3.gg slug: {t1}-vs-{t2}-{DD}-{MM}-{YYYY}
  → verify with API call to bo3.gg

Trading logic:
  1. Poll each live match slug every 5s
  2. During BUY_TIME: classify both teams by equipment_value
  3. If one team is full-buy and the other is eco/semi-eco at high-leverage score → SIGNAL
  4. economy_level field also used when available (more precise than equipment threshold)

Equipment thresholds (Valorant credits):
  Full buy:  >= 20,000  (full rifles + armor + util)
  Semi-buy:  10,000-20,000
  Semi-eco:   5,000-10,000
  Eco:       <  5,000

Usage:
  python scraper/live_score_poller.py --test          # simulate
  python scraper/live_score_poller.py --probe         # show live matches
  python scraper/live_score_poller.py                 # live polling
  python scraper/live_score_poller.py --spread 4.0    # tighter spread filter
  python scraper/live_score_poller.py --kalshi        # live polling + auto-order on Kalshi
"""

import re
import json
import time
import logging
import argparse
import threading
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, date
import urllib.request
import urllib.error

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                    datefmt='%H:%M:%S')

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

BO3_API                = "https://api.bo3.gg/api/v1"
VALORANT_DISCIPLINE_ID = 2
VALORANT_WIN           = 13
HALF_BOUNDARY          = 12   # round 13 = start of second half
POLL_INTERVAL_DISCOVER = 60   # seconds between VLR.gg match scans
POLL_INTERVAL_SCORE    = 5    # seconds between per-match score refreshes

# Equipment value thresholds (Valorant credits)
EQUIP_FULL_BUY  = 20_000
EQUIP_SEMI_BUY  = 10_000
EQUIP_SEMI_ECO  =  5_000
# < EQUIP_SEMI_ECO → eco

# Gun advantage only fires a signal for these economy mismatches:
GUN_ECO_PAIRS = {
    ('full', 'eco'),
    ('full', 'semi-eco'),
    ('semi-buy', 'eco'),
}

GUN_WIN_RATE = 0.822   # empirical from backtest: gun team wins 82.2% of eco rounds

_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


# ─────────────────────────────────────────────────────────────────────────────
# Markov map-win probability table
# ─────────────────────────────────────────────────────────────────────────────

def _build_markov(p: float = 0.5) -> Dict[Tuple[int, int], float]:
    p_ot_tied   = (p**2) / (p**2 + (1 - p)**2)
    p_ot_ahead  = p + (1 - p) * p_ot_tied
    p_ot_behind = p * p_ot_tied

    from functools import lru_cache
    @lru_cache(maxsize=None)
    def prob(t1: int, t2: int) -> float:
        if t1 >= VALORANT_WIN and (t1 - t2) >= 2:
            return 1.0
        if t2 >= VALORANT_WIN and (t2 - t1) >= 2:
            return 0.0
        if t1 >= VALORANT_WIN - 1 and t2 >= VALORANT_WIN - 1:
            d = t1 - t2
            if d == 0:  return p_ot_tied
            if d == 1:  return p_ot_ahead
            if d == -1: return p_ot_behind
            return 1.0 if d > 0 else 0.0
        return p * prob(t1 + 1, t2) + (1 - p) * prob(t1, t2 + 1)

    return {(t1, t2): prob(t1, t2) for t1 in range(16) for t2 in range(16)}

MARKOV = _build_markov(0.5)


# ─────────────────────────────────────────────────────────────────────────────
# Economy classification
# ─────────────────────────────────────────────────────────────────────────────

def classify_economy(equipment_value: int, economy_level: Optional[str] = None) -> str:
    """
    Classify a team's economy as 'full', 'semi-buy', 'semi-eco', or 'eco'.
    Uses economy_level field when available (more precise), falls back to equipment threshold.
    """
    if economy_level:
        lvl = economy_level.upper()
        if 'FULL' in lvl:   return 'full'
        if 'SEMI_BUY' in lvl or 'HALF' in lvl: return 'semi-buy'
        if 'SEMI_ECO' in lvl or 'FORCE' in lvl: return 'semi-eco'
        if 'ECO' in lvl:    return 'eco'
        if 'PISTOL' in lvl: return 'pistol'

    ev = equipment_value or 0
    if ev >= EQUIP_FULL_BUY:  return 'full'
    if ev >= EQUIP_SEMI_BUY:  return 'semi-buy'
    if ev >= EQUIP_SEMI_ECO:  return 'semi-eco'
    return 'eco'


def gun_eco_advantage(econ1: str, econ2: str) -> Optional[int]:
    """Return which team (1 or 2) has gun advantage, or None if no clear mismatch."""
    if (econ1, econ2) in GUN_ECO_PAIRS:
        return 1   # team1 is gun team
    if (econ2, econ1) in GUN_ECO_PAIRS:
        return 2   # team2 is gun team
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Signal evaluation
# ─────────────────────────────────────────────────────────────────────────────

def _eco_adj_fv(t1: int, t2: int, gun_team: int,
                p_gun: float = GUN_WIN_RATE) -> Tuple[float, float]:
    """
    Return (eco_adj_fv_for_gun_team, neutral_fv_for_gun_team).
    eco_adj_fv: expected map win P for gun team given they win this round with prob p_gun.
    """
    if gun_team == 1:
        fv_win  = MARKOV.get((min(t1 + 1, 15), t2), 1.0)
        fv_lose = MARKOV.get((t1, min(t2 + 1, 15)), 0.0)
        neutral = MARKOV.get((t1, t2), 0.5)
    else:
        fv_win  = 1 - MARKOV.get((t1, min(t2 + 1, 15)), 0.0)
        fv_lose = 1 - MARKOV.get((min(t1 + 1, 15), t2), 1.0)
        neutral = 1 - MARKOV.get((t1, t2), 0.5)

    eco_adj = p_gun * fv_win + (1 - p_gun) * fv_lose
    return eco_adj, neutral


def evaluate_signal(t1_score: int, t2_score: int, gun_team: int,
                    gun_name: str, eco_name: str,
                    match_id: int, map_number: int, map_name: str,
                    team1_name: str, team2_name: str,
                    is_map3: bool, round_num: int,
                    max_spread: float = 8.0) -> Optional['TradingSignal']:
    """
    Evaluate whether the current gun/eco mismatch at this score state
    produces positive taker EV. Returns a TradingSignal or None.
    """
    eco_fv, neutral_fv = _eco_adj_fv(t1_score, t2_score, gun_team)
    delta_cents = (eco_fv - neutral_fv) * 100

    # Taker round-trip cost: entry (half spread) + exit (quarter spread) + fee
    round_trip = max_spread / 2 + max_spread / 4 + 0.5
    taker_ev = delta_cents - round_trip

    if taker_ev <= 0:
        log.debug(f"  No signal: {t1_score}-{t2_score} R{round_num} delta={delta_cents:.2f}c EV={taker_ev:.2f}c")
        return None

    if is_map3:
        kalshi_hint = f"BUY {gun_name} MAP3 (= MATCH WINNER) | delta +{delta_cents:.1f}c, EV +{taker_ev:.1f}c"
    else:
        kalshi_hint = f"BUY {gun_name} MAP{map_number} winner | delta +{delta_cents:.1f}c, EV +{taker_ev:.1f}c"

    return TradingSignal(
        timestamp      = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        match_id       = match_id,
        map_number     = map_number,
        map_name       = map_name,
        team1_name     = team1_name,
        team2_name     = team2_name,
        score          = f"{t1_score}-{t2_score}",
        round_num      = round_num,
        gun_team       = gun_team,
        gun_team_name  = gun_name,
        eco_team_name  = eco_name,
        map_fv_neutral = neutral_fv,
        map_fv_eco_adj = eco_fv,
        eco_delta      = delta_cents,
        taker_ev       = taker_ev,
        is_map3        = is_map3,
        kalshi_hint    = kalshi_hint,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TradingSignal:
    timestamp:      str
    match_id:       int
    map_number:     int
    map_name:       str
    team1_name:     str
    team2_name:     str
    score:          str
    round_num:      int
    gun_team:       int
    gun_team_name:  str
    eco_team_name:  str
    map_fv_neutral: float
    map_fv_eco_adj: float
    eco_delta:      float
    taker_ev:       float
    is_map3:        bool
    kalshi_hint:    str


@dataclass
class MatchTracker:
    """Per-match tracking state."""
    bo3_slug:     str
    vlr_id:       int
    team1_name:   str
    team2_name:   str
    last_round:   int = 0
    last_phase:   str = ''
    signal_fired: Dict[int, bool] = field(default_factory=dict)  # round_num -> fired


# ─────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_json(url: str, timeout: int = 12) -> Optional[dict]:
    req = urllib.request.Request(url, headers={'User-Agent': _UA, 'Accept': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        log.debug(f"HTTP {e.code}: {url}")
        return None
    except Exception as e:
        log.debug(f"Request failed {url}: {e}")
        return None


def _fetch_html(url: str, timeout: int = 12) -> Optional[str]:
    req = urllib.request.Request(url, headers={'User-Agent': _UA, 'Accept': 'text/html'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        log.debug(f"HTML fetch failed {url}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# VLR.gg live match discovery
# ─────────────────────────────────────────────────────────────────────────────

def scrape_vlr_live_matches() -> List[dict]:
    """
    Scrape vlr.gg/matches for LIVE-badged matches.
    Returns list with: vlr_id, team1, team2, event, url, match_date (YYYY-MM-DD).

    HTML structure (confirmed from live match 2026-04-09):
      <a class="wf-module-item match-item ...">
        <div class="match-item-vs-team-name">TeamName</div>
        <div class="match-item-eta">
          <div class="ml mod-live"><div class="ml-status">LIVE</div></div>
        </div>
      </a>
    """
    html = _fetch_html("https://www.vlr.gg/matches")
    if not html:
        return []
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log.warning("BeautifulSoup not installed; VLR discovery unavailable")
        return []

    soup = BeautifulSoup(html, 'html.parser')
    live_matches = []

    for item in soup.select('a.wf-module-item.match-item'):
        href = item.get('href', '')
        m = re.match(r'^/(\d+)/', href)
        if not m:
            continue

        # LIVE check: look for div.ml.mod-live or ml-status text
        live_el = item.select_one('.ml.mod-live') or item.select_one('.ml-status')
        if not live_el:
            continue
        if 'LIVE' not in live_el.get_text(strip=True).upper():
            if not item.select_one('[class*="mod-live"]'):
                continue

        match_id = int(m.group(1))
        teams = [t.get_text(strip=True) for t in item.select('.match-item-vs-team-name')]
        event_el = (item.select_one('.match-item-event') or
                    item.select_one('.match-item-league'))
        event_name = event_el.get_text(separator=' ', strip=True) if event_el else ''

        # Try to extract date from the page context (items appear under a date header)
        # Fall back to today
        match_date = date.today().strftime('%Y-%m-%d')

        live_matches.append({
            'vlr_id':     match_id,
            'team1':      teams[0] if teams else 'Team1',
            'team2':      teams[1] if len(teams) > 1 else 'Team2',
            'event':      event_name,
            'url':        f"https://www.vlr.gg{href}",
            'match_date': match_date,
        })
        t1, t2 = (teams[0] if teams else '?'), (teams[1] if len(teams) > 1 else '?')
        log.info(f"VLR LIVE [{match_id}] {t1} vs {t2} — {event_name}")

    return live_matches


# ─────────────────────────────────────────────────────────────────────────────
# bo3.gg slug resolution
# ─────────────────────────────────────────────────────────────────────────────

def _team_to_slug(name: str) -> str:
    """Normalize a team name to a bo3.gg URL slug component."""
    # Lowercase, replace spaces with hyphens, strip trailing special chars
    slug = name.lower().strip()
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    slug = slug.strip('-')
    return slug


def resolve_bo3_slug(team1: str, team2: str, match_date: str) -> Optional[str]:
    """
    Find the bo3.gg match slug for a given matchup.
    Pattern: {t1_slug}-vs-{t2_slug}-{DD}-{MM}-{YYYY}

    Tries both team orderings. Returns slug string or None.
    """
    t1 = _team_to_slug(team1)
    t2 = _team_to_slug(team2)

    # Convert YYYY-MM-DD to DD-MM-YYYY (bo3.gg format)
    try:
        d = datetime.strptime(match_date, '%Y-%m-%d')
        date_sfx = d.strftime('%d-%m-%Y')
    except ValueError:
        date_sfx = datetime.now().strftime('%d-%m-%Y')

    for slug in [f"{t1}-vs-{t2}-{date_sfx}", f"{t2}-vs-{t1}-{date_sfx}"]:
        data = _get_json(f"{BO3_API}/matches/{slug}")
        if data and data.get('discipline_id') == VALORANT_DISCIPLINE_ID:
            log.info(f"  Resolved bo3 slug: {slug} (match ID {data.get('id')})")
            return slug

    log.warning(f"  Could not resolve bo3 slug for {team1} vs {team2} on {match_date}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Live update processing
# ─────────────────────────────────────────────────────────────────────────────

def _is_pistol_round(round_num: int) -> bool:
    """Rounds 1 and 13 are pistol rounds (regulation only)."""
    return round_num in (1, 13)


def process_live_update(tracker: MatchTracker, match_data: dict,
                         max_spread: float) -> Optional[TradingSignal]:
    """
    Parse live_updates from a bo3.gg match response and generate a trading signal
    if an economy mismatch is detected during BUY_TIME at a high-leverage score.
    """
    lu = match_data.get('live_updates')
    if not lu:
        return None
    if lu.get('game_ended') or match_data.get('winner_team_id'):
        return None

    round_num   = lu.get('round_number', 0)
    round_phase = lu.get('round_phase', '')
    t1_data     = lu.get('team_1', {}) or {}
    t2_data     = lu.get('team_2', {}) or {}
    t1_score    = int(t1_data.get('game_score', 0) or 0)
    t2_score    = int(t2_data.get('game_score', 0) or 0)
    t1_equip    = int(t1_data.get('equipment_value', 0) or 0)
    t2_equip    = int(t2_data.get('equipment_value', 0) or 0)
    t1_econ_lvl = t1_data.get('economy_level')
    t2_econ_lvl = t2_data.get('economy_level')
    map_name    = lu.get('map_name', 'Unknown')
    game_number = int(lu.get('game_number', 1) or 1)
    map_score   = match_data.get('team1_score', 0), match_data.get('team2_score', 0)
    bo_type     = int(match_data.get('bo_type', 3) or 3)
    is_map3     = (bo_type == 3 and game_number == 3)

    # Only evaluate during BUY_TIME (window before round starts)
    if round_phase != 'BUY_TIME':
        return None

    # Only regulation rounds (1-24); OT economy is a full reset for both teams
    if round_num > 24:
        return None

    # Deduplicate: only fire once per round per match
    if tracker.signal_fired.get(round_num):
        return None

    # Equipment_value updates live as players purchase during BUY_TIME.
    # An early poll may show incomplete buys (e.g. 17,800 before a player
    # finishes spending up to 29,000). This creates false semi-buy reads.
    #
    # Mitigation: only fire on eco (<5k), which is unambiguously set from the
    # start of BUY_TIME. If we see a semi-buy vs full, wait for the NEXT poll
    # to see if the semi-buy resolves upward before deciding it's a real mismatch.
    # A genuine eco (<5k) cannot be a mid-buy artifact — no one starts at eco
    # and accidentally shows <5k mid-buy.
    econ1 = classify_economy(t1_equip, t1_econ_lvl)
    econ2 = classify_economy(t2_equip, t2_econ_lvl)

    # If either team shows as semi-buy and the other as full, check whether
    # this might be a mid-buy artifact. Track the previous equipment reading
    # per round; only fire if the reading is stable across 2 polls.
    prev_key = f"equip_{round_num}"
    prev = getattr(tracker, '_equip_cache', {}).get(prev_key)
    if not hasattr(tracker, '_equip_cache'):
        tracker._equip_cache = {}
    tracker._equip_cache[prev_key] = (t1_equip, t2_equip)

    pair = gun_eco_advantage(econ1, econ2)
    if pair is not None:
        # If the mismatch involves a semi-buy (not eco), require stability
        gun_econ = econ1 if pair == 1 else econ2
        eco_econ = econ2 if pair == 1 else econ1
        if eco_econ in ('semi-buy', 'semi-eco') and prev is not None:
            prev_e1, prev_e2 = prev
            prev_eco = prev_e2 if pair == 1 else prev_e1
            # If eco team's equipment is growing (still buying), skip this poll
            curr_eco_val = t2_equip if pair == 1 else t1_equip
            if curr_eco_val > prev_eco:
                log.debug(f"  R{round_num} {eco_econ} read may be mid-buy "
                          f"({prev_eco} → {curr_eco_val}), skipping poll")
                return None

    gun_team = pair

    if gun_team is None:
        log.debug(f"  [{map_name}] R{round_num} {t1_score}-{t2_score} BUY_TIME: "
                  f"{econ1}({t1_equip}) vs {econ2}({t2_equip}) — no mismatch")
        return None

    gun_name = tracker.team1_name if gun_team == 1 else tracker.team2_name
    eco_name = tracker.team2_name if gun_team == 1 else tracker.team1_name

    log.info(f"  [{map_name}] R{round_num} {t1_score}-{t2_score} BUY_TIME: "
             f"{gun_name} FULL({t1_equip if gun_team==1 else t2_equip}) vs "
             f"{eco_name} {(econ2 if gun_team==1 else econ1).upper()}({t2_equip if gun_team==1 else t1_equip})")

    # Evaluate EV
    signal = evaluate_signal(
        t1_score, t2_score, gun_team, gun_name, eco_name,
        match_id   = match_data.get('id', 0),
        map_number = game_number,
        map_name   = map_name,
        team1_name = tracker.team1_name,
        team2_name = tracker.team2_name,
        is_map3    = is_map3,
        round_num  = round_num,
        max_spread = max_spread,
    )

    if signal:
        tracker.signal_fired[round_num] = True

    return signal


# ─────────────────────────────────────────────────────────────────────────────
# Main poller
# ─────────────────────────────────────────────────────────────────────────────

class LivePoller:
    def __init__(self, max_spread_cents: float = 8.0,
                 order_manager=None):
        """
        Args:
            max_spread_cents: Maximum Kalshi spread to accept for a taker trade.
            order_manager:    Optional KalshiOrderManager instance. When provided,
                              signals automatically trigger limit orders.
        """
        self.max_spread = max_spread_cents
        self._trackers: Dict[str, MatchTracker] = {}   # bo3_slug -> MatchTracker
        self._signals:  List[TradingSignal] = []
        self._lock = threading.Lock()
        self._order_manager = order_manager   # KalshiOrderManager | None

        # Cache of open Valorant markets refreshed lazily
        self._kalshi_markets: List[dict] = []
        self._kalshi_markets_ts: float = 0.0

    def _on_signal(self, signal: TradingSignal) -> None:
        """Print signal, append to list, and optionally place a Kalshi order."""
        self._signals.append(signal)
        print(f"\n{'='*65}")
        print(f"  *** TRADING SIGNAL — {signal.timestamp} ***")
        print(f"  Match:    {signal.team1_name} vs {signal.team2_name}")
        print(f"  Map {signal.map_number} ({signal.map_name}) — {'MAP 3 = MATCH WINNER' if signal.is_map3 else 'map winner'}")
        print(f"  Score:    {signal.score}  |  Round {signal.round_num} (BUY PHASE)")
        print(f"  Gun team: {signal.gun_team_name}  (full buy)")
        print(f"  Eco team: {signal.eco_team_name}  (eco/semi-eco)")
        print(f"  Neutral map FV:  {signal.map_fv_neutral:.3f}")
        print(f"  Eco-adj map FV:  {signal.map_fv_eco_adj:.3f}")
        print(f"  Eco delta:  +{signal.eco_delta:.2f}c")
        print(f"  Taker EV:   +{signal.taker_ev:.2f}c  (at {self.max_spread}c spread)")
        print(f"  ACTION: {signal.kalshi_hint}")
        print(f"{'='*65}\n")

        if self._order_manager is not None:
            ticker = self._resolve_kalshi_ticker(signal)
            if ticker:
                try:
                    self._order_manager.on_signal(signal, ticker)
                except Exception as exc:
                    log.error("KalshiOrderManager.on_signal raised: %s", exc)
            else:
                log.warning(
                    "Could not resolve Kalshi ticker for %s vs %s — order skipped.",
                    signal.team1_name, signal.team2_name,
                )

    def _resolve_kalshi_ticker(self, signal: TradingSignal) -> Optional[str]:
        """
        Match the gun-team name from signal against open Kalshi Valorant markets.

        Refreshes the market cache at most once every 5 minutes. Returns the
        Kalshi ticker string for the best matching market, or None.
        """
        import time as _time
        now = _time.time()
        if now - self._kalshi_markets_ts > 300:  # refresh every 5 min
            try:
                self._kalshi_markets = self._order_manager._client.find_valorant_markets()
                self._kalshi_markets_ts = now
                log.info("Refreshed Kalshi markets cache: %d markets", len(self._kalshi_markets))
            except Exception as exc:
                log.error("Failed to refresh Kalshi markets: %s", exc)

        if not self._kalshi_markets:
            return None

        t1 = signal.team1_name.lower().strip()
        t2 = signal.team2_name.lower().strip()

        best_ticker: Optional[str] = None
        best_score = 0

        for mkt in self._kalshi_markets:
            a = (mkt.get("team_a") or "").lower().strip()
            b = (mkt.get("team_b") or "").lower().strip()
            title = (mkt.get("title") or "").lower()

            score = 0
            # Direct team name match in extracted team_a / team_b fields
            if (a and (a in t1 or t1 in a)) or (b and (b in t1 or t1 in b)):
                score += 2
            if (a and (a in t2 or t2 in a)) or (b and (b in t2 or t2 in b)):
                score += 2
            # Fallback: team name anywhere in title
            if t1 in title:
                score += 1
            if t2 in title:
                score += 1

            if score > best_score:
                best_score = score
                best_ticker = mkt.get("ticker")

        if best_score < 2:
            log.debug(
                "No confident Kalshi market match for %s vs %s (best score=%d)",
                signal.team1_name, signal.team2_name, best_score,
            )
            return None

        log.info(
            "Matched Kalshi ticker %s for %s vs %s (score=%d)",
            best_ticker, signal.team1_name, signal.team2_name, best_score,
        )
        return best_ticker

    def _poll_match(self, slug: str) -> None:
        data = _get_json(f"{BO3_API}/matches/{slug}")
        if not data:
            return

        with self._lock:
            if slug not in self._trackers:
                return
            tracker = self._trackers[slug]

        lu = data.get('live_updates') or {}
        round_num   = lu.get('round_number', 0)
        round_phase = lu.get('round_phase', '')

        if round_phase:
            log.debug(f"  [{slug[:30]}] R{round_num} {round_phase} "
                      f"score={lu.get('team_1',{}).get('game_score','?')}-"
                      f"{lu.get('team_2',{}).get('game_score','?')}")

        signal = process_live_update(tracker, data, self.max_spread)
        if signal:
            self._on_signal(signal)

    def _add_match(self, vlr_match: dict) -> bool:
        """Try to resolve and register a live VLR match. Returns True if added."""
        slug = resolve_bo3_slug(
            vlr_match['team1'], vlr_match['team2'], vlr_match.get('match_date', '')
        )
        if not slug:
            return False
        with self._lock:
            if slug not in self._trackers:
                self._trackers[slug] = MatchTracker(
                    bo3_slug   = slug,
                    vlr_id     = vlr_match['vlr_id'],
                    team1_name = vlr_match['team1'],
                    team2_name = vlr_match['team2'],
                )
                log.info(f"Tracking: {vlr_match['team1']} vs {vlr_match['team2']} ({slug})")
        return True

    def run(self, poll_discover: int = POLL_INTERVAL_DISCOVER,
             poll_score: int = POLL_INTERVAL_SCORE) -> None:
        """Main polling loop."""
        log.info(f"Starting poller | spread={self.max_spread}c | "
                 f"discover every {poll_discover}s | score every {poll_score}s")
        last_discover = 0

        while True:
            now = time.time()

            # Periodically scan VLR for new live matches
            if now - last_discover >= poll_discover:
                live = scrape_vlr_live_matches()
                if live:
                    for m in live:
                        self._add_match(m)
                else:
                    log.info("No live Valorant matches on VLR.gg")
                last_discover = now

            # Poll scores for all tracked matches
            with self._lock:
                slugs = list(self._trackers.keys())
            for slug in slugs:
                self._poll_match(slug)

            time.sleep(poll_score)


# ─────────────────────────────────────────────────────────────────────────────
# Probe / diagnostics
# ─────────────────────────────────────────────────────────────────────────────

def probe(verbose: bool = False) -> None:
    """Show all live Valorant matches and their current live_updates state."""
    print("\n=== Live Valorant matches ===")
    live = scrape_vlr_live_matches()
    if not live:
        print("  (none on VLR.gg right now)")
        return

    for m in live:
        print(f"\n  VLR [{m['vlr_id']}] {m['team1']} vs {m['team2']}")
        print(f"  Event: {m['event']}")
        print(f"  URL:   {m['url']}")

        slug = resolve_bo3_slug(m['team1'], m['team2'], m.get('match_date', ''))
        if not slug:
            print("  bo3.gg: slug not found")
            continue

        data = _get_json(f"{BO3_API}/matches/{slug}")
        if not data:
            print("  bo3.gg: no data")
            continue

        lu = data.get('live_updates') or {}
        t1 = lu.get('team_1', {}) or {}
        t2 = lu.get('team_2', {}) or {}

        print(f"  bo3 match ID: {data.get('id')}  slug: {slug}")
        print(f"  Series score: {data.get('team1_score')}-{data.get('team2_score')}")
        if lu:
            print(f"  Map {lu.get('game_number')}: {lu.get('map_name')} | "
                  f"Round {lu.get('round_number')} | Phase: {lu.get('round_phase')}")
            print(f"  {m['team1']}:  rounds={t1.get('game_score')}  equip={t1.get('equipment_value')}  "
                  f"side={t1.get('side')}  econ={t1.get('economy_level')}")
            print(f"  {m['team2']}:  rounds={t2.get('game_score')}  equip={t2.get('equipment_value')}  "
                  f"side={t2.get('side')}  econ={t2.get('economy_level')}")
            # Classify economies
            e1 = classify_economy(t1.get('equipment_value', 0), t1.get('economy_level'))
            e2 = classify_economy(t2.get('equipment_value', 0), t2.get('economy_level'))
            gun = gun_eco_advantage(e1, e2)
            print(f"  Economy: {m['team1']}={e1}  {m['team2']}={e2}  "
                  f"gun_team={'none' if gun is None else (m['team1'] if gun==1 else m['team2'])}")
        else:
            print("  No live_updates (match not started or ended)")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Simulation
# ─────────────────────────────────────────────────────────────────────────────

def run_simulation(max_spread: float = 8.0) -> None:
    """
    Simulate the live_updates stream for a map 3 scenario:
    SEN vs C9, 7-5 halftime → C9 wins pistol → close second half → OT
    """
    print(f"\n=== SIMULATION (spread={max_spread}c) ===\n")

    tracker = MatchTracker(bo3_slug='sim', vlr_id=0,
                           team1_name='SEN', team2_name='C9')

    # Sequence: (round_num, t1_score_before_round, t2_score_before_round, gun_team_eq, eco_team_eq, winner)
    # We simulate what live_updates would look like during BUY_TIME
    # Format: (round, t1_rounds_won, t2_rounds_won, t1_equip, t2_equip)
    # These represent the state AT BUY_TIME for each round
    rounds = [
        # First half
        (1,  0,  0, 2900,  2900),   # pistol
        (2,  1,  0, 25000, 2900),   # SEN gun, C9 eco (after SEN wins pistol)
        (3,  2,  0, 25000, 8000),   # SEN gun, C9 semi-eco (bonus round)
        (4,  2,  1, 16000, 25000),  # no mismatch — skip
        (13, 7,  5, 2900,  2900),   # second-half pistol
        (14, 7,  6, 25000, 2900),   # C9 wins pistol → C9 gun, SEN eco
        (15, 7,  7, 25000, 8000),   # C9 bonus round
        (19, 10, 9, 25000, 2900),   # late-game: SEN gun, C9 eco
        (24, 12,11, 25000, 2900),   # regulation final round: SEN gun, C9 eco
    ]

    signals = 0
    for round_num, t1s, t2s, t1_eq, t2_eq in rounds:
        mock_data = {
            'id': 9999, 'team1_score': 0, 'team2_score': 0,
            'bo_type': 3, 'winner_team_id': None,
            'live_updates': {
                'round_number': round_num, 'round_phase': 'BUY_TIME',
                'map_name': 'Bind', 'game_number': 3, 'game_ended': False,
                'team_1': {'game_score': t1s, 'equipment_value': t1_eq, 'economy_level': None, 'side': 'ATK'},
                'team_2': {'game_score': t2s, 'equipment_value': t2_eq, 'economy_level': None, 'side': 'DEF'},
            }
        }
        e1 = classify_economy(t1_eq)
        e2 = classify_economy(t2_eq)
        print(f"  R{round_num:2d}  {t1s}-{t2s}  SEN={e1}({t1_eq})  C9={e2}({t2_eq})", end="")
        sig = process_live_update(tracker, mock_data, max_spread)
        if sig:
            signals += 1
            print(f"  -> SIGNAL: BUY {sig.gun_team_name} +{sig.eco_delta:.1f}c delta, EV +{sig.taker_ev:.1f}c")
        else:
            print()

    print(f"\nTotal signals: {signals}  (spread={max_spread}c)")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='VCT live eco-round Kalshi signal generator')
    parser.add_argument('--test',       action='store_true', help='Run simulation')
    parser.add_argument('--probe',      action='store_true', help='Show live matches + current live_updates')
    parser.add_argument('--spread',     type=float, default=8.0, help='Max Kalshi spread in cents (default: 8.0)')
    parser.add_argument('--poll-score', type=int,   default=5,   help='Seconds between score polls (default: 5)')
    parser.add_argument('--poll-match', type=int,   default=60,  help='Seconds between match discovery (default: 60)')
    parser.add_argument('--match',      type=str,   default=None,
                        help='Force-track a bo3.gg match slug directly, e.g. oxen-vs-9z-team-09-04-2026')
    parser.add_argument('--verbose',    action='store_true', help='Debug logging')
    parser.add_argument('--kalshi',     action='store_true',
                        help=(
                            'Enable live Kalshi order placement. '
                            'Requires env vars KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH. '
                            'Reads dry_run=False — real orders will be placed.'
                        ))
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ----------------------------------------------------------------
    # Build order manager when --kalshi flag is set
    # ----------------------------------------------------------------
    order_manager = None
    if args.kalshi:
        import os as _os
        try:
            from scraper.kalshi_client import KalshiClient
            from scraper.kalshi_order_manager import KalshiOrderManager
        except ImportError:
            from kalshi_client import KalshiClient          # type: ignore[no-redef]
            from kalshi_order_manager import KalshiOrderManager  # type: ignore[no-redef]

        key_id   = _os.environ.get('KALSHI_KEY_ID')
        pem_path = _os.environ.get('KALSHI_PRIVATE_KEY_PATH')

        if not key_id:
            print("ERROR: KALSHI_KEY_ID env var is not set. Cannot enable Kalshi trading.")
            raise SystemExit(1)
        if not pem_path:
            print("ERROR: KALSHI_PRIVATE_KEY_PATH env var is not set. Cannot enable Kalshi trading.")
            raise SystemExit(1)

        try:
            kalshi_client = KalshiClient(key_id=key_id, private_key_path=pem_path)
            order_manager = KalshiOrderManager(client=kalshi_client, dry_run=False)
            log.info("Kalshi integration ENABLED — real orders will be placed.")
        except Exception as exc:
            print(f"ERROR: Failed to initialize Kalshi client: {exc}")
            raise SystemExit(1)

    if args.test:
        run_simulation(args.spread)
    elif args.probe:
        probe(verbose=args.verbose)
    elif args.match:
        # Directly track one match by slug
        data = _get_json(f"{BO3_API}/matches/{args.match}")
        if not data:
            print(f"Could not fetch match: {args.match}")
        else:
            t1 = (data.get('team1') or {}).get('name', 'Team1')
            t2 = (data.get('team2') or {}).get('name', 'Team2')
            poller = LivePoller(max_spread_cents=args.spread, order_manager=order_manager)
            with poller._lock:
                poller._trackers[args.match] = MatchTracker(
                    bo3_slug=args.match, vlr_id=0,
                    team1_name=t1, team2_name=t2,
                )
            log.info(f"Tracking: {t1} vs {t2}")
            try:
                while True:
                    poller._poll_match(args.match)
                    time.sleep(args.poll_score)
            except KeyboardInterrupt:
                print(f"\nStopped. Signals: {len(poller._signals)}")
    else:
        poller = LivePoller(max_spread_cents=args.spread, order_manager=order_manager)
        try:
            poller.run(poll_discover=args.poll_match, poll_score=args.poll_score)
        except KeyboardInterrupt:
            print(f"\nStopped. Signals: {len(poller._signals)}")
