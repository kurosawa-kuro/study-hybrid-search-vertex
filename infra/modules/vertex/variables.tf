variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Primary region for regional resources"
  type        = string
}

variable "vertex_location" {
  description = "Vertex AI location for endpoints and pipelines"
  type        = string
}

variable "service_accounts" {
  description = "Map of SA resources emitted by the iam module. Reserved for future Vertex resources."
  type        = any
}

variable "mlops_dataset_id" {
  description = "BQ dataset ID for mlops tables"
  type        = string
}

variable "feature_mart_dataset_id" {
  description = "BQ dataset ID for feature mart tables"
  type        = string
}

variable "pipeline_root_bucket_name" {
  description = "GCS bucket name used as Vertex AI pipeline root"
  type        = string
}

variable "model_monitoring_alerts_table_id" {
  description = "BigQuery table ID used as the sink for Vertex model monitoring alerts"
  type        = string
}

variable "encoder_endpoint_id" {
  description = "Vertex AI encoder endpoint ID or full resource name. Empty string keeps the module in scaffold mode."
  type        = string
  default     = ""
}

variable "reranker_endpoint_id" {
  description = "Vertex AI reranker endpoint ID or full resource name. Empty string keeps the module in scaffold mode."
  type        = string
  default     = ""
}

variable "encoder_endpoint_display_name" {
  description = "Display name reserved for the encoder endpoint"
  type        = string
}

variable "reranker_endpoint_display_name" {
  description = "Display name reserved for the reranker endpoint"
  type        = string
}

variable "retrain_trigger_topic_id" {
  description = "Pub/Sub topic ID for retrain-trigger events emitted by search-api"
  type        = string
}

variable "retrain_trigger_topic_name" {
  description = "Pub/Sub topic name for retrain-trigger events emitted by search-api"
  type        = string
}
