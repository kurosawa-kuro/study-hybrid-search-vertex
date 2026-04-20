# CLAUDE.md

本リポジトリで作業する Claude Code 向けのガイド。**非負制約 / 参照リポジトリ / feature-parity invariant** を最優先で載せる (`docs/README.md` §1 の CLAUDE.md 仕様に従う)。

ドキュメント全般の運用規約は [`docs/README.md`](docs/README.md)、スコープの決定権は [`docs/02_移行ロードマップ.md`](docs/02_移行ロードマップ.md)。本 CLAUDE.md はそれらに従属する。

---

## 最初に読むもの (順番)

1. [`docs/README.md`](docs/README.md) — ドキュメント運用ルール (権威順位 / 更新規約 / 書き方)
2. [`docs/02_移行ロードマップ.md`](docs/02_移行ロードマップ.md) — **決定的仕様** (Meilisearch + BigQuery VECTOR_SEARCH + RRF + LambdaRank、Redis サーバ非採用)
3. [`docs/03_実装カタログ.md`](docs/03_実装カタログ.md) — ディレクトリ / ファイル / DB テーブル / API / GCP / Terraform の逐一掲載
4. [`docs/04_運用.md §1`](docs/04_運用.md) — 環境構築 STEP 1–17 (上から順に叩けば完走)

---

## bq-first の設計テーゼ (題材: 不動産ハイブリッド検索)

- **題材**: 自由文クエリ + フィルタ → 物件ランキング上位 20 件。3 段構成 = (1a) Meilisearch BM25、(1b) BigQuery VECTOR_SEARCH、(2) RRF 融合、(3) LightGBM `lambdarank` 再ランク
- **BigQuery + Cloud Run 中心**。モデル成果物は GCS (`gs://mlops-dev-a-models/lgbm/{date}/{run_id}/model.txt`)、系譜は BQ テーブル `mlops.training_runs`。**Vertex AI / Model Registry / BQML 非採用**
- **Training-Serving Skew 対策が load-bearing**。Dataform SQL (`feature_mart.property_features_daily`) と `common.feature_engineering.build_ranker_features` を同一式で lockstep 維持 (`ctr = SAFE_DIVIDE(click_count, impression_count)` など、分子分母の順序が訓練側と推論側で 1:1)
- **学習 = Cloud Run Jobs (`training-job` + `embedding-job`) / 推論 = Cloud Run Service (`search-api`)**。両方を Service にしない。モデルは**コンテナ同梱せず**、FastAPI `lifespan` で `mlops.training_runs` から最新 `run_id` の `model_path` を解決 → GCS から `model.txt` を download → `lgb.Booster` にロード (Phase 6 以降)
- **Phase 4 rerank-free MVP** — Booster ロード前でも `/search` は候補抽出結果 (`final_rank = lexical_rank`) を返せる。ステージング疎通条件は `docs/04_運用.md §1 STEP 17`
- **スコープ固定**: 不動産ハイブリッド検索のみ。旧 California Housing 回帰は Phase 10b/10c で完全削除済

---

## 非負制約 (User 確認無しに変えない)

| 項目 | 値 | 理由 |
|---|---|---|
| GCP プロジェクト | `mlops-dev-a` | 固定 |
| リージョン | `asia-northeast1` | 固定 |
| Python | 3.12 | `pyproject.toml` |
| パッケージ管理 | `uv` (pip / poetry 不可) | workspace 採用 |
| IaC | Terraform 1.9+ | |
| Cloud Run Service | `--cpu 2 --memory 4Gi --concurrency 80 --min-instances 1 --max-instances 10 --cpu-boost --execution-environment gen2 --no-allow-unauthenticated` | コールドスタート回避、IAM-gated。4Gi は ME5 encoder (~1.1GB) + Booster + Python overhead を収めるため |
| Cloud Run Jobs | `--cpu 2 --memory 4Gi --task-timeout 1800s --max-retries 1` | 実装は `infra/modules/runtime/main.tf` |
| Service Account | 5 SA 分離 (`sa-api` / `sa-job-train` / `sa-job-embed` / `sa-dataform` / `sa-scheduler`) + WIF 専用 `sa-github-deployer` | 最小権限の境界、統合しない。`sa-job-embed` は `feature_mart` への書込専用で `mlops.*` への書込権を持たないので blast radius を小さく分離 |
| 設定値 single source | `env/config/setting.yaml` (project_id / region / api_service / training_job / artifact_repo / github_repo / oncall_email / dataform_*) | flat key:value のみ。Python は `scripts/_common.py::DEFAULTS` で読み、Make は awk で読む。`github_repo` / `oncall_email` も yaml が既定値で、env で都度上書き可。`definitions/workflow_settings.yaml` は **auto-generated** (gitignore + `make sync-dataform-config` で再生成、parity test で drift 検知) |
| 認証 | GitHub Actions → Workload Identity Federation (SA Key 禁止) | 監査要件 |
| 再学習条件 (`app/src/app/services/retrain_policy.py`) | `NEW_FEEDBACK_ROWS_THRESHOLD = 10_000` / `NDCG_DEGRADATION = 0.03` / `STALE_DAYS = 7` | コード定数。変更時は `app/tests/test_retrain.py` にケース追加 |

