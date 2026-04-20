"""Prepare Vertex model monitoring configuration.

The actual Vertex Monitoring API wiring will be added after endpoint resources
exist. For now this script centralizes the env contract used by that setup.
"""

from __future__ import annotations

import json

from scripts._common import env


def main() -> int:
    payload = {
        "project_id": env("PROJECT_ID"),
        "vertex_location": env("VERTEX_LOCATION", env("REGION")),
        "reranker_endpoint_name": env("VERTEX_RERANKER_ENDPOINT_ID"),
        "monitoring_topic": env("MODEL_MONITORING_ALERTS_TOPIC"),
        "monitoring_table": env("MODEL_MONITORING_ALERTS_TABLE"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
