"""
Live Score Poller for VCT Eco/Anti-Eco Trading Strategy.

Architecture:
  1. REST polling (primary): GET api.bo3.gg/api/v1/matches?discipline_id=2&status=live
     + GET api.bo3.gg/api/v1/games?match_id={id}   ← per-map round scores
  2. WebSocket (enhancement): wss://live.bo3.gg/    ← real-time score pushes

Trading Signal Logic:
  - Monitor current round score within each live Valorant map
  - Detect when a pistol round completes (round 1 or 13 = second-half start)
  - Determine which team has gun advantage (anti-eco the next round)
  - Evaluate if the resulting score state has positive taker EV on Kalshi
  - Score states with positive EV at <=8c spread: 10-9, 9-10, 11-9, 9-11
  - With <=4c spread: 7-6, 6-7 in second half and other close late-map states

Dependencies:
  pip install websockets requests

Usage:
  python scraper/live_score_poller.py               # live mode (poll until stopped)
  python scraper/live_score_poller.py --test         # simulate with a fixed score sequence
  python scraper/live_score_poller.py --spread 4.0   # set max spread for signals
"""

import json
import time
import logging
import argparse
import threading
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import urllib.request
import urllib.error

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

BO3_API = "https://api.bo3.gg/api/v1"
BO3_WS  = "wss://live.bo3.gg/"

POLL_INTERVAL_MATCH  = 30   # seconds between scanning for new live matches
POLL_INTERVAL_MAP    = 5    # seconds between per-map score refreshes

VALORANT_DISCIPLINE_ID = 2
VALORANT_WIN_THRESHOLD = 13  # rounds needed to win a map
HALF_BOUNDARY          = 12  # round 13 = first round of second half

# Pre-computed Markov table (p=0.5 neutral teams, both halves)
# P(team1 wins map | current round score t1-t2)
# Key insight: this is asymmetric at score states where OT structure kicks in.
_p = 0.5
_p_ot_tied   = (_p**2) / (_p**2 + (1-_p)**2)   # 0.5 for equal teams
_p_ot_ahead  = _p + (1-_p) * _p_ot_tied         # 0.75
_p_ot_behind = _p * _p_ot_tied                   # 0.25

def _build_markov(p: float = 0.5) -> Dict[Tuple[int,int], float]:
    p_ot_tied   = (p**2) / (p**2 + (1-p)**2)
    p_ot_ahead  = p + (1-p) * p_ot_tied
    p_ot_behind = p * p_ot_tied

    from functools import lru_cache
    @lru_cache(maxsize=None)
    def prob(t1: int, t2: int) -> float:
        WIN = VALORANT_WIN_THRESHOLD
        if t1 >= WIN and (t1 - t2) >= 2:
            return 1.0
        if t2 >= WIN and (t2 - t1) >= 2:
            return 0.0
        if t1 >= WIN - 1 and t2 >= WIN - 1:
            d = t1 - t2
            if d == 0:  return p_ot_tied
            if d == 1:  return p_ot_ahead
            if d == -1: return p_ot_behind
            return 1.0 if d > 0 else 0.0
        return p * prob(t1+1, t2) + (1-p) * prob(t1, t2+1)

    return {(t1, t2): prob(t1, t2) for t1 in range(16) for t2 in range(16)}

MARKOV = _build_markov(0.5)

# High-leverage score states: score where a round win/loss changes map win prob by >= 5%
# Computed from MARKOV table: states with |FV_after_win - FV_after_loss| > 0.10
HIGH_LEVERAGE_STATES = {
    (s1, s2) for (s1, s2) in MARKOV
    if (min(s1, s2) >= 5 and abs(s1 - s2) <= 3 and
        (MARKOV.get((s1+1, s2), MARKOV[(s1, s2)]) - MARKOV.get((s1, s2+1), MARKOV[(s1, s2)])) > 0.10)
}

