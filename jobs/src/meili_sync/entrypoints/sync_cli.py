"""Meilisearch index sync CLI.

Reads feature_mart.properties_cleaned from BigQuery and upserts documents into
Meilisearch index `properties`.
"""

from __future__ import annotations

import argparse
from typing import Any

import httpx
from google.auth.transport.requests import Request
from google.cloud import bigquery
from google.oauth2 import id_token


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync properties_cleaned -> Meilisearch")
    parser.add_argument("--project-id", default="mlops-dev-a")
    parser.add_argument("--table", default="feature_mart.properties_cleaned")
    parser.add_argument("--meili-base-url", required=True)
    parser.add_argument("--index", default="properties")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--require-identity-token", action="store_true", default=False)
    parser.add_argument("--api-key", default="")
    return parser.parse_args(argv)


def _headers(*, base_url: str, api_key: str, require_identity_token: bool) -> dict[str, str]:
    headers = {"content-type": "application/json"}
    if api_key:
        headers["x-meili-api-key"] = api_key
    if require_identity_token:
        token = id_token.fetch_id_token(Request(), base_url)
        headers["authorization"] = f"Bearer {token}"
    return headers


def _load_rows(*, client: bigquery.Client, table: str) -> list[dict[str, Any]]:
    query = f"""
        SELECT
          property_id,
          title,
          description,
          layout,
          rent,
          walk_min,
          age_years,
          pet_ok
        FROM `{table}`
    """
    rows = client.query(query).result()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "property_id": row["property_id"],
                "title": row["title"],
                "description": row["description"],
                "layout": row["layout"],
                "rent": row["rent"],
                "walk_min": row["walk_min"],
                "age_years": row["age_years"],
                "pet_ok": row["pet_ok"],
            }
        )
    return out


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    fq_table = args.table
    if "." in args.table and args.table.count(".") == 1:
        fq_table = f"{args.project_id}.{args.table}"

    bq = bigquery.Client(project=args.project_id)
    rows = _load_rows(client=bq, table=fq_table)
    if not rows:
        return 0

    headers = _headers(
        base_url=args.meili_base_url,
        api_key=args.api_key,
        require_identity_token=args.require_identity_token,
    )
    base = args.meili_base_url.rstrip("/")

    with httpx.Client(timeout=30.0) as client:
        settings_url = f"{base}/indexes/{args.index}/settings"
        client.patch(
            settings_url,
            json={
                "filterableAttributes": ["rent", "walk_min", "age_years", "layout", "pet_ok"],
                "searchableAttributes": ["title", "description", "layout"],
            },
            headers=headers,
        ).raise_for_status()

        for i in range(0, len(rows), args.batch_size):
            batch = rows[i : i + args.batch_size]
            url = f"{base}/indexes/{args.index}/documents"
            client.put(url, json=batch, headers=headers).raise_for_status()

    return len(rows)


def main(argv: list[str] | None = None) -> int:
    try:
        count = run(argv)
        print(f"synced_documents={count}")
    except Exception as exc:
        print(f"sync_failed={exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
