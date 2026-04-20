"""Tests for concrete adapters in app.adapters (ranker-only after Phase 10b)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.adapters import (
    CloudRunJobRunner,
    PubSubPublisher,
    VertexEndpointEncoder,
    VertexEndpointReranker,
    create_retrain_queries,
)


def test_cloud_run_job_runner_starts_configured_job() -> None:
    fake_client = MagicMock()
    fake_client.run_job.return_value.metadata.name = (
        "projects/p/locations/asia-northeast1/jobs/training-job/executions/abc"
    )

    with patch("google.cloud.run_v2.JobsClient", return_value=fake_client):
        runner = CloudRunJobRunner(
            project_id="p", region="asia-northeast1", job_name="training-job"
        )
        execution = runner.start()

    fake_client.run_job.assert_called_once_with(
        name="projects/p/locations/asia-northeast1/jobs/training-job"
    )
    assert execution == "projects/p/locations/asia-northeast1/jobs/training-job/executions/abc"


def test_create_retrain_queries_wires_bigquery_client() -> None:
    from app.adapters import BigQueryRetrainQueries

    fake_bq_client = MagicMock()
    fake_bq_client.query.return_value.result.return_value = iter([{"ts": None}])
    with patch("google.cloud.bigquery.Client", return_value=fake_bq_client) as client_cls:
        queries = create_retrain_queries(
            project_id="p",
            training_runs_table="p.m.training_runs",
        )
        queries.last_run_finished_at()

    client_cls.assert_called_once_with(project="p")
    assert isinstance(queries, BigQueryRetrainQueries)
    fake_bq_client.query.assert_called_once()
    assert "p.m.training_runs" in fake_bq_client.query.call_args.args[0]


def test_pubsub_publisher_publishes_json_bytes() -> None:
    fake_client = MagicMock()
    fake_client.topic_path.return_value = "projects/p/topics/retrain-trigger"
    fake_future = MagicMock()
    fake_client.publish.return_value = fake_future

    with patch("google.cloud.pubsub_v1.PublisherClient", return_value=fake_client):
        publisher = PubSubPublisher(project_id="p", topic="retrain-trigger")
        publisher.publish({"reasons": ["ndcg_drop=0.05>=0.03"], "日本語": "ok"})

    fake_client.topic_path.assert_called_once_with("p", "retrain-trigger")
    fake_client.publish.assert_called_once()
    call_args = fake_client.publish.call_args.args
    assert call_args[0] == "projects/p/topics/retrain-trigger"
    decoded = json.loads(call_args[1].decode("utf-8"))
    assert decoded == {"reasons": ["ndcg_drop=0.05>=0.03"], "日本語": "ok"}
    fake_future.result.assert_called_once()


def test_vertex_endpoint_encoder_parses_embedding_dict_response() -> None:
    fake_endpoint = MagicMock()
    fake_endpoint.predict.return_value.predictions = [{"embedding": [0.1, 0.2, 0.3]}]

    adapter = VertexEndpointEncoder(
        project_id="p",
        location="asia-northeast1",
        endpoint_id="123",
        endpoint=fake_endpoint,
    )
    vector = adapter.embed("赤羽駅徒歩10分", "query")

    fake_endpoint.predict.assert_called_once_with(instances=[{"text": "query: 赤羽駅徒歩10分"}])
    assert vector == [0.1, 0.2, 0.3]
    assert adapter.endpoint_name == "projects/p/locations/asia-northeast1/endpoints/123"


def test_vertex_endpoint_reranker_parses_scalar_scores() -> None:
    fake_endpoint = MagicMock()
    fake_endpoint.predict.return_value.predictions = [0.9, 0.4, 0.1]

    adapter = VertexEndpointReranker(
        project_id="p",
        location="asia-northeast1",
        endpoint_id="projects/p/locations/asia-northeast1/endpoints/456",
        endpoint=fake_endpoint,
    )
    scores = adapter.predict([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])

    fake_endpoint.predict.assert_called_once_with(instances=[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    assert scores == [0.9, 0.4, 0.1]
    assert adapter.endpoint_name == "projects/p/locations/asia-northeast1/endpoints/456"
