output "mlops_dataset" {
  value = google_bigquery_dataset.mlops
}

output "feature_mart_dataset" {
  value = google_bigquery_dataset.feature_mart
}

output "predictions_dataset" {
  value = google_bigquery_dataset.predictions
}

output "training_runs_table" {
  value = google_bigquery_table.training_runs
}

output "validation_results_table" {
  value = google_bigquery_table.validation_results
}

output "property_features_daily_table" {
  value = google_bigquery_table.property_features_daily
}

output "property_embeddings_table" {
  value = google_bigquery_table.property_embeddings
}

output "search_logs_table" {
  value = google_bigquery_table.search_logs
}

output "ranking_log_table" {
  value = google_bigquery_table.ranking_log
}

output "feedback_events_table" {
  value = google_bigquery_table.feedback_events
}

output "models_bucket" {
  value = google_storage_bucket.models
}

output "artifacts_bucket" {
  value = google_storage_bucket.artifacts
}

output "artifact_registry" {
  value = google_artifact_registry_repository.mlops
}

output "secrets" {
  value = {
    doppler_token = google_secret_manager_secret.doppler_token
    wandb_api_key = google_secret_manager_secret.wandb_api_key
  }
}

output "dataform_repository" {
  description = "google_dataform_repository.main — name is referenced by .github/workflows/deploy-dataform.yml"
  value       = google_dataform_repository.main
}
