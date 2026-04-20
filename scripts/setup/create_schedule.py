"""Create or update a Vertex AI pipeline schedule.

This is env-driven and idempotent-ish at the interface level; the concrete API
call is deferred until the real pipeline template and trigger resources are in
place. For now it prints the resolved configuration that later wiring will use.
"""

from __future__ import annotations

import json

from scripts._common import env


def main() -> int:
    payload = {
        "project_id": env("PROJECT_ID"),
        "vertex_location": env("VERTEX_LOCATION", env("REGION")),
        "pipeline_template_uri": env("PIPELINE_TEMPLATE_URI"),
        "pipeline_root": env("PIPELINE_ROOT", env("PIPELINE_TEMPLATE_GCS_PATH")),
        "schedule_cron": env("PIPELINE_SCHEDULE_CRON", "0 5 * * 1"),
        "service_account": env("PIPELINE_SERVICE_ACCOUNT"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
