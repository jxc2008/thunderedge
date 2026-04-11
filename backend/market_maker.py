"""
backend/market_maker.py

Core market-making engine for Kalshi Valorant series-winner markets.

Quotes passive limit orders around a theoretical probability (theo) derived
from TheoEngine.  Supports dry-run mode (no real orders placed).

Risk controls enforced:
  - dry_run=True by default; real orders only with dry_run=False.
  - Max total exposure per market: max_position cents.
  - No quotes within 5 minutes of market close_time.
  - All open orders cancelled on KeyboardInterrupt.
  - Automatic 60-second pause after 3 consecutive API errors.
"""

import logging
import time
import uuid
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from scraper.kalshi_client import KalshiClient, KalshiAPIError
from backend.theo_engine import TheoEngine

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Data structures
# ------------------------------------------------------------------


@dataclass
class Quote:
    """Represents one resting limit order."""

    ticker: str
    side: str       # 'yes' or 'no'
    action: str     # 'buy' or 'sell'
    price: int      # cents (1-99)
    count: int      # number of contracts
    order_id: Optional[str] = None
    placed_at: Optional[float] = None


# ------------------------------------------------------------------
# MarketMaker
# ------------------------------------------------------------------


class MarketMaker:
    """
    Quotes around a theo price on Kalshi Valorant series markets.

    Args:
        client:       Authenticated KalshiClient instance.
        theo_engine:  TheoEngine instance.
        quote_width:  Half-spread in cents (each side of theo).
        max_position: Maximum cents exposure per market.
        min_edge:     Minimum edge (|theo - mid|) in cents required to quote.
        dry_run:      If True, log orders but do NOT send them to Kalshi.
    """

    # Stale quote threshold in seconds.
    _QUOTE_TTL = 30.0
    # Theo-move threshold (cents) that triggers a re-quote.
    _THEO_MOVE_CANCEL = 3
    # Minutes before close_time to stop quoting.
    _CLOSE_BUFFER_MINUTES = 5
    # API error count before pausing.
    _MAX_ERRORS_BEFORE_PAUSE = 3
    # Pause duration (seconds) after too many errors.
    _ERROR_PAUSE_SECONDS = 60

    def __init__(
        self,
        client: KalshiClient,
        theo_engine: TheoEngine,
        quote_width: int = 4,
        max_position: int = 5000,
        min_edge: int = 2,
        dry_run: bool = True,
    ):
        self.client = client
        self.theo = theo_engine
        self.quote_width = quote_width
        self.max_position = max_position
        self.min_edge = min_edge
        self.dry_run = dry_run

        # Active quotes keyed by ticker → {'bid': Quote, 'ask': Quote}
        self._active_quotes: Dict[str, Dict[str, Quote]] = {}
        # Last theo seen for a ticker (cents).
        self._last_theo: Dict[str, float] = {}
        # Consecutive API error counter.
        self._error_streak: int = 0

    # ------------------------------------------------------------------
    # Quoting logic
    # ------------------------------------------------------------------

    def _compute_quotes(
        self,
        ticker: str,
        theo: float,
        yes_bid: int,
        yes_ask: int,
    ) -> Tuple[Optional[Quote], Optional[Quote]]:
        """
        Given theo (0.0–1.0) and current best bid/ask, decide where to quote.

        Strategy:
          - Convert theo to cents: theo_c = round(theo * 100).
          - Compute mid = (yes_bid + yes_ask) / 2.
          - If edge = |theo_c - mid| < min_edge: don't quote.
          - If theo_c > yes_ask:  market underprices YES → penny ask
              sell YES at (yes_ask - 1) → short YES = long NO = positive EV
          - If theo_c < yes_bid:  market overprices YES → penny bid
              buy  YES at (yes_bid + 1) → long YES = positive EV
          - Otherwise (within quote_width of mid): passive two-sided quote
              bid at max(1, theo_c - quote_width)
              ask at min(99, theo_c + quote_width)

        Returns:
            (bid_quote, ask_quote) — either may be None if not quoted.
        """
        theo_c = round(theo * 100)
        mid = (yes_bid + yes_ask) / 2.0
        edge = abs(theo_c - mid)

        if edge < self.min_edge:
            logger.debug(
                "%s: edge %.1f < min_edge %d — not quoting", ticker, edge, self.min_edge
            )
            return None, None

        # Contract sizing: 1 contract = 1 cent risk; keep within max_position.
        count = max(1, self.max_position // 100)

        bid_quote: Optional[Quote] = None
        ask_quote: Optional[Quote] = None

        if theo_c > yes_ask:
            # Market is BELOW our theo → penny the ask (sell YES dear).
            ask_price = max(1, yes_ask - 1)
            ask_quote = Quote(
                ticker=ticker,
                side="yes",
                action="sell",
                price=ask_price,
                count=count,
            )
            logger.debug(
                "%s: theo %dc > ask %dc → penny ask at %dc",
                ticker, theo_c, yes_ask, ask_price,
            )

        elif theo_c < yes_bid:
            # Market is ABOVE our theo → penny the bid (buy YES cheap).
            bid_price = min(99, yes_bid + 1)
            bid_quote = Quote(
                ticker=ticker,
                side="yes",
                action="buy",
                price=bid_price,
                count=count,
            )
            logger.debug(
                "%s: theo %dc < bid %dc → penny bid at %dc",
                ticker, theo_c, yes_bid, bid_price,
            )

        else:
            # Passive two-sided market making around theo.
            bid_price = max(1, theo_c - self.quote_width)
            ask_price = min(99, theo_c + self.quote_width)

            if bid_price < ask_price:  # sanity check
                bid_quote = Quote(
                    ticker=ticker,
                    side="yes",
                    action="buy",
                    price=bid_price,
                    count=count,
                )
                ask_quote = Quote(
                    ticker=ticker,
                    side="yes",
                    action="sell",
                    price=ask_price,
                    count=count,
                )
                logger.debug(
                    "%s: passive quotes bid=%dc ask=%dc (theo=%dc)",
                    ticker, bid_price, ask_price, theo_c,
                )

        return bid_quote, ask_quote

    # ------------------------------------------------------------------
    # Order placement / cancellation
    # ------------------------------------------------------------------

    def _place_quote(self, quote: Quote) -> bool:
        """
        Place a limit order for the given Quote.

        Sets quote.order_id and quote.placed_at on success.
        Returns True on success, False on failure.
        """
        client_oid = str(uuid.uuid4())
        if self.dry_run:
            quote.order_id = f"DRY_{client_oid[:8]}"
            quote.placed_at = time.time()
            logger.info(
                "[DRY-RUN] Would place order: %s %s %s @ %dc x%d",
                quote.ticker, quote.action.upper(), quote.side.upper(),
                quote.price, quote.count,
            )
            return True

        try:
            order = self.client.place_order(
                ticker=quote.ticker,
                side=quote.side,
                action=quote.action,
                count=quote.count,
                limit_price=quote.price,
                client_order_id=client_oid,
            )
            quote.order_id = order.get("order_id") or order.get("id", client_oid)
            quote.placed_at = time.time()
            logger.info(
                "Placed order %s: %s %s %s @ %dc x%d",
                quote.order_id, quote.ticker,
                quote.action.upper(), quote.side.upper(),
                quote.price, quote.count,
            )
            self._error_streak = 0
            return True
        except KalshiAPIError as exc:
            self._error_streak += 1
            logger.error("Failed to place order for %s: %s", quote.ticker, exc)
            return False

    def _cancel_quote(self, quote: Quote) -> None:
        """Cancel a resting quote.  No-op in dry-run."""
        if not quote.order_id:
            return
        if self.dry_run:
            logger.info("[DRY-RUN] Would cancel order %s", quote.order_id)
            return
        try:
            self.client.cancel_order(quote.order_id)
            logger.info("Cancelled order %s", quote.order_id)
            self._error_streak = 0
        except KalshiAPIError as exc:
            self._error_streak += 1
            logger.warning("Could not cancel order %s: %s", quote.order_id, exc)

    def _cancel_all_for_ticker(self, ticker: str) -> None:
        """Cancel both active quotes (bid + ask) for a ticker."""
        mkt_quotes = self._active_quotes.pop(ticker, {})
        for leg, q in mkt_quotes.items():
            if q and q.order_id:
                self._cancel_quote(q)

    def cancel_all_orders(self) -> None:
        """Cancel every tracked open order.  Called on shutdown."""
        tickers = list(self._active_quotes.keys())
        for ticker in tickers:
            self._cancel_all_for_ticker(ticker)

    # ------------------------------------------------------------------
    # Staleness checks
    # ------------------------------------------------------------------

    def _quotes_are_stale(self, ticker: str, theo_c: float) -> bool:
        """
        Return True if existing quotes should be cancelled and re-quoted.

        Conditions:
          - Any quote older than _QUOTE_TTL seconds.
          - Theo has moved more than _THEO_MOVE_CANCEL cents since last quote.
        """
        mkt_quotes = self._active_quotes.get(ticker, {})
        now = time.time()
        for q in mkt_quotes.values():
            if q and q.placed_at and (now - q.placed_at) > self._QUOTE_TTL:
                return True

        last_theo = self._last_theo.get(ticker)
        if last_theo is not None and abs(theo_c - last_theo) >= self._THEO_MOVE_CANCEL:
            return True

        return False

    @staticmethod
    def _is_near_close(close_time_str: str) -> bool:
        """Return True if market closes within _CLOSE_BUFFER_MINUTES minutes."""
        if not close_time_str:
            return False
        try:
            # Kalshi uses ISO-8601 UTC, e.g. '2024-04-10T18:30:00Z'
            close_dt = datetime.fromisoformat(
                close_time_str.replace("Z", "+00:00")
            )
            now_utc = datetime.now(timezone.utc)
            delta_minutes = (close_dt - now_utc).total_seconds() / 60
            return delta_minutes < MarketMaker._CLOSE_BUFFER_MINUTES
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Main update loop (single market)
    # ------------------------------------------------------------------

    def update_market(
        self,
        ticker: str,
        team_a: str,
        team_b: str,
        map_pool: Optional[List[str]] = None,
        team_a_sides: Optional[Dict[str, str]] = None,
        pre_veto: bool = False,
        pre_veto_theo: Optional[float] = None,
    ) -> None:
        """
        Run one quoting cycle for a single market.

        Steps:
          1. Fetch current market data.
          2. Guard: skip if near close or API error streak too high.
          3. Compute theo from TheoEngine using map_pool + sides.
             If pre_veto=True, use pre_veto_theo directly with 2× spread and
             half position size (wider, smaller to reflect map pool uncertainty).
          4. Cancel stale quotes if needed.
          5. Place new quotes if edge exists.
          6. Log state.

        Args:
            ticker:        Kalshi market ticker.
            team_a:        Team A name (YES side).
            team_b:        Team B name (NO side).
            map_pool:      Ordered list of maps (from pick/ban or top predicted pool).
            team_a_sides:  {map_name: 'atk'|'def'} for team_a's starting side.
            pre_veto:      True when using predicted map pool (not confirmed).
            pre_veto_theo: E[theo] from PickBanModel.predict() — used directly.
        """
        # --- Fetch market ---
        try:
            mkt = self.client.get_market(ticker)
            self._error_streak = 0
        except KalshiAPIError as exc:
            self._error_streak += 1
            logger.error("get_market(%s) failed: %s", ticker, exc)
            return

        # --- Guards ---
        if self._error_streak >= self._MAX_ERRORS_BEFORE_PAUSE:
            logger.warning(
                "Error streak %d — pausing quoting for %ds",
                self._error_streak, self._ERROR_PAUSE_SECONDS,
            )
            time.sleep(self._ERROR_PAUSE_SECONDS)
            self._error_streak = 0
            return

        if MarketMaker._is_near_close(mkt.get("close_time", "")):
            logger.info("%s: near close — skipping quotes", ticker)
            self._cancel_all_for_ticker(ticker)
            return

        if mkt.get("status") != "open":
            logger.info("%s: market status=%s — skipping", ticker, mkt.get("status"))
            return

        yes_bid: int = mkt.get("yes_bid", 0) or 0
        yes_ask: int = mkt.get("yes_ask", 100) or 100

        # --- Theo ---
        if pre_veto and pre_veto_theo is not None:
            theo_prob = pre_veto_theo
            data_w, conf = 0.0, 'PRE'
        elif map_pool:
            theo_prob, data_w, conf = self.theo.series_theo(
                team_a, team_b, map_pool, team_a_sides or {}, yes_ask
            )
        else:
            logger.info('%s: no map pool yet — skipping', ticker)
            return

        theo_c = round(theo_prob * 100)

        logger.info(
            "%s | %s vs %s | theo=%dc (%s) | bid=%dc ask=%dc%s",
            ticker, team_a, team_b, theo_c, conf, yes_bid, yes_ask,
            ' [PRE-VETO]' if pre_veto else '',
        )

        # --- Cancel stale quotes ---
        if self._quotes_are_stale(ticker, theo_c):
            logger.debug("%s: cancelling stale quotes", ticker)
            self._cancel_all_for_ticker(ticker)

        # --- Skip if already quoted (not stale) ---
        if ticker in self._active_quotes and self._active_quotes[ticker]:
            logger.debug("%s: quotes still live — skipping placement", ticker)
            return

        # --- Compute new quotes (wider spread + smaller size for pre-veto) ---
        effective_width    = self.quote_width * 2 if pre_veto else self.quote_width
        effective_max_pos  = self.max_position // 2 if pre_veto else self.max_position

        saved_width   = self.quote_width
        saved_max_pos = self.max_position
        self.quote_width   = effective_width
        self.max_position  = effective_max_pos

        bid_q, ask_q = self._compute_quotes(ticker, theo_prob, yes_bid, yes_ask)

        self.quote_width  = saved_width
        self.max_position = saved_max_pos

        new_quotes: Dict[str, Optional[Quote]] = {}
        for leg, q in (("bid", bid_q), ("ask", ask_q)):
            if q is not None:
                success = self._place_quote(q)
                if success:
                    new_quotes[leg] = q

        if new_quotes:
            self._active_quotes[ticker] = new_quotes
            self._last_theo[ticker] = float(theo_c)

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_teams_from_title(title: str) -> Tuple[str, str]:
        """
        Extract team names from a Kalshi market title.

        Common formats:
          "Team A vs Team B: Series Winner"
          "Team A vs. Team B"
        Returns ('Team A', 'Team B') or ('Unknown', 'Unknown') on failure.
        """
        # Try 'vs' or 'vs.' separator.
        match = re.search(r"^(.+?)\s+vs\.?\s+(.+?)(?::\s*|$)", title, re.IGNORECASE)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return "Unknown", "Unknown"

    def run(self, poll_interval: int = 10) -> None:
        """
        Main quoting loop.

        Discovers open Valorant markets on Kalshi, then continuously quotes
        each one until a KeyboardInterrupt.

        Args:
            poll_interval: Seconds between full market scans.
        """
        logger.info(
            "MarketMaker starting — dry_run=%s, quote_width=%dc, min_edge=%dc",
            self.dry_run, self.quote_width, self.min_edge,
        )

        try:
            while True:
                # Discover markets.
                try:
                    markets = self.client.find_valorant_markets()
                    self._error_streak = 0
                except KalshiAPIError as exc:
                    self._error_streak += 1
                    logger.error("find_valorant_markets failed: %s", exc)
                    markets = []

                if not markets:
                    logger.info("No open Valorant markets found — sleeping %ds", poll_interval)
                else:
                    logger.info("Found %d Valorant market(s)", len(markets))
                    for mkt in markets:
                        ticker = mkt["ticker"]
                        team_a, team_b = self._parse_teams_from_title(mkt.get("title", ""))
                        try:
                            self.update_market(ticker, team_a, team_b)
                        except Exception as exc:
                            logger.exception(
                                "Unexpected error updating market %s: %s", ticker, exc
                            )

                # Error-streak pause check (covers discovery errors).
                if self._error_streak >= self._MAX_ERRORS_BEFORE_PAUSE:
                    logger.warning(
                        "Error streak %d — pausing %ds",
                        self._error_streak, self._ERROR_PAUSE_SECONDS,
                    )
                    time.sleep(self._ERROR_PAUSE_SECONDS)
                    self._error_streak = 0
                else:
                    time.sleep(poll_interval)

        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received — cancelling all open orders…")
            self.cancel_all_orders()
            logger.info("All orders cancelled.  Exiting.")
