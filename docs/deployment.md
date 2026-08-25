# Deployment

Nexis runs on [Google Cloud Run](https://cloud.google.com/run).
[Terraform](https://www.terraform.io/) declares every GCP resource, and
[Firebase Auth](https://firebase.google.com/products/auth) handles sign-in.

This guide takes you from an empty GCP project to a running deployment. It
describes the steps you run, not what the resources look like inside: the
`.tf` files under `infrastructure/terraform/` are the definition. For what the
deployed code does, read [`specification.md`](specification.md). For why this
shape, read [ADR-0012](adr/0012-terraform-infrastructure-management.md),
[ADR-0013](adr/0013-cloud-run-jobs-async-pipeline.md) and
[ADR-0014](adr/0014-firebase-auth-firestore-persistence.md).

## What Terraform creates

| Resource | Name | Role |
|---|---|---|
| Cloud Run Service | `nexis` | FastAPI API and React SPA. Scales to zero when idle |
| Cloud Run Job | `nexis-job` | Runs the pipeline, up to 30 minutes, writes to Firestore |
| Firestore | `(default)`, native mode | The `jobs/` collection |
| Firebase Auth | | Email and password sign-in, verified server side |
| Secret Manager | `openrouter-api-key`, `tavily-api-key`, `langchain-api-key` | API keys, read by both Cloud Run resources |
| Artifact Registry | `ghcr-remote` | Pull-through cache in front of GHCR |

Two of these need a manual step that Terraform cannot take. Steps 5 and 7
below cover them.

## One-time setup

### 1. Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) 1.9 or later
- The [`gcloud`](https://cloud.google.com/sdk/docs/install) CLI, authenticated
  with both `gcloud auth login` and `gcloud auth application-default login`
- A GCP project (`nexis-ai` by default) with a billing account linked

### 2. Create the Terraform state bucket

Terraform needs the GCS backend bucket before `terraform init` runs, so create
it by hand once:

```bash
gcloud storage buckets create gs://nexis-ai-tfstate \
  --project=nexis-ai \
  --location=us-central1 \
  --uniform-bucket-level-access
```

### 3. Apply the Terraform configuration

```bash
cd infrastructure/terraform
terraform init
terraform apply
```

Keep the three outputs. You need all of them later:

| Output | Where it goes |
|---|---|
| `deploy_sa_email` | The `GCP_SA_EMAIL` GitHub Actions secret |
| `wif_provider` | The `GCP_WIF_PROVIDER` GitHub Actions secret |
| `service_url` | The public URL of the deployment |

### 4. Put real values in Secret Manager

Terraform creates each secret with a `CHANGEME` placeholder. Replace all three:

```bash
echo -n 'YOUR_OPENROUTER_KEY' | gcloud secrets versions add openrouter-api-key --data-file=-
echo -n 'YOUR_TAVILY_KEY'     | gcloud secrets versions add tavily-api-key     --data-file=-
echo -n 'YOUR_LANGCHAIN_KEY'  | gcloud secrets versions add langchain-api-key  --data-file=-
```

Cloud Run resolves `version = "latest"` to the highest active version, so the
next revision picks the new values up without a redeploy. Terraform keeps the
placeholder versions, but nothing reads them once a real version exists.

### 5. Turn on email and password sign-in

Terraform marks the project as Firebase-enabled but cannot enable a sign-in
method on the Spark (free) plan. The provider only exposes this through
`google_identity_platform_config`, which would move the project to Blaze
billing.

In the [Firebase Console](https://console.firebase.google.com/):

1. Select the `nexis-ai` project.
2. Go to **Authentication** → **Sign-in method**.
3. Enable **Email/Password** and save.

Later `terraform apply` calls leave this alone.

### 6. Create the user accounts

There is no self-signup. This is a closed tool, so an operator adds each user.

In the Firebase Console, go to **Authentication** → **Users** → **Add user**
and enter an email and a password. Those users sign in at `service_url`.

### 7. Register the Web App and set `FIREBASE_API_KEY`

The SPA fetches its Firebase config from the backend at startup. The `apiKey`
must therefore reach the Cloud Run Service as an environment variable.
Terraform does not create the Web App that issues that key.

In the [Firebase Console](https://console.firebase.google.com/):

1. Select the `nexis-ai` project.
2. Go to **Project settings** → **Your apps** → **Add app** → **Web**.
3. Give it a nickname such as `nexis-web`. Skip Firebase Hosting.
4. Copy `apiKey` from the generated `firebaseConfig` snippet.

Then give it to Terraform, either through `TF_VAR_firebase_api_key` or through
`infrastructure/terraform/terraform.tfvars`, which is gitignored:

```hcl
firebase_api_key = "AIza..."
# firebase_auth_domain = "auth.example.com"   # optional, defaults to <project_id>.firebaseapp.com
```

The `apiKey` is safe in a browser, because the backend enforces auth by
checking the ID token. It therefore lives as a plain Cloud Run environment
variable rather than in Secret Manager.

For local development, set `FIREBASE_API_KEY` in `.env` with the other backend
variables.

### 8. Make the GHCR package public

Cloud Run pulls the image through the `ghcr-remote` cache, which only reads
public upstream packages:

> GitHub → Settings → Packages → nexis → Change visibility → Public

## CI/CD

A push to `master` runs [`ci.yml`](../.github/workflows/ci.yml). It lints,
tests, builds the image and pushes it to GHCR. On success,
[`deploy.yml`](../.github/workflows/deploy.yml) authenticates through Workload
Identity Federation. It then points the Cloud Run Service and the Cloud Run Job
at the new image.

**The deploy workflow only changes the image.** Terraform owns every other
field: environment variables, scaling, resources, secrets, service account,
command and timeout. To change one of those, edit the `.tf` file and apply.

Two GitHub Actions secrets are required. Both come from step 3:

| Secret | Value |
|---|---|
| `GCP_WIF_PROVIDER` | The `wif_provider` output |
| `GCP_SA_EMAIL` | The `deploy_sa_email` output |

The API keys are not GitHub secrets. They live in Secret Manager and reach
Cloud Run through Terraform.

[`evals.yml`](../.github/workflows/evals.yml) is the third workflow. It calls
real models, so it runs only when someone dispatches it by hand.

## Changing infrastructure

Edit the `.tf` files and apply:

```bash
cd infrastructure/terraform
terraform plan     # preview
terraform apply
```

The Cloud Run `ignore_changes` blocks cover only the image and the metadata
that CI/CD writes, so `terraform apply` picks up every other field as expected.

Do not change deployed configuration with `gcloud run services update`. The
next apply would revert it.

## Cost

Hosting is free at this volume. Every component stays inside its free tier.

| Component | Free tier | At roughly 10 runs per month |
|---|---|---|
| Cloud Run Service and Job | 50 CPU-hours, 2M requests | $0 |
| Firestore | 1 GiB, 50k reads and 20k writes per day | $0 |
| Firebase Auth (Spark) | unlimited email and password accounts | $0 |
| Secret Manager | first 6 active versions | $0 |
| Artifact Registry | 0.5 GB storage | $0 |

The LLM calls and the Tavily searches are the real cost, and neither depends on
the hosting platform. The call count follows the pipeline
shape and the run settings; see
[specification §11](specification.md#11-call-volume-per-run). This repository
does not print a dollar figure for that, because the price per call changes
whenever a vendor changes it. Every run reports its own measured cost with the
job, which is the number to trust.
