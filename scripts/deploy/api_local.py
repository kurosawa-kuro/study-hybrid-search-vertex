"""Local alternative to .github/workflows/deploy-api.yml — builds search-api
via Cloud Build and rolls out a Cloud Run revision. Invoked by
`make deploy-api-local` (and indirectly by `make deploy-all`).

**delete-then-push policy** (per project memory): every invocation purges
the entire `search-api` image (all tags + digests) from Artifact Registry
before Cloud Build pushes the new tag. Stale layer / tag mismatch can
otherwise cause Cloud Run to silently keep an old revision when image
push reports success — for a PDCA loop this is unacceptable.
"""

from __future__ import annotations

import subprocess

from scripts._common import env, run

ENV_VARS = ",".join(
    [
        "PROJECT_ID={project_id}",
        "GCS_MODELS_BUCKET={project_id}-models",
        "RANKING_LOG_TOPIC=ranking-log",
        "FEEDBACK_TOPIC=search-feedback",
        "RETRAIN_TOPIC=retrain-trigger",
        "LOG_AS_JSON=1",
        "GCP_LOGGING_ENABLED=1",
    ]
)


def main() -> int:
    project_id = env("PROJECT_ID")
    region = env("REGION")
    artifact_repo = env("ARTIFACT_REPO")
    service = env("API_SERVICE")

    sha = run(["git", "rev-parse", "--short=8", "HEAD"], capture=True).stdout.strip()
    image_path = f"{region}-docker.pkg.dev/{project_id}/{artifact_repo}/{service}"
    uri = f"{image_path}:{sha}"

    print(f"==> Purge existing image {image_path} (all tags)", flush=True)
    subprocess.run(
        [
            "gcloud",
            "artifacts",
            "docker",
            "images",
            "delete",
            image_path,
            "--delete-tags",
            "--quiet",
            f"--project={project_id}",
        ],
        check=False,  # absent on first-ever push, treat as success
    )

    print(f"==> Cloud Build {uri}", flush=True)
    run(
        [
            "gcloud",
            "builds",
            "submit",
            f"--project={project_id}",
            "--config=cloudbuild.api.yaml",
            f"--substitutions=_URI={uri}",
            ".",
        ]
    )

    print(f"==> Deploy {service}", flush=True)
    run(
        [
            "gcloud",
            "run",
            "deploy",
            service,
            f"--project={project_id}",
            f"--region={region}",
            f"--image={uri}",
            f"--service-account=sa-api@{project_id}.iam.gserviceaccount.com",
            "--cpu=2",
            "--memory=4Gi",
            "--concurrency=80",
            "--min-instances=1",
            "--max-instances=10",
            "--cpu-boost",
            "--execution-environment=gen2",
            "--no-allow-unauthenticated",
            f"--set-env-vars={ENV_VARS.format(project_id=project_id)}",
            f"--labels=git-sha={sha}",
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
