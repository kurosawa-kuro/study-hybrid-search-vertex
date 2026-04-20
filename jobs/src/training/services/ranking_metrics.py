"""Ranking evaluation wrapper used by the LambdaRank trainer.

Thin shim around :mod:`common.ranking.metrics` that exposes a single
``evaluate`` taking the same numpy arrays LightGBM's training loop produces.
Kept here so the trainer can import ``from .ranking_metrics import evaluate``
by analogy with the existing ``regression_metrics`` module.
"""

from __future__ import annotations

import numpy as np
from common.ranking import evaluate as _evaluate


def evaluate(
    labels: np.ndarray,
    scores: np.ndarray,
    groups: np.ndarray,
    *,
    k_ndcg: int = 10,
    k_recall: int = 20,
) -> dict[str, float]:
    return _evaluate(labels, scores, groups, k_ndcg=k_ndcg, k_recall=k_recall)
