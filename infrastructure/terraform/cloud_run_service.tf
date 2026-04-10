resource "google_cloud_run_v2_service" "nexis" {
  name     = "nexis"
  location = var.region

  # Allow unauthenticated access — auth is handled at the app level via Firebase Auth.
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.nexis_runtime.email

    # 5-minute timeout is sufficient for the API; the pipeline runs on Cloud Run Job.
    timeout = "300s"

    # Per-revision autoscaling (RevisionScaling in the Cloud Run v2 API). The
    # top-level `scaling` block is reserved for service-wide manual scaling.
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/ghcr-remote/lukasz-zimnoch/nexis:latest"

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          memory = "2Gi"
          cpu    = "1"
        }
      }

      # Non-sensitive environment variables
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "FIREBASE_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "GCP_REGION"
        value = var.region
      }

      env {
        name  = "CLOUD_RUN_JOB_NAME"
        value = "nexis-job"
      }

      env {
        name  = "LANGCHAIN_TRACING_V2"
        value = "false"
      }

      env {
        name  = "LANGCHAIN_PROJECT"
        value = "nexis"
      }

      # API keys injected from Secret Manager
      env {
        name = "OPENROUTER_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.openrouter_api_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "TAVILY_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.tavily_api_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "LANGCHAIN_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.langchain_api_key.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.apis,
    google_project_iam_member.runtime_secret_accessor,
    google_secret_manager_secret_version.openrouter_api_key_placeholder,
    google_secret_manager_secret_version.tavily_api_key_placeholder,
    google_secret_manager_secret_version.langchain_api_key_placeholder,
  ]

  # CI/CD updates the image on every push via `deploy-cloudrun@v2`. Ignore only
  # the image and revision metadata fields the action touches so Terraform still
  # owns env vars, scaling, resources, secrets, and the service account.
  lifecycle {
    ignore_changes = [
      client,
      client_version,
      template[0].revision,
      template[0].containers[0].image,
    ]
  }
}

# Allow unauthenticated invocations — public access is required for the SPA and API.
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  name     = google_cloud_run_v2_service.nexis.name
  location = google_cloud_run_v2_service.nexis.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
