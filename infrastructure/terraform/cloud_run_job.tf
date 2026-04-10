# Cloud Run Job — executes the Nexis pipeline asynchronously.
#
# Triggered by POST /api/jobs on the Cloud Run Service. Reads job config from
# env var overrides injected at trigger time (JOB_ID, RESEARCH_PROMPT, etc.).
# Writes results back to Firestore on completion.
#
# The image is initially set to a placeholder; the CI/CD workflow (deploy.yml)
# updates it to the actual image on every push to master.
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
        image = "us-docker.pkg.dev/cloudrun/container/hello"

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
}
