"""
Kalshi API client for placing limit orders on Valorant match-winner markets.

Auth: RSA-signed requests (PKCS1v15 / SHA-256).
  Required env vars:
    KALSHI_KEY_ID          — API key UUID
    KALSHI_PRIVATE_KEY_PATH — path to .pem file containing the RSA private key

Usage:
    from scraper.kalshi_client import KalshiClient
    client = KalshiClient.from_env()
    markets = client.find_valorant_markets()
"""

import os
import time
import base64
import json
import logging
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any

# Load .env file if present (no-op when env vars are already set)
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on env vars being set externally

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional import — cryptography must be installed (pip install cryptography)
# ---------------------------------------------------------------------------
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False
    log.warning(
        "cryptography library not installed. "
        "Run: pip install cryptography\n"
        "KalshiClient will not function until it is installed."
    )


class KalshiClient:
    BASE = "https://trading-api.kalshi.com/trade-api/v2"

    # Kalshi series tickers to probe for Valorant markets (in priority order)
    _VALORANT_SERIES = ["VGAMES", "VCT", "VALORANT"]

    def __init__(self, key_id: str, private_key_path: str) -> None:
        """
        Initialize the client.

        Args:
            key_id:            Kalshi API key UUID.
            private_key_path:  Path to the RSA private key .pem file.
        """
        if not _CRYPTO_AVAILABLE:
            raise RuntimeError(
                "cryptography library is required. Install with: pip install cryptography"
            )
        if not key_id:
            raise ValueError("key_id must not be empty")
        if not private_key_path:
            raise ValueError("private_key_path must not be empty")

        self._key_id = key_id

        try:
            with open(private_key_path, "rb") as fh:
                self._private_key = serialization.load_pem_private_key(
                    fh.read(), password=None, backend=default_backend()
                )
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Kalshi private key not found at: {private_key_path}\n"
                "Set KALSHI_PRIVATE_KEY_PATH to the correct .pem file path."
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to load Kalshi private key: {exc}") from exc

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "KalshiClient":
        """
        Construct a KalshiClient from environment variables.

        Required env vars:
          KALSHI_KEY_ID            — API key UUID
          KALSHI_PRIVATE_KEY_PATH  — path to .pem file
        """
        key_id = os.environ.get("KALSHI_KEY_ID")
        if not key_id:
            raise EnvironmentError(
                "KALSHI_KEY_ID environment variable is not set. "
                "Export your Kalshi API key UUID before running."
            )

        pem_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
        if not pem_path:
            raise EnvironmentError(
                "KALSHI_PRIVATE_KEY_PATH environment variable is not set. "
                "Export the path to your RSA private key .pem file before running."
            )

        return cls(key_id=key_id, private_key_path=pem_path)

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _sign(self, method: str, path: str) -> Dict[str, str]:
        """
        Build and return the Kalshi authentication headers for a request.

        The signed message is: "{timestamp_ms} {METHOD} {path}"
        where timestamp_ms is milliseconds since epoch (as a string).
        """
        timestamp = str(int(time.time() * 1000))
        message = f"{timestamp} {method.upper()} {path}"
        signature = self._private_key.sign(
            message.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        sig_b64 = base64.b64encode(signature).decode("utf-8")
        return {
            "KALSHI-ACCESS-KEY":       self._key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": sig_b64,
        }

    # ------------------------------------------------------------------
    # Low-level HTTP
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Optional[Any]:
        """
        Make a signed HTTP request to the Kalshi API.

        Returns the parsed JSON body on success, or None on error.
        Logs and swallows non-200 responses so the caller (poller) keeps running.
        """
        # Build query string
        url = f"{self.BASE}{path}"
        if params:
            qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
            url = f"{url}?{qs}"

        # Sign using the raw path (without query string, per Kalshi docs)
        auth_headers = self._sign(method, path)

        headers = {
            "Content-Type":  "application/json",
            "Accept":        "application/json",
            **auth_headers,
        }

        data: Optional[bytes] = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            body_text = ""
            try:
                body_text = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            log.error(
                "Kalshi API %s %s → HTTP %d: %s",
                method.upper(), path, exc.code, body_text[:300],
            )
            return None
        except Exception as exc:
            log.error("Kalshi API %s %s failed: %s", method.upper(), path, exc)
            return None

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def get_markets(
        self,
        series_ticker: Optional[str] = None,
        status: str = "open",
    ) -> List[dict]:
        """
        GET /markets — returns a list of markets.

        Args:
            series_ticker: Optional filter (e.g. "VGAMES").
            status:        Market status filter (default: "open").
        """
        # urllib.parse needed for query string building
        import urllib.parse  # noqa: PLC0415 (local import is fine here)

        params: Dict[str, str] = {"status": status}
        if series_ticker:
            params["series_ticker"] = series_ticker

        path = "/markets"
        url = f"{self.BASE}{path}"
        if params:
            qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
            url = f"{url}?{qs}"

        auth_headers = self._sign("GET", path)
        headers = {"Accept": "application/json", **auth_headers}

        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            log.error("Kalshi GET /markets → HTTP %d", exc.code)
            return []
        except Exception as exc:
            log.error("Kalshi GET /markets failed: %s", exc)
            return []

        return data.get("markets", [])

    def get_market(self, ticker: str) -> Optional[dict]:
        """
        GET /markets/{ticker}

        Returns a dict with keys including:
          yes_bid, yes_ask, last_price, volume, status, title, close_time
        or None on error.
        """
        result = self._request("GET", f"/markets/{ticker}")
        if result is None:
            return None
        return result.get("market", result)

    def get_orderbook(self, ticker: str) -> Optional[dict]:
        """GET /markets/{ticker}/orderbook"""
        result = self._request("GET", f"/markets/{ticker}/orderbook")
        if result is None:
            return None
        return result.get("orderbook", result)

    def place_order(
        self,
        ticker: str,
        side: str,
        action: str,
        count: int,
        limit_price: int,
        client_order_id: Optional[str] = None,
    ) -> Optional[dict]:
        """
        POST /portfolio/orders — place a limit order.

        Args:
            ticker:          Market ticker (e.g. "VGAMES-24-TW1").
            side:            "yes" or "no".
            action:          "buy" or "sell".
            count:           Number of contracts.
            limit_price:     Price in cents (1–99).
            client_order_id: Optional idempotency key.

        Returns the order dict, or None on error.
        """
        if side not in ("yes", "no"):
            raise ValueError(f"side must be 'yes' or 'no', got {side!r}")
        if action not in ("buy", "sell"):
            raise ValueError(f"action must be 'buy' or 'sell', got {action!r}")
        if not 1 <= limit_price <= 99:
            raise ValueError(f"limit_price must be 1–99 cents, got {limit_price}")
        if count < 1:
            raise ValueError(f"count must be >= 1, got {count}")

        payload: Dict[str, Any] = {
            "ticker":      ticker,
            "side":        side,
            "action":      action,
            "count":       count,
            "limit_price": limit_price,
            "type":        "limit",
        }
        if client_order_id:
            payload["client_order_id"] = client_order_id

        result = self._request("POST", "/portfolio/orders", body=payload)
        if result is None:
            return None
        return result.get("order", result)

    def cancel_order(self, order_id: str) -> Optional[dict]:
        """DELETE /portfolio/orders/{order_id}"""
        result = self._request("DELETE", f"/portfolio/orders/{order_id}")
        if result is None:
            return None
        return result.get("order", result)

    def get_positions(self) -> List[dict]:
        """GET /portfolio/positions — returns list of current positions."""
        result = self._request("GET", "/portfolio/positions")
        if result is None:
            return []
        return result.get("market_positions", result if isinstance(result, list) else [])

    def get_balance(self) -> Optional[dict]:
        """GET /portfolio/balance — returns balance dict."""
        return self._request("GET", "/portfolio/balance")

    # ------------------------------------------------------------------
    # Valorant market discovery
    # ------------------------------------------------------------------

    def find_valorant_markets(self) -> List[dict]:
        """
        Search for open Valorant match-winner markets on Kalshi.

        Probes series tickers: "VGAMES", "VCT", "VALORANT" — uses the first
        that returns results. Returns a list of dicts with:
          ticker, title, yes_bid, yes_ask, team_a, team_b

        team_a / team_b are extracted from the market title when possible.
        """
        markets: List[dict] = []

        for series in self._VALORANT_SERIES:
            raw = self.get_markets(series_ticker=series, status="open")
            if raw:
                log.info("Found %d Kalshi markets under series ticker %s", len(raw), series)
                markets = raw
                break
            log.debug("No open markets for series ticker: %s", series)

        if not markets:
            log.warning(
                "No open Valorant markets found on Kalshi. "
                "Tried series tickers: %s",
                ", ".join(self._VALORANT_SERIES),
            )
            return []

        results: List[dict] = []
        for m in markets:
            ticker = m.get("ticker", "")
            title  = m.get("title", "")
            team_a, team_b = _extract_teams_from_title(title)
            results.append({
                "ticker":   ticker,
                "title":    title,
                "yes_bid":  m.get("yes_bid"),
                "yes_ask":  m.get("yes_ask"),
                "team_a":   team_a,
                "team_b":   team_b,
            })

        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_teams_from_title(title: str):
    """
    Attempt to parse team names from a market title such as:
      "Team A vs Team B — Map winner"
      "VALORANT: Team A to win vs Team B"

    Returns (team_a, team_b) strings. Falls back to ("", "") on failure.
    """
    import re
    # Common pattern: "X vs Y" or "X v Y"
    m = re.search(r"(.+?)\s+(?:vs?\.?)\s+(.+?)(?:\s*[—\-|]|$)", title, re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", ""
