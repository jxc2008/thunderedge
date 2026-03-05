# scripts/repopulate_pick_bans.py
"""
Re-scrape VLR pick/ban sequences for 2026 matches and save team-attributed data.

The veto sequence is strictly: T1 ban, T2 ban, T1 pick, T2 pick, T1 ban, T2 ban, remaining.
After this script, match_pick_bans will have t1_ban1, t1_ban2, t1_pick, t2_ban1, t2_ban2,
t2_pick populated — where t1/t2 correspond to matches.team1 / matches.team2.

Usage:
  python scripts/repopulate_pick_bans.py
  python scripts/repopulate_pick_bans.py --dry-run
"""

import sys
import os
import re
import time
import random
import argparse
import logging
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Database
from config import Config

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing deps: pip install requests beautifulsoup4")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

VLR_BASE = 'https://www.vlr.gg'
VALORANT_MAPS = ['Bind', 'Haven', 'Split', 'Ascent', 'Icebox', 'Breeze',
                 'Fracture', 'Pearl', 'Lotus', 'Sunset', 'Abyss', 'Corrode']
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})


def _normalize(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', s.lower())


def _teams_match(vlr_team: str, db_team: str) -> bool:
    """Fuzzy match VLR abbreviated team name to DB full team name."""
    vn = _normalize(vlr_team)
    dn = _normalize(db_team)
    if not vn or not dn:
        return False
    if vn == dn or vn in dn or dn in vn or vn[:5] == dn[:5]:
        return True
    # Acronym check: vn spells out the first letters of db_team words
    words = [w for w in db_team.strip().split() if w and w[0].isalpha()]
    if words:
        acronym = _normalize(''.join(w[0] for w in words))
        if vn == acronym:
            return True
    return False


def _fetch_page(url: str) -> str:
    resp = SESSION.get(url, timeout=15)
    resp.raise_for_status()
    return resp.text


def _extract_pick_bans_attributed(soup, team1: str, team2: str) -> dict:
    """Extract pick/ban sequence and attribute each action to team1 or team2."""
    result = {
        # Legacy sequence-order fields
        'first_ban': None, 'second_ban': None,
        'first_pick': None, 'second_pick': None,
        'decider': None,
        # Team-attributed fields
        't1_ban1': None, 't1_ban2': None, 't1_pick': None,
        't2_ban1': None, 't2_ban2': None, 't2_pick': None,
    }

    try:
        candidate_texts = []
        for cls in ['match-header-note', 'match-header-vs-note', 'match-header']:
            for el in soup.find_all('div', class_=cls):
                t = el.get_text(" ", strip=True)
                if t and ('ban' in t.lower() or 'pick' in t.lower()):
                    candidate_texts.append(t)

        if not candidate_texts:
            return result

        header_text = max(candidate_texts,
                          key=lambda t: t.lower().count('ban') + t.lower().count('pick'))

        action_pattern = re.compile(
            r'([A-Za-z0-9\s]+?)\s+(ban|bans|pick|picks)\s+([A-Za-z]+)',
            re.IGNORECASE,
        )

        # Collect ordered sequence of (vlr_team, action, map)
        sequence = []
        for vlr_team, action, map_name in action_pattern.findall(header_text):
            map_name = map_name.strip()
            if any(m.lower() == map_name.lower() for m in VALORANT_MAPS):
                sequence.append((vlr_team.strip(), action.lower(), map_name))

        if not sequence:
            return result

        # Fill legacy fields
        bans = [m for _, a, m in sequence if a.startswith('ban')]
        picks = [m for _, a, m in sequence if not a.startswith('ban')]
        if len(bans) >= 1: result['first_ban'] = bans[0]
        if len(bans) >= 2: result['second_ban'] = bans[1]
        if len(picks) >= 1: result['first_pick'] = picks[0]
        if len(picks) >= 2: result['second_pick'] = picks[1]

        remains = re.search(r'([A-Za-z]+)\s+remains', header_text, re.IGNORECASE)
        if remains:
            result['decider'] = remains.group(1).strip()

        # Identify which DB team each VLR actor string belongs to.
        # Two-pass approach: first match what we can, then fill remaining slots.
        # This handles cases where one team uses an abbreviation (e.g. "NS", "C9")
        # that can't be matched to the DB name, while the other team CAN be matched.
        unique_vlr_teams = list(dict.fromkeys(vt for vt, _, _ in sequence))
        actor_role = {}
        unmatched = []

        for vlr_team in unique_vlr_teams:
            if _teams_match(vlr_team, team1):
                actor_role[vlr_team] = 1
            elif _teams_match(vlr_team, team2):
                actor_role[vlr_team] = 2
            else:
                unmatched.append(vlr_team)

        # Assign unmatched teams to whichever role isn't yet taken
        for vlr_team in unmatched:
            assigned = set(actor_role.values())
            if 1 not in assigned:
                actor_role[vlr_team] = 1
            elif 2 not in assigned:
                actor_role[vlr_team] = 2
            # else both roles taken (shouldn't happen in a normal match)

        # Apply attribution
        t1_bans, t2_bans = [], []
        t1_picks, t2_picks = [], []
        for vlr_team, action, map_name in sequence:
            role = actor_role.get(vlr_team, 0)
            if action.startswith('ban'):
                (t1_bans if role == 1 else t2_bans).append(map_name)
            else:
                (t1_picks if role == 1 else t2_picks).append(map_name)

        if len(t1_bans) >= 1: result['t1_ban1'] = t1_bans[0]
        if len(t1_bans) >= 2: result['t1_ban2'] = t1_bans[1]
        if t1_picks:          result['t1_pick'] = t1_picks[0]
        if len(t2_bans) >= 1: result['t2_ban1'] = t2_bans[0]
        if len(t2_bans) >= 2: result['t2_ban2'] = t2_bans[1]
        if t2_picks:          result['t2_pick'] = t2_picks[0]

    except Exception as e:
        logger.warning(f"Error extracting pick/bans: {e}")

    return result


def _get_2026_matches(db_path: str, new_only: bool = False) -> list:
    conn = sqlite3.connect(db_path, timeout=30.0)
    c = conn.cursor()
    query = '''
        SELECT m.id, m.match_url, m.team1, m.team2
        FROM matches m
        JOIN vct_events ve ON m.event_id = ve.id
        WHERE ve.year = 2026
    '''
    if new_only:
        query += '''
          AND NOT EXISTS (
            SELECT 1 FROM match_pick_bans pb
            WHERE pb.match_id = m.id AND pb.t1_pick IS NOT NULL
          )
        '''
    query += ' ORDER BY m.id'
    c.execute(query)
    rows = c.fetchall()
    conn.close()
    return [{'id': r[0], 'match_url': r[1], 'team1': r[2], 'team2': r[3]} for r in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--new-only', action='store_true',
                        help='Only process matches that have no team-attributed pick/ban data yet')
    args = parser.parse_args()

    from backend.database import Database
    db = Database(Config.DATABASE_PATH)
    db._init_db()  # runs migration to add t1/t2 columns if missing

    matches = _get_2026_matches(Config.DATABASE_PATH, new_only=args.new_only)
    label = 'new unattributed' if args.new_only else 'all'
    print(f"Repopulating pick/bans for {len(matches)} {label} 2026 matches...")

    ok = skipped = failed = 0

    for i, m in enumerate(matches, 1):
        url = VLR_BASE + m['match_url']
        team1 = m['team1'] or ''
        team2 = m['team2'] or ''
        print(f"  [{i}/{len(matches)}] match {m['id']}: {team1[:20]} vs {team2[:20]}")

        try:
            html = _fetch_page(url)
            soup = BeautifulSoup(html, 'html.parser')
            pb = _extract_pick_bans_attributed(soup, team1, team2)

            has_data = any(pb[k] for k in ['first_ban', 'second_ban', 'first_pick', 'decider'])
            if not has_data:
                print(f"    No pick/ban data found")
                skipped += 1
            else:
                print(f"    t1_bans=({pb['t1_ban1']},{pb['t1_ban2']}) t1_pick={pb['t1_pick']} "
                      f"t2_bans=({pb['t2_ban1']},{pb['t2_ban2']}) t2_pick={pb['t2_pick']} "
                      f"decider={pb['decider']}")
                if not args.dry_run:
                    db.save_match_pick_bans(
                        match_id=m['id'],
                        first_ban=pb['first_ban'], second_ban=pb['second_ban'],
                        first_pick=pb['first_pick'], second_pick=pb['second_pick'],
                        decider=pb['decider'],
                        t1_ban1=pb['t1_ban1'], t1_ban2=pb['t1_ban2'], t1_pick=pb['t1_pick'],
                        t2_ban1=pb['t2_ban1'], t2_ban2=pb['t2_ban2'], t2_pick=pb['t2_pick'],
                    )
                ok += 1

        except Exception as e:
            logger.warning(f"    Error: {e}")
            failed += 1

        time.sleep(random.uniform(0.8, 1.4))

    print(f"\n=== Done ===")
    print(f"Saved: {ok} | No data: {skipped} | Failed: {failed}")
    if args.dry_run:
        print("(dry-run — nothing written)")


if __name__ == '__main__':
    main()
