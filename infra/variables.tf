variable "project_id" {
  type    = string
  default = "mlops-dev-a"
}

variable "region" {
  type    = string
  default = "asia-northeast1"
}

variable "artifact_repo_id" {
  type    = string
  default = "mlops"
}

variable "models_bucket_name" {
  type    = string
  default = "mlops-dev-a-models"
}

variable "pipeline_root_bucket_name" {
  description = "GCS bucket name for Vertex AI pipeline root artifacts and compiled templates"
  type        = string
  default     = "mlops-dev-a-pipeline-root"
}

variable "meili_data_bucket_name" {
  description = "GCS bucket name mounted by meili-search"
  type        = string
  default     = "mlops-dev-a-meili-data"
}

variable "artifacts_bucket_name" {
  type    = string
  default = "mlops-dev-a-artifacts"
}

variable "github_repo" {
  description = "GitHub repository (owner/name) trusted by Workload Identity Federation + used for Dataform git_remote_settings"
  type        = string
  default     = "your-org/study-gcp-mlops-bq-first"
}

variable "dataform_repository_id" {
  description = "Dataform repository name. Must match .github/workflows/deploy-dataform.yml env.REPOSITORY"
  type        = string
  default     = "bq-first"
}

variable "dataform_git_token_secret_version" {
  description = "Secret Manager resource ID for the GitHub PAT Dataform uses to sync definitions/. Empty = no remote sync (use Dataform UI or CI-driven compilationResults only)"
  type        = string
  default     = ""
}

variable "oncall_email" {
  description = "Email notified by log-based alert policies. Required — must be supplied via -var='oncall_email=...' or tfvars at apply time. No default is provided on purpose (avoid shipping placeholder addresses)."
  type        = string

  validation {
    condition     = length(var.oncall_email) > 0 && can(regex("@", var.oncall_email))
    error_message = "oncall_email must be a non-empty address containing '@'."
  }
}

variable "enable_deletion_protection" {
  description = "Toggle BQ table deletion_protection across the data module. Default true (production-safe). `make destroy-all` runs `terraform apply -var=enable_deletion_protection=false` first so the subsequent destroy can proceed (Terraform refuses to destroy a table whose state still says deletion_protection=true)."
  type        = bool
  default     = true
}

variable "search_cache_ttl_seconds" {
  description = "Default /search cache TTL seconds passed to search-api"
  type        = number
  default     = 120
}

variable "vertex_location" {
  description = "Vertex AI location for endpoint calls"
  type        = string
  default     = "asia-northeast1"
}

variable "vertex_encoder_endpoint_id" {
  description = "Vertex AI encoder endpoint ID or full resource name"
  type        = string
  default     = ""
}

variable "vertex_reranker_endpoint_id" {
  description = "Vertex AI reranker endpoint ID or full resource name"
  type        = string
  default     = ""
}
