from __future__ import annotations

import base64
import json

from functions.pipeline_trigger.main import (
    _build_job_id,
    _decode_pubsub_message,
    _merge_parameters,
    _resolve_event_source,
)


def test_decode_pubsub_message_reads_json_payload() -> None:
    payload = {"reasons": ["ndcg_drop"], "parameters": {"force_full_train": True}}
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    event = {"data": {"message": {"data": encoded}}}

    assert _decode_pubsub_message(event) == payload


def test_decode_pubsub_message_returns_empty_when_payload_missing() -> None:
    assert _decode_pubsub_message(None) == {}
    assert _decode_pubsub_message({}) == {}
    assert _decode_pubsub_message({"data": {"message": {}}}) == {}


def test_merge_parameters_promotes_reasons(monkeypatch) -> None:
    monkeypatch.delenv("PIPELINE_PARAMETER_VALUES", raising=False)

    merged = _merge_parameters({"reasons": ["stale_model"]})

    assert merged == {"retrain_reasons": ["stale_model"], "enable_tuning": False}


def test_merge_parameters_overrides_defaults_with_event_payload(monkeypatch) -> None:
    monkeypatch.setenv(
        "PIPELINE_PARAMETER_VALUES",
        json.dumps({"force_full_train": False, "candidate_pool_size": 200}),
    )

    merged = _merge_parameters(
        {
            "parameters": {"force_full_train": True},
            "reasons": ["manual"],
        }
    )

    assert merged == {
        "force_full_train": True,
        "candidate_pool_size": 200,
        "retrain_reasons": ["manual"],
        "enable_tuning": False,
    }


def test_merge_parameters_enables_tuning_for_monitoring_payload(monkeypatch) -> None:
    monkeypatch.delenv("PIPELINE_PARAMETER_VALUES", raising=False)

    merged = _merge_parameters({"source": "monitoring", "reasons": ["feature_drift"]})

    assert merged["enable_tuning"] is True


def test_resolve_event_source_uses_reason_fallback() -> None:
    assert _resolve_event_source({"reasons": ["feature_drift_detected"]}) == "monitoring"
    assert _resolve_event_source({"reasons": ["stale_model"]}) == "scheduler"


def test_build_job_id_uses_prefix() -> None:
    job_id = _build_job_id("property-train")

    assert job_id.startswith("property-train-")
    assert len(job_id.split("-")) >= 4
