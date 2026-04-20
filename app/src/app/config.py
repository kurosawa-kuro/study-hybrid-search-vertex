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
    vertex_location: str = "asia-northeast1"
    vertex_encoder_endpoint_id: str = ""

    # --- Phase 6 /search rerank (optional bolt-on) ---------------------------
    # When False, /search returns candidates in lexical_rank order with score=None.
    # When True, the API calls the configured Vertex AI reranker endpoint.
    enable_rerank: bool = False
    vertex_reranker_endpoint_id: str = ""
    search_cache_ttl_seconds: int = 120
    search_cache_maxsize: int = 2048
