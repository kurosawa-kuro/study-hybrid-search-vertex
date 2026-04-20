"""KFP component: resolve hyperparameters, optionally via Vertex Vizier."""

import json

from kfp import dsl


@dsl.component(
    base_image="python:3.12",
    packages_to_install=["google-cloud-aiplatform>=1.71,<2"],
)
def resolve_hyperparameters(
    enabled: bool,
    baseline_hyperparameters_json: str,
    project_id: str,
    vertex_location: str,
    study_display_name: str,
    max_trial_count: int,
    parallel_trial_count: int,
) -> str:
    if not enabled:
        return baseline_hyperparameters_json

    from google.cloud import aiplatform

    baseline = json.loads(baseline_hyperparameters_json)
    aiplatform.init(project=project_id, location=vertex_location)

    # Placeholder for the real Vizier job wiring. Until the custom job spec lands,
    # keep the pipeline contract stable and return the baseline parameters.
    _ = {
        "study_display_name": study_display_name,
        "max_trial_count": max_trial_count,
        "parallel_trial_count": parallel_trial_count,
    }
    return json.dumps(baseline, ensure_ascii=False)
