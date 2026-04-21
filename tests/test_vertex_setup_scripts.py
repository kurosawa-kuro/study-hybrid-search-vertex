from __future__ import annotations

from scripts.setup.create_schedule import build_schedule_specs
from scripts.setup.print_github_variables import build_gh_commands, build_variable_rows
from scripts.setup.setup_encoder_endpoint import build_endpoint_spec
from scripts.setup.setup_model_monitoring import build_monitoring_spec
from scripts.setup.upload_encoder_assets import build_upload_spec


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


def test_build_upload_spec_targets_models_bucket(monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_ID", "mlops-dev-a")
    monkeypatch.setenv("GCS_MODELS_BUCKET", "mlops-dev-a-models")
    monkeypatch.delenv("ENCODER_ASSET_VERSION", raising=False)

    spec = build_upload_spec()

    assert spec["model_name"] == "intfloat/multilingual-e5-base"
    assert spec["bucket"] == "mlops-dev-a-models"
    assert spec["prefix"] == "encoders/multilingual-e5-base/v1/"
    assert spec["gcs_uri"] == "gs://mlops-dev-a-models/encoders/multilingual-e5-base/v1/"


def test_build_upload_spec_falls_back_to_project_named_bucket(monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_ID", "mlops-dev-a")
    monkeypatch.delenv("GCS_MODELS_BUCKET", raising=False)

    spec = build_upload_spec()

    assert spec["bucket"] == "mlops-dev-a-models"


def test_build_endpoint_spec_wires_ar_image_and_sa(monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_ID", "mlops-dev-a")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast1")
    monkeypatch.setenv("REGION", "asia-northeast1")
    monkeypatch.setenv("ARTIFACT_REPO", "mlops")
    monkeypatch.setenv("GCS_MODELS_BUCKET", "mlops-dev-a-models")
    monkeypatch.setenv("ENCODER_IMAGE_TAG", "abc12345")

    spec = build_endpoint_spec()

    assert spec["serving_container_image_uri"] == (
        "asia-northeast1-docker.pkg.dev/mlops-dev-a/mlops/property-encoder:abc12345"
    )
    assert spec["serving_container_predict_route"] == "/predict"
    assert spec["serving_container_health_route"] == "/health"
    assert spec["serving_container_ports"] == [8080]
    assert spec["artifact_uri"] == "gs://mlops-dev-a-models/encoders/multilingual-e5-base/v1/"
    assert spec["service_account"] == "sa-endpoint-encoder@mlops-dev-a.iam.gserviceaccount.com"
    assert spec["endpoint_display_name"] == "property-encoder-endpoint"
    assert spec["machine_type"] == "n1-standard-2"
    assert spec["traffic_percentage"] == 100
    assert spec["model_alias"] == "staging"


def test_build_variable_rows_marks_empty_values_unresolved(monkeypatch) -> None:
    monkeypatch.setenv("WORKLOAD_IDENTITY_PROVIDER", "projects/1/locations/global/.../github-oidc")
    monkeypatch.setenv("DEPLOYER_SERVICE_ACCOUNT", "sa-github-deployer@mlops-dev-a.iam.gserviceaccount.com")
    monkeypatch.setenv("ONCALL_EMAIL", "oncall@example.org")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast1")
    # Leave the endpoint IDs empty — caller hasn't deployed the Models yet.
    monkeypatch.setenv("VERTEX_ENCODER_ENDPOINT_ID", "")
    monkeypatch.setenv("VERTEX_RERANKER_ENDPOINT_ID", "")

    rows = {row["name"]: row for row in build_variable_rows()}

    assert rows["WORKLOAD_IDENTITY_PROVIDER"]["resolved"] is True
    assert rows["VERTEX_ENCODER_ENDPOINT_ID"]["resolved"] is False
    assert rows["VERTEX_RERANKER_ENDPOINT_ID"]["resolved"] is False


def test_build_gh_commands_quotes_values_with_slashes(monkeypatch) -> None:
    monkeypatch.setenv("WORKLOAD_IDENTITY_PROVIDER", "projects/1/locations/global/workloadIdentityPools/github/providers/github-oidc")
    monkeypatch.setenv("DEPLOYER_SERVICE_ACCOUNT", "sa-github-deployer@mlops-dev-a.iam.gserviceaccount.com")
    monkeypatch.setenv("ONCALL_EMAIL", "oncall@example.org")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast1")
    monkeypatch.setenv("VERTEX_ENCODER_ENDPOINT_ID", "projects/1/locations/asia-northeast1/endpoints/1234567890")
    monkeypatch.setenv("VERTEX_RERANKER_ENDPOINT_ID", "projects/1/locations/asia-northeast1/endpoints/9876543210")

    cmds = build_gh_commands("owner/repo")

    assert cmds[0].startswith("gh variable set WORKLOAD_IDENTITY_PROVIDER --repo owner/repo --body ")
    assert cmds[4].endswith(" projects/1/locations/asia-northeast1/endpoints/1234567890")
    assert "VERTEX_ENCODER_ENDPOINT_ID" in cmds[4]
