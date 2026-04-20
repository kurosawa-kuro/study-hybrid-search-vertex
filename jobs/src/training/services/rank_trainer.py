"""LightGBM LambdaRank trainer — parallel to the legacy regression trainer.

Mirrors the two-stage split of :mod:`.trainer`:

* :func:`train` — pure: consumes train/test DataFrames (must contain
  ``FEATURE_COLS_RANKER`` + ``label`` + ``request_id``), fits
  ``objective='lambdarank'``, returns the booster + metrics + hyperparams.
* :func:`write_artifacts` — I/O: persists ``model.txt`` + ``metrics.json`` +
  ``feature_importance.csv`` under ``output_dir``.

Metrics reported: NDCG@10 (primary), MAP, Recall@20.
Origin: trainer shape copied from jobs/src/training/services/trainer.py;
hyperparameters adapted from study-llm-reranking-mlops/src/trainers/lgbm_trainer.py.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from common import FEATURE_COLS_RANKER, RANKER_GROUP_COL, RANKER_LABEL_COL, get_logger

from .ranking_metrics import evaluate

logger = get_logger(__name__)


@dataclass(frozen=True)
class RankTrainResult:
    booster: lgb.Booster
    metrics: dict[str, float]
    hyperparams: dict[str, object]


@dataclass(frozen=True)
class RankTrainingArtifacts:
    artifacts_dir: Path
    model_path: Path


def build_rank_params(
    *,
    num_leaves: int,
    learning_rate: float,
    feature_fraction: float,
    bagging_fraction: float,
    bagging_freq: int,
    min_data_in_leaf: int,
    lambdarank_truncation_level: int,
) -> dict[str, object]:
    return {
        "objective": "lambdarank",
        "metric": ["ndcg"],
        "ndcg_eval_at": [5, 10, 20],
        "lambdarank_truncation_level": lambdarank_truncation_level,
        "num_leaves": num_leaves,
        "learning_rate": learning_rate,
        "feature_fraction": feature_fraction,
        "bagging_fraction": bagging_fraction,
        "bagging_freq": bagging_freq,
        "min_data_in_leaf": min_data_in_leaf,
        "verbosity": -1,
    }


def _group_sizes(df: pd.DataFrame) -> np.ndarray:
    """Return LightGBM-style group sizes preserving the DataFrame order.

    Requires rows to be grouped contiguously by ``request_id``; the SQL driver
    is expected to ``ORDER BY request_id``.
    """
    group_col = df[RANKER_GROUP_COL].to_numpy()
    if group_col.size == 0:
        return np.array([], dtype=int)
    boundaries = np.where(group_col[:-1] != group_col[1:])[0]
    sizes = np.diff(np.concatenate([[-1], boundaries, [group_col.size - 1]]))
    return sizes.astype(int)


def train(
    *,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    params: dict[str, object],
    num_iterations: int,
    early_stopping_rounds: int,
) -> RankTrainResult:
    """Fit a LightGBM LambdaRank booster, return booster + metrics.

    Pure compute: no filesystem writes. Expects both frames to contain the 9
    columns of ``FEATURE_COLS_RANKER`` plus ``label`` and ``request_id``, and
    to be sorted by ``request_id`` so group boundaries line up.
    """
    required = [*FEATURE_COLS_RANKER, RANKER_LABEL_COL, RANKER_GROUP_COL]
    missing = [c for c in required if c not in train_df.columns]
    if missing:
        raise ValueError(f"Training frame missing columns: {missing}")

    X_train = train_df[FEATURE_COLS_RANKER].to_numpy()
    y_train = train_df[RANKER_LABEL_COL].to_numpy()
    g_train = _group_sizes(train_df)
    X_test = test_df[FEATURE_COLS_RANKER].to_numpy()
    y_test = test_df[RANKER_LABEL_COL].to_numpy()
    g_test = _group_sizes(test_df)

    train_set = lgb.Dataset(X_train, label=y_train, group=g_train, feature_name=FEATURE_COLS_RANKER)
    valid_set = lgb.Dataset(
        X_test,
        label=y_test,
        group=g_test,
        reference=train_set,
        feature_name=FEATURE_COLS_RANKER,
    )

    booster = lgb.train(
        params,
        train_set,
        num_boost_round=num_iterations,
        valid_sets=[valid_set],
        callbacks=[
            lgb.early_stopping(stopping_rounds=early_stopping_rounds),
            lgb.log_evaluation(period=20),
        ],
    )

    y_pred = np.asarray(booster.predict(X_test, num_iteration=booster.best_iteration))
    metrics = evaluate(np.asarray(y_test), y_pred, g_test, k_ndcg=10, k_recall=20)
    metrics["best_iteration"] = int(booster.best_iteration or num_iterations)

    hyperparams = {
        "num_leaves": params["num_leaves"],
        "learning_rate": params["learning_rate"],
        "feature_fraction": params["feature_fraction"],
        "bagging_fraction": params["bagging_fraction"],
        "num_iterations": num_iterations,
        "early_stopping_rounds": early_stopping_rounds,
        "min_data_in_leaf": params["min_data_in_leaf"],
        "lambdarank_truncation_level": params["lambdarank_truncation_level"],
    }
    logger.info("LambdaRank train done — metrics=%s", metrics)
    return RankTrainResult(booster=booster, metrics=metrics, hyperparams=hyperparams)


def write_artifacts(result: RankTrainResult, *, output_dir: Path) -> RankTrainingArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)

    model_path = output_dir / "model.txt"
    result.booster.save_model(str(model_path))

    (output_dir / "metrics.json").write_text(json.dumps(result.metrics, indent=2))

    importances = result.booster.feature_importance(importance_type="gain")
    fi_path = output_dir / "feature_importance.csv"
    with fi_path.open("w", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["feature", "gain"])
        for feat, imp in zip(FEATURE_COLS_RANKER, importances, strict=True):
            w.writerow([feat, float(imp)])

    logger.info("Wrote ranker artifacts to %s", output_dir)
    return RankTrainingArtifacts(artifacts_dir=output_dir, model_path=model_path)
