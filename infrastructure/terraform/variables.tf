variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "nexis-ai"
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

variable "firebase_api_key" {
  description = "Firebase Web SDK apiKey from the Firebase Console Web App registration; served to the SPA by the backend's /config.json endpoint"
  type        = string
}

variable "firebase_auth_domain" {
  description = "Firebase Web SDK authDomain; defaults to ${project_id}.firebaseapp.com when left empty"
  type        = string
  default     = ""
}