# Minimum score state for second-half pistol signal (round >= 13)
# At 8c spread: need at least 10-9 for positive taker EV
# At 4c spread: 7-6 is viable
HIGH_EV_STATES_8C  = {(10,9),(9,10),(11,9),(9,11),(10,10),(11,10),(10,11),(11,11),(12,11),(11,12),(12,12)}
HIGH_EV_STATES_4C  = HIGH_EV_STATES_8C | {(7,6),(6,7),(8,6),(6,8),(8,7),(7,8),(9,8),(8,9),(9,9)}


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MapState:
    """Current state of one map within a live match."""
    match_id:     int
    game_id:      int
    map_number:   int           # 1, 2, or 3
    map_name:     str
    team1_id:     int
    team2_id:     int
    team1_name:   str
    team2_name:   str
    t1_rounds:    int = 0       # rounds won by team1
    t2_rounds:    int = 0       # rounds won by team2
    state:        str = "live"  # "live", "done", "upcoming"
    is_map3:      bool = False

    # Tracking for signal detection
    last_signal_round: int = 0  # which round we last fired a signal on
    half2_pistol_winner: Optional[int] = None  # 1 or 2, after round 13

    @property
    def total_rounds(self) -> int:
        return self.t1_rounds + self.t2_rounds

    @property
    def round_num(self) -> int:
        """Current round number (1-indexed, = total completed rounds + 1)."""
        return self.total_rounds + 1

    @property
    def is_second_half(self) -> bool:
        return self.total_rounds >= HALF_BOUNDARY

    @property
    def in_overtime(self) -> bool:
        return self.t1_rounds >= HALF_BOUNDARY and self.t2_rounds >= HALF_BOUNDARY


@dataclass
class TradingSignal:
    """A detected trading opportunity."""
    timestamp:      str
    match_id:       int
    map_number:     int
    map_name:       str
    team1_name:     str
    team2_name:     str
    score:          str          # e.g. "7-6"
    gun_team:       int          # 1 or 2
    gun_team_name:  str
    eco_team_name:  str
    signal_type:    str          # "second_half_pistol", "ot_pistol"
    map_fv_neutral: float        # neutral Markov FV for gun team
    map_fv_eco_adj: float        # adjusted FV assuming gun team wins
    eco_delta:      float        # eco_adj - neutral (in cents)
    is_map3:        bool
    kalshi_hint:    str          # which Kalshi contract to buy


# ─────────────────────────────────────────────────────────────────────────────
# HTTP helper
# ─────────────────────────────────────────────────────────────────────────────

_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

