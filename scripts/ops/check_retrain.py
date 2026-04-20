"""POST /jobs/check-retrain on search-api with an OIDC token. The endpoint
inspects training_runs / feedback freshness and returns whether the
retrain-trigger Pub/Sub topic should fire (used by Cloud Scheduler daily).
"""

from __future__ import annotations

from scripts._common import cloud_run_url, fail, http_json, identity_token, print_pretty


def main() -> int:
    url = cloud_run_url()
    token = identity_token()
    status, body = http_json("POST", f"{url}/jobs/check-retrain", token=token)
    if status != 200:
        return fail(f"check-retrain returned HTTP {status}: {body}")
    print_pretty(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
