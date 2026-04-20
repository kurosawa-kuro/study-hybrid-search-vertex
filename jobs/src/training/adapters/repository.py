"""Factory that assembles the BigQuery-backed ranker repository from settings."""

from __future__ import annotations

from ..config import TrainSettings
from ..ports.ranker_repository import RankerTrainingRepository
from .bigquery_ranker_repository import BigQueryRankerRepository


def create_rank_repository(settings: TrainSettings) -> RankerTrainingRepository:
    """Build the BQ-backed :class:`RankerTrainingRepository` from settings."""
    project = settings.project_id
    return BigQueryRankerRepository(
        project_id=project,
        ranking_log_table=f"{project}.{settings.bq_dataset_mlops}.ranking_log",
        feedback_events_table=f"{project}.{settings.bq_dataset_mlops}.feedback_events",
        training_runs_table=(
            f"{project}.{settings.bq_dataset_mlops}.{settings.bq_table_training_runs}"
        ),
    )
