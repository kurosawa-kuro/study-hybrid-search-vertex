"""AST-based layer boundary checker.

Walks every Port / pure-logic module listed in `RULES` and reports any
forbidden import (concrete adapter, GCP SDK, W&B, LightGBM where
inapplicable). Each file is inspected at *every* `Import` / `ImportFrom`
node — top-level AND inside functions — so lazy imports cannot smuggle a
banned dependency back in.

Two consumers share the canonical ruleset declared here:

- `tests/test_import_boundaries.py` imports `RULES`, `UNIVERSAL_BANS`, and
  `find_violations()` so pytest cases stay aligned with this script (no
  duplication).
- `make check-layers` runs `python -m scripts.check_layers` for ad-hoc
  inspection outside pytest. Exit code 0 = clean, 1 = violations found,
  with `<rel_path>:<line>` references for every offending import.

To add a rule: extend `RULES` below. Both the CLI and the pytest cases
pick the change up automatically.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Every Port / pure-logic file is disallowed from importing these at all.
UNIVERSAL_BANS: frozenset[str] = frozenset({"google.cloud", "wandb"})

# Reused per-file ban-set: the common workspace's concrete adapters / GCS
# storage layer must not leak into Ports or pure-logic modules of any
# downstream workspace.
COMMON_ADAPTERS: frozenset[str] = frozenset(
    {
        "common.adapters",  # covers common.adapters.*
        "common.storage",  # covers common.storage.*
    }
)

RULES: dict[str, frozenset[str]] = {
    # common/ — Port + pure-logic layer
    "common/src/common/ports/embedding_store.py": frozenset({"lightgbm", "sentence_transformers"}),
    "common/src/common/feature_engineering.py": frozenset({"lightgbm"}),
    "common/src/common/schema/feature_schema.py": frozenset({"lightgbm", "pandas", "numpy"}),
    "common/src/common/ranking/metrics.py": frozenset({"lightgbm", "pandas"}),
    "common/src/common/ranking/label_gain.py": frozenset({"lightgbm", "pandas", "numpy"}),
    "common/src/common/embeddings/e5_encoder.py": frozenset({"lightgbm", "pandas"}),
    "common/src/common/run_id.py": frozenset({"lightgbm", "pandas", "numpy"}),
    "common/src/common/logging/structured_logging.py": frozenset({"lightgbm", "pandas", "numpy"}),
    "common/src/common/config.py": frozenset({"lightgbm"}),
    # app/ — Port + pure-logic layer
    "app/src/app/ports/publisher.py": COMMON_ADAPTERS,
    "app/src/app/ports/retrain_queries.py": COMMON_ADAPTERS,
    "app/src/app/ports/training_job_runner.py": COMMON_ADAPTERS,
    "app/src/app/ports/cache_store.py": COMMON_ADAPTERS,
    "app/src/app/ports/lexical_search.py": COMMON_ADAPTERS,
    "app/src/app/ports/candidate_retriever.py": COMMON_ADAPTERS | frozenset({"lightgbm"}),
    "app/src/app/ports/model_store.py": COMMON_ADAPTERS | frozenset({"lightgbm"}),
    "app/src/app/services/retrain_policy.py": COMMON_ADAPTERS,
    "app/src/app/services/ranking.py": COMMON_ADAPTERS | frozenset({"sentence_transformers"}),
    "app/src/app/services/model_store.py": COMMON_ADAPTERS,
    "app/src/app/schemas/search.py": COMMON_ADAPTERS | frozenset({"lightgbm", "numpy"}),
    "app/src/app/middleware/request_logging.py": COMMON_ADAPTERS,
    "app/src/app/config.py": COMMON_ADAPTERS | frozenset({"lightgbm"}),
    # jobs/ — Port + pure-logic layer
    "jobs/src/training/entrypoints/rank_cli.py": frozenset(),
    "jobs/src/training/entrypoints/embed_cli.py": frozenset(),
    "jobs/src/training/ports/ranker_repository.py": COMMON_ADAPTERS
    | frozenset({"lightgbm", "training.adapters"}),
    "jobs/src/training/ports/artifact_uploader.py": COMMON_ADAPTERS
    | frozenset({"lightgbm", "training.adapters"}),
    "jobs/src/training/ports/experiment_tracker.py": COMMON_ADAPTERS
    | frozenset({"lightgbm", "training.adapters", "wandb"}),
    "jobs/src/training/services/rank_trainer.py": COMMON_ADAPTERS,
    "jobs/src/training/services/ranking_metrics.py": COMMON_ADAPTERS | frozenset({"lightgbm"}),
    "jobs/src/training/services/embedding_runner.py": COMMON_ADAPTERS
    | frozenset({"lightgbm", "sentence_transformers", "training.adapters"}),
    "jobs/src/training/config.py": frozenset({"lightgbm"}),
}


@dataclass(frozen=True)
class Violation:
    """One forbidden import in one file."""

    rel_path: str
    line: int
    imported: str
    banned_prefix: str

    def __str__(self) -> str:
        return (
            f"{self.rel_path}:{self.line}  import {self.imported!r} "
            f"hits banned prefix {self.banned_prefix!r}"
        )


def _imports_with_lines(path: Path) -> list[tuple[int, str]]:
    """Every imported module name + the source line where it appears.

    Walks the AST exhaustively (via `ast.walk`), so imports inside
    functions / class bodies / conditional branches are caught as well as
    top-level ones — lazy imports cannot bypass the check.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
    return found


def _matches(imported: str, banned: str) -> bool:
    """Prefix match: imported equals `banned` itself or is one of its submodules."""
    return imported == banned or imported.startswith(banned + ".")


def find_violations(rel_path: str) -> list[Violation]:
    """Return every `(line, imported, banned_prefix)` violation in the given file."""
    path = REPO_ROOT / rel_path
    if not path.exists():
        return [Violation(rel_path, 0, "<missing source file>", "")]

    bans = UNIVERSAL_BANS | RULES[rel_path]
    found: list[Violation] = []
    for line, imp in _imports_with_lines(path):
        for banned in bans:
            if _matches(imp, banned):
                found.append(Violation(rel_path, line, imp, banned))
    return sorted(found, key=lambda v: (v.rel_path, v.line, v.imported))


def main() -> int:
    total = 0
    for rel_path in sorted(RULES):
        for v in find_violations(rel_path):
            print(v)
            total += 1
    if total == 0:
        print(f"check-layers: OK ({len(RULES)} files clean)")
        return 0
    print(f"check-layers: FAIL ({total} violations across {len(RULES)} files)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
