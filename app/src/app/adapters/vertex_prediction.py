"""Vertex AI Endpoint adapters for encoder / reranker inference."""

from __future__ import annotations

from typing import Any, Literal


def _normalize_endpoint_name(*, project_id: str, location: str, endpoint_id: str) -> str:
    endpoint_id = endpoint_id.strip()
    if endpoint_id.startswith("projects/"):
        return endpoint_id
    return f"projects/{project_id}/locations/{location}/endpoints/{endpoint_id}"


def _create_endpoint(*, project_id: str, location: str, endpoint_name: str) -> Any:
    from google.cloud import aiplatform

    aiplatform.init(project=project_id, location=location)
    return aiplatform.Endpoint(endpoint_name)


def _coerce_float_list(value: Any, *, field_name: str) -> list[float]:
    if isinstance(value, list):
        return [float(item) for item in value]
    raise TypeError(f"Expected list for {field_name}, got {type(value).__name__}")


class VertexEndpointEncoder:
    """Adapter over a Vertex AI Endpoint that returns one embedding per text."""

    def __init__(
        self,
        *,
        project_id: str,
        location: str,
        endpoint_id: str,
        endpoint: Any | None = None,
    ) -> None:
        self.endpoint_name = _normalize_endpoint_name(
            project_id=project_id,
            location=location,
            endpoint_id=endpoint_id,
        )
        self._endpoint = endpoint or _create_endpoint(
            project_id=project_id,
            location=location,
            endpoint_name=self.endpoint_name,
        )

    def embed(self, text: str, kind: Literal["query", "passage"]) -> list[float]:
        payload = {"text": f"{kind}: {text.strip()}"}
        response = self._endpoint.predict(instances=[payload])
        predictions = list(getattr(response, "predictions", []))
        if not predictions:
            raise ValueError("Vertex encoder returned no predictions")
        first = predictions[0]
        if isinstance(first, dict):
            for key in ("embedding", "embeddings", "values"):
                if key in first:
                    return _coerce_float_list(first[key], field_name=key)
            raise KeyError("Vertex encoder response dict missing embedding payload")
        return _coerce_float_list(first, field_name="prediction")


class VertexEndpointReranker:
    """Adapter over a Vertex AI Endpoint that returns one score per row."""

    def __init__(
        self,
        *,
        project_id: str,
        location: str,
        endpoint_id: str,
        endpoint: Any | None = None,
    ) -> None:
        self.endpoint_name = _normalize_endpoint_name(
            project_id=project_id,
            location=location,
            endpoint_id=endpoint_id,
        )
        self._endpoint = endpoint or _create_endpoint(
            project_id=project_id,
            location=location,
            endpoint_name=self.endpoint_name,
        )

    def predict(self, instances: list[list[float]]) -> list[float]:
        response = self._endpoint.predict(instances=instances)
        predictions = list(getattr(response, "predictions", []))
        scores: list[float] = []
        for prediction in predictions:
            if isinstance(prediction, dict):
                for key in ("score", "prediction", "value"):
                    if key in prediction:
                        scores.append(float(prediction[key]))
                        break
                else:
                    raise KeyError("Vertex reranker response dict missing score payload")
            else:
                scores.append(float(prediction))
        return scores
