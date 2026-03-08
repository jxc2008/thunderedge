"""Player embedding model for kill prediction.

Entity embedding MLP that learns player representations as a byproduct of
predicting per-map kill counts. Embedding vectors are extracted for downstream
k-NN similarity search and visualization.
"""
import logging
from typing import Optional

import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


class PlayerEmbeddingModel(nn.Module):
    """Entity embedding MLP for player kill prediction.

    Architecture:
        - Embedding layers for player, map, role (categorical features)
        - MLP head that combines embeddings with continuous features
        - Output: predicted kill count (scalar)

    The player embedding layer is the key artifact -- its learned weights
    encode player skill/style into a dense vector space.
    """

    def __init__(
        self,
        n_players: int,
        n_maps: int,
        n_roles: int,
        n_continuous: int,
        embed_dim: int = 8,
        map_embed_dim: int = 4,
        role_embed_dim: int = 3,
        hidden_dims: Optional[list[int]] = None,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()

        if hidden_dims is None:
            hidden_dims = [64, 32]

        # Embedding layers
        self.player_embed = nn.Embedding(n_players, embed_dim)
        self.map_embed = nn.Embedding(n_maps, map_embed_dim)
        self.role_embed = nn.Embedding(n_roles, role_embed_dim)

        # MLP head
        mlp_input_dim = embed_dim + map_embed_dim + role_embed_dim + n_continuous
        layers: list[nn.Module] = []
        prev_dim = mlp_input_dim

        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.ReLU(),
                nn.Dropout(dropout),
            ])
            prev_dim = hidden_dim

        layers.append(nn.Linear(prev_dim, 1))
        self.mlp = nn.Sequential(*layers)

        # Store config for serialization
        self.embed_dim = embed_dim
        self.n_players = n_players
        self.n_maps = n_maps
        self.n_roles = n_roles
        self.n_continuous = n_continuous

        logger.info(
            "PlayerEmbeddingModel: %d players, embed_dim=%d, "
            "mlp_input=%d, hidden=%s",
            n_players, embed_dim, mlp_input_dim, hidden_dims,
        )

    def forward(
        self,
        player_idx: torch.Tensor,
        map_idx: torch.Tensor,
        role_idx: torch.Tensor,
        continuous: torch.Tensor,
    ) -> torch.Tensor:
        """Forward pass: predict kill count.

        Args:
            player_idx: (batch_size,) LongTensor of player indices
            map_idx: (batch_size,) LongTensor of map indices
            role_idx: (batch_size,) LongTensor of role indices
            continuous: (batch_size, n_continuous) FloatTensor

        Returns:
            (batch_size, 1) FloatTensor of predicted kills
        """
        p_emb = self.player_embed(player_idx)
        m_emb = self.map_embed(map_idx)
        r_emb = self.role_embed(role_idx)

        x = torch.cat([p_emb, m_emb, r_emb, continuous], dim=1)
        return self.mlp(x)

    def get_player_embedding(self, player_idx: torch.Tensor) -> torch.Tensor:
        """Extract player embedding vector (detached from computation graph).

        Args:
            player_idx: (N,) LongTensor of player indices

        Returns:
            (N, embed_dim) FloatTensor of embedding vectors
        """
        with torch.no_grad():
            return self.player_embed(player_idx).detach()

    def get_all_embeddings(self) -> torch.Tensor:
        """Return the full player embedding weight matrix (detached).

        Returns:
            (n_players, embed_dim) FloatTensor
        """
        return self.player_embed.weight.data.detach()
