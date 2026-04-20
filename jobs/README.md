# jobs/ — Cloud Run Jobs (Phase 3)

## LightGBM 学習ジョブ

### ローカル実行 (スモーク)

```bash
uv sync --package jobs
uv run --package jobs train --dry-run
```

`--dry-run` は GCS upload と training_runs INSERT をスキップ。ADC (`gcloud auth application-default login`) が必要。

### 本番デプロイ

```bash
# image ビルド + push
docker build -f jobs/Dockerfile -t asia-northeast1-docker.pkg.dev/mlops-dev-a/mlops/training-job:$(git rev-parse --short HEAD) .
docker push  asia-northeast1-docker.pkg.dev/mlops-dev-a/mlops/training-job:$(git rev-parse --short HEAD)

# Cloud Run Jobs 作成/更新 (Terraform or gcloud)
gcloud run jobs deploy training-job \
  --region asia-northeast1 \
  --image asia-northeast1-docker.pkg.dev/mlops-dev-a/mlops/training-job:... \
  --service-account sa-job-train@mlops-dev-a.iam.gserviceaccount.com \
  --cpu 2 --memory 4Gi --task-timeout 1800s

# 実行
gcloud run jobs execute training-job --region asia-northeast1
```

## 生成物

- GCS: `gs://mlops-dev-a-models/lgbm/{YYYY-MM-DD}/{run_id}/{model.txt,metrics.json,feature_importance.csv}`
- BQ: `mlops.training_runs` に 1 行 INSERT
- W&B: `WANDB_API_KEY` がある場合のみ。未指定時は offline モード

## 環境変数

| 変数 | デフォルト | 説明 |
|---|---|---|
| `PROJECT_ID` | `mlops-dev-a` | GCP project |
| `GCS_MODELS_BUCKET` | `mlops-dev-a-models` | モデル保存先 |
| `BQ_DATASET_FEATURE_MART` | `feature_mart` | 入力データセット |
| `BQ_TABLE_FEATURE_MART` | `california_housing_features` | 入力テーブル |
| `BQ_DATASET_MLOPS` | `mlops` | メタデータセット |
| `WANDB_API_KEY` | (空) | 空だと offline 実行 |
| `WANDB_PROJECT` | `bq-first-california-housing` | W&B プロジェクト |
| `NUM_LEAVES` / `LEARNING_RATE` / ... | | LightGBM ハイパラ (TrainSettings 参照) |
| `GIT_SHA` | (空) | training_runs の `git_sha` に保存 |

## Training-Serving Skew の砦

`common/feature_engineering.py::engineer_features_input` は Dataform SQL
(`definitions/features/california_housing_features.sqlx`) の `bedroom_ratio`
`rooms_per_person` と **同じ式**。ロジック変更時は両方同時に。