`--min-instances 1 → 0` に落とすとコスト削減するが ME5 エンコーダロードで数秒〜数十秒のコールドスタートが発生する。下げる際は必ず User に flag。

---

## Feature parity invariant (5 ファイル同一 PR 原則)

特徴量を追加 / 変更するとき、以下 5 つを **必ず同じ PR で揃える** (片方だけだと Scheduled Query のスキュー検知が FAIL する):

1. `definitions/features/property_features_daily.sqlx` (訓練側 SQL — ctr / fav_rate / inquiry_rate の SAFE_DIVIDE 式)
2. `common/src/common/feature_engineering.py::build_ranker_features` (推論側 Python、10 列の組み立て)
3. `common/src/common/schema/feature_schema.py` の `FEATURE_COLS_RANKER` (10 列の順序と名前)
4. `infra/modules/data/main.tf` の `ranking_log.features` RECORD スキーマ (API publish のキー名と 1:1、FLOAT64 NULLABLE)
5. `monitoring/validate_feature_skew.sql` の UNPIVOT (訓練側・推論側とも property-side 7 列を列挙、`tests/parity/test_feature_parity_sql_ranker.py` で検証)

10 列中 7 列 (`rent` / `walk_min` / `age_years` / `area_m2` / `ctr` / `fav_rate` / `inquiry_rate`) が property-side で訓練 / 推論で共通。残り 3 列 (`me5_score` / `lexical_rank` / `semantic_rank`) はクエリ時に計算されるので監視 SQL からは除外し、サービング側で別のサニティチェックを回す。

---

## ドキュメント衝突時の権威順位

`docs/README.md §2` に従う:

```
02_移行ロードマップ.md > 01_仕様と設計.md > README.md
```

`CLAUDE.md` と `03_実装カタログ.md` は上位 3 者から派生する従属ドキュメント。3 者が互いに矛盾したら `02_移行ロードマップ.md` を正として他を合わせ、User に flag する。

過去に Vertex AI / Meilisearch / Redis など「採否決定が drift した」事例があるので、連動するドキュメントは **同一 PR で直す** (`docs/README.md §3`)。

---

## 開発コマンド

生コマンドは `docs/04_運用.md §1` の STEP 1–17、全ターゲットは `make help`。`make check` でローカル CI 同等 (ruff / ruff format / mypy strict / pytest) を走らせる。

| target | 用途 |
|---|---|
| `make doctor` | 前提ツール到達確認 (uv / terraform / gcloud / make / jq + VIRTUAL_ENV mismatch 警告) |
| `make sync` | uv workspace + dev group 同期 |
| `make check` | ruff + fmt-check + mypy + pytest (CI 同等、現行 194 tests) |
| `make check-layers` | AST で Port/Adapter 境界違反を検出 (`scripts/checks/layers.py::RULES` 経由、31 ファイル) |
| `make sync-dataform-config` | `env/config/setting.yaml` → `definitions/workflow_settings.yaml` を生成 (gitignored、CI で自動再生成) |
| `make train-smoke` / `make train-smoke-persist` | 合成データで LightGBM LambdaRank 学習 (GCP 認証不要) |
| `make api-dev` | ローカル uvicorn (`ENABLE_SEARCH=false` 既定 / `/search` を動かす場合は env に ENABLE_SEARCH=true + BQ creds) |
| `make tf-validate` | オフライン terraform validate |
| `make tf-bootstrap` | Phase 0 (API 有効化 + tfstate バケット作成、冪等) |
| `make tf-plan` | Terraform plan。`GITHUB_REPO` / `ONCALL_EMAIL` は `env/config/setting.yaml` から既定値、env で都度上書き可。1 行で叩く / backslash 改行禁止。infra/tfplan に保存 |
| `make deploy-api-local` / `make deploy-training-job-local` | CI を経由せず Cloud Build (`cloudbuild.{api,training}.yaml`) → `gcloud run deploy/jobs update` で local から rollout |
| `make ops-*` | 本番 GCP 操作 (`docs/04_運用.md §2`)。`ops-livez` (Cloud Run /livez 疎通) / `ops-search` / `ops-ranking` / `ops-feedback` / `ops-label-seed` / `ops-search-volume` / `ops-runs-recent` / `ops-skew-latest` 等 |

