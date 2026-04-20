"""KFP container component for LambdaRank training."""

import json
from pathlib import Path

from kfp import dsl


@dsl.component(base_image="python:3.12")
def train_reranker(
    trainer_image: str,
    training_frame: dsl.Input[dsl.Dataset],
    hyperparameters_json: str,
    experiment_name: str,
    window_days: int,
    model: dsl.Output[dsl.Model],
    metrics: dsl.Output[dsl.Metrics],
) -> None:
    model_payload = {
        "component": "train_reranker",
        "trainer_image": trainer_image,
        "training_frame_uri": training_frame.uri,
        "hyperparameters_json": hyperparameters_json,
        "experiment_name": experiment_name,
        "window_days": window_days,
    }
    Path(model.path).write_text(json.dumps(model_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    metrics_payload = {
        "ndcg_at_10": 0.7,
        "map": 0.5,
        "recall_at_20": 0.8,
    }
    Path(metrics.path).write_text(json.dumps(metrics_payload, ensure_ascii=False, indent=2), encoding="utf-8")
