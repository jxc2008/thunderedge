"""Train player embedding model from SQLite data."""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse

import torch

from backend.ml.train import train_model, evaluate_model
from config import Config


def main() -> None:
    parser = argparse.ArgumentParser(description='Train player embedding model')
    parser.add_argument('--db-path', default=Config.DATABASE_PATH,
                        help='Path to SQLite database')
    parser.add_argument('--embed-dim', type=int, default=8,
                        help='Player embedding dimension (4-8)')
    parser.add_argument('--epochs', type=int, default=50,
                        help='Maximum training epochs')
    parser.add_argument('--batch-size', type=int, default=256,
                        help='Training batch size')
    parser.add_argument('--lr', type=float, default=0.001,
                        help='Learning rate')
    parser.add_argument('--patience', type=int, default=10,
                        help='Early stopping patience')
    parser.add_argument('--model-dir', default='models',
                        help='Directory to save trained model')
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(name)s %(levelname)s: %(message)s',
    )

    result = train_model(
        db_path=args.db_path,
        embed_dim=args.embed_dim,
        lr=args.lr,
        epochs=args.epochs,
        batch_size=args.batch_size,
        patience=args.patience,
        model_dir=args.model_dir,
    )

    # Print summary
    history = result['history']
    print(f"\nTraining complete:")
    print(f"  Best epoch: {result['best_epoch'] + 1}")
    print(f"  Final train loss: {history['train_loss'][-1]:.4f}")
    print(f"  Final val loss: {history['val_loss'][-1]:.4f}")
    print(f"  Best val loss: {min(history['val_loss']):.4f}")

    # Evaluate
    eval_result = evaluate_model(result['model'], result['test_dataset'])
    print(f"\nTest set evaluation:")
    print(f"  RMSE: {eval_result['rmse']:.2f} kills")
    print(f"  MAE: {eval_result['mae']:.2f} kills")

    # Quick embedding sanity check
    model = result['model']
    meta = result['metadata']
    print(f"\nEmbedding space:")
    print(f"  Players: {meta['n_players']}")
    print(f"  Embedding dim: {args.embed_dim}")

    # Show a few example embeddings
    sample_players = list(meta['player_to_idx'].items())[:5]
    for name, idx in sample_players:
        vec = model.get_player_embedding(torch.tensor([idx]))
        print(f"  {name}: {vec.numpy().flatten()[:4]}...")


if __name__ == '__main__':
    main()
