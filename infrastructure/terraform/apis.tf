locals {
  required_apis = toset([
    # Existing APIs (previously enabled via setup-gcp.sh)
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "artifactregistry.googleapis.com",
    # New APIs for Firebase Auth, Firestore, and resource management
    "firestore.googleapis.com",
    "firebase.googleapis.com",
    "identitytoolkit.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ])
}

resource "google_project_service" "apis" {
  for_each = local.required_apis

  project = var.project_id
  service = each.value

  # Do not disable the API when the resource is destroyed — other resources may
  # depend on it and disabling APIs requires a 30-day waiting period.
  disable_on_destroy = false
}
