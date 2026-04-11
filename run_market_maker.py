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
import time


def _match_vlr_to_kalshi(team_a: str, team_b: str, vlr_matches: list) -> dict:
    """
    Find the VLR.gg match entry that best matches a Kalshi market's teams.

    Fuzzy-matches on lowercased team name containment.
    Returns the first match or None.
    """
    a_lo = team_a.lower()
    b_lo = team_b.lower()
    for m in vlr_matches:
        va = m['team_a'].lower()
        vb = m['team_b'].lower()
        if (a_lo in va or va in a_lo) and (b_lo in vb or vb in b_lo):
            return m
        if (b_lo in va or va in b_lo) and (a_lo in vb or vb in a_lo):
            return m
    return None


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
    from scraper.pickban_watcher import get_upcoming_matches, wait_for_pickban

    rates_path = os.path.join(os.path.dirname(args.db), 'half_win_rates.json')
    if not os.path.isfile(rates_path):
        log.error(
            'half_win_rates.json not found at %s. '
            'Run scripts/half_win_rate_model.py first.', rates_path
        )
        sys.exit(1)

    log.info("Initialising KalshiClient…")
    client = KalshiClient()

    log.info("Initialising TheoEngine (rates=%s)…", rates_path)
    theo_engine = TheoEngine(rates_path=rates_path)

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
    # Main loop: discover upcoming matches → wait for pick/ban → quote.
    # -----------------------------------------------------------------
    # Tracks which match URLs have already been processed this session.
    processed: set = set()

    try:
        while True:
            # Step 1: discover open Kalshi Valorant markets
            try:
                kalshi_markets = client.find_valorant_markets()
            except Exception as exc:
                log.error("Could not fetch Kalshi markets: %s", exc)
                time.sleep(args.interval)
                continue

            if not kalshi_markets:
                log.info("No open Valorant markets on Kalshi — sleeping %ds", args.interval)
                time.sleep(args.interval)
                continue

            # Step 2: discover upcoming VLR.gg matches
            vlr_matches = get_upcoming_matches(max_matches=20)

            # Step 3: for each Kalshi market, find matching VLR.gg match
            for mkt in kalshi_markets:
                ticker = mkt['ticker']
                title  = mkt.get('title', '')
                yes_ask = mkt.get('yes_ask', 50) or 50

                # Extract team names from Kalshi title
                team_a, team_b = mm._parse_teams_from_title(title)
                if team_a == 'Unknown':
                    log.warning("Could not parse teams from: %s", title)
                    continue

                # Find the VLR.gg match
                vlr_match = _match_vlr_to_kalshi(team_a, team_b, vlr_matches)
                if not vlr_match:
                    log.info(
                        "%s: no VLR.gg match found for %s vs %s",
                        ticker, team_a, team_b,
                    )
                    # Still quote using side-agnostic fallback if we have
                    # a reasonable map pool guess — skip for now
                    continue

                match_url = vlr_match['match_url']
                if match_url in processed:
                    # Already quoted this match — re-quote in case prices moved
                    log.debug("%s: already processed, re-quoting", ticker)

                # Step 4: get pick/ban (non-blocking — returns None if not ready)
                from scraper.pickban_watcher import get_pickban
                pb = get_pickban(match_url)

                if not pb or not pb.get('complete'):
                    log.info(
                        "%s: pick/ban not ready for %s — skipping this cycle",
                        ticker, match_url,
                    )
                    continue

                # Step 5: extract map pool and sides
                map_pool = [m['map'] for m in pb['maps']]
                team_a_sides = {
                    m['map']: m['team_a_side']
                    for m in pb['maps']
                    if m['team_a_side'] is not None
                }

                log.info(
                    "%s: pick/ban ready — maps=%s sides=%s",
                    ticker, map_pool, team_a_sides,
                )

                # Step 6: quote
                mm.update_market(
                    ticker=ticker,
                    team_a=team_a,
                    team_b=team_b,
                    map_pool=map_pool,
                    team_a_sides=team_a_sides if team_a_sides else None,
                )
                processed.add(match_url)

            time.sleep(args.interval)

    except KeyboardInterrupt:
        log.info("KeyboardInterrupt — cancelling all open orders…")
        mm.cancel_all_orders()
        log.info("Done.")


if __name__ == "__main__":
    main()
