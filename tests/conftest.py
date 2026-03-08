"""Shared test fixtures for the ML pipeline tests."""
import pytest
import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config


@pytest.fixture(scope='session')
def db_path():
    """Return the path to the real SQLite database (local-only, no CI)."""
    return Config.DATABASE_PATH


@pytest.fixture
def sample_raw_rows():
    """Return a small list of dicts mimicking the SQL query output for deterministic testing."""
    return [
        {
            'player_name': 'TenZ', 'map_name': 'Ascent', 'agent': 'Jett',
            'kills': 22, 'deaths': 15, 'assists': 3,
            'acs': 280, 'adr': 165.0, 'kast': 72.0, 'first_bloods': 4,
            'map_score': '13-8', 'match_id': 100, 'map_number': 1,
            'event_id': 80, 'team1': 'Sentinels', 'team2': 'Cloud9',
            'player_team': 'Sentinels',
        },
        {
            'player_name': 'TenZ', 'map_name': 'Bind', 'agent': 'Raze',
            'kills': 18, 'deaths': 17, 'assists': 5,
            'acs': 230, 'adr': 140.0, 'kast': 68.0, 'first_bloods': 2,
            'map_score': '11-13', 'match_id': 101, 'map_number': 1,
            'event_id': 81, 'team1': 'Sentinels', 'team2': 'LOUD',
            'player_team': 'Sentinels',
        },
        {
            'player_name': 'TenZ', 'map_name': 'Haven', 'agent': 'Jett',
            'kills': 25, 'deaths': 12, 'assists': 4,
            'acs': 310, 'adr': 180.0, 'kast': 78.0, 'first_bloods': 5,
            'map_score': '13-5', 'match_id': 102, 'map_number': 2,
            'event_id': 82, 'team1': 'Sentinels', 'team2': 'NRG',
            'player_team': 'Sentinels',
        },
        {
            'player_name': 'aspas', 'map_name': 'Ascent', 'agent': 'Jett',
            'kills': 20, 'deaths': 16, 'assists': 2,
            'acs': 260, 'adr': 155.0, 'kast': 70.0, 'first_bloods': 3,
            'map_score': '13-10', 'match_id': 103, 'map_number': 1,
            'event_id': 80, 'team1': 'LOUD', 'team2': 'Leviatan',
            'player_team': 'LOUD',
        },
        {
            'player_name': 'aspas', 'map_name': 'Bind', 'agent': 'Reyna',
            'kills': 15, 'deaths': 18, 'assists': 6,
            'acs': 210, 'adr': 130.0, 'kast': 65.0, 'first_bloods': 1,
            'map_score': '9-13', 'match_id': 104, 'map_number': 1,
            'event_id': 81, 'team1': 'LOUD', 'team2': 'FURIA',
            'player_team': 'LOUD',
        },
        {
            'player_name': 'SparsePlayer', 'map_name': 'Lotus', 'agent': 'Sage',
            'kills': 10, 'deaths': 14, 'assists': 8,
            'acs': 180, 'adr': 110.0, 'kast': 60.0, 'first_bloods': 0,
            'map_score': '7-13', 'match_id': 105, 'map_number': 1,
            'event_id': 83, 'team1': 'Unknown Team', 'team2': 'Cloud9',
            'player_team': None,
        },
        {
            'player_name': 'TenZ', 'map_name': 'Ascent', 'agent': 'Jett',
            'kills': 19, 'deaths': 14, 'assists': 3,
            'acs': 250, 'adr': 150.0, 'kast': 71.0, 'first_bloods': 3,
            'map_score': '13-11', 'match_id': 106, 'map_number': 1,
            'event_id': 84, 'team1': 'Sentinels', 'team2': 'G2 Esports',
            'player_team': 'Sentinels',
        },
    ]
