"""Feature extraction pipeline for player kill prediction.

Extracts per-player-per-map feature vectors from SQLite, computes rolling
statistics with strict causality (only prior events), handles sparse player
histories via global mean imputation, and attaches opponent strength features.
"""
import logging
import re
import sqlite3
from typing import Optional

import numpy as np

from config import Config

logger = logging.getLogger(__name__)

# All 29 agents mapped to 4 roles
AGENT_ROLES: dict[str, str] = {
    'Jett': 'duelist', 'Raze': 'duelist', 'Reyna': 'duelist',
    'Phoenix': 'duelist', 'Yoru': 'duelist', 'Neon': 'duelist',
    'Iso': 'duelist', 'Waylay': 'duelist',
    'Sova': 'initiator', 'Breach': 'initiator', 'Skye': 'initiator',
    'Kayo': 'initiator', 'Fade': 'initiator', 'Gekko': 'initiator',
    'Tejo': 'initiator',
    'Brimstone': 'controller', 'Omen': 'controller', 'Astra': 'controller',
    'Viper': 'controller', 'Harbor': 'controller', 'Clove': 'controller',
    'Sage': 'sentinel', 'Cypher': 'sentinel', 'Killjoy': 'sentinel',
    'Chamber': 'sentinel', 'Deadlock': 'sentinel', 'Vyse': 'sentinel',
    'Veto': 'sentinel',
}

# Stats used for rolling feature computation
ROLLING_STATS = ['kills', 'deaths', 'assists', 'acs', 'adr', 'kast', 'first_bloods']


def clean_team_name(raw: str) -> str:
    """Strip event-name pollution from a stored team name.

    Mirrors Database._clean_team_name() -- strips everything from the first
    year (20XX) or known event keyword (vct, champions tour, challengers).
    """
    if not raw:
        return raw
    m = re.search(
        r'\s+(?:20\d{2}|vct\b|champions?\s+tour\b|challengers?\b)',
        raw,
        flags=re.IGNORECASE,
    )
    return raw[:m.start()].strip() if m else raw.strip()