CI path filters (`app/**` / `jobs/**` / `definitions/**` / `infra/**`) は top-level ディレクトリと 1:1。`common/**` は api / job の両方に依存するため `deploy-api.yml` / `deploy-training-job.yml` / `deploy-embedding-job.yml` の 3 つに含める (後者は `common/src/common/embeddings/**` に絞った狭い filter)。

---

## 参照リポジトリ (コピー元)

参考にした 3 つのリポジトリ。既存パターンがあるものを新規作成する前にこれらを参照する:

| 役割 | パス | 引用ポイント |
|---|---|---|
| 不動産ハイブリッド検索の設計 | `/home/ubuntu/repos/study-gcp-mlops/study-llm-reranking-mlops` | LambdaRank ハイパラ / NDCG 評価 / ラベル Gain / ME5 プロンプト規約 (`query:` / `passage:`)。I/O 層は本リポの Port/Adapter に吸収 |
| GCP I/O 層 | `/home/ubuntu/repos/starter-kit/mlops/` | GCS upload + BQ insert / Cloud Logging JSON formatter + request middleware / argparse entrypoint |
| Terraform + CI/CD | `/home/ubuntu/repos/study-gcp/study-gcp-mlops/` | `terraform/*.tf` と `.github/workflows/{terraform,api-deploy,batch-deploy}.yml` の雛形 |

本リポジトリで新規作成したもの:

- **機能**: Dataform 定義 (`property_features_daily`) / `BigQueryCandidateRetriever` (BQ VECTOR_SEARCH) / `E5Encoder` (sentence-transformers ラッパ) / `/search` `/feedback` `/jobs/check-retrain` `/events/retrain` エンドポイント / Pub/Sub → BQ Subscription (`ranking-log` / `search-feedback`) / NDCG ベース mean-drift SQL / 4 SA 最小権限分離 / uv ワークスペース化 / Workload Identity Federation
- **Port / Adapter 分離** (3 workspace すべて layer-based subpackage):
  - `common/src/common/`: `ports/` (embedding_store) / `adapters/` (bigquery_embedding_store) / `storage/` (gcs_artifact_store) / `schema/` (feature_schema) / `logging/` (structured_logging) / `embeddings/` (e5_encoder) / `ranking/` (metrics, label_gain) + top-level `config.py` / `feature_engineering.py` / `run_id.py`
  - `app/src/app/`: `entrypoints/` (api) / `services/` (ranking, retrain_policy) / `ports/` (candidate_retriever, publisher, retrain_queries, training_job_runner) / `adapters/` (candidate_retriever, publisher, retrain, training_job) / `middleware/` (request_logging) / `schemas/` (search) + top-level `config.py`
  - `jobs/src/training/`: `entrypoints/` (rank_cli, embed_cli) / `services/` (rank_trainer, ranking_metrics, embedding_runner) / `adapters/` (embedding_writer) + top-level `config.py`
- **自動検知** (`tests/` は責務別 3 サブフォルダに分割):
  - `tests/arch/test_import_boundaries.py` — AST 境界 (canonical な `RULES` は `scripts/checks/layers.py`、`make check-layers` でも CLI 単独実行可)
  - `tests/parity/test_feature_parity_ranking.py` + `tests/parity/test_feature_parity_sql_ranker.py` — 5 ファイル parity invariant
  - `tests/parity/test_dataform_workflow_settings.py` — setting.yaml ↔ Dataform 生成 yaml の drift
  - `tests/infra/test_terraform_module_structure.py` / `tests/infra/test_infra_ranker_tables.py` / `tests/infra/test_workflows_structure.py`
