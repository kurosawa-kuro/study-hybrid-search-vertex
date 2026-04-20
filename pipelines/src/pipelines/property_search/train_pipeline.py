"""KFP train pipeline for reranker training / registration."""

from __future__ import annotations

from kfp import dsl

from .components import evaluate_reranker, load_features, register_reranker, resolve_hyperparameters, train_reranker

PIPELINE_NAME = "property-search-train"


@dsl.pipeline(name=PIPELINE_NAME, description="Reranker training / evaluation / registration pipeline")
def property_search_train_pipeline(
    project_id: str = "mlops-dev-a",
    vertex_location: str = "asia-northeast1",
    feature_dataset_id: str = "feature_mart",
    feature_table: str = "property_features_daily",
    mlops_dataset_id: str = "mlops",
    ranking_log_table: str = "ranking_log",
    feedback_events_table: str = "feedback_events",
    window_days: int = 90,
    trainer_image: str = "asia-northeast1-docker.pkg.dev/mlops-dev-a/mlops/trainer:latest",
    experiment_name: str = "property-reranker-lgbm",
    baseline_hyperparameters_json: str = '{"num_leaves":31,"learning_rate":0.05,"feature_fraction":0.9,"bagging_fraction":0.8,"min_data_in_leaf":50,"lambdarank_truncation_level":20}',
    enable_tuning: bool = False,
    vizier_max_trials: int = 8,
    vizier_parallel_trials: int = 2,
    gate_metric_name: str = "ndcg_at_10",
    gate_threshold: float = 0.6,
    model_display_name: str = "property-reranker",
    endpoint_resource_name: str = "",
    serving_container_image_uri: str = "asia-northeast1-docker.pkg.dev/mlops-dev-a/mlops/reranker:latest",
    deploy_service_account: str = "",
    traffic_new_percentage: int = 10,
    deploy_machine_type: str = "n1-standard-2",
) -> None:
    features = load_features(
        project_id=project_id,
        feature_dataset_id=feature_dataset_id,
        feature_table=feature_table,
        mlops_dataset_id=mlops_dataset_id,
        ranking_log_table=ranking_log_table,
        feedback_events_table=feedback_events_table,
        window_days=window_days,
    )
    hyperparameters = resolve_hyperparameters(
        enabled=enable_tuning,
        baseline_hyperparameters_json=baseline_hyperparameters_json,
        project_id=project_id,
        vertex_location=vertex_location,
        study_display_name=f"{model_display_name}-vizier",
        max_trial_count=vizier_max_trials,
        parallel_trial_count=vizier_parallel_trials,
    )
    train_task = train_reranker(
        trainer_image=trainer_image,
        training_frame=features.outputs["training_frame"],
        hyperparameters_json=hyperparameters.output,
        experiment_name=experiment_name,
        window_days=window_days,
    )
    evaluate_task = evaluate_reranker(
        metrics_artifact=train_task.outputs["metrics"],
        metric_name=gate_metric_name,
        threshold=gate_threshold,
    )
    with dsl.Condition(evaluate_task.output == True):
        register_reranker(
            project_id=project_id,
            vertex_location=vertex_location,
            model_display_name=model_display_name,
            endpoint_resource_name=endpoint_resource_name,
            serving_container_image_uri=serving_container_image_uri,
            service_account=deploy_service_account,
            traffic_new_percentage=traffic_new_percentage,
            deploy_machine_type=deploy_machine_type,
            model_artifact=train_task.outputs["model"],
        )


def build_train_pipeline_spec() -> dict[str, object]:
    return {
        "name": PIPELINE_NAME,
        "description": "Reranker training / evaluation / registration pipeline",
        "parameters": {
            "project_id": "mlops-dev-a",
            "vertex_location": "asia-northeast1",
            "feature_dataset_id": "feature_mart",
            "feature_table": "property_features_daily",
            "mlops_dataset_id": "mlops",
            "ranking_log_table": "ranking_log",
            "feedback_events_table": "feedback_events",
            "window_days": 90,
            "trainer_image": "asia-northeast1-docker.pkg.dev/mlops-dev-a/mlops/trainer:latest",
            "experiment_name": "property-reranker-lgbm",
            "enable_tuning": False,
            "gate_metric_name": "ndcg_at_10",
            "gate_threshold": 0.6,
            "model_display_name": "property-reranker",
        },
        "steps": ["load_features", "resolve_hyperparameters", "train_reranker", "evaluate", "register_reranker"],
    }


def get_train_pipeline() -> dsl.Pipeline:
    return property_search_train_pipeline
