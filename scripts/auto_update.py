"""
scripts/auto_update.py

Continuous data pipeline for Thunderedge.

Runs on a schedule and keeps the database current without manual prompting:
  1. Scrape new completed matches into player_map_stats + match_pick_bans
  2. Scrape economy (atk/def halves) for new matches
  3. Regenerate half_win_rates.json when new halves data is available

Designed to be efficient — every step is checkpoint-based and skips
matches that have already been processed.

Usage:
    # Run once immediately
    python scripts/auto_update.py --once

    # Run on a loop every N minutes (default: 60)
    python scripts/auto_update.py --interval 60

    # Dry-run: show what would be scraped without writing
    python scripts/auto_update.py --once --dry-run
"""

import argparse
import logging
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

os.makedirs(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs'), exist_ok=True)
_log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs', 'auto_update.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_log_file, encoding='utf-8'),
    ],
)
logger = logging.getLogger('auto_update')

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DB_PATH      = os.path.join(PROJECT_ROOT, 'data', 'valorant_stats.db')
RATES_PATH   = os.path.join(PROJECT_ROOT, 'data', 'half_win_rates.json')
HALVES_SCRAPER = os.path.join(
    PROJECT_ROOT, '..', 'worktrees', 'half-win-rate', 'scraper', 'halves_scraper.py'
)
HALVES_MODEL = os.path.join(
    PROJECT_ROOT, '..', 'worktrees', 'half-win-rate', 'scripts', 'half_win_rate_model.py'
)

