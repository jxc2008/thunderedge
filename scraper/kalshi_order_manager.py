"""
KalshiOrderManager — wires eco-round TradingSignals to Kalshi limit orders.

dry_run=True (default): logs what would happen but never calls the Kalshi API.
dry_run=False:          places real orders. Only used when --kalshi flag is set.

Position tracking:
  _positions   : ticker -> {side, count, avg_price}
  _open_orders : order_id -> order dict (returned by Kalshi on placement)
"""

import logging
import uuid
from typing import Optional, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from scraper.kalshi_client import KalshiClient
    from scraper.live_score_poller import TradingSignal

log = logging.getLogger(__name__)

# Default limit: 15 USD = 1500 cents
DEFAULT_MAX_POSITION_CENTS = 1500

# Minimum contracts per order — avoid placing 0-contract orders
MIN_CONTRACTS = 1


class KalshiOrderManager:
    """
    Translates eco-round TradingSignals into passive limit orders on Kalshi.

    Parameters
    ----------
    client : KalshiClient
        Authenticated Kalshi API client.
    max_position_cents : int
        Maximum dollars × 100 committed per ticker at any one time (default 1500).
    dry_run : bool
        When True (default) log intent but do NOT call the API.
    """

    def __init__(
        self,
        client: "KalshiClient",
        max_position_cents: int = DEFAULT_MAX_POSITION_CENTS,
        dry_run: bool = True,
    ) -> None:
        self._client = client
        self._max_position_cents = max_position_cents
        self._dry_run = dry_run
        self._positions: Dict[str, dict] = {}    # ticker -> {side, count, avg_price}
        self._open_orders: Dict[str, dict] = {}  # order_id -> order dict

        mode = "DRY-RUN" if dry_run else "LIVE"
        log.info(
            "KalshiOrderManager initialized [%s] | max_position=%d¢ per ticker",
            mode, max_position_cents,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def on_signal(self, signal: "TradingSignal", ticker: str) -> None:
        """
        Called when an eco-round signal fires.

        Strategy:
          1. Check current position — skip if already at max_position_cents.
          2. Fetch the current orderbook for the ticker.
          3. Place a passive limit buy at (yes_ask - 1) cents to penny the ask.
          4. Size = min(max_remaining_cents // price, available YES contracts at ask).
          5. Log the resulting order ID for tracking.

        We always buy YES contracts for the gun team winning.
        The caller is responsible for mapping the gun-team name to the correct
        Kalshi ticker before calling this method.

        Args:
            signal: TradingSignal produced by the live poller.
            ticker: Kalshi market ticker for the relevant map/match winner.
        """
        log.info(
            "[%s] Signal received for %s | gun_team=%s delta=+%.1f¢ EV=+%.1f¢",
            "DRY-RUN" if self._dry_run else "LIVE",
            ticker,
            signal.gun_team_name,
            signal.eco_delta,
            signal.taker_ev,
        )

        # --- 1. Position check ---
        pos = self._positions.get(ticker)
        if pos is not None:
            current_exposure = pos["count"] * pos["avg_price"]
            if current_exposure >= self._max_position_cents:
                log.info(
                    "  [%s] Already at max position in %s (%d¢). Skipping.",
                    ticker, current_exposure,
                )
                return

        # --- 2. Fetch orderbook ---
        if self._dry_run:
            # In dry-run mode we cannot (and should not) hit the API.
            # Use the signal's eco-adjusted FV as a proxy for the mid-price.
            estimated_ask = max(1, min(99, round(signal.map_fv_eco_adj * 100)))
            limit_price = max(1, estimated_ask - 1)
            available_at_ask = 10  # placeholder size
            log.info(
                "  [DRY-RUN] Would fetch orderbook for %s; "
                "estimated ask≈%d¢, limit=%d¢",
                ticker, estimated_ask, limit_price,
            )
        else:
            orderbook = self._client.get_orderbook(ticker)
            if orderbook is None:
                log.warning("  Could not fetch orderbook for %s. Skipping order.", ticker)
                return

            yes_ask, available_at_ask = _best_ask(orderbook)
            if yes_ask is None:
                log.warning("  No YES asks available in orderbook for %s. Skipping.", ticker)
                return

            # Penny the ask: place one cent below the best ask (passive fill)
            limit_price = max(1, yes_ask - 1)
            log.info(
                "  Orderbook best ask=%d¢ → limit=%d¢ (available=%d contracts)",
                yes_ask, limit_price, available_at_ask,
            )

        # --- 3. Size the order ---
        remaining_cents = self._max_position_cents
        if pos is not None:
            remaining_cents -= pos["count"] * pos["avg_price"]

        if limit_price <= 0:
            log.warning("  Calculated limit_price=%d¢ is invalid. Skipping.", limit_price)
            return

        size = remaining_cents // limit_price
        if available_at_ask:
            size = min(size, available_at_ask)
        size = int(size)

        if size < MIN_CONTRACTS:
            log.info(
                "  Calculated order size %d < minimum %d. Skipping.",
                size, MIN_CONTRACTS,
            )
            return

        client_order_id = f"eco-{signal.match_id}-m{signal.map_number}-r{signal.round_num}-{uuid.uuid4().hex[:8]}"

        log.info(
            "  %s limit BUY %d × YES @ %d¢ on %s [coid=%s]",
            "[DRY-RUN]" if self._dry_run else "PLACING",
            size, limit_price, ticker, client_order_id,
        )

        # --- 4. Place the order (or simulate) ---
        if self._dry_run:
            # Simulate an order fill for position tracking purposes
            order = {
                "order_id":        f"dry-{client_order_id}",
                "ticker":          ticker,
                "side":            "yes",
                "action":          "buy",
                "count":           size,
                "limit_price":     limit_price,
                "status":          "dry_run",
                "client_order_id": client_order_id,
            }
        else:
            order = self._client.place_order(
                ticker          = ticker,
                side            = "yes",
                action          = "buy",
                count           = size,
                limit_price     = limit_price,
                client_order_id = client_order_id,
            )
            if order is None:
                log.error("  Order placement failed for %s. See above errors.", ticker)
                return

        order_id = order.get("order_id") or order.get("id") or client_order_id
        self._open_orders[order_id] = order

        log.info(
            "  Order %s: %d × YES @ %d¢ on %s [status=%s]",
            order_id, size, limit_price, ticker, order.get("status", "unknown"),
        )

    def reconcile(self) -> None:
        """
        Poll open orders and update _positions on fills.

        Iterates over all tracked open orders, queries their status from the
        Kalshi API (or skips in dry_run mode), and promotes filled orders to
        the _positions dict.
        """
        if self._dry_run:
            log.debug("[DRY-RUN] reconcile() called — nothing to poll.")
            return

        to_remove: List[str] = []

        for order_id, cached_order in list(self._open_orders.items()):
            ticker = cached_order.get("ticker", "")
            # Kalshi GET /portfolio/orders/{order_id} — re-use _request via client
            refreshed = self._client._request("GET", f"/portfolio/orders/{order_id}")
            if refreshed is None:
                log.debug("  reconcile: could not fetch order %s", order_id)
                continue

            order = refreshed.get("order", refreshed)
            status = order.get("status", "")

            if status in ("filled", "executed"):
                filled_count = int(order.get("count_filled", order.get("count", 0)))
                fill_price   = int(order.get("limit_price", 0))
                log.info(
                    "  Order %s FILLED: %d × YES @ %d¢ on %s",
                    order_id, filled_count, fill_price, ticker,
                )
                self._update_position(ticker, "yes", filled_count, fill_price)
                to_remove.append(order_id)

            elif status in ("canceled", "cancelled", "expired"):
                log.info("  Order %s is %s — removing from tracking.", order_id, status)
                to_remove.append(order_id)

        for oid in to_remove:
            self._open_orders.pop(oid, None)

    def close_position(self, ticker: str) -> None:
        """
        Market-sell (or best-limit-sell) any open YES position in ticker.

        In dry_run mode, just logs the action.
        """
        pos = self._positions.get(ticker)
        if not pos or pos.get("count", 0) <= 0:
            log.info("[close_position] No open position in %s.", ticker)
            return

        count = pos["count"]
        log.info(
            "  %s SELL %d × YES on %s (close position)",
            "[DRY-RUN]" if self._dry_run else "PLACING",
            count, ticker,
        )

        if self._dry_run:
            self._positions.pop(ticker, None)
            return

        # Use limit_price=1 to simulate a market sell (fills against best bid)
        order = self._client.place_order(
            ticker      = ticker,
            side        = "yes",
            action      = "sell",
            count       = count,
            limit_price = 1,
        )
        if order:
            log.info(
                "  Close order placed: %s", order.get("order_id") or order.get("id")
            )
            self._positions.pop(ticker, None)
        else:
            log.error("  Failed to place close order for %s.", ticker)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_position(self, ticker: str, side: str, count: int, price: int) -> None:
        """Update (or create) a position entry after a fill."""
        existing = self._positions.get(ticker)
        if existing is None:
            self._positions[ticker] = {"side": side, "count": count, "avg_price": price}
        else:
            # Compute new average price
            total_count = existing["count"] + count
            avg = (existing["count"] * existing["avg_price"] + count * price) // total_count
            self._positions[ticker] = {"side": side, "count": total_count, "avg_price": avg}

        log.info(
            "  Position updated: %s | %s × %d @ avg %d¢",
            ticker, side, self._positions[ticker]["count"], self._positions[ticker]["avg_price"],
        )


# ---------------------------------------------------------------------------
# Orderbook helpers
# ---------------------------------------------------------------------------

def _best_ask(orderbook: dict):
    """
    Extract the best YES ask price and available contracts from an orderbook dict.

    Kalshi orderbook format (v2):
      {
        "yes": [[price_cents, contracts], ...],   # asks, ascending price
        "no":  [[price_cents, contracts], ...],   # bids (mirror)
      }

    Returns (best_ask_price: int, available_contracts: int) or (None, 0).
    """
    yes_levels = orderbook.get("yes", [])
    if not yes_levels:
        return None, 0

    # yes[] entries are [price, size]; lowest price = best ask
    try:
        # Sort ascending by price just in case
        sorted_asks = sorted(yes_levels, key=lambda x: x[0])
        best = sorted_asks[0]
        price = int(best[0])
        size  = int(best[1])
        return price, size
    except (IndexError, TypeError, ValueError):
        return None, 0
