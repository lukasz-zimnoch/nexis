# Marks the GCP project as Firebase-enabled so the Firebase Admin SDK (used in
# src/nexis/auth.py) and the Firebase JS SDK (frontend) can talk to it.
#
# `google_firebase_project` is only available in the `google-beta` provider.
# The operation is idempotent — applying against a project that is already
# Firebase-enabled is a no-op.
#
# Manual bootstrap step: email/password sign-in must be enabled once in the
# Firebase Console (https://console.firebase.google.com/):
#   Authentication → Sign-in method → Email/Password → Enable → Save
#
# The Terraform provider does not currently expose a resource for configuring
# Firebase Auth sign-in methods on the Spark (free) plan without upgrading to
# Identity Platform (which requires Blaze billing). User accounts must also be
# created manually from the same console — by design for this closed tool.
resource "google_firebase_project" "nexis" {
  provider = google-beta
  project  = var.project_id

  depends_on = [google_project_service.apis]
}
