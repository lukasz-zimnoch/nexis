terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 7.0"
    }
  }

  # GCS backend — create the bucket manually before running `terraform init`:
  #   gcloud storage buckets create gs://nexis-pipeline-tfstate \
  #     --project=nexis-pipeline --location=us-central1 \
  #     --uniform-bucket-level-access
  backend "gcs" {
    bucket = "nexis-pipeline-tfstate"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

data "google_project" "project" {}
