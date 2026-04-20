# ----- Runtime Service Accounts (5 SA 分離) -----

resource "google_service_account" "api" {
  account_id   = "sa-api"
  display_name = "Cloud Run Service (FastAPI) runtime SA"
}

resource "google_service_account" "job_train" {
  account_id   = "sa-job-train"
  display_name = "Cloud Run Jobs (LightGBM LambdaRank training) runtime SA"
}

resource "google_service_account" "job_embed" {
  account_id   = "sa-job-embed"
  display_name = "Cloud Run Jobs (multilingual-e5 embedding batch) runtime SA"
}

resource "google_service_account" "dataform" {
  account_id   = "sa-dataform"
  display_name = "Dataform service SA (feature mart writer)"
}

resource "google_service_account" "scheduler" {
  account_id   = "sa-scheduler"
  display_name = "Cloud Scheduler SA (invoke API / publish retrain trigger)"
}

# ----- Workload Identity Federation for GitHub Actions -----

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  attribute_condition = "assertion.repository == \"${var.github_repo}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "github_deployer" {
  account_id   = "sa-github-deployer"
  display_name = "GitHub Actions deployer (via WIF)"
}

resource "google_service_account_iam_member" "github_wif_binding" {
  service_account_id = google_service_account.github_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

# Deployer needs enough power to run terraform apply + gcloud deploys.
# Keep it a single role for this PoC; tighten later.
resource "google_project_iam_member" "github_deployer_editor" {
  project = var.project_id
  role    = "roles/editor"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_project_iam_member" "github_deployer_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

# ----- Project-level IAM for runtime SAs -----

resource "google_project_iam_member" "api_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "train_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.job_train.email}"
}

resource "google_project_iam_member" "train_bq_read_session" {
  project = var.project_id
  role    = "roles/bigquery.readSessionUser"
  member  = "serviceAccount:${google_service_account.job_train.email}"
}

resource "google_project_iam_member" "embed_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.job_embed.email}"
}

resource "google_project_iam_member" "embed_bq_read_session" {
  project = var.project_id
  role    = "roles/bigquery.readSessionUser"
  member  = "serviceAccount:${google_service_account.job_embed.email}"
}

resource "google_project_iam_member" "dataform_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.dataform.email}"
}

# sa-scheduler must be able to start the training job (called from /events/retrain
# which runs on search-api = sa-api). Kept here for locality with other project IAM.
resource "google_project_iam_member" "scheduler_run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.scheduler.email}"
}
