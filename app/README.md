# app/ — Cloud Run Service (Phase 4)

## エンドポイント

| Method | Path | 役割 |
|---|---|---|
| GET | `/healthz` | Cloud Run liveness |
| GET | `/readyz` | モデルロード確認 (未ロードなら 503) |
| POST | `/predict` | 推論。Pub/Sub に publish |

## ローカル実行

```bash
uv sync --package app
# モデルパスを override してローカル推論 (ADC 不要)
MODEL_PATH_OVERRIDE=gs://mlops-dev-a-models/lgbm/2026-04-18/.../model.txt \
PUBLISH_PREDICTIONS=false \
uv run --package app uvicorn app.main:app --reload
```

本番では `MODEL_PATH_OVERRIDE` は空にし、起動時に `mlops.training_runs` から最新 run を取得する。

## Cloud Run デプロイ (Phase 4 roadmap §4 参照)

```bash
gcloud run deploy search-api \
  --region asia-northeast1 \
  --image asia-northeast1-docker.pkg.dev/mlops-dev-a/mlops/search-api:$(git rev-parse --short HEAD) \
  --service-account sa-api@mlops-dev-a.iam.gserviceaccount.com \
  --cpu 2 --memory 2Gi \
  --concurrency 80 \
  --min-instances 1 --max-instances 10 \
  --cpu-boost \
  --execution-environment gen2 \
  --no-allow-unauthenticated \
  --set-env-vars "PROJECT_ID=mlops-dev-a,GCS_MODELS_BUCKET=mlops-dev-a-models"
```

## 動作確認 (IAM 認証)

```bash
URL=$(gcloud run services describe search-api --region asia-northeast1 --format='value(status.url)')
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
     -H 'Content-Type: application/json' \
     -d '{"med_inc":3.5,"house_age":25,"ave_rooms":5,"ave_bedrms":1,"population":1500,"ave_occup":2.5,"latitude":34,"longitude":-118}' \
     $URL/predict
```

## Pub/Sub → BigQuery

`/predict` は `predictions` トピックに以下 JSON を publish:

```json
{"request_id": "...", "ts": "...", "model_path": "gs://...", "prediction": 2.34,
 "latency_ms": 12.3, "features": {...}}
```

`predictions-to-bq` subscription が自動で `mlops.predictions_log` にストリーム書き込み。

## Training-Serving Skew

`common/feature_engineering.py::engineer_features_input` は Dataform SQL と **同じ式**
で `bedroom_ratio` / `rooms_per_person` を算出。ロジック変更時は両方同時に。