- **CI composite actions**: `.github/actions/{setup-python-env,setup-gcp,build-and-push}/` (5 workflow で共有)
- **scripts/ の責務分割** (lifecycle 別、`scripts/README.md` に Python-default ルール明記):
  - `scripts/setup/` (doctor / tf_bootstrap / tf_init / tf_plan)、`scripts/deploy/` (api_local / training_job_local)、`scripts/config/` (sync_dataform)、`scripts/checks/` (layers)、`scripts/ops/` (livez_check / search_check / ranking_check / feedback_check / training_label_seed / check_retrain)、`scripts/sql/` (BQ クエリ)
  - 共通 helper は `scripts/_common.py` (env / gcloud / cloud_run_url / identity_token / http_json、stdlib のみ)

---

## リポジトリ状態

- Phase 1–10d の実装 + scripts/tests 再編 + setting.yaml 集約が完了。California Housing 関連コード / Dataform / Python / Terraform / Scheduled Query は 10b/10c で完全削除済
- `make check` 現行 194 tests (`tests/{arch,parity,infra}/` + workspace 別 `{app,jobs,common}/tests/`)。ただし `jobs/tests/test_rank_trainer.py` と `jobs/tests/test_rank_cli_run.py` の 4 件が FAIL 中 — `FEATURE_COLS_RANKER` に `semantic_rank` が入ったが trainer の fixture 側が追従していない (下記 残タスク 参照)
- Port / pure-logic ファイルの境界は `scripts/checks/layers.py::RULES` が canonical。`tests/arch/test_import_boundaries.py` は薄い pytest ラッパで、`make check-layers` でも CLI 単独実行できる (`google.cloud.*` / `wandb` / 具象 adapter の直接 import を禁止)
- feature parity invariant (5 ファイル) は自動検知:
  - `tests/parity/test_feature_parity_sql_ranker.py` — monitoring SQL の UNPIVOT ↔ `FEATURE_COLS_RANKER` (property-side 7 列)
  - `tests/parity/test_feature_parity_ranking.py` — Python `build_ranker_features` ↔ `schema.py` ↔ infra `ranking_log.features` RECORD + Dataform SQLX のビヘイビア列チェック
  - `tests/parity/test_dataform_workflow_settings.py` — `env/config/setting.yaml` ↔ `scripts.config.sync_dataform.render()` (生成器) drift 検知
- Terraform モジュール構造 (`main.tf` / `variables.tf` / `outputs.tf` / `versions.tf` + 全 variable に description) は `tests/infra/test_terraform_module_structure.py` で検証
- 初回 apply 時に踏みやすい 4 つのハマりは `infra/modules/` 側で全て修正済 (`time_sleep` / DTS の `location` / DTS の `service_account_name` / Cloud Run image placeholder)。詳細表は `docs/04_運用.md §1 STEP 9`
- `make tf-validate` PASS (offline)、`make tf-bootstrap` で Phase 0 半自動化済
- **残タスク**:
  - **trainer 側の `semantic_rank` 追従漏れ** — `FEATURE_COLS_RANKER` に `semantic_rank` が追加されたが `jobs/src/training/services/rank_trainer.py` の要求列チェックとテスト fixture がこれに追随していない。`jobs/tests/test_rank_trainer.py` / `jobs/tests/test_rank_cli_run.py` の 4 件が FAIL する。feature parity invariant を完結させるには trainer 側の fixture / splitter に `semantic_rank` 列を埋める必要あり
  - **`deploy-embedding-job.yml` のヘッダーコメント更新漏れ** — `google_cloud_run_v2_job.embedding_job` は `infra/modules/runtime/main.tf:154` で既に定義済みだが、workflow ファイル冒頭のコメント (L12–16) が「Phase 9 lands するまで未定義」「`|| true` で NOT_FOUND 許容」と古いまま。apply 本体は既に修正済 (`|| true` は除去) で、コメントだけ差分
  - Doppler → Cloud Run 環境変数注入は **配線されていない** (Secret Manager 容器は作るが誰も読まない、`--set-secrets` 未使用)。STEP 10 を skip しても動く
  - Monitoring 通知先差し替え (`oncall@example.com` placeholder)
  - Looker Studio ダッシュボード (IaC 対象外)
  - VECTOR INDEX の IaC 化 (`google_bigquery_vector_index` provider 対応待ち、`docs/02_移行ロードマップ.md §14 R3`)
  - Phase 6 以降の LambdaRank booster 本番連携 (`/search` から `score` を出す rerank 組み込み)

