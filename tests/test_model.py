"""Tests for PlayerEmbeddingModel architecture and training loop."""
import os
import sys
import json
import tempfile

import pytest
import torch
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.ml.embedding_model import PlayerEmbeddingModel
from backend.ml.train import train_model, evaluate_model, load_model


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def small_model():
    """Create a small model for unit tests."""
    return PlayerEmbeddingModel(
        n_players=10, n_maps=5, n_roles=4,
        n_continuous=8, embed_dim=8,
    )


@pytest.fixture
def batch():
    """Create a small synthetic batch."""
    bs = 4
    return {
        'player_idx': torch.randint(0, 10, (bs,)),
        'map_idx': torch.randint(0, 5, (bs,)),
        'role_idx': torch.randint(0, 4, (bs,)),
        'continuous': torch.randn(bs, 8),
        'target': torch.randn(bs),
    }


# ---------------------------------------------------------------------------
# Model architecture tests
# ---------------------------------------------------------------------------

class TestModelArchitecture:

    def test_model_forward_shape(self, small_model, batch):
        """Output shape is (batch_size, 1)."""
        out = small_model(
            batch['player_idx'], batch['map_idx'],
            batch['role_idx'], batch['continuous'],
        )
        assert out.shape == (4, 1)

    def test_model_embedding_dim(self, small_model):
        """get_player_embedding returns vector of correct dim."""
        idx = torch.tensor([1])
        emb = small_model.get_player_embedding(idx)
        assert emb.shape == (1, 8)

    def test_model_no_nan_output(self, small_model, batch):
        """Forward pass produces no NaN."""
        out = small_model(
            batch['player_idx'], batch['map_idx'],
            batch['role_idx'], batch['continuous'],
        )
        assert not torch.isnan(out).any()

    def test_get_all_embeddings(self, small_model):
        """get_all_embeddings returns full weight matrix."""
        embs = small_model.get_all_embeddings()
        assert embs.shape == (10, 8)
        assert not embs.requires_grad


# ---------------------------------------------------------------------------
# Training loop tests
# ---------------------------------------------------------------------------

class TestTraining:

    def test_training_loss_decreases(self, tmp_path, db_path):
        """Train for a few epochs on real data, assert loss decreases."""
        model_dir = str(tmp_path / 'models')
        result = train_model(
            db_path=db_path,
            embed_dim=8, lr=0.001, epochs=5,
            batch_size=256, patience=10,
            model_dir=model_dir,
        )
        history = result['history']
        assert history['train_loss'][-1] < history['train_loss'][0], \
            "Training loss should decrease over epochs"

    def test_val_loss_tracked(self, tmp_path, db_path):
        """history dict contains val_loss list with correct length."""
        model_dir = str(tmp_path / 'models')
        result = train_model(
            db_path=db_path,
            embed_dim=8, lr=0.001, epochs=3,
            batch_size=256, patience=10,
            model_dir=model_dir,
        )
        history = result['history']
        assert 'val_loss' in history
        assert len(history['val_loss']) == 3

    def test_model_save_load_roundtrip(self, tmp_path, db_path):
        """Save model, load it, verify same output for same input."""
        model_dir = str(tmp_path / 'models')
        result = train_model(
            db_path=db_path,
            embed_dim=8, lr=0.001, epochs=3,
            batch_size=256, patience=10,
            model_dir=model_dir,
        )

        # Get output from original model
        original_model = result['model']
        original_model.eval()
        test_idx = torch.tensor([1])
        with torch.no_grad():
            orig_emb = original_model.get_player_embedding(test_idx)

        # Load model from disk
        loaded_model, loaded_meta = load_model(model_dir)
        loaded_model.eval()
        with torch.no_grad():
            loaded_emb = loaded_model.get_player_embedding(test_idx)

        assert torch.allclose(orig_emb, loaded_emb, atol=1e-6), \
            "Loaded model should produce identical embeddings"

        # Verify metadata was saved
        assert os.path.exists(os.path.join(model_dir, 'training_meta.json'))
        assert os.path.exists(os.path.join(model_dir, 'player_embeddings.pt'))
