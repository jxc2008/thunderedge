"""PyTorch Dataset and temporal train/test split for player kill prediction.

Provides:
- temporal_split: chronological split by event_id
- PlayerMapDataset: torch Dataset returning feature/target tensors
- create_datasets: end-to-end pipeline from SQLite to train/test Datasets
"""
import logging
from typing import Any

import numpy as np
import torch
from torch.utils.data import Dataset

from backend.ml.features import build_feature_matrix

logger = logging.getLogger(__name__)

# Continuous features in fixed order for tensor construction
CONTINUOUS_FEATURES = [
    'rolling_kills', 'rolling_deaths', 'rolling_assists',
    'rolling_acs', 'rolling_adr', 'rolling_kast', 'rolling_first_bloods',
    'opponent_win_rate',
]


def temporal_split(
    event_ids: list[int],
    split_ratio: float = 0.8,
) -> tuple[set[int], set[int]]:
    """Split event IDs chronologically into train and test sets.

    Args:
        event_ids: List of event IDs (may contain duplicates).
        split_ratio: Fraction of events for training (default 0.8).

    Returns:
        Tuple of (train_event_set, test_event_set) with no overlap.
    """
    sorted_events = sorted(set(event_ids))
    split_idx = int(len(sorted_events) * split_ratio)
    # Ensure at least 1 event in test
    if split_idx >= len(sorted_events):
        split_idx = len(sorted_events) - 1
    train_events = set(sorted_events[:split_idx])
    test_events = set(sorted_events[split_idx:])
    return train_events, test_events


def build_categorical_mappings(
    feature_dicts: list[dict],
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    """Create {value: index} mappings for categorical features.

    Index 0 is reserved for unknown/unseen values.

    Returns:
        (player_to_idx, map_to_idx, role_to_idx)
    """
    players = sorted(set(d['player_name'].lower() for d in feature_dicts))
    maps = sorted(set(d['map_name'] for d in feature_dicts))
    roles = sorted(set(d['agent_role'] for d in feature_dicts))

    # Reserve 0 for unknown
    player_to_idx = {name: i + 1 for i, name in enumerate(players)}
    map_to_idx = {name: i + 1 for i, name in enumerate(maps)}
    role_to_idx = {name: i + 1 for i, name in enumerate(roles)}

    return player_to_idx, map_to_idx, role_to_idx


class PlayerMapDataset(Dataset):
    """PyTorch Dataset for player-map kill prediction.

    Stores encoded categorical indices (player, map, role) as LongTensors
    and normalized continuous features as float32 tensors.
    Target is kills as float32.
    """

    def __init__(
        self,
        feature_dicts: list[dict],
        player_to_idx: dict[str, int],
        map_to_idx: dict[str, int],
        role_to_idx: dict[str, int],
        norm_mean: np.ndarray,
        norm_std: np.ndarray,
    ) -> None:
        n = len(feature_dicts)

        # Encode categoricals
        player_indices = np.zeros(n, dtype=np.int64)
        map_indices = np.zeros(n, dtype=np.int64)
        role_indices = np.zeros(n, dtype=np.int64)

        # Continuous features matrix
        continuous = np.zeros((n, len(CONTINUOUS_FEATURES)), dtype=np.float32)

        # Targets
        targets = np.zeros(n, dtype=np.float32)

        for i, d in enumerate(feature_dicts):
            player_indices[i] = player_to_idx.get(d['player_name'].lower(), 0)
            map_indices[i] = map_to_idx.get(d['map_name'], 0)
            role_indices[i] = role_to_idx.get(d['agent_role'], 0)

            for j, feat in enumerate(CONTINUOUS_FEATURES):
                val = d.get(feat, 0.0)
                continuous[i, j] = float(val) if val is not None else 0.0

            targets[i] = float(d['kills'])

        # Normalize continuous features
        safe_std = np.where(norm_std > 0, norm_std, 1.0)
        continuous = (continuous - norm_mean) / safe_std

        # Convert to tensors
        self.player_idx = torch.from_numpy(player_indices)
        self.map_idx = torch.from_numpy(map_indices)
        self.role_idx = torch.from_numpy(role_indices)
        self.continuous = torch.from_numpy(continuous)
        self.target = torch.from_numpy(targets)

    def __len__(self) -> int:
        return len(self.target)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        return {
            'player_idx': self.player_idx[idx],
            'map_idx': self.map_idx[idx],
            'role_idx': self.role_idx[idx],
            'continuous': self.continuous[idx],
            'target': self.target[idx],
        }


def create_datasets(
    db_path: str,
    split_ratio: float = 0.8,
) -> tuple[PlayerMapDataset, PlayerMapDataset, dict[str, Any]]:
    """End-to-end pipeline: SQLite -> features -> train/test Datasets.

    Args:
        db_path: Path to SQLite database.
        split_ratio: Fraction of events for training.

    Returns:
        (train_dataset, test_dataset, metadata_dict)
    """
    # Build full feature matrix
    all_features = build_feature_matrix(db_path)
    logger.info("Total feature rows: %d", len(all_features))

    # Temporal split
    event_ids = [d['event_id'] for d in all_features]
    train_events, test_events = temporal_split(event_ids, split_ratio)

    # Split features by event membership
    train_features = [d for d in all_features if d['event_id'] in train_events]
    test_features = [d for d in all_features if d['event_id'] in test_events]
    logger.info("Train: %d rows, Test: %d rows", len(train_features), len(test_features))

    # Build categorical mappings from TRAINING data only
    player_to_idx, map_to_idx, role_to_idx = build_categorical_mappings(train_features)

    # Compute normalization stats from TRAINING continuous features only
    n_continuous = len(CONTINUOUS_FEATURES)
    train_continuous = np.zeros((len(train_features), n_continuous), dtype=np.float32)
    for i, d in enumerate(train_features):
        for j, feat in enumerate(CONTINUOUS_FEATURES):
            val = d.get(feat, 0.0)
            train_continuous[i, j] = float(val) if val is not None else 0.0

    norm_mean = train_continuous.mean(axis=0)
    norm_std = train_continuous.std(axis=0)

    # Create datasets
    train_ds = PlayerMapDataset(
        train_features, player_to_idx, map_to_idx, role_to_idx, norm_mean, norm_std
    )
    test_ds = PlayerMapDataset(
        test_features, player_to_idx, map_to_idx, role_to_idx, norm_mean, norm_std
    )

    metadata = {
        'player_to_idx': player_to_idx,
        'map_to_idx': map_to_idx,
        'role_to_idx': role_to_idx,
        'norm_mean': norm_mean.tolist(),
        'norm_std': norm_std.tolist(),
        'n_players': len(player_to_idx) + 1,  # +1 for unknown (index 0)
        'n_maps': len(map_to_idx) + 1,
        'n_roles': len(role_to_idx) + 1,
        'n_continuous': n_continuous,
        'train_events': train_events,
        'test_events': test_events,
        'feature_names': CONTINUOUS_FEATURES,
    }

    return train_ds, test_ds, metadata
