"""Register the encoder Model in Vertex AI and deploy it to an Endpoint.

Phase 3 one-off, consumed after:

1. ``scripts/setup/upload_encoder_assets.py --apply`` populated
   ``gs://{models-bucket}/encoders/multilingual-e5-base/v1/``
2. ``deploy-encoder-image.yml`` pushed ``property-encoder:<sha>`` to Artifact
   Registry.

Reranker has no sibling script because the KFP ``register_reranker``
component handles upload + deploy inside the train pipeline; the encoder
sits outside any pipeline so it needs an explicit setup step.

Follows the ``setup_model_monitoring.py`` / ``create_schedule.py`` split:
:func:`build_endpoint_spec` resolves a plain-dict spec from env (unit-testable,
no GCP calls); :func:`_apply` performs the actual ``aiplatform.Model.upload``
+ ``Endpoint.deploy`` and is only invoked under ``--apply``.

Idempotent: Endpoints are matched by display_name (create-or-reuse), and the
Model is always uploaded as a new version with alias ``staging``. Traffic is
routed to the new version at 100%. Rollback is ``scripts/ops/promote.py``.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from scripts._common import env

DEFAULT_MACHINE_TYPE: str = "n1-standard-2"
DEFAULT_MIN_REPLICAS: int = 1
DEFAULT_MAX_REPLICAS: int = 3
DEFAULT_ASSET_VERSION: str = "v1"


def _artifact_registry_image(project_id: str, region: str, repo: str, tag: str) -> str:
    return f"{region}-docker.pkg.dev/{project_id}/{repo}/property-encoder:{tag}"


def build_endpoint_spec() -> dict[str, Any]:
    """Resolve the Model-upload + Endpoint-deploy spec without SDK calls."""
    project_id = env("PROJECT_ID")
    region = env("VERTEX_LOCATION", env("REGION"))
    repo = env("ARTIFACT_REPO", "mlops")
    image_tag = env("ENCODER_IMAGE_TAG", "latest")
    bucket = env("GCS_MODELS_BUCKET", f"{project_id}-models" if project_id else "")
    version = env("ENCODER_ASSET_VERSION", DEFAULT_ASSET_VERSION)
    artifact_prefix = f"encoders/multilingual-e5-base/{version}/"
    return {
        "project_id": project_id,
        "vertex_location": region,
        "endpoint_display_name": env(
            "ENCODER_ENDPOINT_DISPLAY_NAME", "property-encoder-endpoint"
        ),
        "model_display_name": env("ENCODER_MODEL_DISPLAY_NAME", "property-encoder"),
        "serving_container_image_uri": _artifact_registry_image(
            project_id, region, repo, image_tag
        ),
        "serving_container_predict_route": "/predict",
        "serving_container_health_route": "/health",
        "serving_container_ports": [8080],
        "artifact_uri": f"gs://{bucket}/{artifact_prefix}" if bucket else "",
        "machine_type": env("ENCODER_MACHINE_TYPE", DEFAULT_MACHINE_TYPE),
        "min_replica_count": int(env("ENCODER_MIN_REPLICAS", str(DEFAULT_MIN_REPLICAS))),
        "max_replica_count": int(env("ENCODER_MAX_REPLICAS", str(DEFAULT_MAX_REPLICAS))),
        "service_account": env(
            "ENCODER_ENDPOINT_SERVICE_ACCOUNT",
            f"sa-endpoint-encoder@{project_id}.iam.gserviceaccount.com"
            if project_id
            else "",
        ),
        "model_alias": env("ENCODER_MODEL_ALIAS", "staging"),
        "traffic_percentage": int(env("ENCODER_TRAFFIC_PERCENTAGE", "100")),
    }


def _get_or_create_endpoint(aiplatform: Any, spec: dict[str, Any]) -> Any:
    existing = aiplatform.Endpoint.list(
        filter=f'display_name="{spec["endpoint_display_name"]}"',
        project=spec["project_id"],
        location=spec["vertex_location"],
    )
    if existing:
        return existing[0]
    return aiplatform.Endpoint.create(
        display_name=spec["endpoint_display_name"],
        project=spec["project_id"],
        location=spec["vertex_location"],
    )


def _apply(spec: dict[str, Any]) -> dict[str, Any]:
    if not spec["artifact_uri"]:
        raise RuntimeError(
            "artifact_uri is empty; run scripts/setup/upload_encoder_assets.py --apply first"
        )
    from google.cloud import aiplatform

    aiplatform.init(project=spec["project_id"], location=spec["vertex_location"])
    model = aiplatform.Model.upload(
        display_name=spec["model_display_name"],
        serving_container_image_uri=spec["serving_container_image_uri"],
        serving_container_predict_route=spec["serving_container_predict_route"],
        serving_container_health_route=spec["serving_container_health_route"],
        serving_container_ports=spec["serving_container_ports"],
        artifact_uri=spec["artifact_uri"],
        version_aliases=[spec["model_alias"]],
    )
    endpoint = _get_or_create_endpoint(aiplatform, spec)
    model.deploy(
        endpoint=endpoint,
        machine_type=spec["machine_type"],
        min_replica_count=spec["min_replica_count"],
        max_replica_count=spec["max_replica_count"],
        traffic_percentage=spec["traffic_percentage"],
        service_account=spec["service_account"],
    )
    return {
        "endpoint_resource_name": endpoint.resource_name,
        "model_resource_name": model.resource_name,
        "model_version_id": model.version_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register + deploy the Vertex AI encoder Model onto its Endpoint"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually call aiplatform.Model.upload + Endpoint.deploy (requires auth).",
    )
    args = parser.parse_args()

    spec = build_endpoint_spec()
    print(json.dumps(spec, ensure_ascii=False, indent=2))
    if args.apply:
        result = _apply(spec)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
