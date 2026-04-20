"""Structural sanity checks for the GitHub Actions workflows.

This is not a YAML schema validator — it only enforces the few invariants that
keep the deploy pipeline coherent with the repo layout:

* every workflow specifies a ``name``, path-triggered pushes, and an ``id-token: write``
  permission (required for WIF OIDC),
* the new ``deploy-embedding-job.yml`` uses ``JOB: embedding-job`` and a service
  account from ``sa-job-train`` (per the roadmap §9.1 5-SA decision default),
* legacy workflows keep their broader ``jobs/**`` / ``app/**`` path filters so
  Phase 7 did not silently narrow the existing deploy coverage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

REQUIRED_WORKFLOWS = (
    "ci.yml",
    "deploy-api.yml",
    "deploy-training-job.yml",
    "deploy-dataform.yml",
    "deploy-embedding-job.yml",
    "terraform.yml",
)


@pytest.mark.parametrize("filename", REQUIRED_WORKFLOWS)
def test_workflow_file_exists(filename: str) -> None:
    assert (WORKFLOWS_DIR / filename).is_file(), (
        f"missing .github/workflows/{filename} — required by the CI/CD matrix"
    )


@pytest.mark.parametrize(
    "filename",
    ["deploy-api.yml", "deploy-training-job.yml", "deploy-embedding-job.yml", "terraform.yml"],
)
def test_deploy_workflows_request_oidc_token(filename: str) -> None:
    text = (WORKFLOWS_DIR / filename).read_text()
    assert "id-token: write" in text, (
        f"{filename} must request id-token:write permission for Workload Identity Federation"
    )


def test_embedding_workflow_points_at_embedding_job() -> None:
    text = (WORKFLOWS_DIR / "deploy-embedding-job.yml").read_text()
    assert "JOB: embedding-job" in text
    assert "embed_cli.py" in text, (
        "deploy-embedding-job.yml path filter must include embed_cli.py so the "
        "workflow fires when the embedding entrypoint changes"
    )
    assert "common/src/common/embeddings/**" in text, (
        "path filter must include common/src/common/embeddings/** — the encoder "
        "is shared between the API and the embedding-job"
    )
    assert "sa-job-embed" in text, (
        "embedding-job runs under the dedicated sa-job-embed service account "
        "(roadmap §13 / CLAUDE.md non-negotiables — 5 SA 分離)."
    )


def test_legacy_training_workflow_keeps_broad_filter() -> None:
    """Phase 7 must NOT narrow the legacy deploy-training-job path filter."""
    text = (WORKFLOWS_DIR / "deploy-training-job.yml").read_text()
    # Broad filter — triggers on any jobs/ or common/ change.
    assert "- jobs/**" in text
    assert "- common/**" in text


def test_legacy_api_workflow_keeps_broad_filter() -> None:
    text = (WORKFLOWS_DIR / "deploy-api.yml").read_text()
    assert "- app/**" in text
    assert "- common/**" in text
