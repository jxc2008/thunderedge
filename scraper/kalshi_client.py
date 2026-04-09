"""
scraper/kalshi_client.py

Kalshi REST API client with RSA-signed authentication.
Auth scheme:
  - Key ID:      KALSHI_KEY_ID env var
  - Private key: path from KALSHI_PRIVATE_KEY_PATH env var
  - Signature:   PKCS1v15 SHA-256 over f"{timestamp_ms} {METHOD} {path}"
  - Headers:     KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP, KALSHI-ACCESS-SIGNATURE
"""

import os
import time
import base64
import hashlib
import logging
from typing import Dict, List, Optional, Any

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"


class KalshiAPIError(Exception):
    """Raised when Kalshi returns a non-2xx response."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Kalshi API error {status_code}: {message}")


class KalshiClient:
    """
    Thin wrapper around the Kalshi trading API v2.

    Usage:
        client = KalshiClient()
        markets = client.find_valorant_markets()
    """

    def __init__(
        self,
        key_id: Optional[str] = None,
        private_key_path: Optional[str] = None,
        base_url: str = BASE_URL,
    ):
        self.key_id = key_id or os.environ.get("KALSHI_KEY_ID", "")
        pem_path = private_key_path or os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")

        if not self.key_id:
            raise ValueError("KALSHI_KEY_ID must be set (env var or constructor arg)")
        if not pem_path:
            raise ValueError(
                "KALSHI_PRIVATE_KEY_PATH must be set (env var or constructor arg)"
            )

        with open(pem_path, "rb") as f:
            self._private_key = serialization.load_pem_private_key(
                f.read(), password=None, backend=default_backend()
            )

        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _timestamp_ms(self) -> str:
        """Current time as milliseconds-since-epoch string."""
        return str(int(time.time() * 1000))

    def _sign(self, method: str, path: str) -> Dict[str, str]:
        """
        Build authentication headers for a request.

        Signed message: f"{timestamp_ms} {METHOD} {path}"
        Signature is PKCS1v15 with SHA-256, base64-encoded.
        """
        ts = self._timestamp_ms()
        message = f"{ts} {method.upper()} {path}".encode("utf-8")
        signature = self._private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
        sig_b64 = base64.b64encode(signature).decode("utf-8")
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": sig_b64,
        }

    # ------------------------------------------------------------------
    # Low-level request
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        json: Optional[Dict] = None,
    ) -> Any:
        """
        Execute a signed HTTP request and return the parsed JSON body.
        Raises KalshiAPIError on non-2xx responses.
        """
        headers = self._sign(method, path)
        url = self.base_url + path
        resp = self._session.request(
            method, url, params=params, json=json, headers=headers, timeout=10
        )
        if not resp.ok:
            raise KalshiAPIError(resp.status_code, resp.text)
        return resp.json()

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_markets(
        self,
        series_ticker: Optional[str] = None,
        status: str = "open",
        limit: int = 100,
    ) -> List[Dict]:
        """
        Return a list of markets.

        Args:
            series_ticker: Optional series ticker to filter by.
            status: Market status filter (default 'open').
            limit: Max results per call (Kalshi max is 200).

        Returns:
            List of raw market dicts from the API.
        """
        params: Dict[str, Any] = {"status": status, "limit": limit}
        if series_ticker:
            params["series_ticker"] = series_ticker

        data = self._request("GET", "/markets", params=params)
        return data.get("markets", [])

    def get_market(self, ticker: str) -> Dict:
        """
        Fetch a single market and return a normalised dict.

        Returns:
            {
                yes_bid: int (cents),
                yes_ask: int (cents),
                last_price: int | None,
                volume: int,
                status: str,
                title: str,
                close_time: str,
            }
        """
        data = self._request("GET", f"/markets/{ticker}")
        mkt = data.get("market", data)
        return {
            "yes_bid": mkt.get("yes_bid", 0),
            "yes_ask": mkt.get("yes_ask", 100),
            "last_price": mkt.get("last_price"),
            "volume": mkt.get("volume", 0),
            "status": mkt.get("status", ""),
            "title": mkt.get("title", ""),
            "close_time": mkt.get("close_time", ""),
            "ticker": ticker,
        }

    def get_orderbook(self, ticker: str) -> Dict:
        """
        Fetch the full orderbook for a market.

        Returns:
            {
                yes: [[price, size], ...],   # descending by price
                no:  [[price, size], ...],   # descending by price
            }
        """
        data = self._request("GET", f"/markets/{ticker}/orderbook")
        book = data.get("orderbook", data)
        return {
            "yes": book.get("yes", []),
            "no": book.get("no", []),
        }

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def place_order(
        self,
        ticker: str,
        side: str,
        action: str,
        count: int,
        limit_price: int,
        client_order_id: Optional[str] = None,
    ) -> Dict:
        """
        Place a limit order.

        Args:
            ticker:          Market ticker (e.g. 'VCSERIES-TEAMAVTEAMB-2024').
            side:            'yes' or 'no'.
            action:          'buy' or 'sell'.
            count:           Number of contracts.
            limit_price:     Price in cents (1-99).
            client_order_id: Optional idempotency key.

        Returns:
            Order dict from the API.
        """
        body: Dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "count": count,
            "limit_price": limit_price,
            "type": "limit",
        }
        if client_order_id:
            body["client_order_id"] = client_order_id

        data = self._request("POST", "/portfolio/orders", json=body)
        return data.get("order", data)

    def cancel_order(self, order_id: str) -> Dict:
        """
        Cancel an open order.

        Returns:
            The cancelled order dict from the API.
        """
        data = self._request("DELETE", f"/portfolio/orders/{order_id}")
        return data.get("order", data)

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------

    def get_positions(self) -> List[Dict]:
        """
        Return all current positions.

        Returns:
            List of position dicts (ticker, side, quantity, market_exposure, …).
        """
        data = self._request("GET", "/portfolio/positions")
        return data.get("market_positions", [])

    def get_balance(self) -> Dict:
        """
        Return account balance information.

        Returns:
            Dict with at least {'balance': int} (cents).
        """
        data = self._request("GET", "/portfolio/balance")
        return data

    # ------------------------------------------------------------------
    # Valorant market discovery
    # ------------------------------------------------------------------

    def find_valorant_markets(self) -> List[Dict]:
        """
        Find open VCT/Valorant series-winner markets.

        Searches for markets whose title contains common Valorant-tournament
        keywords.  Returns a list of normalised market dicts (same shape as
        get_market()).

        Returns:
            List of market dicts for open Valorant series markets.
        """
        keywords = ["valorant", "vct", "vcs", "vcl", "challengers", "masters", "champions"]
        results = []
        seen: set = set()

        for kw in keywords:
            try:
                raw_markets = self._request(
                    "GET",
                    "/markets",
                    params={"status": "open", "limit": 200, "search": kw},
                )
                for mkt in raw_markets.get("markets", []):
                    ticker = mkt.get("ticker", "")
                    if ticker in seen:
                        continue
                    title_lower = (mkt.get("title", "") + mkt.get("series_ticker", "")).lower()
                    if any(k in title_lower for k in keywords):
                        seen.add(ticker)
                        results.append({
                            "yes_bid": mkt.get("yes_bid", 0),
                            "yes_ask": mkt.get("yes_ask", 100),
                            "last_price": mkt.get("last_price"),
                            "volume": mkt.get("volume", 0),
                            "status": mkt.get("status", ""),
                            "title": mkt.get("title", ""),
                            "close_time": mkt.get("close_time", ""),
                            "ticker": ticker,
                        })
            except KalshiAPIError as exc:
                logger.warning("find_valorant_markets: search '%s' failed: %s", kw, exc)

        return results
