from __future__ import annotations

from scripts.setup.create_schedule import build_schedule_specs
from scripts.setup.setup_model_monitoring import build_monitoring_spec


def test_build_schedule_specs_returns_embed_and_train(monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_ID", "mlops-dev-a")
    monkeypatch.setenv("PIPELINE_ROOT_BUCKET", "mlops-dev-a-pipeline-root")
    monkeypatch.setenv("PIPELINE_TEMPLATE_GCS_PATH", "gs://mlops-dev-a-pipeline-root/templates")
    monkeypatch.setenv("PIPELINE_SERVICE_ACCOUNT", "sa-pipeline@example.com")

    specs = build_schedule_specs("all")

    assert [spec["target"] for spec in specs] == ["embed", "train"]
    assert specs[0]["template_uri"].endswith("property-search-embed.yaml")
    assert specs[1]["template_uri"].endswith("property-search-train.yaml")


def test_build_monitoring_spec_contains_feature_list(monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_ID", "mlops-dev-a")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast1")
    monkeypatch.setenv("VERTEX_RERANKER_ENDPOINT_ID", "projects/x/locations/y/endpoints/z")

    spec = build_monitoring_spec()

    assert spec["feature_names"] == [
        "rent",
        "walk_min",
        "age_years",
        "area_m2",
        "ctr",
        "fav_rate",
        "inquiry_rate",
    ]
    assert spec["monitoring_topic"].endswith("/topics/model-monitoring-alerts")