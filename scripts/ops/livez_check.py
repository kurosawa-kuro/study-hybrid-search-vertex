"""Hit /livez on the deployed search-api. /healthz is reserved by Cloud Run's
Knative frontend (returns its own HTML 404 before reaching the container),
so we use the /livez alias registered in app/src/app/entrypoints/api.py.
"""

from __future__ import annotations

from scripts._common import cloud_run_url, fail, http_json, identity_token


def main() -> int:
    url = cloud_run_url()
    token = identity_token()
    status, body = http_json("GET", f"{url}/livez", token=token)
    if status != 200:
        return fail(f"livez returned HTTP {status}: {body}")
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
