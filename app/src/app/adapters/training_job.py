"""Concrete adapter implementing :class:`app.main.TrainingJobRunner` via Cloud Run Jobs."""

from __future__ import annotations


class CloudRunJobRunner:
    """Starts a Cloud Run Job execution via the Jobs API."""

    def __init__(self, *, project_id: str, region: str, job_name: str) -> None:
        self._full_job_name = f"projects/{project_id}/locations/{region}/jobs/{job_name}"

    def start(self) -> str:
        from google.cloud import run_v2

        client = run_v2.JobsClient()
        operation = client.run_job(name=self._full_job_name)
        return str(operation.metadata.name)
