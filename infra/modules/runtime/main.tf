# On first apply, Artifact Registry is empty — search-api / training-job images
# have not been built yet (CI pushes them via deploy-api.yml / deploy-training-job.yml
# after Terraform creates the registry + SAs). Cloud Run rejects creation if the
# referenced image does not exist, so we seed with the canonical hello-world image
# and rely on `lifecycle.ignore_changes = [... image ...]` to let CI roll the real
# image in afterwards without Terraform reverting it.
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
        # memory bumped from 2Gi to 4Gi in Phase 6 to accommodate the
        # multilingual-e5-base encoder (~1.1GB) loaded in lifespan + LightGBM
        # booster (~50MB) + Python runtime overhead. Keep this in lockstep with
        # deploy-api.yml's `--memory` flag and CLAUDE.md non-negotiables.
        limits = {
          cpu    = "2"
          memory = "4Gi"
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

# =========================================================================
# Cloud Run Jobs — training-job (LightGBM LambdaRank trainer CLI)
# =========================================================================

resource "google_cloud_run_v2_job" "training_job" {
  name     = "training-job"
  location = var.region

  template {
    task_count = 1
    template {
      service_account = var.service_accounts.job_train.email
      timeout         = "1800s"
      max_retries     = 1
      containers {
        image = local.image_placeholder
        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
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
          name  = "BQ_DATASET_FEATURE_MART"
          value = var.feature_mart_dataset_id
        }
        env {
          name  = "BQ_DATASET_MLOPS"
          value = var.mlops_dataset_id
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      template[0].template[0].containers[0].env,
      client,
      client_version,
    ]
  }
}

# =========================================================================
# Cloud Run Jobs — embedding-job (multilingual-e5-base batch encoder)
#
# Consumes raw.properties / feature_mart.properties_cleaned and writes
# feature_mart.property_embeddings (768d vectors). Runs on `sa-job-embed`
# so the IAM blast radius excludes `mlops.*` writes. Invoked via
# `gcloud run jobs execute embedding-job --wait` (see docs/04_運用.md
# STEP 15).
# =========================================================================

resource "google_cloud_run_v2_job" "embedding_job" {
  name     = "embedding-job"
  location = var.region

  template {
    task_count = 1
    template {
      service_account = var.service_accounts.job_embed.email
      timeout         = "1800s"
      max_retries     = 1
      containers {
        image   = local.image_placeholder
        command = ["embed"]
        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
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
          name  = "BQ_DATASET_FEATURE_MART"
          value = var.feature_mart_dataset_id
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      template[0].template[0].containers[0].env,
      client,
      client_version,
    ]
  }
}

# ----- Invoker IAM: only explicit identities can invoke search-api / training-job -----

resource "google_cloud_run_v2_service_iam_member" "api_scheduler_invoker" {
  name     = google_cloud_run_v2_service.search_api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.service_accounts.scheduler.email}"
}

resource "google_cloud_run_v2_job_iam_member" "trigger_invoker" {
  name     = google_cloud_run_v2_job.training_job.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.service_accounts.scheduler.email}"
}

# search-api's /events/retrain calls run_v2.JobsClient.run_job() with its own identity (sa-api).
resource "google_cloud_run_v2_job_iam_member" "api_invoker" {
  name     = google_cloud_run_v2_job.training_job.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.service_accounts.api.email}"
}

# embedding-job is invoked by Cloud Scheduler (daily 03:30 JST per §2.1
# in docs/04_運用.md) and by operators running `gcloud run jobs execute`.
# Only sa-scheduler gets invoker — operators use ADC.
resource "google_cloud_run_v2_job_iam_member" "embedding_scheduler_invoker" {
  name     = google_cloud_run_v2_job.embedding_job.name
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
# Cloud Scheduler + Eventarc — retrain orchestration
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

# Eventarc: Pub/Sub retrain-trigger → Cloud Run Jobs execute
resource "google_eventarc_trigger" "retrain_trigger" {
  name     = "retrain-trigger"
  location = var.region

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.pubsub.topic.v1.messagePublished"
  }

  transport {
    pubsub {
      topic = google_pubsub_topic.retrain_trigger.id
    }
  }

  destination {
    cloud_run_service {
      # Eventarc v1 requires a Cloud Run Service target. For a Job, use Workflows
      # or a thin /jobs/run proxy. We drop it onto search-api with path /events/retrain,
      # which then calls Cloud Run Jobs `training-job`.
      service = google_cloud_run_v2_service.search_api.name
      region  = var.region
      path    = "/events/retrain"
    }
  }

  service_account = var.service_accounts.scheduler.email
}
