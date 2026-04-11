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
    Report pick/ban data readiness per team using recency-weighted appearances.

    Each match is weighted by its stage recency (same scheme as half-win-rate model):
      current stage = 1.0, previous stage = 0.5, older = excluded.

    Tiers (from PICKBAN_PREDICTION.md):
      effective < 8:   LOW  — use win-rate model only, no tendency prior
      effective 8-15:  MED  — blend tendency prior with win-rate score
      effective > 15:  HIGH — lean on team-specific patterns
    """
    import re as _re
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Detect current and previous stage using event round keys
    _STAGE_ORDER = {'Kickoff': 0, 'Stage 1': 1, 'Stage 2': 2, 'Stage 3': 3}

    def _round_key(event_name):
        m = _re.match(r'VCT (\d{4}).*?(Kickoff|Stage\s+\d+)', event_name or '')
        if m:
            return (int(m.group(1)), _STAGE_ORDER.get(m.group(2).strip(), -1))
        return (0, -1)

    cur.execute('SELECT id, event_name FROM vct_events')
    all_events = cur.fetchall()
    event_rounds = {eid: _round_key(ename) for eid, ename in all_events}
    ranked = sorted(set(event_rounds.values()), reverse=True)
    round_weights = {}
    for i, rk in enumerate(ranked):
        round_weights[rk] = 1.0 if i == 0 else (0.5 if i == 1 else 0.0)

    def _event_weight(event_id):
        return round_weights.get(event_rounds.get(event_id, (0, -1)), 0.0)

    # Fetch all pick/ban match event IDs
    cur.execute('''
        SELECT m.team1, m.team2, m.event_id
        FROM match_pick_bans pb
        JOIN matches m ON m.id = pb.match_id
    ''')
    rows = cur.fetchall()
    conn.close()

    from collections import defaultdict
    effective = defaultdict(float)
    for team1, team2, event_id in rows:
        w = _event_weight(event_id)
        if w > 0:
            effective[team1] += w
            effective[team2] += w

    low  = {t: round(n, 1) for t, n in effective.items() if n < 8}
    med  = {t: round(n, 1) for t, n in effective.items() if 8 <= n <= 15}
    high = {t: round(n, 1) for t, n in effective.items() if n > 15}

    return {'low': low, 'med': med, 'high': high}


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
    n_high = len(threshold['high'])
    n_med  = len(threshold['med'])
    n_low  = len(threshold['low'])
    total_pb = _row_count('match_pick_bans')

    logger.info(
        '=== Done. match_map_halves=%d | pick_bans=%d | '
        'pick/ban tiers: high=%d med=%d low=%d ===',
        _row_count('match_map_halves'), total_pb, n_high, n_med, n_low,
    )

    if n_med + n_high > 0 and not dry_run:
        logger.info(
            'Teams with MED/HIGH pick/ban signal: %s',
            ', '.join(sorted({**threshold['med'], **threshold['high']}.keys())),
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
