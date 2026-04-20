"""Concrete candidate retrieval + log-write adapters.

Three adapters live here:

* :class:`BigQueryCandidateRetriever` — hybrid retrieval:
    lexical (Meilisearch) + semantic (BigQuery VECTOR_SEARCH) + RRF fusion,
    then feature enrichment via BigQuery joins.
* :class:`PubSubRankingLogPublisher` / :class:`PubSubFeedbackRecorder` — write
  events to the Pub/Sub topics declared by the runtime module.
* :class:`NoopRankingLogPublisher` / :class:`NoopFeedbackRecorder` — null
  implementations used when the matching topic is unconfigured (local dev).

The Pub/Sub publishers serialize to JSON the same way
:class:`app.adapters.publisher.PubSubPublisher` does, so the BQ Subscription
consumes identical payload shapes. Publisher client construction is lazy so
unit tests can instantiate the noop variants without GCP creds.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from google.cloud import bigquery

from ..ports.candidate_retriever import Candidate
from ..ports.lexical_search import LexicalSearchPort
from ..services.ranking import RRF_K, rrf_fuse


class BigQueryCandidateRetriever:
    """Hybrid candidate generation via lexical + semantic retrieval.

    Args:
        project_id: GCP project.
        lexical: lexical search adapter (Meilisearch).
        embeddings_table: fully-qualified ``project.dataset.table`` for
            ``feature_mart.property_embeddings`` (768d vectors).
        features_table: ``property_features_daily`` fully-qualified name
            (for ctr / fav_rate / inquiry_rate enrichment).
        properties_table: ``feature_mart.properties_cleaned`` for rent /
            walk_min / age_years / area_m2 / pet_ok / layout filter columns.
        client: optional pre-built BQ client (tests).
    """

    def __init__(
        self,
        *,
        project_id: str,
        lexical: LexicalSearchPort,
        embeddings_table: str,
        features_table: str,
        properties_table: str,
        client: bigquery.Client | None = None,
    ) -> None:
        self._lexical = lexical
        self._embeddings_table = embeddings_table
        self._features_table = features_table
        self._properties_table = properties_table
        self._client = client or bigquery.Client(project=project_id)

    def retrieve(
        self,
        *,
        query_text: str,
        query_vector: list[float],
        filters: dict[str, Any],
        top_k: int,
    ) -> list[Candidate]:
        lexical_results = self._lexical.search(query=query_text, filters=filters, top_k=200)
        semantic_results = self._semantic_search(query_vector=query_vector, filters=filters, top_k=200)

        semantic_rank_pairs = [(pid, rank) for pid, rank, _ in semantic_results]
        fused_ids = rrf_fuse(
            lexical_results=lexical_results,
            semantic_results=semantic_rank_pairs,
            top_n=max(top_k, 100),
            k=RRF_K,
        )
        if not fused_ids:
            return []

        lexical_rank_map = {pid: rank for pid, rank in lexical_results}
        semantic_rank_map = {pid: rank for pid, rank, _ in semantic_results}
        me5_score_map = {pid: score for pid, _, score in semantic_results}
        rrf_rank_map = {pid: rank for rank, pid in enumerate(fused_ids, start=1)}

        return self._enrich_from_bq(
            property_ids=fused_ids,
            lexical_rank_map=lexical_rank_map,
            semantic_rank_map=semantic_rank_map,
            me5_score_map=me5_score_map,
            rrf_rank_map=rrf_rank_map,
        )

    def _semantic_search(
        self,
        *,
        query_vector: list[float],
        filters: dict[str, Any],
        top_k: int,
    ) -> list[tuple[str, int, float]]:
        query = f"""
            WITH base AS (
              SELECT
                v.base.property_id AS property_id,
                v.distance AS cosine_distance
              FROM VECTOR_SEARCH(
                TABLE `{self._embeddings_table}`,
                'embedding',
                (SELECT @query_vec AS embedding),
                top_k => @pool_size,
                distance_type => 'COSINE'
              ) v
            ),
            filtered AS (
              SELECT
                b.property_id,
                b.cosine_distance
              FROM base b
              LEFT JOIN `{self._properties_table}` p USING (property_id)
              WHERE
                (@max_rent IS NULL OR p.rent <= @max_rent)
                AND (@layout IS NULL OR p.layout = @layout)
                AND (@max_walk_min IS NULL OR p.walk_min <= @max_walk_min)
                AND (@pet_ok IS NULL OR p.pet_ok = @pet_ok)
                AND (@max_age IS NULL OR p.age_years <= @max_age)
            )
            SELECT
              property_id,
              cosine_distance,
              ROW_NUMBER() OVER (ORDER BY cosine_distance ASC) AS semantic_rank
            FROM filtered
            ORDER BY cosine_distance ASC
            LIMIT @pool_size
        """
        params = [
            bigquery.ArrayQueryParameter("query_vec", "FLOAT64", query_vector),
            bigquery.ScalarQueryParameter("pool_size", "INT64", top_k),
            bigquery.ScalarQueryParameter("max_rent", "INT64", filters.get("max_rent")),
            bigquery.ScalarQueryParameter("layout", "STRING", filters.get("layout")),
            bigquery.ScalarQueryParameter("max_walk_min", "INT64", filters.get("max_walk_min")),
            bigquery.ScalarQueryParameter("pet_ok", "BOOL", filters.get("pet_ok")),
            bigquery.ScalarQueryParameter("max_age", "INT64", filters.get("max_age")),
        ]
        rows = self._client.query(
            query, job_config=bigquery.QueryJobConfig(query_parameters=params)
        ).result()
        out: list[tuple[str, int, float]] = []
        for row in rows:
            property_id = str(row["property_id"])
            semantic_rank = int(row["semantic_rank"])
            me5_score = 1.0 - float(row["cosine_distance"] or 1.0)
            out.append((property_id, semantic_rank, me5_score))
        return out

    def _enrich_from_bq(
        self,
        *,
        property_ids: list[str],
        lexical_rank_map: dict[str, int],
        semantic_rank_map: dict[str, int],
        me5_score_map: dict[str, float],
        rrf_rank_map: dict[str, int],
    ) -> list[Candidate]:
        query = f"""
            WITH selected AS (
              SELECT property_id, offset + 1 AS rrf_rank
              FROM UNNEST(@property_ids) AS property_id WITH OFFSET
            )
            SELECT
              s.property_id,
              s.rrf_rank,
              p.rent AS p_rent,
              p.walk_min AS p_walk_min,
              p.age_years AS p_age_years,
              p.area_m2 AS p_area_m2,
              f.ctr AS f_ctr,
              f.fav_rate AS f_fav_rate,
              f.inquiry_rate AS f_inquiry_rate
            FROM selected s
            LEFT JOIN `{self._properties_table}` p USING (property_id)
            LEFT JOIN (
              SELECT *
              FROM `{self._features_table}`
              WHERE event_date = (SELECT MAX(event_date) FROM `{self._features_table}`)
            ) f USING (property_id)
            ORDER BY s.rrf_rank ASC
        """
        params = [bigquery.ArrayQueryParameter("property_ids", "STRING", property_ids)]
        rows = self._client.query(
            query,
            job_config=bigquery.QueryJobConfig(query_parameters=params),
        ).result()

        candidates: list[Candidate] = []
        for row in rows:
            property_id = str(row["property_id"])
            lexical_rank = lexical_rank_map.get(property_id, 10_000)
            semantic_rank = semantic_rank_map.get(property_id, 10_000)
            me5_score = me5_score_map.get(property_id, 0.0)
            candidates.append(
                Candidate(
                    property_id=property_id,
                    lexical_rank=lexical_rank,
                    semantic_rank=semantic_rank,
                    me5_score=me5_score,
                    property_features={
                        "rent": row["p_rent"],
                        "walk_min": row["p_walk_min"],
                        "age_years": row["p_age_years"],
                        "area_m2": row["p_area_m2"],
                        "ctr": row["f_ctr"],
                        "fav_rate": row["f_fav_rate"],
                        "inquiry_rate": row["f_inquiry_rate"],
                        "rrf_rank": rrf_rank_map.get(property_id),
                    },
                )
            )
        candidates.sort(key=lambda c: rrf_rank_map.get(c.property_id, 10_000))
        return candidates


class PubSubRankingLogPublisher:
    """Writes ranking-log rows to the ``ranking-log`` Pub/Sub topic."""

    def __init__(self, *, project_id: str, topic: str) -> None:
        from google.cloud import pubsub_v1  # type: ignore[attr-defined]

        self._client = pubsub_v1.PublisherClient()
        self._topic_path = self._client.topic_path(project_id, topic)

    def publish_candidates(
        self,
        *,
        request_id: str,
        candidates: list[Candidate],
        final_ranks: list[int],
        scores: list[float | None],
        model_path: str | None,
    ) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        for cand, final_rank, score in zip(candidates, final_ranks, scores, strict=True):
            payload = {
                "request_id": request_id,
                "ts": ts,
                "property_id": cand.property_id,
                "schema_version": 2,
                "lexical_rank": cand.lexical_rank,
                "semantic_rank": cand.semantic_rank,
                "rrf_rank": cand.property_features.get("rrf_rank"),
                "final_rank": final_rank,
                "score": score,
                "me5_score": cand.me5_score,
                "features": {
                    "rent": _as_float(cand.property_features.get("rent")),
                    "walk_min": _as_float(cand.property_features.get("walk_min")),
                    "age_years": _as_float(cand.property_features.get("age_years")),
                    "area_m2": _as_float(cand.property_features.get("area_m2")),
                    "ctr": _as_float(cand.property_features.get("ctr")),
                    "fav_rate": _as_float(cand.property_features.get("fav_rate")),
                    "inquiry_rate": _as_float(cand.property_features.get("inquiry_rate")),
                    "me5_score": cand.me5_score,
                    "lexical_rank": float(cand.lexical_rank),
                    "semantic_rank": float(cand.semantic_rank),
                },
                "model_path": model_path,
            }
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._client.publish(self._topic_path, data).result(timeout=5)


class PubSubFeedbackRecorder:
    """Writes feedback events to the ``search-feedback`` Pub/Sub topic."""

    def __init__(self, *, project_id: str, topic: str) -> None:
        from google.cloud import pubsub_v1  # type: ignore[attr-defined]

        self._client = pubsub_v1.PublisherClient()
        self._topic_path = self._client.topic_path(project_id, topic)

    def record(self, *, request_id: str, property_id: str, action: str) -> None:
        payload = {
            "request_id": request_id,
            "property_id": property_id,
            "action": action,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._client.publish(self._topic_path, data).result(timeout=5)


class NoopRankingLogPublisher:
    def publish_candidates(
        self,
        *,
        request_id: str,
        candidates: list[Candidate],
        final_ranks: list[int],
        scores: list[float | None],
        model_path: str | None,
    ) -> None:
        return None


class NoopFeedbackRecorder:
    def record(self, *, request_id: str, property_id: str, action: str) -> None:
        return None


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]
