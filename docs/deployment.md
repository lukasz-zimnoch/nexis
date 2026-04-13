# Deployment

Nexis runs on [Google Cloud Run](https://cloud.google.com/run) with asynchronous pipeline execution via Cloud Run Jobs. Infrastructure is managed declaratively with [Terraform](https://www.terraform.io/), and authentication is handled by [Firebase Auth](https://firebase.google.com/products/auth).

Relevant ADRs:
- [ADR-0012](adr/0012-terraform-infrastructure-management.md) — Terraform for infrastructure
- [ADR-0013](adr/0013-cloud-run-jobs-async-pipeline.md) — Cloud Run Jobs for async execution
- [ADR-0014](adr/0014-firebase-auth-firestore-persistence.md) — Firebase Auth + Firestore

## Architecture

- **Cloud Run Service** (`nexis`) — FastAPI + React SPA. Handles `POST /api/jobs`, `GET /api/jobs`, `GET /api/jobs/{id}`, and serves the frontend. Scales to zero when idle.
- **Cloud Run Job** (`nexis-job`) — executes the LangGraph pipeline. Triggered by the Service via `trigger_job_execution()`, runs for up to 30 minutes, writes results to Firestore.
- **Firestore** (`(default)` database, native mode) — persists job state in the `jobs/` collection.
- **Firebase Authentication** — email/password sign-in; ID tokens verified server-side via the Firebase Admin SDK.
- **Secret Manager** — holds `openrouter-api-key`, `tavily-api-key`, `langchain-api-key`. Referenced by both Cloud Run resources via `value_source.secret_key_ref`.
- **Artifact Registry** — `ghcr-remote` pull-through cache in front of GHCR.

## One-time setup

### 1. Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) `>= 1.9`
- [`gcloud`](https://cloud.google.com/sdk/docs/install) CLI, authenticated (`gcloud auth login` and `gcloud auth application-default login`)
- A GCP project (`nexis-pipeline` by default) with a billing account linked

### 2. Create the Terraform state bucket

Terraform expects the GCS backend bucket to exist before `terraform init`. Create it once:

```bash
gcloud storage buckets create gs://nexis-pipeline-tfstate \
  --project=nexis-pipeline \
  --location=us-central1 \
  --uniform-bucket-level-access
```

### 3. Apply the Terraform configuration

```bash
cd infrastructure/terraform
terraform init
terraform apply
```

On first apply, note the outputs:

| Output | Purpose |
|---|---|
| `deploy_sa_email` | Set as `GCP_SA_EMAIL` in GitHub Actions secrets |
| `wif_provider` | Set as `GCP_WIF_PROVIDER` in GitHub Actions secrets |
| `service_url` | Public URL of the Cloud Run Service |

### 4. Populate Secret Manager values

Terraform creates the secret shells with placeholder values (`CHANGEME`). Replace them with real keys:

```bash
echo -n 'YOUR_OPENROUTER_KEY' | gcloud secrets versions add openrouter-api-key --data-file=-
echo -n 'YOUR_TAVILY_KEY'     | gcloud secrets versions add tavily-api-key     --data-file=-
echo -n 'YOUR_LANGCHAIN_KEY'  | gcloud secrets versions add langchain-api-key  --data-file=-
```

Cloud Run resolves `version = "latest"` to the highest active version, so the new values take effect on the next revision without redeploying. The `CHANGEME` placeholder versions are kept by Terraform but never used once a real version exists.

### 5. Enable Firebase email/password sign-in

Terraform marks the project as Firebase-enabled (`google_firebase_project`) but cannot enable sign-in methods on the Spark (free) plan — the Terraform provider only exposes this via `google_identity_platform_config`, which would upgrade the project to Blaze billing.

In the [Firebase Console](https://console.firebase.google.com/):

1. Select the `nexis-pipeline` project
2. **Authentication** → **Sign-in method**
3. Enable **Email/Password** → **Save**

This is a one-time step; subsequent `terraform apply` calls do not touch it.

### 6. Create user accounts

In the Firebase Console:

1. **Authentication** → **Users** → **Add user**
2. Enter email and password for each authorized user

Users sign in via the web UI at `service_url` with these credentials. There is no self-signup (by design for a closed internal tool).

### 7. Register the Firebase Web App and wire `FIREBASE_API_KEY`

The React SPA fetches its Firebase Web SDK config from the backend's `/config.json` endpoint at startup, so the `apiKey` (and optionally a custom `authDomain`) must reach the Cloud Run Service as env vars. Terraform marks the project Firebase-enabled but does **not** create a Web App — that's a one-time console step.

In the [Firebase Console](https://console.firebase.google.com/):

1. Select the `nexis-pipeline` project
2. **Project settings** → **Your apps** → **Add app** → **Web** (`</>` icon)
3. Pick a nickname (e.g. `nexis-web`); skip Firebase Hosting
4. Copy the `apiKey` from the generated `firebaseConfig` snippet

Then supply it to Terraform (e.g. via `infrastructure/terraform/terraform.tfvars`, which is gitignored, or `TF_VAR_firebase_api_key`):

```hcl
firebase_api_key = "AIza..."
# firebase_auth_domain = "auth.example.com"   # optional; defaults to <project_id>.firebaseapp.com
```

The `apiKey` is safe to expose in the browser — real auth is enforced by the backend's ID-token check — so it lives as a plain Cloud Run env var rather than in Secret Manager.

For local development, set `FIREBASE_API_KEY` in `.env` alongside the other backend vars; `npm run dev` under Vite proxies `/config.json` to `localhost:8000`.

### 8. GHCR package visibility

Cloud Run pulls images through the `ghcr-remote` Artifact Registry pull-through cache. The upstream GHCR package must be **public**:

> GitHub → Settings → Packages → nexis → Change visibility → Public

## CI/CD

Pushes to `master` trigger [`.github/workflows/ci.yml`](../.github/workflows/ci.yml), which builds and pushes the Docker image to GHCR. On CI success, [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) authenticates via Workload Identity Federation and updates both the Cloud Run Service and Cloud Run Job to point at the new image.

**The deploy workflow only updates the image.** All other configuration (env vars, scaling, resources, secrets, service account, command, timeout) is owned by Terraform. If you need to change any of those fields, edit the relevant `.tf` file and `terraform apply`.

### Required GitHub Actions secrets

| Secret | Value |
|---|---|
| `GCP_WIF_PROVIDER` | `wif_provider` output from `terraform apply` |
| `GCP_SA_EMAIL` | `deploy_sa_email` output from `terraform apply` |

API keys (`OPENROUTER_API_KEY`, `TAVILY_API_KEY`, `LANGCHAIN_API_KEY`) are **no longer** stored as GitHub secrets — they are managed in Secret Manager and wired into Cloud Run via Terraform.

## Changing infrastructure

Edit the relevant `.tf` files under `infrastructure/terraform/` and run:

```bash
cd infrastructure/terraform
terraform plan    # preview changes
terraform apply   # apply
```

Because the Cloud Run Service and Job lifecycle blocks `ignore_changes` only cover the image and metadata fields that CI/CD touches, all other fields (env vars, scaling, resources, secrets, service account, command, timeout) are picked up by `terraform apply` as expected.

## Cost

| Component | Free tier | Expected monthly cost |
|---|---|---|
| Cloud Run Service + Job | 50 CPU-hours, 2M requests | $0 (~3 CPU-hours/month) |
| Firestore | 1 GiB storage, 50k reads/day, 20k writes/day | $0 (~10 jobs/month) |
| Firebase Auth (Spark) | unlimited email/password accounts | $0 |
| Secret Manager | first 6 active versions free | $0 (3 secrets) |
| Artifact Registry | 0.5 GB storage | $0 (small cached image) |

**LLM calls:** ~$2.80 per run based on ~65 LLM calls and ~370K tokens (8 candidate ideas, 3 surviving to Layer 3). Search tool costs are additional. Both are independent of the hosting platform.

Expected monthly GCP cost: **$0**.
