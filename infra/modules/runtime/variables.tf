variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Region for Cloud Run Service / Job / Scheduler / Eventarc"
  type        = string
}

variable "artifact_repo_id" {
  description = "Artifact Registry repository ID (for image path construction)"
  type        = string
}

variable "models_bucket_name" {
  description = "GCS bucket name for models + encoder checkpoints (injected as Cloud Run env var)"
  type        = string
}

variable "mlops_dataset_id" {
  description = "BQ dataset ID for mlops (training_runs, ranking_log, search_logs, feedback_events, validation_results)"
  type        = string
}

variable "feature_mart_dataset_id" {
  description = "BQ dataset ID for feature_mart (property_features_daily, property_embeddings)"
  type        = string
}

variable "ranking_log_table_id" {
  description = "BQ table ID for ranking_log (Pub/Sub subscription sink — one row per candidate)"
  type        = string
  default     = "ranking_log"
}

variable "feedback_events_table_id" {
  description = "BQ table ID for feedback_events (Pub/Sub subscription sink — user click/favorite/inquiry)"
  type        = string
  default     = "feedback_events"
}

variable "service_accounts" {
  description = "Map of SA resources emitted by the iam module. Uses .email for bindings."
  type        = any
}

variable "meili_base_url" {
  description = "Base URL of meili-search Cloud Run service"
  type        = string
  default     = ""
}

variable "search_cache_ttl_seconds" {
  description = "Default /search cache TTL in seconds"
  type        = number
  default     = 120
}
