"""Training loop for player embedding model.

Provides train_model() for end-to-end training with validation and early
stopping, evaluate_model() for computing metrics, and load_model() for
restoring a trained model from disk.
"""
import json
import logging
import os
from typing import Any, Optional

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from backend.ml.dataset import create_datasets
from backend.ml.embedding_model import PlayerEmbeddingModel

logger = logging.getLogger(__name__)


def collate_fn(batch: list[dict[str, torch.Tensor]]) -> dict[str, torch.Tensor]:
    """Stack dict-based dataset items into batched tensors.

    Args:
        batch: List of dicts from PlayerMapDataset.__getitem__

    Returns:
        Dict with same keys, values stacked into batch tensors.
    """
    return {
        'player_idx': torch.stack([b['player_idx'] for b in batch]),
        'map_idx': torch.stack([b['map_idx'] for b in batch]),
        'role_idx': torch.stack([b['role_idx'] for b in batch]),
        'continuous': torch.stack([b['continuous'] for b in batch]),
        'target': torch.stack([b['target'] for b in batch]),
    }


def train_model(
    db_path: str,
    embed_dim: int = 8,
    lr: float = 0.001,
    epochs: int = 50,
    batch_size: int = 256,
    patience: int = 10,
    model_dir: str = 'models',
) -> dict[str, Any]:
    """Train the player embedding model end-to-end.

    Args:
        db_path: Path to SQLite database.
        embed_dim: Dimension of player embeddings (4-8).
        lr: Learning rate for Adam optimizer.
        epochs: Maximum training epochs.
        batch_size: Mini-batch size.
        patience: Early stopping patience (epochs without val improvement).
        model_dir: Directory to save trained model and metadata.

    Returns:
        Dict with keys: model, metadata, history, best_epoch, test_dataset
    """
    # Create datasets
    train_ds, test_ds, metadata = create_datasets(db_path)
    logger.info(
        "Datasets created: train=%d, test=%d, players=%d, maps=%d, roles=%d",
        len(train_ds), len(test_ds),
        metadata['n_players'], metadata['n_maps'], metadata['n_roles'],
    )

    # Create model
    model = PlayerEmbeddingModel(
        n_players=metadata['n_players'],
        n_maps=metadata['n_maps'],
        n_roles=metadata['n_roles'],
        n_continuous=metadata['n_continuous'],
        embed_dim=embed_dim,
    )

    # Optimizer and loss
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    # Data loaders
    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True, collate_fn=collate_fn,
    )
    val_loader = DataLoader(
        test_ds, batch_size=batch_size, shuffle=False, collate_fn=collate_fn,
    )

    # Training loop
    history: dict[str, list[float]] = {'train_loss': [], 'val_loss': []}
    best_val_loss = float('inf')
    best_epoch = 0
    best_state = None
    epochs_without_improvement = 0

    for epoch in range(epochs):
        # Train
        model.train()
        train_losses: list[float] = []
        for batch_data in train_loader:
            optimizer.zero_grad()
            pred = model(
                batch_data['player_idx'],
                batch_data['map_idx'],
                batch_data['role_idx'],
                batch_data['continuous'],
            )
            loss = criterion(pred.squeeze(), batch_data['target'])
            loss.backward()
            optimizer.step()
            train_losses.append(loss.item())

        avg_train_loss = float(np.mean(train_losses))

        # Validate
        model.eval()
        val_losses: list[float] = []
        with torch.no_grad():
            for batch_data in val_loader:
                pred = model(
                    batch_data['player_idx'],
                    batch_data['map_idx'],
                    batch_data['role_idx'],
                    batch_data['continuous'],
                )
                loss = criterion(pred.squeeze(), batch_data['target'])
                val_losses.append(loss.item())

        avg_val_loss = float(np.mean(val_losses))

        history['train_loss'].append(avg_train_loss)
        history['val_loss'].append(avg_val_loss)

        # Early stopping check
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            best_epoch = epoch
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1

        # Log progress every 5 epochs
        if (epoch + 1) % 5 == 0 or epoch == 0:
            logger.info(
                "Epoch %d/%d  train_loss=%.4f  val_loss=%.4f  best_val=%.4f",
                epoch + 1, epochs, avg_train_loss, avg_val_loss, best_val_loss,
            )

        if epochs_without_improvement >= patience:
            logger.info(
                "Early stopping at epoch %d (no improvement for %d epochs)",
                epoch + 1, patience,
            )
            break

    # Restore best model
    if best_state is not None:
        model.load_state_dict(best_state)
    logger.info("Best epoch: %d with val_loss=%.4f", best_epoch + 1, best_val_loss)

    # Save model and metadata
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, 'player_embeddings.pt')
    torch.save(model.state_dict(), model_path)
    logger.info("Model saved to %s", model_path)

    # Prepare serializable metadata
    meta_to_save = {
        'n_players': metadata['n_players'],
        'n_maps': metadata['n_maps'],
        'n_roles': metadata['n_roles'],
        'n_continuous': metadata['n_continuous'],
        'embed_dim': embed_dim,
        'player_to_idx': metadata['player_to_idx'],
        'map_to_idx': metadata['map_to_idx'],
        'role_to_idx': metadata['role_to_idx'],
        'norm_mean': metadata['norm_mean'],
        'norm_std': metadata['norm_std'],
        'feature_names': metadata['feature_names'],
        'train_events': sorted(metadata['train_events']),
        'test_events': sorted(metadata['test_events']),
        'history': history,
        'best_epoch': best_epoch,
        'best_val_loss': best_val_loss,
    }
    meta_path = os.path.join(model_dir, 'training_meta.json')
    with open(meta_path, 'w') as f:
        json.dump(meta_to_save, f, indent=2)
    logger.info("Metadata saved to %s", meta_path)

    return {
        'model': model,
        'metadata': metadata,
        'history': history,
        'best_epoch': best_epoch,
        'test_dataset': test_ds,
    }


