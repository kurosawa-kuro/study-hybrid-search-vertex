# On first apply, Artifact Registry is empty and the search-api image may not
# exist yet. Cloud Run rejects creation if the referenced image does not exist,
# so we seed with the canonical hello-world image and rely on
# `lifecycle.ignore_changes = [... image ...]` to let later deploy flows roll
# the real image in without Terraform reverting it.
locals {
  image_placeholder = "gcr.io/cloudrun/hello"
}

data "google_project" "current" {}

# =========================================================================
# Cloud Run Service — search-api (FastAPI hybrid search + retrain endpoints)
# =========================================================================

resource "google_cloud_run_v2_service" "search_api" {
  name     = "search-api"
  location = var.region

  template {
    service_account                  = var.service_accounts.api.email
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    max_instance_request_concurrency = 80
    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }
    containers {
      image = local.image_placeholder
      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        cpu_idle          = false
        startup_cpu_boost = true
      }
      ports {
        container_port = 8080
      }
      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCS_MODELS_BUCKET"
        value = var.models_bucket_name
      }
      env {
        name  = "RANKING_LOG_TOPIC"
        value = google_pubsub_topic.ranking_log.name
      }
      env {
        name  = "FEEDBACK_TOPIC"
        value = google_pubsub_topic.search_feedback.name
      }
      env {
        name  = "RETRAIN_TOPIC"
        value = google_pubsub_topic.retrain_trigger.name
      }
      env {
        name  = "MEILI_BASE_URL"
        value = var.meili_base_url
      }
      env {
        name  = "SEARCH_CACHE_TTL_SECONDS"
        value = tostring(var.search_cache_ttl_seconds)
      }
      env {
        name  = "ENABLE_SEARCH"
        value = var.vertex_encoder_endpoint_id != "" ? "true" : "false"
      }
      env {
        name  = "ENABLE_RERANK"
        value = var.vertex_reranker_endpoint_id != "" ? "true" : "false"
      }
      env {
        name  = "VERTEX_LOCATION"
        value = var.vertex_location
      }
      env {
        name  = "VERTEX_ENCODER_ENDPOINT_ID"
        value = var.vertex_encoder_endpoint_id
      }
      env {
        name  = "VERTEX_RERANKER_ENDPOINT_ID"
        value = var.vertex_reranker_endpoint_id
      }
      env {
        name  = "VERTEX_PREDICT_TIMEOUT_SECONDS"
        value = "30.0"
      }
    }
  }

  # CI / `make deploy-api-local` redeploy the image and env via `gcloud run deploy`.
  # Terraform sets the initial revision (placeholder image + baseline env), then
  # stays out of the way. `env` is explicitly ignored so a subsequent
  # `gcloud run services update --update-env-vars="ENABLE_SEARCH=true,..."`
  # (STEP 17 enablement) is not clobbered by the next `terraform apply`.
  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      template[0].containers[0].env,
      client,
      client_version,
    ]
  }
}

# ----- Invoker IAM: only explicit identities can invoke search-api -----

resource "google_cloud_run_v2_service_iam_member" "api_scheduler_invoker" {
  name     = google_cloud_run_v2_service.search_api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.service_accounts.scheduler.email}"
}

# =========================================================================
# Pub/Sub — ranking_log + search_feedback sinks + retrain trigger
#
# Phase 10c removed: ``predictions`` topic + ``predictions-to-bq`` subscription
# (California regressor sink). Operators on an existing project must run:
#
#   gcloud pubsub subscriptions delete predictions-to-bq
#   gcloud pubsub topics        delete predictions
#
# *before* the next `terraform apply`. See ``docs/04_運用.md §3.9`` for the
# full two-phase apply checklist.
# =========================================================================

resource "google_pubsub_topic" "ranking_log" {
  name = "ranking-log"
}

resource "google_pubsub_topic" "search_feedback" {
  name = "search-feedback"
}

resource "google_pubsub_topic" "retrain_trigger" {
  name = "retrain-trigger"
}

# Publisher grants
resource "google_pubsub_topic_iam_member" "api_publish_ranking_log" {
  topic  = google_pubsub_topic.ranking_log.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${var.service_accounts.api.email}"
}

resource "google_pubsub_topic_iam_member" "api_publish_feedback" {
  topic  = google_pubsub_topic.search_feedback.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${var.service_accounts.api.email}"
}

resource "google_pubsub_topic_iam_member" "api_publish_retrain" {
  topic  = google_pubsub_topic.retrain_trigger.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${var.service_accounts.api.email}"
}

resource "google_pubsub_topic_iam_member" "scheduler_publish_retrain" {
  topic  = google_pubsub_topic.retrain_trigger.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${var.service_accounts.scheduler.email}"
}

# Pub/Sub → BQ Subscriptions (no subscriber code)
resource "google_pubsub_subscription" "ranking_log_to_bq" {
  name  = "ranking-log-to-bq"
  topic = google_pubsub_topic.ranking_log.name

  bigquery_config {
    table               = "${var.project_id}.${var.mlops_dataset_id}.${var.ranking_log_table_id}"
    use_table_schema    = true
    drop_unknown_fields = true
    write_metadata      = false
  }

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s" # 7 days

  depends_on = [
    google_project_iam_member.pubsub_bq_writer,
    google_project_iam_member.pubsub_bq_metadata_viewer,
  ]
}

resource "google_pubsub_subscription" "search_feedback_to_bq" {
  name  = "search-feedback-to-bq"
  topic = google_pubsub_topic.search_feedback.name

  bigquery_config {
    table               = "${var.project_id}.${var.mlops_dataset_id}.${var.feedback_events_table_id}"
    use_table_schema    = true
    drop_unknown_fields = true
    write_metadata      = false
  }

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"

  depends_on = [
    google_project_iam_member.pubsub_bq_writer,
    google_project_iam_member.pubsub_bq_metadata_viewer,
  ]
}

# Pub/Sub service agent needs BQ writer on the sink tables
locals {
  pubsub_service_agent = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "pubsub_bq_writer" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = local.pubsub_service_agent
}

resource "google_project_iam_member" "pubsub_bq_metadata_viewer" {
  project = var.project_id
  role    = "roles/bigquery.metadataViewer"
  member  = local.pubsub_service_agent
}

# =========================================================================
# Cloud Scheduler — retrain orchestration entrypoint
# =========================================================================

resource "google_cloud_scheduler_job" "check_retrain_daily" {
  name        = "check-retrain-daily"
  description = "POST /jobs/check-retrain on search-api once a day (04:00 JST)"
  schedule    = "0 4 * * *"
  time_zone   = "Asia/Tokyo"
  region      = var.region

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.search_api.uri}/jobs/check-retrain"

    oidc_token {
      service_account_email = var.service_accounts.scheduler.email
      audience              = google_cloud_run_v2_service.search_api.uri
    }
  }

  retry_config {
    retry_count          = 1
    max_retry_duration   = "120s"
    min_backoff_duration = "30s"
  }

  depends_on = [
    google_cloud_run_v2_service_iam_member.api_scheduler_invoker,
  ]
}
