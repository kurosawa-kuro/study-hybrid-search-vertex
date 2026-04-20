variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository (owner/name) trusted by Workload Identity Federation"
  type        = string
}