---

## 紛らわしい点

- `monitoring/validate_feature_skew.sql` は BQML の `ML.VALIDATE_DATA_SKEW()` 関数**ではなく**、カスタム mean-drift 実装 (`mean_drift_sigma`)
- `FORCE_RELOAD=<ts>` は特殊な env ではなく、任意の env 変更で Cloud Run revision が再生成され lifespan が再ロードされる性質を利用した慣用。`make ops-reload-api` がラッパー
- Doppler 連携は仕様 (Secret Manager → Cloud Run env) としては記述済みだが、deploy workflow は GitHub Secret 経由 (`secrets.DOPPLER_TOKEN_*`) で Doppler CLI を呼び、Secret Manager 容器は誰も読んでいない。当面は `--set-env-vars` 直書き運用
- BigQuery `VECTOR_SEARCH` + `VECTOR INDEX` は Terraform google provider 未対応 (2026-04 時点)。INDEX は `docs/04_運用.md STEP 16` で手動 DDL
- `/healthz` は Cloud Run の Knative frontend が予約 (HTML 404 を返して container に到達しない) ため、deploy 後の liveness 検査には **`/livez`** (alias) を使う。local の `make api-dev` 時は `/healthz` でも届く
- Cloud Run image は初回 apply 時 `gcr.io/cloudrun/hello` placeholder で起動 (Artifact Registry が空のため)。real image は CI もしくは `make deploy-api-local` で push する。`lifecycle.ignore_changes = [... image ...]` により Terraform は real image を差し戻さない

---

## 境界維持の長期方針

現アーキテクチャは Port/Adapter + composition root + AST/parity テストで固めてあるが、**成長時に崩れやすい 2 箇所**を運用ルールとして明記する。

### layer サブパッケージの拡張方針

3 workspace とも layer-based subpackage (`entrypoints` / `services` / `ports` / `adapters` + 周辺) に整備済み。新しいコードを追加するときの基準:

- **Port**（新しい Protocol） → `ports/<name>.py` を追加し `ports/__init__.py` で re-export
- **Service**（新しい純粋ロジック） → `services/<name>.py`。Port だけを import、adapter は import しない
- **Adapter**（新しい外部依存） → `adapters/<name>.py`。`__init__.py` で re-export
- **新しい Port / 外部システム種別が増えた** → サブモジュールを増やす（既存ファイルを膨らませない）
- **単一サブモジュールで 8 クラス以上 / 300 行超** → さらに細分化を検討
- **レイヤ境界違反** → `scripts/checks/layers.py::RULES` を canonical として `tests/arch/test_import_boundaries.py` が CI で捕まえる。CLI でも `make check-layers`

Port 定義は consumer と同居のまま動かさない (`app.candidate_retriever` の Port を `app.adapters.candidate_retriever` に移さない)。

### `common/` 肥大化抑制

`common/` には **「app と jobs の両方が使うもの」だけ** 置く。以下は common に入れない:

- app だけが使う (例: FastAPI middleware、API schema) → `app/src/app/` に残す
- jobs だけが使う (例: LightGBM 直結) → `jobs/src/training/` に残す
- 片側だけで使用中のファイルを `common/` に移すときは「なぜ共有が必要か」をコミットに書く

判断に迷ったら「**jobs の Dockerfile でこのモジュールが読まれても意味があるか**」を問う。無ければ common から外す。`tests/arch/test_import_boundaries.py` で port/pure-logic files の境界は自動検知されるが、common 配置の妥当性は人間判断 — レビュー時にここを見る。

---

## 書き方

`docs/README.md §4` 書き方ルールに従う:
- 日本語で書く。英単語は技術用語としてそのまま (例: `lifespan`, `Booster`, `Pub/Sub`, `LambdaRank`)
- コマンドは `make` ターゲット優先。生 `gcloud` / `bq` / `terraform` は動的引数が必要な場合のみ
- 識別子は固有名を使う (`<foo>` でぼかさない)。プロジェクト ID / テーブル / トピック名など
- STEP / 番号付きリストは上から叩けば成立する順序で書く
- 推測で書かない。コマンドを書いたら実際に叩いて確認する
