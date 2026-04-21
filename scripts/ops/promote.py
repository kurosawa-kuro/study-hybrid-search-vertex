"""Promote a registered Vertex model version to production."""

from __future__ import annotations

import argparse
import json

from google.cloud import aiplatform

from scripts._common import env


def build_promotion_plan(model_kind: str, version_alias: str) -> dict[str, str]:
    project_id = env("PROJECT_ID")
    location = env("VERTEX_LOCATION", env("REGION"))
    endpoint = env(
        "VERTEX_RERANKER_ENDPOINT_ID" if model_kind == "reranker" else "VERTEX_ENCODER_ENDPOINT_ID"
    )
    display_name = env(
        "RERANKER_ENDPOINT_DISPLAY_NAME"
        if model_kind == "reranker"
        else "ENCODER_ENDPOINT_DISPLAY_NAME",
        "property-reranker" if model_kind == "reranker" else "property-encoder",
    )
    return {
        "project_id": project_id,
        "location": location,
        "endpoint": endpoint,
        "display_name": display_name,
        "version_alias": version_alias,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a Vertex model alias")
    parser.add_argument("model_kind", choices=["reranker", "encoder"])
    parser.add_argument("version_alias")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    plan = build_promotion_plan(args.model_kind, args.version_alias)
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    aiplatform.init(project=plan["project_id"], location=plan["location"])
    models = aiplatform.Model.list(filter=f'display_name="{plan["display_name"]}"')
    matched = None
    for model in models:
        version_aliases = getattr(model, "version_aliases", []) or []
        if args.version_alias in version_aliases or model.display_name.endswith(args.version_alias):
            matched = model
            break
    if matched is None:
        raise RuntimeError(f"model alias not found: {args.version_alias}")

    endpoint_name = plan["endpoint"]
    endpoint = aiplatform.Endpoint(endpoint_name=endpoint_name)
    matched.deploy(
        endpoint=endpoint,
        deployed_model_display_name=plan["display_name"],
        machine_type="n1-standard-2",
        min_replica_count=1,
        max_replica_count=5,
        traffic_percentage=100,
        sync=True,
    )
    print(
        json.dumps({"promoted_model": matched.resource_name, **plan}, ensure_ascii=False, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
