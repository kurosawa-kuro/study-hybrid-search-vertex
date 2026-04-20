locals {
  required_apis = [
    "bigquery.googleapis.com",
    "bigquerystorage.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "aiplatform.googleapis.com",
    "dataform.googleapis.com",
    "pubsub.googleapis.com",
    "cloudscheduler.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "eventarc.googleapis.com",
    "cloudfunctions.googleapis.com",
    "cloudbuild.googleapis.com",
    "notebooks.googleapis.com",
  ]
}

resource "google_project_service" "enabled" {
  for_each           = toset(local.required_apis)
  service            = each.value
  disable_on_destroy = false
}
