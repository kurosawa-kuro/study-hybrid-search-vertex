"""KFP component: evaluate gating metric from a metrics artifact."""

from __future__ import annotations

import json
from pathlib import Path

from kfp import dsl


@dsl.component(base_image="python:3.12")
def evaluate_reranker(
    metrics_artifact: dsl.Input[dsl.Metrics],
    metric_name: str,
    threshold: float,
) -> bool:
    metrics_path = Path(metrics_artifact.path)
    payload = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    value = float(payload.get(metric_name, 0.0))
    return value >= threshold
