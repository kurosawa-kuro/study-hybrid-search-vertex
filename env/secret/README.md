# env/secret/

ローカル開発用クレデンシャル置き場。

**このディレクトリは `.gitignore` 対象。** README.md のみコミットする。

## ファイル

| ファイル | 用途 | 参照箇所 |
|---|---|---|
| `credential.yaml` | flat YAML でローカル用シークレットを集約（`wandb_api_key` など） | `common/src/common/config.py::BaseAppSettings` が `YamlConfigSettingsSource` で読み込む |

非クレデンシャル設定（project_id, region, artifact_repo 等）は `env/config/setting.yaml`。

## 本番環境との関係

本番 (Cloud Run / Cloud Run Jobs) は **Doppler** 経由で環境変数に注入される（`.github/workflows/deploy-*.yml` 参照）。
`credential.yaml` はローカル開発でのみ使われる。

## 形式

```yaml
# flat key: value のみ。ネスト・リスト非対応。
wandb_api_key: "<your-wandb-api-key>"
```

値は `BaseAppSettings` の対応フィールド名と **小文字キーで一致** させる
（pydantic-settings が大文字小文字を区別せずに解決）。

## 新しいシークレット追加手順

1. `BaseAppSettings` または派生 Settings に `secret_name: str = ""` フィールドを追加
2. `credential.yaml` に同名キーを flat YAML で追加
3. 本番で必要なら Doppler にも登録し、deploy workflow の `--set-env-vars` に
   `SECRET_NAME=$(doppler secrets get SECRET_NAME --plain)` 等で転送
