"""Compile pipeline scaffolds into JSON templates.

This is a deliberate placeholder until the real KFP DAGs land. The interface is
kept stable so CI and ops scripts can start wiring around it now.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .embed_pipeline import build_embed_pipeline_spec
from .train_pipeline import build_train_pipeline_spec


def _target_path(root: Path, target: str) -> Path:
    if target == "embed":
        return root / "property-search-embed.json"
    if target == "train":
        return root / "property-search-train.json"
    raise ValueError(f"unknown target: {target}")


def _spec(target: str) -> dict[str, object]:
    if target == "embed":
        return build_embed_pipeline_spec()
    if target == "train":
        return build_train_pipeline_spec()
    raise ValueError(f"unknown target: {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile property-search pipeline scaffold")
    parser.add_argument("--target", choices=["embed", "train"], required=True)
    parser.add_argument(
        "--output-dir",
        default="dist/pipelines",
        help="Directory where the compiled template is written",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = _target_path(output_dir, args.target)
    path.write_text(json.dumps(_spec(args.target), ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
