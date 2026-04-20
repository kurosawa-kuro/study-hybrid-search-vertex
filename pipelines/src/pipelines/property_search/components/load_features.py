"""KFP component: materialize the training-frame query contract."""

from __future__ import annotations

import json
from pathlib import Path

from kfp import dsl


@dsl.component(base_image="python:3.12")
def load_features(
    project_id: str,
    feature_dataset_id: str,
    feature_table: str,
    mlops_dataset_id: str,
    ranking_log_table: str,
    feedback_events_table: str,
    window_days: int,
    training_frame: dsl.Output[dsl.Dataset],
) -> None:
    query = f"""
    SELECT
      r.request_id,
      r.property_id,
      r.features.rent,
      r.features.walk_min,
      r.features.age_years,
      r.features.area_m2,
      r.features.ctr,
      r.features.fav_rate,
      r.features.inquiry_rate,
      r.features.me5_score,
      r.features.lexical_rank,
      COALESCE(l.label, 0) AS label
    FROM `{project_id}.{mlops_dataset_id}.{ranking_log_table}` r
    LEFT JOIN `{project_id}.{mlops_dataset_id}.{feedback_events_table}` l
      USING (request_id, property_id)
    JOIN `{project_id}.{feature_dataset_id}.{feature_table}` f
      USING (property_id)
    WHERE r.ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window_days} DAY)
    ORDER BY r.request_id, r.features.lexical_rank
    """.strip()

    payload = {
        "component": "load_features",
        "project_id": project_id,
        "feature_dataset_id": feature_dataset_id,
        "feature_table": feature_table,
        "mlops_dataset_id": mlops_dataset_id,
        "ranking_log_table": ranking_log_table,
        "feedback_events_table": feedback_events_table,
        "window_days": window_days,
        "split_strategy": "FARM_FINGERPRINT(request_id) % 10 < 8",
        "query": query,
    }
    training_frame.metadata.update(payload)
    Path(training_frame.path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
