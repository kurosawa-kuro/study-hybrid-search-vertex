# scripts/

Makefile から呼ばれる補助 script の置き場。**Makefile は原則 1 行で対応 script を呼ぶだけ** にし、手続き的なロジックは全て `scripts/` 側に外出しする。

---

## 言語選択ルール (最優先)

> **原則 script は Python**。
> 但し、**文字列展開が全くない / 単純なコマンド羅列のみ** であれば shell script を許可。
> 結果として shell script は自然に皆無になる設計。

「文字列展開」の定義 (これらが 1 つでもあれば Python へ寄せる):

- 変数を文字列に埋め込む (`"foo-${VAR}-bar"` / `f"..."` / `printf`)
- JSON / YAML を組み立てる (`jq -n` / heredoc / format string)
- 条件分岐 / ループ / 関数定義
- パイプの中で `sed` / `awk` / `cut` で整形
- 外部コマンドの出力を変数にキャプチャして再利用 (`X=$(...)` の二段以上)
- パス計算 (`$(dirname ...)` / `realpath` / `Path(...).resolve()` 等)

Shell が許される具体例 (これだけ):

```bash
#!/usr/bin/env bash
set -euo pipefail
gcloud services enable serviceusage.googleapis.com bigquery.googleapis.com ...
```

```bash
#!/usr/bin/env bash
terraform -chdir=infra fmt -check -diff
```

これ以上のことをしたくなったら **Python に書き換える**。

---

## ディレクトリ構成

責務 (lifecycle stage) ごとにサブフォルダを切る。新規 script は **必ずどれかに属する**形で追加する。

```
scripts/
  README.md                          ← 本ファイル
  __init__.py / _common.py           ← 共通 helper (env / gcloud / cloud_run_url / identity_token / http_json)
  setup/                             ← 環境前提・IaC ブートストラップ
    doctor.py                        ← `make doctor`
    tf_bootstrap.py                  ← `make tf-bootstrap`
    tf_init.py                       ← `make tf-init`
    tf_plan.py                       ← `make tf-plan`
  deploy/                            ← Cloud Build + Cloud Run rollout (CI 不在時の手動 deploy)
    api_local.py                     ← `make deploy-api-local`
    training_job_local.py            ← `make deploy-training-job-local`
  config/                            ← 派生設定ファイル生成
    sync_dataform.py                 ← `make sync-dataform-config` (env/config/setting.yaml → definitions/workflow_settings.yaml)
  checks/                            ← 静的検査 (lint 系)
    layers.py                        ← `make check-layers` (AST で Port/Adapter 境界を検証)
  ops/                               ← デプロイ後の runtime smoke / 検査
    livez_check.py                   ← `make ops-livez`
    search_check.py                  ← `make ops-search`
    ranking_check.py                 ← `make ops-ranking`
    feedback_check.py                ← `make ops-feedback`
    training_label_seed.py           ← `make ops-label-seed`
    check_retrain.py                 ← `make ops-check-retrain`
  sql/                               ← BQ クエリ (`bq query < scripts/sql/X.sql`)
    skew_latest.sql                  ← `make ops-skew-latest`
    search_volume.sql                ← `make ops-search-volume`
    runs_recent.sql                  ← `make ops-runs-recent`
    bq_scan_top.sql                  ← `make ops-bq-scan-top`
```

サブフォルダの役割境界:

| folder | 含めるもの | 含めないもの |
|---|---|---|
| `setup/` | 1 回だけ叩く / 開発環境前提を整える系 | 反復実行する run/ops |
| `deploy/` | image を build して Cloud Run revision を作る | runtime の HTTP 検査 (それは ops/) |
| `config/` | committed yaml/json から派生ファイルを生成 | 値そのものの変更 (それは env/config/setting.yaml) |
| `checks/` | repo 構造 / 命名 / 境界 / 静的解析 | 実行時の HTTP / DB 検査 (それは ops/) |
| `ops/` | デプロイ後の API / Job への HTTP / RPC 検査 | 構造検査 (それは checks/ や tests/) |
| `sql/` | 1 ファイル 1 SQL、`bq query` で叩く | Python ロジック |

`tests/` 側も同じ責務分割: `tests/arch/` (boundary tests) / `tests/parity/` (cross-file invariants) / `tests/infra/` (terraform / table / workflow shape)。

---

## Makefile 側の規約

