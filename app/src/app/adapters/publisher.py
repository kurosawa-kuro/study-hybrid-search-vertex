"""Concrete adapter implementing :class:`app.publisher.PredictionPublisher` over Pub/Sub."""

from __future__ import annotations

import json


class PubSubPublisher:
    """Synchronously publishes JSON-encoded payloads to a Pub/Sub topic."""

    def __init__(self, *, project_id: str, topic: str) -> None:
        from google.cloud import pubsub_v1  # type: ignore[attr-defined]

        self._client = pubsub_v1.PublisherClient()
        self._topic_path = self._client.topic_path(project_id, topic)

    def publish(self, payload: dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._client.publish(self._topic_path, data).result(timeout=5)
