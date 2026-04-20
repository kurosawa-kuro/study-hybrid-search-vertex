"""Port for ranker training data + run metadata persistence.

Concrete adapter: :class:`training.adapters.bigquery_ranker_repository.BigQueryRankerRepository`.
Kept free of GCP SDK imports so unit tests + rank_cli orchestration depend on
the Protocol rather than the BigQuery client surface.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

import pandas as pd


class RankerTrainingRepository(Protocol):
    def fetch_training_rows(self, *, window_days: int) -> pd.DataFrame:
        """Return a DataFrame sorted contiguously by ``request_id``.

        Columns MUST be ``FEATURE_COLS_RANKER + [RANKER_LABEL_COL, RANKER_GROUP_COL,
        "property_id"]`` — ordering of the group column determines the LightGBM
        group sizes, so the adapter is responsible for ``ORDER BY request_id``.
        """
        ...

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
    ) -> None: ...

    def latest_model_path(self) -> str | None: ...
