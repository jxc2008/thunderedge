# scraper/prizepicks_api.py
"""
Fetch real-time Valorant player lines from PrizePicks API.
Uses api.prizepicks.com/projections with league_id=159 (Valorant).
"""
import requests
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PRIZEPICKS_API_URL = "https://api.prizepicks.com/projections"
VALORANT_LEAGUE_ID = 159  # VAL in PrizePicks leagues

# Stat type names we support (kills for 2-map combo analysis)
SUPPORTED_STAT_TYPES = frozenset(['kills', 'kill', 'k'])  # case-insensitive match


def _default_headers() -> Dict[str, str]:
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://app.prizepicks.com/',
    }


def fetch_valorant_projections(
    stat_filter: Optional[List[str]] = None,
    per_page: int = 250,
) -> List[Dict]:
    """
    Fetch Valorant projections from PrizePicks API.
    
    Args:
        stat_filter: If provided, only include projections whose stat_type contains
                     any of these strings (case-insensitive). Default: kills only.
        per_page: Max projections to fetch.
        
    Returns:
        List of dicts with: player_name, line, stat_type, projection_id, description
    """
    if stat_filter is None:
        stat_filter = ['kill']  # Default to kills (matches "Kills", "Maps 1-2 Kills", etc.)
    
    params = {
        'league_id': VALORANT_LEAGUE_ID,
        'per_page': per_page,
        'single_stat': 'true',
    }
    
    try:
        session = requests.Session()
        session.trust_env = False
        session.proxies = {}
        resp = session.get(
            PRIZEPICKS_API_URL,
            params=params,
            headers=_default_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        status = getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
        logger.error(f"PrizePicks API request failed: {e} (status={status})")
        if status == 403:
            raise  # Caller can show specific 403 message
        return []
    except ValueError as e:
        logger.error(f"PrizePicks API invalid JSON: {e}")
        return []
    
    # Parse JSON:API format - data has projections, included has new_player, stat_type
    projections = data.get('data', [])
    included = data.get('included', [])
    
    # Build lookup: {type: {id: attrs}} - use str(id) for consistent lookup
    by_type_id = {}
    for inc in included:
        t = inc.get('type', '')
        iid = str(inc.get('id', ''))
        attrs = inc.get('attributes', {})
        if t not in by_type_id:
            by_type_id[t] = {}
        by_type_id[t][iid] = attrs
    
    # Resolve relationships
    new_player = by_type_id.get('new_player', {})
    stat_type = by_type_id.get('stat_type', {})
    
    results = []
    for proj in projections:
        if proj.get('type') != 'projection':
            continue
        
        attrs = proj.get('attributes', {})
        rels = proj.get('relationships', {})
        
        line_score = attrs.get('line_score')
        if line_score is None:
            continue
        
        # Get player name
        player_rel = rels.get('new_player', {}).get('data', {})
        player_id = player_rel.get('id')
        player_attrs = new_player.get(str(player_id), {}) if player_id else {}
        player_name = player_attrs.get('name', '').strip()
        if not player_name:
            continue
        
        # Get stat type
        stat_rel = rels.get('stat_type', {}).get('data', {})
        stat_id = stat_rel.get('id')
        stat_attrs = stat_type.get(str(stat_id), {}) if stat_id else {}
        stat_name = stat_attrs.get('name', '').lower()
        
        # Filter by stat type
        if not any(f.lower() in stat_name for f in stat_filter):
            continue
        
        # Description (e.g. "Maps 1-2 Kills" or match info)
        description = attrs.get('description') or stat_name
        
        results.append({
            'player_name': player_name,
            'line': float(line_score),
            'stat_type': stat_name,
            'stat_type_display': stat_attrs.get('name', stat_name),
            'projection_id': proj.get('id'),
            'description': description,
        })
    
    logger.info(f"PrizePicks API: fetched {len(results)} Valorant kill projections")
    return results
