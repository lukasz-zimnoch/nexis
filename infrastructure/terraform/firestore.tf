# If Firestore was already created in the project (e.g., via the GCP Console),
# import it before applying:
#   terraform import google_firestore_database.nexis 'nexis-pipeline/(default)'
resource "google_firestore_database" "nexis" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  # Prevent accidental data loss — abandon the DB resource on `terraform destroy`
  # instead of deleting it.
  delete_protection_state = "DELETE_PROTECTION_ENABLED"
  deletion_policy         = "ABANDON"

  depends_on = [google_project_service.apis]
}

# Composite index for listing a user's jobs sorted by creation time (used by
# GET /api/jobs which queries: WHERE user_id == X ORDER BY created_at DESC).
resource "google_firestore_index" "jobs_by_user_created" {
  project    = var.project_id
  database   = google_firestore_database.nexis.name
  collection = "jobs"

  fields {
    field_path = "user_id"
    order      = "ASCENDING"
  }

  fields {
    field_path = "created_at"
    order      = "DESCENDING"
  }
}
