"""Local alternative to .github/workflows/deploy-training-job.yml — builds the
training-job image via Cloud Build and updates the Cloud Run Job revision.
Invoked by `make deploy-training-job-local` (and indirectly by `make deploy-all`).

**delete-then-push policy** (per project memory): see scripts/deploy/api_local.py
for rationale. Same purge step before Cloud Build.
"""

from __future__ import annotations

import subprocess

from scripts._common import env, run


def main() -> int:
    project_id = env("PROJECT_ID")
    region = env("REGION")
    artifact_repo = env("ARTIFACT_REPO")
    job = env("TRAINING_JOB")

    sha = run(["git", "rev-parse", "--short=8", "HEAD"], capture=True).stdout.strip()
    image_path = f"{region}-docker.pkg.dev/{project_id}/{artifact_repo}/{job}"
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
        check=False,
    )

    print(f"==> Cloud Build {uri}", flush=True)
    run(
        [
            "gcloud",
            "builds",
            "submit",
            f"--project={project_id}",
            "--config=cloudbuild.training.yaml",
            f"--substitutions=_URI={uri}",
            ".",
        ]
    )

    print(f"==> Update {job}", flush=True)
    run(
        [
            "gcloud",
            "run",
            "jobs",
            "update",
            job,
            f"--project={project_id}",
            f"--region={region}",
            f"--image={uri}",
            f"--service-account=sa-job-train@{project_id}.iam.gserviceaccount.com",
            f"--set-env-vars=PROJECT_ID={project_id},GIT_SHA={sha}",
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
