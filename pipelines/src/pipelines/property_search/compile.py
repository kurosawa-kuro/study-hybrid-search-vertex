"""Compile and optionally submit property-search Vertex pipelines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from kfp.compiler import Compiler

from .embed_pipeline import build_embed_pipeline_spec, get_embed_pipeline
from .train_pipeline import build_train_pipeline_spec, get_train_pipeline


def _target_path(root: Path, target: str) -> Path:
    if target == "embed":
        return root / "property-search-embed.yaml"
    if target == "train":
        return root / "property-search-train.yaml"
    raise ValueError(f"unknown target: {target}")


def _spec(target: str) -> dict[str, object]:
    if target == "embed":
        return build_embed_pipeline_spec()
    if target == "train":
        return build_train_pipeline_spec()
    raise ValueError(f"unknown target: {target}")


def _pipeline(target: str):
    if target == "embed":
        return get_embed_pipeline()
    if target == "train":
        return get_train_pipeline()
    raise ValueError(f"unknown target: {target}")


def _coerce_parameter_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        pass
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _merge_parameter_values(target: str, overrides: list[str]) -> dict[str, Any]:
    spec = _spec(target)
    params = dict(spec.get("parameters", {}))
    for item in overrides:
        key, sep, value = item.partition("=")
        if not sep:
            raise ValueError(f"parameter override must be key=value: {item}")
        params[key] = _coerce_parameter_value(value)
    return params


def _submit_pipeline(
    *,
    target: str,
    template_path: Path,
    pipeline_root: str,
    project_id: str,
    location: str,
    service_account: str,
    parameter_values: dict[str, Any],
) -> str:
    from google.cloud import aiplatform

    aiplatform.init(project=project_id, location=location)
    job = aiplatform.PipelineJob(
        display_name=f"property-search-{target}",
        template_path=str(template_path),
        pipeline_root=pipeline_root,
        parameter_values=parameter_values,
        enable_caching=False,
    )
    job.submit(service_account=service_account or None)
    return job.resource_name


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile property-search pipelines")
    parser.add_argument("--target", choices=["embed", "train"], required=True)
    parser.add_argument(
        "--output-dir",
        default="dist/pipelines",
        help="Directory where the compiled template is written",
    )
    parser.add_argument(
        "--parameter",
        action="append",
        default=[],
        help="Override pipeline parameter values as key=value (repeatable)",
    )
    parser.add_argument("--submit", action="store_true", help="Submit the compiled pipeline to Vertex AI")
    parser.add_argument("--project-id", default="mlops-dev-a")
    parser.add_argument("--location", default="asia-northeast1")
    parser.add_argument("--pipeline-root", default="gs://mlops-dev-a-pipeline-root/runs")
    parser.add_argument("--service-account", default="")
    parser.add_argument(
        "--write-spec-json",
        action="store_true",
        help="Also write the resolved pipeline spec as JSON next to the compiled YAML",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = _target_path(output_dir, args.target)
    Compiler().compile(pipeline_func=_pipeline(args.target), package_path=str(path))
    params = _merge_parameter_values(args.target, args.parameter)
    if args.write_spec_json:
        spec_path = path.with_suffix(".json")
        spec_payload = _spec(args.target) | {"resolved_parameters": params}
        spec_path.write_text(json.dumps(spec_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.submit:
        resource_name = _submit_pipeline(
            target=args.target,
            template_path=path,
            pipeline_root=args.pipeline_root,
            project_id=args.project_id,
            location=args.location,
            service_account=args.service_account,
            parameter_values=params,
        )
        print(resource_name)
        return 0
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