- ターゲットは **1 行で script を呼ぶだけ** (`uv run python scripts/X.py` / `bash scripts/X.sh` / `bq query --project_id=$(PROJECT_ID) < scripts/sql/X.sql`)。
- Makefile に inline shell / heredoc / SQL define ブロックを書かない (出てきたら `scripts/` に移動)。
- ターゲット名と script ファイル名は対応させる (`make ops-livez` → `scripts/ops/livez_check.{py,sh}`)。
- export しているのは `PROJECT_ID` / `REGION` / `API_SERVICE` / `TRAINING_JOB` / `ARTIFACT_REPO` の 5 変数。script 側はこれらを env から受け取り、未指定時の既定値は `env/config/setting.yaml` から読む。
- これら 5 つの値は **`env/config/setting.yaml` が single source of truth**。Make は awk で、Python は `scripts/_common.py::_load_settings()` でその yaml を読む。yaml を編集すれば両者に反映される (どちらか一方をハードコードで上書きしないこと)。

---

## Python script の規約

| 項目 | 約束 |
|---|---|
| 実行コマンド | `uv run python scripts/X.py` (project の `.venv` を使う) |
| shebang | 任意 (uv 経由実行が前提なので付けても付けなくても可) |
| 構造 | `def main() -> int:` + `if __name__ == "__main__": raise SystemExit(main())` |
| 引数 | env var を **第一**、`argparse` を補助。`os.environ.get("PROJECT_ID", "mlops-dev-a")` のように既定値を持つ |
| 認証 | `subprocess.run(["gcloud", "auth", "print-identity-token"], ...)` で OIDC を取る (Cloud Run は `--no-allow-unauthenticated`) |
| 外部依存 | 標準ライブラリ (`urllib.request` / `subprocess` / `json`) を優先。requests / httpx 等の追加依存は持ち込まない |
| 終了コード | 成功 0、失敗 非 0 |
| 出力 | stdout に結果、エラーは stderr。最終行のサマリは 1 行 (例: `posted=3`) |
| Lint | `make check` の ruff / mypy 対象に入る (`pyproject.toml` の include に `scripts/**/*.py` が入っている前提) |

---

## Shell script (例外的に許される場合) の規約

例外で .sh を書く場合は以下を守る:

| 項目 | 約束 |
|---|---|
| shebang | `#!/usr/bin/env bash` |
| 安全フラグ | 先頭で `set -euo pipefail` |
| 行数 | **目安 5 行以内** (それ超は Python へ) |
| 文字列展開 | 一切しない (`${X}` 埋め込み、heredoc、$(...)、jq -n 全て不可) |
| 引数 | 位置引数を取らない |
| 実行権限 | `chmod +x` で committする |

---

## SQL ファイルの規約

- 1 ファイル 1 SQL。先頭コメントに **何のためのクエリか + 参照テーブルのスキーマ位置** (`infra/modules/data/main.tf::training_runs` 等) を書く。
- リテラル `mlops-dev-a` / `asia-northeast1` を直書きしてよい (本リポは単一プロジェクト前提、CLAUDE.md 非負制約)。
- 旧 California 残骸 (`predictions_log` / `metrics.rmse` / `validate_data_skew.sql`) を参照しない — schema は `infra/modules/data/main.tf` を権威とする。

---

## 新規 script を追加するとき

1. **言語を決める**: 文字列展開が 1 つでもあれば Python、ゼロなら shell。
2. **置き場所を決める**:
   - 開発環境セットアップ / Terraform → `scripts/X.{py,sh}`
   - デプロイ後の運用 / API smoke → `scripts/ops/X.{py,sh}`
   - BQ クエリだけ → `scripts/sql/X.sql`
3. 上記言語別規約に従って書く。
4. `Makefile` に対応するターゲットを **1 行で** 追加 (`X: ## description\n\tuv run python scripts/.../X.py`)。
5. `.PHONY` リストにターゲット名を追加。
6. `make help` に説明文が出ることを確認。

## 何を置かないか

- **本番ロジック**: `app/` / `jobs/` / `common/` に置く。`scripts/` は thin wrapper のみ。
- **テスト**: `tests/` / `app/tests/` / `common/tests/` / `jobs/tests/` に置く。
- **使い捨ての一回 migration スクリプト**: 完了後に削除する (リポに残さない)。
- **別リポからのコピー**: そのまま置かない。本リポの API スキーマ・命名・依存に合わせて書き直すか削除する。

---

## 現在の状態 (2026-04-20 時点)

旧 shell 群は全て Python 化完了。さらに lifecycle 別に 5 サブフォルダ (`setup/` / `deploy/` / `config/` / `checks/` / `ops/`) + `sql/` に再編。`scripts/` 直下と各サブフォルダは `__init__.py` を持つパッケージで、共通 helper は `scripts/_common.py` に集約 (env 取得 / gcloud subprocess / Cloud Run URL 解決 / OIDC token / IAM-gated http_json)。Makefile から `uv run python -m scripts.<folder>.<module>` で呼び出す。SQL ファイル (`scripts/sql/*.sql`) は当初からルール準拠、変更なし。`tests/` も同じ責務分割 (`arch/` / `parity/` / `infra/`)。