# Current active VCT events — update when new events launch
ACTIVE_EVENTS = [
    {'url': '/event/2860/vct-2026-americas-stage-1',  'name': 'VCT 2026: Americas Stage 1',  'region': 'Americas', 'year': 2026},
    {'url': '/event/2863/vct-2026-emea-stage-1',      'name': 'VCT 2026: EMEA Stage 1',      'region': 'EMEA',     'year': 2026},
    {'url': '/event/2775/vct-2026-pacific-stage-1',   'name': 'VCT 2026: Pacific Stage 1',   'region': 'Pacific',  'year': 2026},
    {'url': '/event/2864/vct-2026-china-stage-1',     'name': 'VCT 2026: China Stage 1',     'region': 'China',    'year': 2026},
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _row_count(table: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    n = cur.fetchone()[0]
    conn.close()
    return n


def _unscraped_match_count() -> int:
    """Matches not yet in match_map_halves."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        SELECT COUNT(*) FROM matches
        WHERE id NOT IN (SELECT DISTINCT match_id FROM match_map_halves)
    ''')
    n = cur.fetchone()[0]
    conn.close()
    return n


def _run(cmd: list, dry_run: bool = False) -> bool:
    """Run a subprocess command. Returns True on success."""
    label = ' '.join(os.path.basename(c) if c.endswith('.py') else c for c in cmd)
    if dry_run:
        logger.info('[DRY-RUN] Would run: %s', ' '.join(cmd))
        return True
    logger.info('Running: %s', label)
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        logger.error('%s failed (exit %d)', label, result.returncode)
        return False
    return True


# --------------------------------------------------------------------------- #
# Pipeline steps
# --------------------------------------------------------------------------- #

def step_populate_matches(dry_run: bool) -> bool:
    """
    Scrape new completed matches for active events into player_map_stats
    and match_pick_bans.

    Uses populate_database.py's existing checkpoint — only processes
    matches not already in player_map_stats.
    """
    logger.info('--- Step 1: Populate new match data ---')
    before = _row_count('player_map_stats')

    # Call populate_database with a flag to scrape active events only
    # Pass event URLs as env vars so we don't need interactive menu
    ok = _run([
        sys.executable,
        os.path.join(SCRIPT_DIR, 'populate_database.py'),
        '--events', 'active',   # scrape ACTIVE_EVENTS only (see populate_database.py)
    ], dry_run)

    if not dry_run:
        after = _row_count('player_map_stats')
        new_rows = after - before
        logger.info('player_map_stats: %d → %d (+%d rows)', before, after, new_rows)
        return new_rows

    return 0


def step_scrape_halves(dry_run: bool, limit: int = 200) -> int:
    """
    Scrape atk/def half scores for matches not yet in match_map_halves.
    Returns number of new rows inserted.
    """
    logger.info('--- Step 2: Scrape half scores ---')
    unscraped = _unscraped_match_count()
    if unscraped == 0:
        logger.info('No unscraped matches — skipping halves scraper')
        return 0

    logger.info('%d unscraped matches found', unscraped)
    before = _row_count('match_map_halves')

    ok = _run([
        sys.executable,
        HALVES_SCRAPER,
        '--db', DB_PATH,
        '--limit', str(min(limit, unscraped)),
    ], dry_run)

    if not dry_run:
        after = _row_count('match_map_halves')
        new_rows = after - before
        logger.info('match_map_halves: %d → %d (+%d rows)', before, after, new_rows)
        return new_rows

    return 0


def step_regenerate_rates(dry_run: bool, new_halves: int) -> bool:
    """
    Regenerate half_win_rates.json only when new halves data was added.
    """
    logger.info('--- Step 3: Regenerate win rates ---')
    if new_halves == 0:
        logger.info('No new halves data — skipping rate regeneration')
        return False

    ok = _run([
        sys.executable,
        HALVES_MODEL,
        DB_PATH,
        RATES_PATH,
    ], dry_run)

    if ok and not dry_run:
        logger.info('half_win_rates.json updated')

        # Also copy to market-maker data dir
        market_maker_rates = os.path.normpath(os.path.join(
            PROJECT_ROOT, '..', 'worktrees', 'market-maker', 'data', 'half_win_rates.json'
        ))
        if os.path.isdir(os.path.dirname(market_maker_rates)):
            import shutil
            shutil.copy(RATES_PATH, market_maker_rates)
            logger.info('Copied to market-maker/data/half_win_rates.json')

    return ok


# --------------------------------------------------------------------------- #
# Data threshold check
# --------------------------------------------------------------------------- #

def check_pickban_threshold() -> dict:
    """
    Report pick/ban data readiness per team.
    Used to decide when to switch from manual to automated pre-match predictions.

    Thresholds (from PICKBAN_PREDICTION.md):
      < 15 appearances: manual only
      15-40:            semi-auto (requires human confirmation)
      > 40:             fully automated
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute('''
        SELECT m.team1 AS team, COUNT(*) AS appearances
        FROM match_pick_bans pb
        JOIN matches m ON m.id = pb.match_id
        GROUP BY m.team1
        UNION ALL
        SELECT m.team2, COUNT(*)
        FROM match_pick_bans pb
        JOIN matches m ON m.id = pb.match_id
        GROUP BY m.team2
    ''')
    rows = cur.fetchall()
    conn.close()

    from collections import defaultdict
    counts = defaultdict(int)
    for team, n in rows:
        counts[team] += n

    manual    = {t: n for t, n in counts.items() if n < 15}
    semi_auto = {t: n for t, n in counts.items() if 15 <= n <= 40}
    full_auto = {t: n for t, n in counts.items() if n > 40}

    return {
        'manual':    manual,
        'semi_auto': semi_auto,
        'full_auto': full_auto,
    }


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #

def run_once(dry_run: bool):
    logger.info('=== Auto-update started at %s ===', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    os.makedirs(os.path.join(PROJECT_ROOT, 'logs'), exist_ok=True)

    new_matches  = step_populate_matches(dry_run)
    new_halves   = step_scrape_halves(dry_run, limit=300)
    rates_updated = step_regenerate_rates(dry_run, new_halves)

    # Summary
    threshold = check_pickban_threshold()
    n_full   = len(threshold['full_auto'])
    n_semi   = len(threshold['semi_auto'])
    n_manual = len(threshold['manual'])
    total_pb = _row_count('match_pick_bans')

    logger.info(
        '=== Done. match_map_halves=%d | pick_bans=%d | '
        'auto-ready teams: full=%d semi=%d manual=%d ===',
        _row_count('match_map_halves'), total_pb, n_full, n_semi, n_manual,
    )

    if n_full > 0 and not dry_run:
        logger.info(
            'Teams ready for fully automated pick/ban prediction: %s',
            ', '.join(sorted(threshold['full_auto'].keys())),
        )


def main():
    parser = argparse.ArgumentParser(description='Thunderedge continuous data updater')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--interval', type=int, default=60, metavar='MIN',
                        help='Minutes between update cycles (default: 60)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would run without executing')
    args = parser.parse_args()

    if args.once:
        run_once(args.dry_run)
        return

    logger.info('Starting continuous updater — interval=%d min', args.interval)
    while True:
        run_once(args.dry_run)
        next_run = datetime.fromtimestamp(time.time() + args.interval * 60)
        logger.info('Next update at %s', next_run.strftime('%H:%M:%S'))
        time.sleep(args.interval * 60)


if __name__ == '__main__':
    main()