def _get_json(url: str, timeout: int = 15) -> Optional[dict]:
    """Fetch a JSON endpoint. Returns parsed dict/list or None on error."""
    req = urllib.request.Request(url, headers={'User-Agent': _UA, 'Accept': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        log.debug(f"HTTP {e.code} for {url}")
        return None
    except Exception as e:
        log.debug(f"Request failed {url}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Bo3.gg API queries
# ─────────────────────────────────────────────────────────────────────────────

def fetch_live_valorant_matches() -> List[dict]:
    """
    Return list of currently live Valorant match objects from bo3.gg.

    Note: discipline_id=2 is Valorant. Also try game=valorant as a fallback
    since the filter parameter name may vary between API versions.
    """
    # Primary: filter by discipline_id
    data = _get_json(f"{BO3_API}/matches?discipline_id={VALORANT_DISCIPLINE_ID}&status=live&limit=20")
    matches = []
    if data and 'results' in data:
        matches = [m for m in data['results'] if m.get('discipline_id') == VALORANT_DISCIPLINE_ID]
        if matches:
            log.debug(f"Found {len(matches)} live Valorant matches via discipline_id filter")

    # Fallback: status=live with broader filter, check discipline_id manually
    if not matches:
        data = _get_json(f"{BO3_API}/matches?status=live&limit=50")
        if data and 'results' in data:
            matches = [m for m in data['results'] if m.get('discipline_id') == VALORANT_DISCIPLINE_ID]
            log.debug(f"Fallback: {len(matches)} Valorant matches in live feed")

    return matches


def fetch_match_games(match_id: int) -> List[dict]:
    """
    Return list of game (map) objects for a match.
    Each game has the current round score during live play.

    Expected live fields (verified against bo3.gg finished game schema):
      id, match_id, state ("live"/"done"), map_name, number (map order),
      winner_clan_score, loser_clan_score  ← final scores (done)
      team1_score, team2_score             ← live round scores (if available)

    Since we only have finished-game data to reference, we log the raw structure
    on the first live game encountered to verify the actual live field names.
    """
    data = _get_json(f"{BO3_API}/games?match_id={match_id}&limit=10")
    if not data or 'results' not in data:
        return []
    return data['results']


def fetch_match_teams(match_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Fetch team names for a match. Returns (team1_name, team2_name)."""
    data = _get_json(f"{BO3_API}/matches/{match_id}")
    if not data:
        return None, None
    # Team names might be nested under team1/team2 objects
    t1 = data.get('team1') or {}
    t2 = data.get('team2') or {}
    t1_name = (t1.get('name') or t1.get('clan_name') or
               data.get('team1_name') or f"Team1-{data.get('team1_id', '?')}")
    t2_name = (t2.get('name') or t2.get('clan_name') or
               data.get('team2_name') or f"Team2-{data.get('team2_id', '?')}")
    return t1_name, t2_name


def _extract_round_scores(game: dict) -> Tuple[int, int]:
    """
    Extract current round scores (t1_rounds, t2_rounds) from a game object.

    Bo3.gg uses different field names depending on game state:
      - Finished: winner_clan_score / loser_clan_score (no positional info!)
      - Live:     team1_score / team2_score (assumed based on match schema)
                  OR partial_score_1 / partial_score_2
                  OR score1 / score2

    We log unknown structures on first encounter for debugging.
    """
    # Prefer positional team scores (consistent across live/done)
    for f1, f2 in [('team1_score', 'team2_score'),
                   ('score1', 'score2'),
                   ('partial_score_1', 'partial_score_2'),
                   ('score_team1', 'score_team2')]:
        if f1 in game and f2 in game:
            return int(game[f1] or 0), int(game[f2] or 0)

    # For finished games, winner_clan_score exists but loses team ordering.
    # We can't reliably assign t1/t2 from winner/loser without knowing who's who.
    # Return (0,0) and let caller log a warning.
    if game.get('state') == 'done':
        w = game.get('winner_clan_score', 0) or 0
        l = game.get('loser_clan_score', 0) or 0
        # We don't know who is t1/t2 from winner/loser alone — skip.
        log.debug(f"  game {game.get('id')}: finished {w}-{l} (winner/loser, ordering unknown)")
    else:
        log.warning(f"  UNKNOWN score fields in game {game.get('id', '?')}: {list(game.keys())}")

    return 0, 0


# ─────────────────────────────────────────────────────────────────────────────
# Trading signal evaluation
# ─────────────────────────────────────────────────────────────────────────────

GUN_WIN_RATE = 0.822   # empirical: 82.2% gun team win rate (n=73 from backtest)

def _eco_adjusted_fv(t1: int, t2: int, gun_team: int, p_gun_wins: float = GUN_WIN_RATE) -> float:
    """
    Eco-adjusted map FV for the gun team.
    = P(gun wins round) * FV(score+1) + P(eco wins) * FV(score-1)
    """
    if gun_team == 1:
        fv_win  = MARKOV.get((min(t1+1, 15), t2), 1.0)
        fv_lose = MARKOV.get((t1, min(t2+1, 15)), 0.0)
        neutral_fv = MARKOV.get((t1, t2), 0.5)
    else:
        # gun_team == 2: express as P(team1 wins) = 1 - P(team2 wins)
        fv_win  = 1 - MARKOV.get((t1, min(t2+1, 15)), 0.0)  # team2 wins round
        fv_lose = 1 - MARKOV.get((min(t1+1, 15), t2), 1.0)  # team1 wins round
        neutral_fv = 1 - MARKOV.get((t1, t2), 0.5)

    eco_adj = p_gun_wins * fv_win + (1 - p_gun_wins) * fv_lose
    return eco_adj, neutral_fv


def evaluate_signal(state: MapState, gun_team: int, signal_type: str,
                    max_spread_cents: float = 8.0) -> Optional[TradingSignal]:
    """
    Determine if current score state has positive taker EV given the gun advantage.

    Taker EV = eco_delta * 100 - spread/2 - fee
    (spread/2 because we enter at market + spread/2, exit at limit)
    """
    t1, t2 = state.t1_rounds, state.t2_rounds

    # Express score as seen by gun team (gun team always "team1" in FV calc)
    eco_fv, neutral_fv = _eco_adjusted_fv(t1, t2, gun_team)

    # Delta: how much the market should move to reflect eco advantage
    eco_delta_cents = (eco_fv - neutral_fv) * 100

    # Taker EV formula: edge after round-trip spread cost + ~0.5c fee
    fee_cents = 0.5
    entry_cost = max_spread_cents / 2    # we pay half spread on entry (take)
    exit_cost  = max_spread_cents / 4    # exit via limit (pay quarter spread)
    round_trip_cost = entry_cost + exit_cost + fee_cents
    taker_ev = eco_delta_cents - round_trip_cost

    if taker_ev <= 0:
        log.debug(f"  No signal at {t1}-{t2}: delta={eco_delta_cents:.2f}c, EV={taker_ev:.2f}c")
        return None

    gun_name = state.team1_name if gun_team == 1 else state.team2_name
    eco_name = state.team2_name if gun_team == 1 else state.team1_name

    # For map 3: match winner contract = map winner → direct bet
    # For maps 1-2: map winner contract (or match winner if score is 0-0 or 1-0/0-1)
    if state.is_map3:
        kalshi_hint = f"BUY {gun_name} MAP3 (= MATCH WINNER) | expected delta +{eco_delta_cents:.1f}c"
    else:
        kalshi_hint = f"BUY {gun_name} MAP{state.map_number} | expected delta +{eco_delta_cents:.1f}c"

    return TradingSignal(
        timestamp      = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        match_id       = state.match_id,
        map_number     = state.map_number,
        map_name       = state.map_name,
        team1_name     = state.team1_name,
        team2_name     = state.team2_name,
        score          = f"{t1}-{t2}",
        gun_team       = gun_team,
        gun_team_name  = gun_name,
        eco_team_name  = eco_name,
        signal_type    = signal_type,
        map_fv_neutral = neutral_fv,
        map_fv_eco_adj = eco_fv,
        eco_delta      = eco_delta_cents,
        is_map3        = state.is_map3,
        kalshi_hint    = kalshi_hint,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Score transition detection
# ─────────────────────────────────────────────────────────────────────────────

def _is_pistol_round(round_num: int) -> bool:
    """
    Return True if round_num is a pistol round.
    Pistol rounds: 1, 13, and OT pairs (25, 28, 31, ...) i.e. every 3 rounds after 24.
    """
    if round_num in (1, 13):
        return True
    if round_num >= 25 and (round_num - 25) % 3 == 0:
        return True
    return False


def process_score_update(state: MapState, new_t1: int, new_t2: int,
                          max_spread: float = 8.0) -> Optional[TradingSignal]:
    """
    Called every time we detect a score change.
    Determines if this completes a pistol round and fires a signal.

    Round N just completed when (new_t1 + new_t2) == N.
    """
    old_total = state.total_rounds
    new_total = new_t1 + new_t2
    rounds_completed = new_total - old_total

    if rounds_completed == 0:
        return None  # no change

    if rounds_completed != 1:
        log.warning(f"  Score jumped {rounds_completed} rounds at once ({state.t1_rounds}-{state.t2_rounds} -> {new_t1}-{new_t2}). Catch-up?")

    # Determine who won each round (for multi-round jumps, simplify to last)
    round_just_completed = old_total + 1   # most recent round number

    # Update state
    prev_t1, prev_t2 = state.t1_rounds, state.t2_rounds
    state.t1_rounds, state.t2_rounds = new_t1, new_t2

    gun_team = None
    signal_type = None

    if _is_pistol_round(round_just_completed):
        # Who won this pistol?
        if new_t1 > prev_t1:
            gun_team = 1  # team1 won pistol → gun advantage next round
        elif new_t2 > prev_t2:
            gun_team = 2

        if gun_team is None:
            log.warning(f"  Pistol round {round_just_completed} completed but can't determine winner?")
            return None

        if round_just_completed == 1:
            signal_type = "first_half_pistol"
        elif round_just_completed == 13:
            signal_type = "second_half_pistol"
            state.half2_pistol_winner = gun_team
        else:
            signal_type = "ot_pistol"

        log.info(f"  [{state.map_name}] Round {round_just_completed} (pistol) done. "
                 f"Score: {new_t1}-{new_t2}. Gun team: {gun_team} ({state.team1_name if gun_team==1 else state.team2_name})")

        # Evaluate trade signal at current score state
        signal = evaluate_signal(state, gun_team, signal_type, max_spread)
        if signal:
            state.last_signal_round = round_just_completed
            return signal

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Main poller
# ─────────────────────────────────────────────────────────────────────────────

class LivePoller:
    """
    Polls bo3.gg for live Valorant matches and emits trading signals.
    """

    def __init__(self, max_spread_cents: float = 8.0, use_websocket: bool = False):
        self.max_spread = max_spread_cents
        self.use_websocket = use_websocket
        self._live_states: Dict[Tuple[int,int], MapState] = {}  # (match_id, game_id) -> state
        self._signals: List[TradingSignal] = []
        self._lock = threading.Lock()

    def _build_map_state(self, match: dict, game: dict) -> MapState:
        """Build a MapState from a match and game API object."""
        t1_name, t2_name = fetch_match_teams(match['id'])
        t1, t2 = _extract_round_scores(game)

        map_number = game.get('number', 1)
        # Map 3 if bo_type=3 and this is map 3
        is_map3 = (match.get('bo_type', 3) == 3 and map_number == 3)

        return MapState(
            match_id    = match['id'],
            game_id     = game['id'],
            map_number  = map_number,
            map_name    = game.get('map_name', 'Unknown'),
            team1_id    = match.get('team1_id', 0),
            team2_id    = match.get('team2_id', 0),
            team1_name  = t1_name or f"T1-{match.get('team1_id','')}",
            team2_name  = t2_name or f"T2-{match.get('team2_id','')}",
            t1_rounds   = t1,
            t2_rounds   = t2,
            state       = game.get('state', 'live'),
            is_map3     = is_map3,
        )

    def _on_signal(self, signal: TradingSignal) -> None:
        """Called when a trade signal is detected. Override to connect to Kalshi."""
        self._signals.append(signal)
        print(f"\n{'='*60}")
        print(f"  *** TRADING SIGNAL DETECTED ***")
        print(f"  {signal.timestamp}")
        print(f"  Match:    {signal.team1_name} vs {signal.team2_name} (Map {signal.map_number}: {signal.map_name})")
        print(f"  Score:    {signal.score}  (round {int(signal.score.split('-')[0]) + int(signal.score.split('-')[1]) + 1} about to start)")
        print(f"  Signal:   {signal.signal_type}")
        print(f"  Gun team: {signal.gun_team_name}  ({signal.gun_team_name} won pistol)")
        print(f"  Eco team: {signal.eco_team_name}  (on eco next round)")
        print(f"  Neutral FV:    {signal.map_fv_neutral:.3f}")
        print(f"  Eco-adj FV:    {signal.map_fv_eco_adj:.3f}")
        print(f"  Eco delta:     +{signal.eco_delta:.2f}c")
        print(f"  Map 3 flag:    {signal.is_map3}")
        print(f"  Action:   {signal.kalshi_hint}")
        print(f"{'='*60}\n")

    def _refresh_match(self, match: dict) -> None:
        """
        Check for score updates on a live match.
        Compares new scores against cached state, fires signals on changes.
        """
        games = fetch_match_games(match['id'])
        if not games:
            return

        for game in games:
            state_key = (match['id'], game['id'])
            new_t1, new_t2 = _extract_round_scores(game)
            game_state = game.get('state', 'live')

            with self._lock:
                if state_key not in self._live_states:
                    # First time seeing this map
                    if game_state == 'live' and (new_t1 + new_t2) > 0:
                        state = self._build_map_state(match, game)
                        self._live_states[state_key] = state
                        log.info(f"  Tracking new map: {state.map_name} (map {state.map_number}) "
                                 f"score {new_t1}-{new_t2}, {'Map 3!' if state.is_map3 else ''}")
                    continue

                state = self._live_states[state_key]

                if game_state == 'done' and state.state != 'done':
                    log.info(f"  Map {state.map_name} completed: {new_t1}-{new_t2}")
                    state.state = 'done'
                    continue

                if game_state != 'live':
                    continue

                # Detect round completion and evaluate signal
                if new_t1 != state.t1_rounds or new_t2 != state.t2_rounds:
                    signal = process_score_update(state, new_t1, new_t2, self.max_spread)
                    if signal:
                        self._on_signal(signal)

    def run_rest_loop(self, poll_match_every: int = POLL_INTERVAL_MATCH,
                      poll_score_every: int = POLL_INTERVAL_MAP) -> None:
        """Main REST polling loop. Runs until KeyboardInterrupt."""
        log.info(f"Starting REST polling loop (match scan every {poll_match_every}s, "
                 f"score refresh every {poll_score_every}s, max spread {self.max_spread}c)")

        last_match_scan = 0

        while True:
            now = time.time()

            # Periodically scan for new live matches
            if now - last_match_scan >= poll_match_every:
                matches = fetch_live_valorant_matches()
                if matches:
                    log.info(f"Live Valorant matches: {len(matches)}")
                    for m in matches:
                        log.info(f"  Match {m['id']}: {m.get('slug','')}")
                else:
                    log.debug("No live Valorant matches currently")
                last_match_scan = now

            # Refresh scores for all tracked live matches
            with self._lock:
                active_match_ids = {s.match_id for s in self._live_states.values()
                                    if s.state == 'live'}

            for match_id in active_match_ids:
                # We need the full match object; reconstruct a minimal one
                mock_match = {'id': match_id, 'team1_id': 0, 'team2_id': 0, 'bo_type': 3}
                self._refresh_match(mock_match)

            # Also scan for newly started matches
            live_matches = fetch_live_valorant_matches()
            for m in live_matches:
                self._refresh_match(m)

            time.sleep(poll_score_every)

    def run_websocket(self) -> None:
        """
        Attempt WebSocket connection to wss://live.bo3.gg/ for real-time updates.
        Falls back to REST polling if WebSocket connection fails.

        NOTE: The exact message format is unknown without live network inspection.
        We try several common subscribe patterns and log all received messages to
        help reverse-engineer the protocol.
        """
        try:
            import websockets
            import asyncio
        except ImportError:
            log.warning("websockets not installed. Install with: pip install websockets")
            log.info("Falling back to REST polling")
            self.run_rest_loop()
            return

        import asyncio

        async def _ws_connect(match_ids: List[int]) -> None:
            async with websockets.connect(BO3_WS) as ws:
                log.info(f"WebSocket connected: {BO3_WS}")

                # Try multiple subscribe formats (reverse-engineered guesses)
                for match_id in match_ids:
                    for fmt in [
                        {"type": "subscribe", "topic": f"match:{match_id}"},
                        {"event": "subscribe", "data": {"match_id": match_id}},
                        {"action": "subscribe", "channel": "MatchChannel", "match_id": match_id},
                    ]:
                        await ws.send(json.dumps(fmt))
                        log.debug(f"Sent subscribe: {fmt}")

                async for raw_msg in ws:
                    try:
                        msg = json.loads(raw_msg)
                        log.debug(f"WS message: {json.dumps(msg)[:200]}")
                        # TODO: parse actual message format once observed in production
                        # Expected fields: match_id, game_id, team1_score, team2_score, round_num
                        self._handle_ws_message(msg)
                    except json.JSONDecodeError:
                        log.debug(f"WS non-JSON: {raw_msg[:100]}")

        async def _ws_main() -> None:
            live_matches = fetch_live_valorant_matches()
            match_ids = [m['id'] for m in live_matches]
            if not match_ids:
                log.info("No live matches to subscribe to")
                return
            try:
                await asyncio.wait_for(_ws_connect(match_ids), timeout=300)
            except Exception as e:
                log.warning(f"WebSocket error: {e}")

        asyncio.run(_ws_main())

    def _handle_ws_message(self, msg: dict) -> None:
        """
        Handle a WebSocket message from bo3.gg.

        TODO: populate this once the message format is observed in production.
        Suspected structure based on REST schema:
          {"type": "score_update", "match_id": 12345, "game_id": 678,
           "team1_score": 8, "team2_score": 7}
        """
        msg_type = msg.get('type') or msg.get('event') or msg.get('action', '')
        if 'score' in str(msg_type).lower() or 'update' in str(msg_type).lower():
            match_id = msg.get('match_id')
            game_id  = msg.get('game_id')
            if match_id and game_id:
                t1 = msg.get('team1_score', msg.get('score1', 0))
                t2 = msg.get('team2_score', msg.get('score2', 0))
                with self._lock:
                    key = (match_id, game_id)
                    if key in self._live_states:
                        signal = process_score_update(self._live_states[key], int(t1), int(t2),
                                                       self.max_spread)
                        if signal:
                            self._on_signal(signal)
        else:
            log.debug(f"Unhandled WS message type: {msg_type}")


# ─────────────────────────────────────────────────────────────────────────────
# Test mode: simulate score transitions
# ─────────────────────────────────────────────────────────────────────────────

def run_simulation(max_spread: float = 8.0) -> None:
    """
    Simulate a Valorant map 3 score sequence to test signal detection.
    Scenario: close match → 7-5 halftime → team2 wins second-half pistol at 7-6 →
              score closes to 10-9 → team1 wins OT pistol
    """
    print("\n=== SIMULATION MODE ===")
    print(f"Max spread: {max_spread}c\n")

    state = MapState(
        match_id=9999, game_id=1, map_number=3, map_name="Bind",
        team1_id=1, team2_id=2, team1_name="SEN", team2_name="C9",
        t1_rounds=0, t2_rounds=0, is_map3=True,
    )

    # Simulate score sequence: round-by-round
    # Format: (t1_after, t2_after) after each round
    score_sequence = [
        # First half: team1 wins 7-5
        (1,0),(2,0),(3,0),(3,1),(4,1),(4,2),(5,2),(6,2),(6,3),(7,3),(7,4),(7,5),
        # Round 13 (second-half pistol): team2 wins
        (7,6),
        # Second half continues: team2 on bonus, team1 eco → team2 wins streak
        (7,7),(7,8),(7,9),(8,9),
        # Score: 8-9, team1 fighting back
        (9,9),(10,9),  # team1 wins round 19 → score 10-9
        # Round 20: close finish
        (10,10),(11,10),(11,11),(12,11),(12,12),
        # OT: round 25 = OT pistol
        (13,12),(14,12),  # team1 wins OT
    ]

    signals_fired = 0
    for new_t1, new_t2 in score_sequence:
        prev_total = state.total_rounds
        round_num = new_t1 + new_t2
        print(f"  Round {round_num} complete | Score: {new_t1}-{new_t2}", end="")
        if _is_pistol_round(prev_total + 1):
            print(f" [PISTOL R{prev_total+1}]", end="")
        print()

        signal = process_score_update(state, new_t1, new_t2, max_spread)
        if signal:
            signals_fired += 1
            print(f"\n  *** SIGNAL: BUY {signal.gun_team_name} at {signal.score} ***")
            print(f"      Delta: +{signal.eco_delta:.2f}c  Type: {signal.signal_type}")
            print(f"      Neutral FV: {signal.map_fv_neutral:.3f}  Eco-adj FV: {signal.map_fv_eco_adj:.3f}")
            print(f"      {signal.kalshi_hint}\n")

    print(f"\nSimulation complete. Signals fired: {signals_fired}")
    print("(At 8c spread, signals expected only at high-leverage late-map score states)")


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='VCT live score poller for Kalshi eco-round strategy')
    parser.add_argument('--test',        action='store_true', help='Run simulation instead of live polling')
    parser.add_argument('--spread',      type=float, default=8.0, help='Max spread in cents (default: 8.0)')
    parser.add_argument('--websocket',   action='store_true', help='Use WebSocket instead of REST polling')
    parser.add_argument('--poll-match',  type=int, default=30, help='Seconds between match scans (default: 30)')
    parser.add_argument('--poll-score',  type=int, default=5,  help='Seconds between score refreshes (default: 5)')
    parser.add_argument('--verbose',     action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.test:
        run_simulation(max_spread=args.spread)
    elif args.websocket:
        poller = LivePoller(max_spread_cents=args.spread, use_websocket=True)
        try:
            poller.run_websocket()
        except KeyboardInterrupt:
            print(f"\nStopped. Total signals: {len(poller._signals)}")
    else:
        poller = LivePoller(max_spread_cents=args.spread)
        try:
            poller.run_rest_loop(
                poll_match_every=args.poll_match,
                poll_score_every=args.poll_score,
            )
        except KeyboardInterrupt:
            print(f"\nStopped. Total signals: {len(poller._signals)}")
