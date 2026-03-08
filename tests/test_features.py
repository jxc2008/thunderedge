"""Tests for the feature extraction pipeline (backend.ml.features)."""
import math
import pytest

from backend.ml.features import (
    extract_all_player_map_features,
    compute_rolling_features,
    build_feature_matrix,
    AGENT_ROLES,
)

REQUIRED_KEYS = {
    'player_name', 'map_name', 'agent', 'agent_role',
    'kills', 'deaths', 'assists', 'acs', 'adr', 'kast', 'first_bloods',
    'event_id', 'match_id', 'opponent_win_rate',
    'rolling_kills', 'rolling_deaths', 'rolling_assists',
    'rolling_acs', 'rolling_adr', 'rolling_kast', 'rolling_first_bloods',
}


class TestExtractFeatures:
    """Tests for extract_all_player_map_features."""

    def test_extract_features_returns_rows(self, db_path):
        """extract_all_player_map_features returns a non-empty list of dicts."""
        rows = extract_all_player_map_features(db_path)
        assert isinstance(rows, list)
        assert len(rows) > 0
        assert isinstance(rows[0], dict)

    def test_null_map_rows_filtered(self, db_path):
        """No row should have map_name=None after extraction."""
        rows = extract_all_player_map_features(db_path)
        for row in rows:
            assert row['map_name'] is not None, f"Found row with NULL map_name: {row}"


class TestBuildFeatureMatrix:
    """Tests for build_feature_matrix (full pipeline)."""

    @pytest.fixture(scope='class')
    def feature_matrix(self, db_path):
        """Build the feature matrix once for all tests in this class."""
        return build_feature_matrix(db_path)

    def test_feature_row_has_required_keys(self, feature_matrix):
        """Each feature dict must have all required keys."""
        for i, row in enumerate(feature_matrix[:100]):  # check first 100
            missing = REQUIRED_KEYS - set(row.keys())
            assert not missing, f"Row {i} missing keys: {missing}"

    def test_sparse_player_features_no_nan(self, feature_matrix):
        """Players with few maps should still have valid (non-NaN) rolling features."""
        rolling_keys = [k for k in REQUIRED_KEYS if k.startswith('rolling_')]
        for row in feature_matrix:
            for key in rolling_keys:
                val = row[key]
                assert val is not None, f"None in {key} for {row['player_name']}"
                assert not math.isnan(val), f"NaN in {key} for {row['player_name']}"

    def test_rolling_features_are_causal(self, db_path):
        """Rolling stats for a sample must use ONLY data from events with LOWER event_id."""
        rows = extract_all_player_map_features(db_path)
        if not rows:
            pytest.skip("No raw rows available")

        # Group by player
        by_player = {}
        for r in rows:
            key = r['player_name'].lower()
            by_player.setdefault(key, []).append(r)

        # Pick a player with multiple events
        test_player = None
        for name, player_rows in by_player.items():
            event_ids = sorted(set(r['event_id'] for r in player_rows))
            if len(event_ids) >= 3:
                test_player = name
                break
        assert test_player is not None, "No player with 3+ events found"

        player_rows = by_player[test_player]
        event_ids = sorted(set(r['event_id'] for r in player_rows))
        target_event = event_ids[2]  # third event -- should have 2 prior events

        rolling = compute_rolling_features(
            test_player, target_event, player_rows, window=10
        )
        # Rolling features should only reflect data from events < target_event
        prior_kills = [r['kills'] for r in player_rows if r['event_id'] < target_event]
        if prior_kills and rolling is not None:
            import numpy as np
            expected_avg = np.mean(sorted(prior_kills, key=lambda x: -1)[:10])
            # Just verify rolling_kills is close to the average of prior kills
            assert rolling['rolling_kills'] == pytest.approx(
                np.mean([r['kills'] for r in sorted(
                    [r for r in player_rows if r['event_id'] < target_event],
                    key=lambda x: x['event_id'], reverse=True
                )[:10]]),
                rel=1e-5,
            )

    def test_opponent_strength_computed(self, feature_matrix):
        """opponent_win_rate must be a float in [0, 1] for all rows."""
        for row in feature_matrix[:200]:
            owr = row['opponent_win_rate']
            assert isinstance(owr, float), f"opponent_win_rate not float: {type(owr)}"
            assert 0.0 <= owr <= 1.0, f"opponent_win_rate out of range: {owr}"

    def test_agent_roles_valid(self, feature_matrix):
        """All agent_role values should be one of the 4 roles or 'unknown'."""
        valid_roles = {'duelist', 'initiator', 'controller', 'sentinel', 'unknown'}
        for row in feature_matrix[:200]:
            assert row['agent_role'] in valid_roles, f"Invalid role: {row['agent_role']}"
