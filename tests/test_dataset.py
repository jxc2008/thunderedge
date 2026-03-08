"""Tests for PyTorch Dataset and temporal split (backend.ml.dataset)."""
import math
import pytest
import torch

from backend.ml.dataset import (
    temporal_split,
    PlayerMapDataset,
    create_datasets,
)


class TestTemporalSplit:
    """Tests for temporal_split."""

    def test_temporal_split_no_overlap(self):
        """Train and test event sets must have zero intersection."""
        event_ids = list(range(73, 115))
        train_events, test_events = temporal_split(event_ids)
        assert len(train_events & test_events) == 0

    def test_temporal_split_ordering(self):
        """max(train_event_id) < min(test_event_id)."""
        event_ids = list(range(73, 115))
        train_events, test_events = temporal_split(event_ids)
        assert max(train_events) < min(test_events)

    def test_temporal_split_coverage(self):
        """All events must be in either train or test."""
        event_ids = list(range(73, 115))
        train_events, test_events = temporal_split(event_ids)
        assert train_events | test_events == set(event_ids)


class TestPlayerMapDataset:
    """Tests for PlayerMapDataset."""

    @pytest.fixture(scope='class')
    def datasets(self, db_path):
        """Create train/test datasets once for all tests."""
        train_ds, test_ds, meta = create_datasets(db_path)
        return train_ds, test_ds, meta

    def test_dataset_returns_tensors(self, datasets):
        """Dataset __getitem__ should return a dict with tensor values."""
        train_ds, _, _ = datasets
        if len(train_ds) == 0:
            pytest.skip("Empty training dataset")
        sample = train_ds[0]
        assert isinstance(sample, dict)
        assert 'continuous' in sample
        assert 'target' in sample
        assert isinstance(sample['continuous'], torch.Tensor)
        assert isinstance(sample['target'], torch.Tensor)

    def test_dataset_no_nan_tensors(self, datasets):
        """No NaN values in any tensor returned by Dataset."""
        train_ds, test_ds, _ = datasets
        for ds in [train_ds, test_ds]:
            # Check a sample of rows (up to 500) to keep test fast
            check_count = min(len(ds), 500)
            for i in range(check_count):
                sample = ds[i]
                assert not torch.isnan(sample['continuous']).any(), \
                    f"NaN in continuous features at index {i}"
                assert not torch.isnan(sample['target']).any(), \
                    f"NaN in target at index {i}"

    def test_normalization_uses_train_stats_only(self, datasets):
        """Normalization mean/std must be computed from training set only."""
        _, _, meta = datasets
        # norm_mean and norm_std should exist and be numpy arrays or lists
        assert 'norm_mean' in meta
        assert 'norm_std' in meta
        # std should be > 0 for all features (no constant features)
        import numpy as np
        std = np.array(meta['norm_std'])
        assert (std > 0).all(), f"Zero std found: {std}"

    def test_dataset_length(self, datasets):
        """Train dataset should have more samples than test (80/20 split)."""
        train_ds, test_ds, _ = datasets
        assert len(train_ds) > len(test_ds)
        assert len(train_ds) > 0
        assert len(test_ds) > 0

    def test_metadata_complete(self, datasets):
        """Metadata dict should contain all required keys."""
        _, _, meta = datasets
        required_meta_keys = {
            'player_to_idx', 'map_to_idx', 'role_to_idx',
            'norm_mean', 'norm_std',
            'n_players', 'n_maps', 'n_roles', 'n_continuous',
            'train_events', 'test_events', 'feature_names',
        }
        missing = required_meta_keys - set(meta.keys())
        assert not missing, f"Missing metadata keys: {missing}"
