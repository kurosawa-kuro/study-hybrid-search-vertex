"""BQ-backed :class:`RankerTrainingRepository` adapter.

Assembles the LambdaRank training set by joining
``mlops.ranking_log`` (features + lexical_rank + me5_score) to
``mlops.feedback_events`` (labels). Rows are ordered by ``request_id``
followed by ``lexical_rank`` so LightGBM group sizes line up directly.

``save_run`` writes ranker metrics (``ndcg_at_10`` / ``map`` /
``recall_at_20`` / ``best_iteration``) + LambdaRank hyperparameters into
``mlops.training_runs``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from common.logging import get_logger
from google.cloud import bigquery

logger = get_logger(__name__)

# Column order in the SELECT must match FEATURE_COLS_RANKER + [label, request_id, property_id]
# so the DataFrame is ready to split + feed the trainer without a reorder.
_TRAINING_SELECT = """
  SELECT
    r.request_id,
    r.property_id,
    r.features.rent       AS rent,
    r.features.walk_min   AS walk_min,
    r.features.age_years  AS age_years,
    r.features.area_m2    AS area_m2,
    r.features.ctr        AS ctr,
    r.features.fav_rate   AS fav_rate,
    r.features.inquiry_rate AS inquiry_rate,
    r.features.me5_score    AS me5_score,
    r.features.lexical_rank AS lexical_rank,
    COALESCE(l.label, 0)  AS label
  FROM `{ranking_log}` r
  LEFT JOIN (
    SELECT
      request_id,
      property_id,
      CASE
        WHEN COUNTIF(action = 'inquiry')  > 0 THEN 3
        WHEN COUNTIF(action = 'favorite') > 0 THEN 2
        WHEN COUNTIF(action = 'click')    > 0 THEN 1
        ELSE 0
      END AS label
    FROM `{feedback_events}`
    WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @window_days DAY)
    GROUP BY request_id, property_id
  ) l
  USING (request_id, property_id)
  WHERE r.ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @window_days DAY)
    AND r.features.rent IS NOT NULL
  ORDER BY r.request_id, r.lexical_rank
"""


class BigQueryRankerRepository:
    """BigQuery-backed ranker training repository."""

    def __init__(
        self,
        *,
        project_id: str,
        ranking_log_table: str,
        feedback_events_table: str,
        training_runs_table: str,
        client: bigquery.Client | None = None,
    ) -> None:
        self._project_id = project_id
        self._ranking_log_table = ranking_log_table
        self._feedback_events_table = feedback_events_table
        self._training_runs_table = training_runs_table
        self._client = client or bigquery.Client(project=project_id)

    def fetch_training_rows(self, *, window_days: int) -> pd.DataFrame:
        query = _TRAINING_SELECT.format(
            ranking_log=self._ranking_log_table,
            feedback_events=self._feedback_events_table,
        )
        logger.info(
            "Fetching ranker training rows (window=%dd) from %s",
            window_days,
            self._ranking_log_table,
        )
        job = self._client.query(
            query,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("window_days", "INT64", window_days)
                ]
            ),
        )
        df = job.result().to_dataframe(create_bqstorage_client=True)
        logger.info("Fetched %d rows spanning %d request_ids", len(df), df["request_id"].nunique())
        return df

    def save_run(
        self,
        *,
        run_id: str,
        started_at: datetime,
        finished_at: datetime,
        model_path: str,
        metrics: dict[str, float],
        hyperparams: dict[str, object],
        git_sha: str | None = None,
        dataset_version: str | None = None,
    ) -> None:
        row = {
            "run_id": run_id,
            "started_at": started_at.astimezone(timezone.utc).isoformat(),
            "finished_at": finished_at.astimezone(timezone.utc).isoformat(),
            "model_path": model_path,
            "git_sha": git_sha,
            "dataset_version": dataset_version,
            "metrics": {
                k: metrics.get(k) for k in ("best_iteration", "ndcg_at_10", "map", "recall_at_20")
            },
            "hyperparams": {
                k: hyperparams.get(k)
                for k in (
                    "num_leaves",
                    "learning_rate",
                    "feature_fraction",
                    "bagging_fraction",
                    "num_iterations",
                    "early_stopping_rounds",
                    "min_data_in_leaf",
                    "lambdarank_truncation_level",
                )
            },
        }
        errors = self._client.insert_rows_json(self._training_runs_table, [row])
        if errors:
            raise RuntimeError(f"BigQuery insert_rows_json failed: {errors}")
        logger.info("Recorded ranker run %s in %s", run_id, self._training_runs_table)

    def latest_model_path(self) -> str | None:
        query = f"""
            SELECT model_path
            FROM `{self._training_runs_table}`
            WHERE finished_at IS NOT NULL
            ORDER BY finished_at DESC
            LIMIT 1
        """
        rows = list(self._client.query(query).result())
        return rows[0]["model_path"] if rows else None
