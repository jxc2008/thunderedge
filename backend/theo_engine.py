"""
backend/theo_engine.py

Two-tier theoretical probability engine for Valorant series-winner markets.

Tier 1 (primary):  historical win rates from moneyline_matches DB table.
Tier 2 (fallback): Kalshi-implied probability (yes_ask) when DB is empty.
"""

import sqlite3
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class TheoEngine:
    """
    Compute theoretical series-win probabilities for Valorant BO3 matches.

    Usage:
        engine = TheoEngine(db_path='data/valorant_stats.db')
        prob   = engine.series_win_prob('Team Liquid', 'NaVi')
        conf   = engine.confidence('Team Liquid', 'NaVi')
    """

    # Minimum matches a team must have for Tier-1 data to be considered reliable.
    _MED_THRESHOLD = 5
    _HIGH_THRESHOLD = 20

    def __init__(self, db_path: str = "data/valorant_stats.db"):
        self.db_path = db_path
        self._team_stats: Dict[str, Dict] = {}  # name → {wins, matches}
        self._loaded = False

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_team_stats(self) -> None:
        """
        Load win/loss records from the moneyline_matches table.

        Populates self._team_stats with:
            { team_name: { 'wins': int, 'matches': int } }
        """
        self._team_stats = {}
        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT team1, team2, winner FROM moneyline_matches WHERE winner IS NOT NULL"
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception as exc:  # DB missing / table missing
            logger.warning("TheoEngine: could not load team stats: %s", exc)
            self._loaded = True
            return

        for row in rows:
            t1, t2, winner = row["team1"], row["team2"], row["winner"]
            for team in (t1, t2):
                if team not in self._team_stats:
                    self._team_stats[team] = {"wins": 0, "matches": 0}
                self._team_stats[team]["matches"] += 1
            if winner in self._team_stats:
                self._team_stats[winner]["wins"] += 1

        logger.info(
            "TheoEngine: loaded stats for %d teams (%d match records)",
            len(self._team_stats),
            len(rows),
        )
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._load_team_stats()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def team_win_rate(self, team: str) -> float:
        """
        Overall win rate for *team*.  Returns 0.5 if the team is unknown
        or has no recorded matches.
        """
        self._ensure_loaded()
        stats = self._team_stats.get(team)
        if not stats or stats["matches"] == 0:
            return 0.5
        return stats["wins"] / stats["matches"]

    def series_win_prob(self, team_a: str, team_b: str) -> float:
        """
        P(team_a wins a best-of-3 series).

        Method:
          1. Compute each team's historical win rate.
          2. Normalise to get per-map win probability p_map.
          3. Apply Markov:
               P(2-0) = p^2
               P(2-1) = 2 * p^2 * (1-p)   [win map3 after split]
          4. Return P(2-0) + P(2-1).

        Falls back to 0.5 if both teams are unknown.

        Args:
            team_a: Name string for team A (same spelling as DB).
            team_b: Name string for team B.

        Returns:
            Probability in [0, 1].
        """
        self._ensure_loaded()

        wr_a = self.team_win_rate(team_a)
        wr_b = self.team_win_rate(team_b)

        # If both default to 0.5 we get exactly 0.5 — fine.
        total = wr_a + wr_b
        if total == 0:
            return 0.5

        p_map = wr_a / total  # normalised head-to-head map win prob

        p_2_0 = p_map ** 2
        p_2_1 = 2 * (p_map ** 2) * (1 - p_map)
        return p_2_0 + p_2_1

    def series_win_prob_with_fallback(
        self,
        team_a: str,
        team_b: str,
        kalshi_yes_ask: Optional[int] = None,
    ) -> Tuple[float, str]:
        """
        Series win probability with two-tier fallback logic.

        Tier 1: DB-derived if either team has meaningful data.
        Tier 2: Kalshi-implied (yes_ask / 100) with a tiny alpha nudge
                toward DB win rate when partial data is available.

        Args:
            team_a:          Team A name.
            team_b:          Team B name.
            kalshi_yes_ask:  Current ask price in cents (1–99), used for fallback.

        Returns:
            (probability, tier_used)  where tier_used is 'tier1' or 'tier2'.
        """
        self._ensure_loaded()

        stats_a = self._team_stats.get(team_a, {})
        stats_b = self._team_stats.get(team_b, {})
        matches_a = stats_a.get("matches", 0)
        matches_b = stats_b.get("matches", 0)

        if matches_a >= self._MED_THRESHOLD or matches_b >= self._MED_THRESHOLD:
            return self.series_win_prob(team_a, team_b), "tier1"

        # --- Tier 2 fallback ---
        if kalshi_yes_ask is None:
            return 0.5, "tier2"

        market_prob = kalshi_yes_ask / 100.0

        # Small alpha: if we have *any* data, nudge toward our estimate.
        if matches_a > 0 or matches_b > 0:
            our_est = self.series_win_prob(team_a, team_b)
            alpha = min((matches_a + matches_b) / (2 * self._MED_THRESHOLD), 0.2)
            blended = (1 - alpha) * market_prob + alpha * our_est
            return blended, "tier2"

        return market_prob, "tier2"

    def confidence(self, team_a: str, team_b: str) -> str:
        """
        Qualitative confidence label based on sample sizes.

        Returns:
            'HIGH'  – both teams have >= _HIGH_THRESHOLD matches
            'MED'   – both teams have >= _MED_THRESHOLD matches
            'LOW'   – otherwise
        """
        self._ensure_loaded()

        stats_a = self._team_stats.get(team_a, {"matches": 0})
        stats_b = self._team_stats.get(team_b, {"matches": 0})
        m_a = stats_a["matches"]
        m_b = stats_b["matches"]

        if m_a >= self._HIGH_THRESHOLD and m_b >= self._HIGH_THRESHOLD:
            return "HIGH"
        if m_a >= self._MED_THRESHOLD and m_b >= self._MED_THRESHOLD:
            return "MED"
        return "LOW"
