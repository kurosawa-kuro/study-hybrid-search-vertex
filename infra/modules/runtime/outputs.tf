output "api_service" {
  value = google_cloud_run_v2_service.search_api
}

output "training_job" {
  value = google_cloud_run_v2_job.training_job
}

output "ranking_log_topic" {
  value = google_pubsub_topic.ranking_log
}

output "search_feedback_topic" {
  value = google_pubsub_topic.search_feedback
}

output "retrain_trigger_topic" {
  value = google_pubsub_topic.retrain_trigger
}
