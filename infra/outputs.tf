output "project_id" {
  value = var.project_id
}

output "region" {
  value = var.region
}

output "models_bucket" {
  value = module.data.models_bucket.name
}

output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${module.data.artifact_registry.repository_id}"
}

output "training_runs_table" {
  value = "${var.project_id}.${module.data.mlops_dataset.dataset_id}.${module.data.training_runs_table.table_id}"
}

output "ranking_log_table" {
  value = "${var.project_id}.${module.data.mlops_dataset.dataset_id}.${module.data.ranking_log_table.table_id}"
}

output "feedback_events_table" {
  value = "${var.project_id}.${module.data.mlops_dataset.dataset_id}.${module.data.feedback_events_table.table_id}"
}

output "ranking_log_topic" {
  value = module.runtime.ranking_log_topic.name
}

output "search_feedback_topic" {
  value = module.runtime.search_feedback_topic.name
}

output "retrain_trigger_topic" {
  value = module.runtime.retrain_trigger_topic.name
}

output "service_accounts" {
  value = {
    api       = module.iam.service_accounts.api.email
    job_train = module.iam.service_accounts.job_train.email
    job_embed = module.iam.service_accounts.job_embed.email
    dataform  = module.iam.service_accounts.dataform.email
    scheduler = module.iam.service_accounts.scheduler.email
  }
}

output "workload_identity_provider" {
  description = "Register as GitHub Actions var WORKLOAD_IDENTITY_PROVIDER"
  value       = module.iam.workload_identity_provider
}

output "github_deployer_sa_email" {
  description = "Register as GitHub Actions var DEPLOYER_SERVICE_ACCOUNT"
  value       = module.iam.github_deployer_sa_email
}

output "dataform_repository_name" {
  description = "Dataform repository name — matches env.REPOSITORY in .github/workflows/deploy-dataform.yml"
  value       = module.data.dataform_repository.name
}

output "meili_base_url" {
  description = "Cloud Run URL of meili-search service"
  value       = module.meilisearch.meili_base_url
}

output "meili_data_bucket" {
  description = "GCS bucket mounted by meili-search"
  value       = module.meilisearch.meili_data_bucket.name
}
