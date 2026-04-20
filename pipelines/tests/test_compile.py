from __future__ import annotations

import json

from pipelines.property_search.compile import _spec


def test_embed_spec_contains_expected_steps() -> None:
    spec = _spec("embed")
    assert spec["name"] == "property-search-embed"
    assert spec["steps"] == [
        "load_properties",
        "batch_predict_embeddings",
        "write_embeddings",
    ]


def test_train_spec_is_json_serializable() -> None:
    spec = _spec("train")
    encoded = json.dumps(spec)
    assert "property-search-train" in encoded
