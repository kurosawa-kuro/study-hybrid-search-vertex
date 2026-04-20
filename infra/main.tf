# =========================================================================
# Root module — orchestrates sub-modules with clear boundary:
#   iam        → Service Accounts / WIF / project-level role bindings
#   data       → BigQuery / GCS / Artifact Registry / Secret Manager + data IAM
#   runtime    → Cloud Run Service & Job / Pub/Sub / Scheduler / Eventarc + invoker IAM
#   meilisearch→ Cloud Run Service (BM25 lexical retrieval) + GCS FUSE data mount
#   monitoring → log-based metrics / alert policies / mean-drift Scheduled Query
#
# Shared preconditions (API enablement) live in apis.tf and are enforced via
# `depends_on = [google_project_service.enabled]` on each module call.
# =========================================================================

module "iam" {
  source = "./modules/iam"

  project_id  = var.project_id
  github_repo = var.github_repo

  depends_on = [google_project_service.enabled]
}

module "data" {
  source = "./modules/data"

  project_id                        = var.project_id
  region                            = var.region
  artifact_repo_id                  = var.artifact_repo_id
  models_bucket_name                = var.models_bucket_name
  artifacts_bucket_name             = var.artifacts_bucket_name
  service_accounts                  = module.iam.service_accounts
  github_repo                       = var.github_repo
  dataform_repository_id            = var.dataform_repository_id
  dataform_git_token_secret_version = var.dataform_git_token_secret_version
  # Deterministic form (not module.iam.github_deployer_sa_email) so the data
  # module's `count = ... != "" ? 1 : 0` can be evaluated at plan time. The SA
  # is still created by module.iam; ordering is preserved via the
  # `service_accounts` reference above, which establishes an implicit dep.
  github_deployer_sa_email   = "sa-github-deployer@${var.project_id}.iam.gserviceaccount.com"
  enable_deletion_protection = var.enable_deletion_protection

  depends_on = [google_project_service.enabled]
}

module "runtime" {
  source = "./modules/runtime"

  project_id              = var.project_id
  region                  = var.region
  artifact_repo_id        = var.artifact_repo_id
  models_bucket_name      = module.data.models_bucket.name
  mlops_dataset_id        = module.data.mlops_dataset.dataset_id
  feature_mart_dataset_id = module.data.feature_mart_dataset.dataset_id
  ranking_log_table_id    = module.data.ranking_log_table.table_id
  feedback_events_table_id = module.data.feedback_events_table.table_id
  service_accounts        = module.iam.service_accounts
  meili_base_url          = module.meilisearch.meili_base_url
  search_cache_ttl_seconds = var.search_cache_ttl_seconds

  depends_on = [
    google_project_service.enabled,
    module.data,
    module.meilisearch,
  ]
}

module "meilisearch" {
  source = "./modules/meilisearch"

  project_id            = var.project_id
  region                = var.region
  service_accounts      = module.iam.service_accounts
  meili_data_bucket_name = var.meili_data_bucket_name

  depends_on = [google_project_service.enabled]
}

module "monitoring" {
  source = "./modules/monitoring"

  project_id           = var.project_id
  region               = var.region
  mlops_dataset_id     = module.data.mlops_dataset.dataset_id
  ranker_skew_sql_path = "${path.root}/../monitoring/validate_feature_skew.sql"
  oncall_email         = var.oncall_email
  service_accounts     = module.iam.service_accounts

  depends_on = [
    google_project_service.enabled,
    module.data,
  ]
}
