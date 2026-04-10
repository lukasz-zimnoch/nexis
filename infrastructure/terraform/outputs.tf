output "service_url" {
  description = "Cloud Run service URL (set as GCP_SERVICE_URL in GitHub Actions if needed)"
  value       = google_cloud_run_v2_service.nexis.uri
}

output "deploy_sa_email" {
  description = "Deploy service account email — set as GCP_SA_EMAIL in GitHub Actions secrets"
  value       = google_service_account.nexis_deploy.email
}

output "wif_provider" {
  description = "Workload Identity Federation provider resource name — set as GCP_WIF_PROVIDER in GitHub Actions secrets"
  value       = google_iam_workload_identity_pool_provider.nexis_repo.name
}
