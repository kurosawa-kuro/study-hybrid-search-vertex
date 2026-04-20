"""KFP container component for LambdaRank training."""

from __future__ import annotations

from kfp import dsl


@dsl.container_component
def train_reranker(
    trainer_image: str,
    training_frame: dsl.Input[dsl.Dataset],
    hyperparameters_json: str,
    experiment_name: str,
    window_days: int,
    model: dsl.Output[dsl.Model],
    metrics: dsl.Output[dsl.Metrics],
) -> dsl.ContainerSpec:
    return dsl.ContainerSpec(
        image=trainer_image,
        command=["python", "-m", "training.entrypoints.rank_cli"],
        args=[
            "--mode",
            "kfp",
            "--train-dataset-uri",
            training_frame.uri,
            "--hyperparams-json",
            hyperparameters_json,
            "--experiment-name",
            experiment_name,
            "--window-days",
            window_days,
            "--model-output-path",
            model.path,
            "--metrics-output-path",
            metrics.path,
        ],
    )
