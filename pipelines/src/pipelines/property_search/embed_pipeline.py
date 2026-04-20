"""Embed pipeline scaffold.

The concrete KFP DAG is intentionally deferred until the surrounding Vertex
resources are fully wired. This module keeps a stable import path so Terraform,
CI, and follow-on implementation can converge on one canonical location.
"""

from __future__ import annotations


PIPELINE_NAME = "property-search-embed"


def build_embed_pipeline_spec() -> dict[str, object]:
    return {
        "name": PIPELINE_NAME,
        "description": "Scaffold for property text embedding batch pipeline",
        "steps": [
            "load_properties",
            "batch_predict_embeddings",
            "write_embeddings",
        ],
    }
