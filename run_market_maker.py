#!/usr/bin/env python3
"""
run_market_maker.py

CLI entry point for the Kalshi Valorant market-making bot.

Usage:
    python run_market_maker.py [options]

Options:
    --dry-run        Simulate orders without sending them (DEFAULT).
    --no-dry-run     Send real orders to Kalshi (USE WITH CAUTION).
    --spread INT     Half-spread in cents each side of theo (default: 4).
    --max-pos INT    Max exposure per market in cents (default: 5000 = $50).
    --min-edge INT   Min edge in cents required to quote (default: 2).
    --interval INT   Poll interval in seconds (default: 10).
    --verbose        Set logging level to DEBUG.
    --db PATH        Path to SQLite DB (default: data/valorant_stats.db).

Environment variables required (unless already exported):
    KALSHI_KEY_ID             Your Kalshi API key ID.
    KALSHI_PRIVATE_KEY_PATH   Absolute path to your RSA private key .pem file.

Examples:
    # Paper-trade mode (safe, no real orders):
    python run_market_maker.py --dry-run --verbose

    # Live trading with tighter spread:
    python run_market_maker.py --no-dry-run --spread 3 --min-edge 2
"""

import argparse
import logging
import os
import sys


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kalshi Valorant series-winner market-making bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Simulate orders without sending to Kalshi (default).",
    )
    mode.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Send REAL orders to Kalshi.  Requires valid credentials.",
    )

    parser.add_argument(
        "--spread",
        type=int,
        default=4,
        metavar="CENTS",
        help="Half-spread (quote_width) in cents each side of theo (default: 4).",
    )
    parser.add_argument(
        "--max-pos",
        type=int,
        default=5000,
        metavar="CENTS",
        help="Maximum exposure per market in cents (default: 5000 = $50).  "
             "Global max across all markets is hard-capped at $150.",
    )
    parser.add_argument(
        "--min-edge",
        type=int,
        default=2,
        metavar="CENTS",
        help="Minimum edge in cents to place a quote (default: 2).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        metavar="SECS",
        help="Seconds between market polls (default: 10).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable DEBUG logging.",
    )
    parser.add_argument(
        "--db",
        default="data/valorant_stats.db",
        metavar="PATH",
        help="Path to the valorant_stats SQLite database (default: data/valorant_stats.db).",
    )
    return parser.parse_args()


def main() -> None:
    # Load .env if python-dotenv is available (graceful fallback otherwise).
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    args = _parse_args()
    _setup_logging(args.verbose)
    log = logging.getLogger("run_market_maker")

    # -----------------------------------------------------------------
    # Validate credentials before importing heavy modules.
    # -----------------------------------------------------------------
    key_id = os.environ.get("KALSHI_KEY_ID", "")
    pem_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")

    if not key_id or not pem_path:
        log.error(
            "Missing credentials: set KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH "
            "in your environment or in a .env file."
        )
        sys.exit(1)

    if not os.path.isfile(pem_path):
        log.error("Private key file not found: %s", pem_path)
        sys.exit(1)

    # -----------------------------------------------------------------
    # Enforce global exposure cap.
    # -----------------------------------------------------------------
    GLOBAL_MAX_POSITION_CENTS = 15_000  # $150
    max_pos = min(args.max_pos, GLOBAL_MAX_POSITION_CENTS)
    if args.max_pos > GLOBAL_MAX_POSITION_CENTS:
        log.warning(
            "--max-pos %d exceeds hard cap %d; clamped to %d",
            args.max_pos, GLOBAL_MAX_POSITION_CENTS, max_pos,
        )

    # -----------------------------------------------------------------
    # Import & initialise components.
    # -----------------------------------------------------------------
    from scraper.kalshi_client import KalshiClient
    from backend.theo_engine import TheoEngine
    from backend.market_maker import MarketMaker

    log.info("Initialising KalshiClient…")
    client = KalshiClient()

    log.info("Initialising TheoEngine (db=%s)…", args.db)
    theo_engine = TheoEngine(db_path=args.db)

    log.info(
        "Initialising MarketMaker — dry_run=%s, spread=%dc, max_pos=%dc, min_edge=%dc",
        args.dry_run, args.spread, max_pos, args.min_edge,
    )
    mm = MarketMaker(
        client=client,
        theo_engine=theo_engine,
        quote_width=args.spread,
        max_position=max_pos,
        min_edge=args.min_edge,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        log.info("*** DRY-RUN MODE: no real orders will be placed ***")
    else:
        log.warning("*** LIVE MODE: real orders WILL be sent to Kalshi ***")

    # -----------------------------------------------------------------
    # Run.
    # -----------------------------------------------------------------
    mm.run(poll_interval=args.interval)


if __name__ == "__main__":
    main()
