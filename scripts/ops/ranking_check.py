"""Inspect the rank-level details of a single /search response. Useful for
eyeballing whether lexical_rank / final_rank diverge once the booster lands
(Phase 6+) and whether me5_score is being populated correctly.
"""

from __future__ import annotations

import json
import os

from scripts._common import cloud_run_url, fail, http_json, identity_token


def main() -> int:
    query = os.environ.get("QUERY", "新宿駅 1LDK")
    top_k = int(os.environ.get("TOP_K", "5"))

    url = cloud_run_url()
    token = identity_token()
    payload = {"query": query, "top_k": top_k}
    status, body = http_json("POST", f"{url}/search", token=token, payload=payload)
    if status != 200:
        return fail(f"search returned HTTP {status}: {body}")

    data = json.loads(body)
    summary = {
        "request_id": data.get("request_id"),
        "results": [
            {
                "property_id": r.get("property_id"),
                "lexical_rank": r.get("lexical_rank"),
                "final_rank": r.get("final_rank"),
                "score": r.get("score"),
                "me5_score": r.get("me5_score"),
            }
            for r in data.get("results", [])
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
