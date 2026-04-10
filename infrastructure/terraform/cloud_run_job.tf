resource "google_cloud_run_v2_job" "nexis" {
  name     = "nexis-job"
  location = var.region

  deletion_protection = false

  template {
    # TaskTemplate — one task per job execution, no retries (pipeline is not idempotent)
    template {
      service_account = google_service_account.nexis_runtime.email
      max_retries     = 0
      timeout         = "1800s"

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/ghcr-remote/lukasz-zimnoch/nexis:latest"

        # Override CMD to run the job runner instead of the API server
        command = ["uv", "run", "python", "-m", "nexis.job_runner"]

        resources {
          limits = {
            memory = "2Gi"
            cpu    = "1"
          }
        }

        # Non-sensitive environment variables (job-specific vars are injected at
        # trigger time as overrides by job_trigger.py)
        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "GCP_REGION"
          value = var.region
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
  }

  depends_on = [
    google_project_service.apis,
    google_project_iam_member.runtime_secret_accessor,
    google_secret_manager_secret_version.openrouter_api_key_placeholder,
    google_secret_manager_secret_version.tavily_api_key_placeholder,
    google_secret_manager_secret_version.langchain_api_key_placeholder,
  ]

  # CI/CD updates the image on every push via `gcloud run jobs update --image`.
  # Ignore only the image field so Terraform still owns env vars, resources,
  # secrets, command, max_retries, timeout, and the service account — in
  # particular the `command` override that distinguishes the Job from the
  # Service image.
  lifecycle {
    ignore_changes = [
      client,
      client_version,
      template[0].template[0].containers[0].image,
    ]
  }
}