def extract_all_player_map_features(db_path: str) -> list[dict]:
    """Extract all complete player-map records with event context from SQLite.

    Joins player_map_stats + matches + players. Filters out rows where
    map_name or kills is NULL.

    Returns:
        List of dicts, each representing one player-map record.
    """
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pms.player_name, pms.map_name, pms.agent,
               pms.kills, pms.deaths, pms.assists,
               pms.acs, pms.adr, pms.kast, pms.first_bloods,
               pms.map_score, pms.match_id, pms.map_number,
               m.event_id, m.team1, m.team2,
               p.team as player_team
        FROM player_map_stats pms
        JOIN matches m ON pms.match_id = m.id
        LEFT JOIN players p ON LOWER(pms.player_name) = LOWER(p.ign)
        WHERE pms.map_name IS NOT NULL
          AND pms.kills IS NOT NULL
        ORDER BY m.event_id ASC
    ''')
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    logger.info("Extracted %d raw feature rows from database", len(rows))
    return rows


def compute_team_win_records(rows: list[dict]) -> dict[str, dict]:
    """Compute win/total records per team from map scores.

    Parses map_score ("A-B") to determine which team won each map,
    using player_team + team1/team2 to attribute wins.

    Returns:
        Dict mapping team_name_lower -> {'wins': int, 'total': int}.
    """
    records: dict[str, dict] = {}

    # Track matches we've already counted to avoid double-counting
    # (multiple players per team per map)
    seen: set[tuple] = set()

    for row in rows:
        map_score = row.get('map_score')
        if not map_score or '-' not in str(map_score):
            continue

        match_key = (row['match_id'], row.get('map_number', 1))
        if match_key in seen:
            continue
        seen.add(match_key)

        try:
            parts = str(map_score).split('-')
            t1_rounds = int(parts[0].strip())
            t2_rounds = int(parts[1].strip())
        except (ValueError, IndexError):
            continue

        t1_clean = clean_team_name(row.get('team1', '') or '').lower()
        t2_clean = clean_team_name(row.get('team2', '') or '').lower()

        if not t1_clean or not t2_clean:
            continue

        # Initialize records
        for team in [t1_clean, t2_clean]:
            if team not in records:
                records[team] = {'wins': 0, 'total': 0}

        records[t1_clean]['total'] += 1
        records[t2_clean]['total'] += 1

        if t1_rounds > t2_rounds:
            records[t1_clean]['wins'] += 1
        elif t2_rounds > t1_rounds:
            records[t2_clean]['wins'] += 1
        # Ties: neither team gets a win but both get a total

    return records


def compute_opponent_win_rate(
    player_team: Optional[str],
    team1: str,
    team2: str,
    team_records: dict[str, dict],
) -> float:
    """Derive opponent strength from team win records.

    Determines which team the player is on, finds the opponent,
    and returns the opponent's win rate. Defaults to 0.5 for unknown.
    """
    if not player_team:
        return 0.5

    t1_clean = clean_team_name(team1 or '').lower()
    t2_clean = clean_team_name(team2 or '').lower()
    pt_lower = player_team.lower()

    # Determine opponent: check if player_team matches team1 or team2
    if t1_clean and t1_clean in pt_lower:
        opponent = t2_clean
    elif t2_clean and t2_clean in pt_lower:
        opponent = t1_clean
    else:
        # Try reverse containment (team name may be substring of player_team)
        if t1_clean and pt_lower in t1_clean:
            opponent = t2_clean
        elif t2_clean and pt_lower in t2_clean:
            opponent = t1_clean
        else:
            return 0.5

    record = team_records.get(opponent)
    if record and record['total'] > 0:
        return record['wins'] / record['total']
    return 0.5


def compute_rolling_features(
    player_name: str,
    current_event_id: int,
    player_history: list[dict],
    window: int = 10,
) -> Optional[dict[str, float]]:
    """Compute rolling average stats using ONLY data from prior events.

    Strictly causal: only uses rows where event_id < current_event_id.
    Takes the most recent `window` records (sorted by event_id desc).

    Returns:
        Dict of rolling_* features, or None if no prior records exist.
    """
    prior = [r for r in player_history if r['event_id'] < current_event_id]
    if not prior:
        return None

    # Sort by event_id descending, take most recent window
    prior.sort(key=lambda x: x['event_id'], reverse=True)
    recent = prior[:window]

    result = {}
    for stat in ROLLING_STATS:
        values = [r[stat] for r in recent if r.get(stat) is not None]
        if values:
            result[f'rolling_{stat}'] = float(np.mean(values))
        else:
            result[f'rolling_{stat}'] = 0.0

    return result


def build_feature_matrix(db_path: str) -> list[dict]:
    """Orchestrate the full feature extraction pipeline.

    1. Extract all raw rows from SQLite
    2. Compute global mean stats for imputation
    3. Group rows by player for efficient rolling lookups
    4. Compute team win records
    5. For each row: attach rolling features, opponent strength, agent role

    Returns:
        List of complete feature dicts ready for Dataset consumption.
    """
    # Step 1: Extract raw rows
    rows = extract_all_player_map_features(db_path)
    if not rows:
        logger.warning("No rows extracted from database")
        return []

    logger.info("Building feature matrix from %d raw rows", len(rows))

    # Step 2: Compute global means for imputation
    global_means: dict[str, float] = {}
    for stat in ROLLING_STATS:
        values = [r[stat] for r in rows if r.get(stat) is not None]
        global_means[stat] = float(np.mean(values)) if values else 0.0

    # Step 3: Group by player (lowercased) for rolling lookups
    by_player: dict[str, list[dict]] = {}
    for r in rows:
        key = r['player_name'].lower()
        by_player.setdefault(key, []).append(r)

    # Step 4: Compute team win records
    team_records = compute_team_win_records(rows)

    # Step 5: Build complete feature dicts
    feature_matrix: list[dict] = []
    for row in rows:
        player_key = row['player_name'].lower()

        # Rolling features (strictly causal)
        rolling = compute_rolling_features(
            player_key,
            row['event_id'],
            by_player[player_key],
            window=10,
        )

        # Impute with global means if no prior data
        if rolling is None:
            rolling = {f'rolling_{s}': global_means[s] for s in ROLLING_STATS}

        # Agent role
        agent = row.get('agent') or ''
        agent_role = AGENT_ROLES.get(agent, 'unknown')

        # Opponent win rate
        owr = compute_opponent_win_rate(
            row.get('player_team'),
            row.get('team1', ''),
            row.get('team2', ''),
            team_records,
        )

        feature_dict = {
            'player_name': row['player_name'],
            'map_name': row['map_name'],
            'agent': agent,
            'agent_role': agent_role,
            'kills': row['kills'],
            'deaths': row.get('deaths', 0) or 0,
            'assists': row.get('assists', 0) or 0,
            'acs': row.get('acs', 0) or 0,
            'adr': float(row.get('adr', 0) or 0),
            'kast': float(row.get('kast', 0) or 0),
            'first_bloods': row.get('first_bloods', 0) or 0,
            'event_id': row['event_id'],
            'match_id': row['match_id'],
            'opponent_win_rate': owr,
            **rolling,
        }
        feature_matrix.append(feature_dict)

    logger.info("Built feature matrix: %d rows, %d features each",
                len(feature_matrix), len(feature_matrix[0]) if feature_matrix else 0)
    return feature_matrix
