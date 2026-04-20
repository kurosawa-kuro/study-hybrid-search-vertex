"""Ranking metrics + label helpers. Pure numpy — no GCP SDK, no LightGBM."""

from .label_gain import assign_label
from .metrics import evaluate, mean_average_precision, ndcg_at_k, recall_at_k

__all__ = [
    "assign_label",
    "evaluate",
    "mean_average_precision",
    "ndcg_at_k",
    "recall_at_k",
]
