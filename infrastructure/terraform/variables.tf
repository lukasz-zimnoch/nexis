variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "nexis-pipeline"
}

variable "region" {
  description = "GCP region for Cloud Run, Artifact Registry, and Firestore"
  type        = string
  default     = "us-central1"
}

variable "github_repo" {
  description = "GitHub repository in the format owner/repo (used for Workload Identity Federation)"
  type        = string
  default     = "lukasz-zimnoch/nexis"
}

variable "billing_account_id" {
  description = "GCP billing account ID (required only if creating a new project; existing projects are not managed here)"
  type        = string
  default     = ""
}
