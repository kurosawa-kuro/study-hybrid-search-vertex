# definitions/ — Dataform (Phase 2)

## 目的

`raw.california_housing` から `feature_mart.california_housing_features` を生成する。**学習・推論で同じ view を参照する**ことで Training-Serving Skew を防ぐ。

## パイプライン

```
raw.california_housing (declaration)
  └─ staging.california_housing_cleaned (view)
       ├─ 欠損値を中央値で補完
       ├─ 99%ile で外れ値キャップ (ave_rooms, ave_bedrms, population, ave_occup)
       └─ log1p 変換 (population, ave_occup)

  └─ feature_mart.california_housing_features (table, partitioned by event_date + clustered by location_id)
       ├─ bedroom_ratio = ave_bedrms / ave_rooms
       └─ rooms_per_person = ave_rooms / ave_occup
```

## Assertions

- `california_housing_features_quality` — NULL / 範囲チェック (緯度経度、比率の上限下限)
- `california_housing_features_freshness` — 過去 2 日分のデータ存在確認

## Training-Serving Skew の砦

推論側 (`app/src/common/feature_engineering.py`) は `bedroom_ratio` / `rooms_per_person` と **同じ式** を Python で計算する。ロジック変更時は両方同時に。

定数 (`CAP_UPPER_PERCENTILE`, `CAP_COLS`, `LOG_COLS`) は `includes/constants.js` と推論側 Python 定数を **1 セット** で管理すること。

## 運用

- **スケジュール**: Dataform repository の scheduled executions で JST 03:00 日次 (Terraform で後日追加)
- **失敗時**: assertions が発火した場合 Cloud Logging に構造化ログが残るので、それを元にアラート
- **再実行**: `dataform run` CLI / UI からタグ `california_housing` を指定
