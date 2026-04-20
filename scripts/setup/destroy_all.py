"""End-to-end teardown of every Terraform-managed resource. **No interactive
prompt** — this is a learning / PDCA dev project (`mlops-dev-a`) where fast
iteration matters. Pair with `deploy-all` for a build-test-destroy loop.

Steps:

1. `bq rm -f feature_mart.properties_cleaned` — drop the out-of-Terraform-state
   table that `make seed-test` (`scripts/setup/seed_minimal.py`) creates. It
   blocks `feature_mart` dataset destroy with `resourceInUse` otherwise.
   `check=False` makes this benign when the table is absent.
2. `terraform apply -auto-approve -var=enable_deletion_protection=false
   -target=<each-table>` — flip every BQ table's `deletion_protection` to
   false in Terraform state. `-target` is **load-bearing**: a bare apply
   would also try to (re)create any resource that drifted out of state
   from a previous half-destroy (e.g. SAs whose IAM bindings linger as
   `deleted:serviceaccount:...?uid=...` in dataset IAM policies). Limiting
   apply to the 7 BQ tables guarantees this state-flip is a pure attribute
   change, no resource (re)creation.
3. `terraform destroy -auto-approve` — actually tears infra down. The
   var is passed again so Terraform's destroy-time guard sees
   deletion_protection=false.

What this does NOT touch (preserved for the next `make deploy-all`):

- The tfstate bucket (`<PROJECT_ID>-tfstate`).
- API enablements (cost nothing when no resource exists).
- Local artifacts (`infra/tfplan`, `definitions/workflow_settings.yaml`,
  `.venv`) — `make clean` covers these.
"""

from __future__ import annotations

from pathlib import Path

from scripts._common import env, run
from scripts.setup.seed_minimal_clean import main as seed_clean_main

INFRA = Path(__file__).resolve().parent.parent.parent / "infra"

# Resource addresses for the 7 BQ tables that carry deletion_protection.
# Kept in sync with infra/modules/data/main.tf — if a new protected table
# is added, append it here.
PROTECTED_TABLE_TARGETS = [
    "module.data.google_bigquery_table.training_runs",
    "module.data.google_bigquery_table.search_logs",
    "module.data.google_bigquery_table.ranking_log",
    "module.data.google_bigquery_table.feedback_events",
    "module.data.google_bigquery_table.validation_results",
    "module.data.google_bigquery_table.property_features_daily",
    "module.data.google_bigquery_table.property_embeddings",
]


def main() -> int:
    project_id = env("PROJECT_ID")
    github_repo = env("GITHUB_REPO")
    oncall_email = env("ONCALL_EMAIL")

    common_vars = [
        "-var=enable_deletion_protection=false",
        f"-var=github_repo={github_repo}",
        f"-var=oncall_email={oncall_email}",
    ]

    print(f"==> destroy-all on project {project_id!r}")

    print("==> [1/3] seed-test-clean (drop out-of-TF tables that block dataset destroy)")
    seed_clean_main()

    print(
        "==> [2/3] terraform apply -target=<7 BQ tables> "
        "-var=enable_deletion_protection=false (state-flip only, no recreate)"
    )
    targets = [arg for tgt in PROTECTED_TABLE_TARGETS for arg in ("-target", tgt)]
    run(
        [
            "terraform",
            f"-chdir={INFRA}",
            "apply",
            "-auto-approve",
            *common_vars,
            *targets,
        ]
    )

    print("==> [3/3] terraform destroy -auto-approve")
    run(
        [
            "terraform",
            f"-chdir={INFRA}",
            "destroy",
            "-auto-approve",
            *common_vars,
        ]
    )

    print()
    print("==> destroy-all complete.")
    print("    tfstate bucket preserved. Re-provision with: make deploy-all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
