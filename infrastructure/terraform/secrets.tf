# Secret Manager secrets — shells only. Values must be populated manually after
# `terraform apply` before the Cloud Run service and job can start:
#
#   echo -n 'YOUR_KEY' | gcloud secrets versions add openrouter-api-key --data-file=-
#   echo -n 'YOUR_KEY' | gcloud secrets versions add tavily-api-key --data-file=-
#   echo -n 'YOUR_KEY' | gcloud secrets versions add langchain-api-key --data-file=-
#
# The placeholder version created by Terraform is ignored once you add a real one
# (Cloud Run always resolves `latest` to the highest active version).

resource "google_secret_manager_secret" "openrouter_api_key" {
  secret_id = "openrouter-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "openrouter_api_key_placeholder" {
  secret      = google_secret_manager_secret.openrouter_api_key.id
  secret_data = "CHANGEME"

  lifecycle {
    # Never overwrite a real secret value that was set outside Terraform
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret" "tavily_api_key" {
  secret_id = "tavily-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "tavily_api_key_placeholder" {
  secret      = google_secret_manager_secret.tavily_api_key.id
  secret_data = "CHANGEME"

  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret" "langchain_api_key" {
  secret_id = "langchain-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "langchain_api_key_placeholder" {
  secret      = google_secret_manager_secret.langchain_api_key.id
  secret_data = "CHANGEME"

  lifecycle {
    ignore_changes = [secret_data]
  }
}
