"""Insert the bare-minimum data needed for `make ops-search` etc. to return
200. This is a verification shortcut — production seed comes from raw.properties
+ Dataform staging (`properties_cleaned`) + Dataform feature mart
(`property_features_daily`) + embedding-job. Here we bypass all of those and
materialise just enough rows in `feature_mart` for the Cloud Run search-api's
SQL to return non-empty results.

What gets inserted (5 sample 物件):

- `feature_mart.properties_cleaned` — created as a TABLE (not the Dataform
  view) with property_id / rent / walk_min / age_years / area_m2 / layout /
  pet_ok columns the candidate retriever joins on.
- `feature_mart.property_features_daily` — one row per property for today,
  with ctr / fav_rate / inquiry_rate.
- `feature_mart.property_embeddings` — 768d unit vectors (orthogonal-ish)
  so VECTOR_SEARCH ranks by approximate cosine distance.

Idempotent: each table uses `CREATE OR REPLACE TABLE` so re-running wipes
and rewrites.
"""

from __future__ import annotations

from scripts._common import env, run

PROPERTIES = [
    # (property_id, title, city, ward, rent, layout, walk_min, age_years, area_m2, pet_ok)
    ("p001", "新宿区西新宿 1LDK", "東京都", "新宿区", 120000, "1LDK", 5, 8, 35.0, True),
    ("p002", "渋谷区道玄坂 ワンルーム", "東京都", "渋谷区", 95000, "1R", 3, 12, 22.0, False),
    ("p003", "品川区五反田 2LDK", "東京都", "品川区", 165000, "2LDK", 7, 5, 50.0, True),
    ("p004", "港区赤羽橋 1K", "東京都", "港区", 110000, "1K", 4, 15, 25.0, False),
    ("p005", "目黒区中目黒 2DK", "東京都", "目黒区", 140000, "2DK", 6, 10, 42.0, True),
]


def _vec_literal(idx: int, dim: int = 768) -> str:
    """768d unit vector — basis-like (mostly zeros, one big component) so
    different properties end up at large cosine distance from each other."""
    base = [0.0] * dim
    base[idx % dim] = 1.0
    return "[" + ", ".join(f"{x:.6f}" for x in base) + "]"


def _bq(query: str) -> None:
    print(f"==> bq query (first 80 chars): {query[:80]}…")
    run(
        [
            "bq",
            "query",
            "--use_legacy_sql=false",
            f"--project_id={env('PROJECT_ID')}",
            query,
        ]
    )


def main() -> int:
    project_id = env("PROJECT_ID")

    # 1. properties_cleaned (would normally be a Dataform view)
    rows_props = ",\n  ".join(
        "({pid!r}, {title!r}, {city!r}, {ward!r}, {rent}, {layout!r}, {walk}, {age}, {area}, {pet})".format(
            pid=p[0],
            title=p[1],
            city=p[2],
            ward=p[3],
            rent=p[4],
            layout=p[5],
            walk=p[6],
            age=p[7],
            area=p[8],
            pet="TRUE" if p[9] else "FALSE",
        )
        for p in PROPERTIES
    )
    _bq(
        f"""
        CREATE OR REPLACE TABLE `{project_id}.feature_mart.properties_cleaned` AS
        SELECT * FROM UNNEST([
          STRUCT<property_id STRING, title STRING, city STRING, ward STRING,
                 rent INT64, layout STRING, walk_min INT64, age_years INT64,
                 area_m2 FLOAT64, pet_ok BOOL>
          {rows_props}
        ])
        """
    )

    # 2. property_features_daily — today's row per property
    rows_feat = ",\n  ".join(
        f"(CURRENT_DATE('Asia/Tokyo'), {p[0]!r}, {p[4]}, {p[6]}, {p[7]}, "
        f"{p[8]}, 0.05, 0.10, 0.02, 0.5)"
        for p in PROPERTIES
    )
    _bq(
        f"""
        DELETE FROM `{project_id}.feature_mart.property_features_daily`
        WHERE event_date = CURRENT_DATE('Asia/Tokyo');
        INSERT INTO `{project_id}.feature_mart.property_features_daily`
          (event_date, property_id, rent, walk_min, age_years, area_m2,
           ctr, fav_rate, inquiry_rate, popularity_score)
        VALUES
          {rows_feat}
        """
    )

    # 3. property_embeddings — basis-like 768d vectors
    rows_emb = ",\n  ".join(
        f"({p[0]!r}, {_vec_literal(i)}, 'seed-{p[0]}', "
        f"'intfloat/multilingual-e5-base', CURRENT_TIMESTAMP())"
        for i, p in enumerate(PROPERTIES)
    )
    _bq(
        f"""
        DELETE FROM `{project_id}.feature_mart.property_embeddings` WHERE TRUE;
        INSERT INTO `{project_id}.feature_mart.property_embeddings`
          (property_id, embedding, text_hash, model_name, generated_at)
        VALUES
          {rows_emb}
        """
    )

    # Sanity probe — counts
    print("==> verification counts:")
    _bq(
        f"""
        SELECT
          (SELECT COUNT(*) FROM `{project_id}.feature_mart.properties_cleaned`) AS properties_cleaned,
          (SELECT COUNT(*) FROM `{project_id}.feature_mart.property_features_daily`
            WHERE event_date = CURRENT_DATE('Asia/Tokyo')) AS features_today,
          (SELECT COUNT(*) FROM `{project_id}.feature_mart.property_embeddings`) AS embeddings
        """
    )

    print()
    print(f"==> seed-minimal complete. {len(PROPERTIES)} properties materialised.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
