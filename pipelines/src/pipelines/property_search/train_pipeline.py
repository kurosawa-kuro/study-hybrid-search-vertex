"""Train pipeline scaffold."""

from __future__ import annotations


PIPELINE_NAME = "property-search-train"


def build_train_pipeline_spec() -> dict[str, object]:
    return {
        "name": PIPELINE_NAME,
        "description": "Scaffold for reranker training / evaluation / registration pipeline",
        "steps": [
            "load_features",
            "train_reranker",
            "evaluate",
            "register_reranker",
        ],
    }
