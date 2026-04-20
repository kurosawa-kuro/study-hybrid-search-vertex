output "encoder_endpoint_name" {
  description = "Resolved encoder endpoint resource name placeholder"
  value       = local.encoder_endpoint_name
}

output "reranker_endpoint_name" {
  description = "Resolved reranker endpoint resource name placeholder"
  value       = local.reranker_endpoint_name
}

output "pipeline_root_bucket_name" {
  description = "Vertex pipeline root bucket wired into this module"
  value       = var.pipeline_root_bucket_name
}

output "feature_group_property_features" {
  description = "Canonical property-side feature declarations for the Vertex Feature Group scaffold"
  value       = local.feature_group_property_features
}

output "model_monitoring_alerts_topic" {
  description = "Pub/Sub topic intended for Vertex model monitoring alerts"
  value       = google_pubsub_topic.model_monitoring_alerts
}

output "monitoring_alerts_subscription" {
  description = "BigQuery subscription that persists monitoring alerts into mlops.model_monitoring_alerts"
  value       = google_pubsub_subscription.monitoring_alerts_to_bq
}

output "pipeline_trigger_function_name" {
  description = "Cloud Function name for the Vertex pipeline trigger"
  value       = google_cloudfunctions2_function.pipeline_trigger.name
}

output "pipeline_trigger_eventarc_name" {
  description = "Eventarc trigger name for retrain-to-pipeline wiring"
  value       = google_eventarc_trigger.retrain_to_pipeline.name
}

output "monitoring_trigger_eventarc_name" {
  description = "Eventarc trigger name for monitoring-to-pipeline wiring"
  value       = google_eventarc_trigger.monitoring_to_pipeline.name
}
