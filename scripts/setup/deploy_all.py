"""End-to-end provisioning + rollout in one shot. Calls (in order):

1. `tf_bootstrap` — enable APIs + create tfstate bucket (idempotent)
2. `tf_init` — terraform init with bucket preflight
3. `_recover_wif_state` — undelete + import WIF pool/provider if a previous
   `make destroy-all` left them soft-deleted (GCP keeps WIF resources for
   30 days after delete; recreating with the same ID otherwise hits HTTP
   409 "already exists")
4. `sync_dataform` — regenerate definitions/workflow_settings.yaml
5. `tf_plan` — terraform plan -out=tfplan (using setting.yaml defaults)
6. `terraform apply tfplan -auto-approve` — apply infra
7. `deploy/api_local` — Cloud Build + gcloud run deploy search-api
8. `deploy/training_job_local` — Cloud Build + gcloud run jobs update training-job

Idempotent — re-running on an already-provisioned project applies a zero-diff
plan and rolls a fresh image revision (search-api / training-job get a new
git-sha tag). Costs accrue from the moment infra is created (Cloud Run
min-instances=1, BQ storage, etc.) — see CLAUDE.md non-negotiables.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts._common import env, run
from scripts.config.sync_dataform import main as sync_dataform_main
from scripts.deploy.api_local import main as deploy_api_main
from scripts.deploy.training_job_local import main as deploy_training_main
from scripts.setup.tf_bootstrap import main as tf_bootstrap_main
from scripts.setup.tf_init import main as tf_init_main
from scripts.setup.tf_plan import main as tf_plan_main

INFRA = Path(__file__).resolve().parent.parent.parent / "infra"


def _step(n: int, total: int, label: str) -> None:
    print()
    print("================================================================")
    print(f" deploy-all  step {n}/{total}: {label}")
    print("================================================================")


def _gcloud_capture(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        ["gcloud", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout.strip()


def _tf_var_args() -> list[str]:
    return [
        f"-var=github_repo={env('GITHUB_REPO')}",
        f"-var=oncall_email={env('ONCALL_EMAIL')}",
    ]


def _recover_wif_state(project_id: str) -> None:
    """Undelete + import WIF pool/provider if soft-deleted from a prior destroy.

    Detection:
    - Pool: `gcloud iam workload-identity-pools describe github` returns
      `state: DELETED` when soft-deleted.
    - Provider: `gcloud ... providers describe github-oidc` succeeds and
      returns a non-empty `expireTime` only for soft-deleted ones.

    Recovery for each: undelete → `terraform state rm` (in case stale entry)
    → `terraform import` so the next `terraform plan` sees them as
    in-state instead of "to be created" (which would 409).
    """
    pool_args = [
        "iam",
        "workload-identity-pools",
        "describe",
        "github",
        "--location=global",
        f"--project={project_id}",
        "--format=value(state)",
    ]
    rc, pool_state = _gcloud_capture(pool_args)
    if rc == 0 and pool_state == "DELETED":
        print("==> Recovery: undelete soft-deleted WIF pool 'github'")
        run(
            [
                "gcloud",
                "iam",
                "workload-identity-pools",
                "undelete",
                "github",
                "--location=global",
                f"--project={project_id}",
                "--quiet",
            ]
        )
        subprocess.run(
            [
                "terraform",
                f"-chdir={INFRA}",
                "state",
                "rm",
                "module.iam.google_iam_workload_identity_pool.github",
            ],
            check=False,
        )
        run(
            [
                "terraform",
                f"-chdir={INFRA}",
                "import",
                *_tf_var_args(),
                "module.iam.google_iam_workload_identity_pool.github",
                f"projects/{project_id}/locations/global/workloadIdentityPools/github",
            ]
        )

    prov_args = [
        "iam",
        "workload-identity-pools",
        "providers",
        "describe",
        "github-oidc",
        "--workload-identity-pool=github",
        "--location=global",
        f"--project={project_id}",
        "--format=value(expireTime)",
    ]
    rc, expire_time = _gcloud_capture(prov_args)
    if rc == 0 and expire_time:
        print("==> Recovery: undelete soft-deleted WIF provider 'github-oidc'")
        run(
            [
                "gcloud",
                "iam",
                "workload-identity-pools",
                "providers",
                "undelete",
                "github-oidc",
                "--workload-identity-pool=github",
                "--location=global",
                f"--project={project_id}",
                "--quiet",
            ]
        )
        subprocess.run(
            [
                "terraform",
                f"-chdir={INFRA}",
                "state",
                "rm",
                "module.iam.google_iam_workload_identity_pool_provider.github",
            ],
            check=False,
        )
        run(
            [
                "terraform",
                f"-chdir={INFRA}",
                "import",
                *_tf_var_args(),
                "module.iam.google_iam_workload_identity_pool_provider.github",
                f"projects/{project_id}/locations/global/workloadIdentityPools/github/providers/github-oidc",
            ]
        )


def main() -> int:
    total = 8
    project_id = env("PROJECT_ID")

    _step(1, total, "tf-bootstrap (enable APIs + tfstate bucket, idempotent)")
    if (rc := tf_bootstrap_main()) != 0:
        return rc

    _step(2, total, "tf-init (preflight + terraform init)")
    if (rc := tf_init_main()) != 0:
        return rc

    _step(3, total, "recover WIF pool/provider if soft-deleted (PDCA loop safety)")
    _recover_wif_state(project_id)

    _step(4, total, "sync-dataform-config (regenerate workflow_settings.yaml)")
    if (rc := sync_dataform_main()) != 0:
        return rc

    _step(5, total, "tf-plan (saves infra/tfplan)")
    if (rc := tf_plan_main()) != 0:
        return rc

    _step(6, total, "terraform apply tfplan -auto-approve")
    run(["terraform", f"-chdir={INFRA}", "apply", "-auto-approve", "tfplan"])

    _step(7, total, "deploy-api-local (Cloud Build + run deploy search-api)")
    if (rc := deploy_api_main()) != 0:
        return rc

    _step(8, total, "deploy-training-job-local (Cloud Build + run jobs update)")
    if (rc := deploy_training_main()) != 0:
        return rc

    print()
    print("==> deploy-all complete.")
    print("    Verify with: make ops-livez && make ops-api-url")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
