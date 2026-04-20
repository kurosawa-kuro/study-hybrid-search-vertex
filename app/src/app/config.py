"""API settings."""

from common.config import BaseAppSettings


class ApiSettings(BaseAppSettings):
    # --- /search + /feedback -------------------------------------------------
    enable_search: bool = False
    ranking_log_topic: str = "ranking-log"
    feedback_topic: str = "search-feedback"
    retrain_topic: str = "retrain-trigger"
    bq_table_property_embeddings: str = "property_embeddings"
    bq_table_property_features_daily: str = "property_features_daily"
    bq_table_properties_cleaned: str = "properties_cleaned"
    meili_base_url: str = ""
    meili_index_name: str = "properties"
    meili_api_key: str = ""
    meili_require_identity_token: bool = True
    # Local directory or GCS URI (gs://...) for the ME5 encoder checkpoint.
    # Empty string => sentence-transformers pulls from HuggingFace on startup
    # (dev-only path; not appropriate for Cloud Run).
    encoder_model_dir: str = ""

    # --- Phase 6 /search rerank (optional bolt-on) ---------------------------
    # When False, /search returns candidates in lexical_rank order with score=None
    # even if enable_search is True (Phase 4 behavior preserved).
    # When True, lifespan attempts to resolve the latest LambdaRank booster
    # from mlops.training_runs + GCS and calls booster.predict() during /search.
    # A load failure logs a warning and falls back to rerank-off — the API stays
    # available so staging smoke tests don't flap while the training loop ramps.
    enable_rerank: bool = False
    # Optional explicit model path override (skips BQ lookup). Accepts gs://,
    # file://, or plain local paths. Useful for local smoke + canary deploys.
    model_path_override: str = ""
    # Local cache directory for the downloaded booster file.
    local_model_dir: str = "/tmp/model"
    search_cache_ttl_seconds: int = 120
    search_cache_maxsize: int = 2048
