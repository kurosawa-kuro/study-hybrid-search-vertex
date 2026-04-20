locals {
  # Feature Group parity invariant:
  # - common/src/common/schema/feature_schema.py::FEATURE_COLS_RANKER (property-side 7 cols)
  # - monitoring/validate_feature_skew.sql UNPIVOT lists
  # - tests/parity/test_feature_parity_feature_group.py
  #
  # Query-time signals (me5_score / lexical_rank / semantic_rank) are excluded.
  feature_group_property_features = [
    {
      name        = "rent"
      value_type  = "DOUBLE"
      description = "Monthly rent"
    },
    {
      name        = "walk_min"
      value_type  = "DOUBLE"
      description = "Walking minutes to nearest station"
    },
    {
      name        = "age_years"
      value_type  = "DOUBLE"
      description = "Property age in years"
    },
    {
      name        = "area_m2"
      value_type  = "DOUBLE"
      description = "Floor area in square meters"
    },
    {
      name        = "ctr"
      value_type  = "DOUBLE"
      description = "Historical click-through rate"
    },
    {
      name        = "fav_rate"
      value_type  = "DOUBLE"
      description = "Historical favorite rate"
    },
    {
      name        = "inquiry_rate"
      value_type  = "DOUBLE"
      description = "Historical inquiry conversion rate"
    },
  ]

  encoder_endpoint_name = (
    var.encoder_endpoint_id != ""
    ? var.encoder_endpoint_id
    : "projects/${var.project_id}/locations/${var.vertex_location}/endpoints/${var.encoder_endpoint_display_name}"
  )
  reranker_endpoint_name = (
    var.reranker_endpoint_id != ""
    ? var.reranker_endpoint_id
    : "projects/${var.project_id}/locations/${var.vertex_location}/endpoints/${var.reranker_endpoint_display_name}"
  )
  pipeline_trigger_function_name = "pipeline-trigger"
  pipeline_trigger_eventarc_name = "retrain-to-pipeline"
  pubsub_service_agent = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_pubsub_topic" "model_monitoring_alerts" {
  name = "model-monitoring-alerts"
}

resource "google_bigquery_dataset_iam_member" "pubsub_mlops_editor" {
  dataset_id = var.mlops_dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = local.pubsub_service_agent
}

resource "google_bigquery_dataset_iam_member" "pubsub_mlops_metadata_viewer" {
  dataset_id = var.mlops_dataset_id
  role       = "roles/bigquery.metadataViewer"
  member     = local.pubsub_service_agent
}

resource "google_pubsub_subscription" "monitoring_alerts_to_bq" {
  name  = "monitoring-alerts-to-bq"
  topic = google_pubsub_topic.model_monitoring_alerts.name

  bigquery_config {
    table               = "${var.project_id}.${var.mlops_dataset_id}.${var.model_monitoring_alerts_table_id}"
    use_table_schema    = true
    drop_unknown_fields = true
    write_metadata      = false
  }

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"

  depends_on = [
    google_bigquery_dataset_iam_member.pubsub_mlops_editor,
    google_bigquery_dataset_iam_member.pubsub_mlops_metadata_viewer,
  ]
}
