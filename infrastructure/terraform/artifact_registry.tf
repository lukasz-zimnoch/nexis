resource "google_artifact_registry_repository" "ghcr_remote" {
  location      = var.region
  repository_id = "ghcr-remote"
  description   = "GHCR pull-through cache for nexis Docker images"
  format        = "DOCKER"
  mode          = "REMOTE_REPOSITORY"

  remote_repository_config {
    description = "GitHub Container Registry pull-through cache"
    # No credentials needed — GHCR packages are public
    common_repository {
      uri = "https://ghcr.io"
    }
  }

  depends_on = [google_project_service.apis]
}
