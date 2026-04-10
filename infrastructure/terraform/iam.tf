# ---------------------------------------------------------------------------
# Service accounts
# ---------------------------------------------------------------------------

resource "google_service_account" "nexis_deploy" {
  account_id   = "nexis-deploy"
  display_name = "Nexis GitHub Actions Deploy"
}

resource "google_service_account" "nexis_runtime" {
  account_id   = "nexis-runtime"
  display_name = "Nexis Cloud Run Runtime"
}

# ---------------------------------------------------------------------------
# Deploy SA roles — used by GitHub Actions CI/CD
# ---------------------------------------------------------------------------

resource "google_project_iam_member" "deploy_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.nexis_deploy.email}"
}

resource "google_project_iam_member" "deploy_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.nexis_deploy.email}"
}

resource "google_project_iam_member" "deploy_ar_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.nexis_deploy.email}"
}

# ---------------------------------------------------------------------------
# Runtime SA roles — used by Cloud Run Service and Job at runtime
# ---------------------------------------------------------------------------

resource "google_project_iam_member" "runtime_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.nexis_runtime.email}"
}

resource "google_project_iam_member" "runtime_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.nexis_runtime.email}"
}

# Allows the Cloud Run Service (running as nexis-runtime) to trigger Cloud Run Jobs
resource "google_project_iam_member" "runtime_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.nexis_runtime.email}"
}

# ---------------------------------------------------------------------------
# Workload Identity Federation — keyless GitHub Actions authentication
# ---------------------------------------------------------------------------

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "nexis_repo" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "nexis-repo"
  display_name                       = "Nexis Repo"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }

  # Restrict to the specific repository — any other repo cannot impersonate the SA
  attribute_condition = "attribute.repository == '${var.github_repo}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Allow GitHub Actions workflows from the nexis repo to impersonate the deploy SA
resource "google_service_account_iam_member" "wif_deploy" {
  service_account_id = google_service_account.nexis_deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}