def evaluate_model(
    model: PlayerEmbeddingModel,
    dataset: Any,
    batch_size: int = 256,
) -> dict[str, float]:
    """Compute evaluation metrics on a dataset.

    Args:
        model: Trained PlayerEmbeddingModel.
        dataset: PlayerMapDataset instance.
        batch_size: Batch size for evaluation.

    Returns:
        Dict with keys: mse, mae, rmse
    """
    loader = DataLoader(
        dataset, batch_size=batch_size, shuffle=False, collate_fn=collate_fn,
    )

    model.eval()
    all_preds: list[torch.Tensor] = []
    all_targets: list[torch.Tensor] = []

    with torch.no_grad():
        for batch_data in loader:
            pred = model(
                batch_data['player_idx'],
                batch_data['map_idx'],
                batch_data['role_idx'],
                batch_data['continuous'],
            )
            all_preds.append(pred.squeeze())
            all_targets.append(batch_data['target'])

    preds = torch.cat(all_preds)
    targets = torch.cat(all_targets)

    mse = float(nn.functional.mse_loss(preds, targets).item())
    mae = float(torch.mean(torch.abs(preds - targets)).item())
    rmse = float(np.sqrt(mse))

    return {'mse': mse, 'mae': mae, 'rmse': rmse}


def load_model(
    model_dir: str = 'models',
) -> tuple[PlayerEmbeddingModel, dict[str, Any]]:
    """Load a trained model and its metadata from disk.

    Args:
        model_dir: Directory containing player_embeddings.pt and training_meta.json.

    Returns:
        (model, metadata_dict)
    """
    meta_path = os.path.join(model_dir, 'training_meta.json')
    with open(meta_path, 'r') as f:
        metadata = json.load(f)

    model = PlayerEmbeddingModel(
        n_players=metadata['n_players'],
        n_maps=metadata['n_maps'],
        n_roles=metadata['n_roles'],
        n_continuous=metadata['n_continuous'],
        embed_dim=metadata['embed_dim'],
    )

    model_path = os.path.join(model_dir, 'player_embeddings.pt')
    model.load_state_dict(torch.load(model_path, weights_only=True))
    model.eval()

    return model, metadata
