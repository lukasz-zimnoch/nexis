#!/usr/bin/env bash
# GCP one-time setup for Nexis Cloud Run deployment.
#
# Prerequisites:
#   - gcloud CLI installed and logged in (gcloud auth login)
#   - Billing account available (gcloud billing accounts list)
#
# Usage:
#   export BILLING_ACCOUNT_ID=<your-billing-account-id>
#   bash scripts/setup-gcp.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-nexis-pipeline}"
REGION="${REGION:-us-central1}"
REPO="${REPO:-lukasz-zimnoch/nexis}"
BILLING_ACCOUNT_ID="${BILLING_ACCOUNT_ID:?Set BILLING_ACCOUNT_ID before running this script}"

# Override ADC quota project so API calls bill against the target project,
# not whatever quota project is baked into Application Default Credentials.
export CLOUDSDK_BILLING_QUOTA_PROJECT="${PROJECT_ID}"

SA_EMAIL="nexis-deploy@${PROJECT_ID}.iam.gserviceaccount.com"

echo "==> [0/7] Environment diagnostics"
echo "    PROJECT_ID: ${PROJECT_ID}"
echo "    CLOUDSDK_BILLING_QUOTA_PROJECT: ${CLOUDSDK_BILLING_QUOTA_PROJECT:-<unset>}"
echo "    gcloud active account: $(gcloud config get-value account 2>/dev/null)"
echo "    gcloud active project: $(gcloud config get-value project 2>/dev/null)"
echo "    gcloud billing/quota_project: $(gcloud config get-value billing/quota_project 2>/dev/null || echo '<unset>')"
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)' 2>/dev/null || echo '<unknown>')
echo "    Target project number: ${PROJECT_NUMBER}"
echo "    ADC quota project (from creds file):"
ADC_FILE="${CLOUDSDK_CONFIG:-$HOME/.config/gcloud}/application_default_credentials.json"
if [[ -f "${ADC_FILE}" ]]; then
  echo "      file: ${ADC_FILE}"
  echo "      quota_project_id: $(python3 -c "import json; print(json.load(open('${ADC_FILE}')).get('quota_project_id', '<not set>'))" 2>/dev/null || echo '<parse error>')"
else
  echo "      ADC file not found at ${ADC_FILE}"
fi
echo ""

echo "==> [1/7] Creating GCP project: ${PROJECT_ID}"
if gcloud projects describe "${PROJECT_ID}" &>/dev/null; then
  echo "    Project already exists, skipping creation."
else
  gcloud projects create "${PROJECT_ID}" --name="Nexis Pipeline"
fi
gcloud config set project "${PROJECT_ID}"

echo "==> [2/7] Linking billing account"
gcloud billing projects link "${PROJECT_ID}" --billing-account="${BILLING_ACCOUNT_ID}"

echo "==> [3/7] Enabling required APIs"
REQUIRED_APIS=(
  run.googleapis.com
  secretmanager.googleapis.com
  iap.googleapis.com
  iam.googleapis.com
  iamcredentials.googleapis.com
  artifactregistry.googleapis.com
)
ENABLED_APIS=$(gcloud services list --enabled --format='value(config.name)' --project="${PROJECT_ID}")
APIS_TO_ENABLE=()
for api in "${REQUIRED_APIS[@]}"; do
  if ! echo "${ENABLED_APIS}" | grep -q "^${api}$"; then
    APIS_TO_ENABLE+=("${api}")
  fi
done
if [[ ${#APIS_TO_ENABLE[@]} -gt 0 ]]; then
  gcloud services enable "${APIS_TO_ENABLE[@]}"
  echo "    Waiting for API activation to propagate..."
  sleep 60
else
  echo "    All required APIs already enabled, skipping."
fi

echo "==> [4/7] Creating Artifact Registry remote repository for GHCR"
AR_REPO="ghcr-remote"
if gcloud artifacts repositories describe "${AR_REPO}" --location="${REGION}" &>/dev/null; then
  echo "    Repository '${AR_REPO}' already exists, skipping creation."
else
  gcloud artifacts repositories create "${AR_REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --mode=remote-repository \
    --remote-repo-config-desc="GHCR pull-through cache" \
    --remote-docker-repo=https://ghcr.io \
    --verbosity=debug || true
fi

echo "==> [5/7] Creating deploy service account: ${SA_EMAIL}"
if gcloud iam service-accounts describe "${SA_EMAIL}" &>/dev/null; then
  echo "    Service account already exists, skipping creation."
else
  gcloud iam service-accounts create nexis-deploy \
    --display-name="Nexis GitHub Actions Deploy"
fi

echo "    Granting roles/run.admin"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/run.admin"

echo "    Granting roles/iam.serviceAccountUser"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/iam.serviceAccountUser"

echo "    Granting roles/artifactregistry.reader"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/artifactregistry.reader"

echo "==> [6/7] Setting up Workload Identity Federation for GitHub Actions"
if gcloud iam workload-identity-pools describe github --location=global &>/dev/null; then
  echo "    Pool 'github' already exists, skipping creation."
else
  gcloud iam workload-identity-pools create "github" \
    --location="global" \
    --display-name="GitHub Actions"
fi

if gcloud iam workload-identity-pools providers describe nexis-repo \
     --location=global --workload-identity-pool=github &>/dev/null; then
  echo "    Provider 'nexis-repo' already exists, skipping creation."
else
  gcloud iam workload-identity-pools providers create-oidc "nexis-repo" \
    --location="global" \
    --workload-identity-pool="github" \
    --display-name="Nexis Repo" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository=='${REPO}'" \
    --issuer-uri="https://token.actions.githubusercontent.com"
fi

PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')

gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/attribute.repository/${REPO}"

echo "==> [7/7] Setup complete. Add these secrets to your GitHub repository:"
echo ""
echo "    GCP_WIF_PROVIDER:"
gcloud iam workload-identity-pools providers describe "nexis-repo" \
  --location="global" \
  --workload-identity-pool="github" \
  --format="value(name)"
echo ""
echo "    GCP_SA_EMAIL: ${SA_EMAIL}"
echo ""
echo "Next steps:"
echo "  1. Add the secrets above to GitHub (Settings → Secrets and variables → Actions)"
echo "  2. Add OPENROUTER_API_KEY, TAVILY_API_KEY, LANGCHAIN_API_KEY secrets"
echo "  3. Make the GHCR package public (Settings → Packages → nexis → Visibility → Public)"
echo "  4. Push to master — the deploy workflow will create the Cloud Run service automatically"
echo "  5. After first deploy, grant IAP access:"
echo "     gcloud beta iap web add-iam-policy-binding \\"
echo "       --resource-type=cloud-run --service=nexis --region=${REGION} \\"
echo "       --member=\"user:your-email@example.com\" --role=\"roles/iap.httpsResourceAccessor\""
echo "  6. Enable IAP via Cloud Console (Security → Identity-Aware Proxy) on first use"
