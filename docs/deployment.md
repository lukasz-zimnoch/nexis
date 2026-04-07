# Deployment

Nexis deploys to [Google Cloud Run](https://cloud.google.com/run) on every push to `master` that passes CI. It uses IAP (Identity-Aware Proxy) for email-based access control and scales to zero when idle.

## Container

CI builds a standard Docker image (see `Dockerfile`) that runs a FastAPI/Uvicorn server (`nexis.server:app`). The server exposes:

- `POST /run` — run the full pipeline (accepts `RunRequest`, returns reports)
- `GET /health` — health check

The graph uses in-memory checkpointing (`MemorySaver`) for intra-run state. No external database is required. The `langgraph.json` file is retained for local development with `langgraph dev` but is not used in production.

## One-time GCP setup

```bash
export BILLING_ACCOUNT_ID=<your-billing-account-id>
bash scripts/setup-gcp.sh
```

The script creates the GCP project, enables APIs, sets up a deploy service account with Workload Identity Federation (keyless auth for GitHub Actions), and prints the secret values you need to add to GitHub.

## GitHub secrets required

| Secret | Value |
|---|---|
| `GCP_WIF_PROVIDER` | Output of `scripts/setup-gcp.sh` (step 6) |
| `GCP_SA_EMAIL` | `nexis-deploy@nexis-pipeline.iam.gserviceaccount.com` |
| `OPENROUTER_API_KEY` | Your OpenRouter API key |
| `TAVILY_API_KEY` | Your Tavily API key |
| `LANGCHAIN_API_KEY` | Your LangSmith API key (optional) |

Add these at: **Settings > Secrets and variables > Actions**

## GHCR package visibility

Cloud Run pulls the image from GHCR at deploy time using GCP credentials, not a GitHub token. The package must be **public**:

> GitHub > Settings > Packages > nexis > Change visibility > Public

## IAP access (after first deploy)

After the first successful deploy, grant access to specific emails:

```bash
gcloud beta iap web add-iam-policy-binding \
  --resource-type=cloud-run --service=nexis --region=us-central1 \
  --member="user:your-email@example.com" \
  --role="roles/iap.httpsResourceAccessor"
```

Enable IAP for the first time via the Cloud Console (Security > Identity-Aware Proxy) to auto-generate the OAuth consent screen.

## Cost

**Cloud Run:** Free tier covers typical pipeline usage (~10 runs/month x 10 min x 1 CPU = 1.7 CPU-hours, well within the 50 CPU-hour free limit). Expected monthly cost: $0.

**LLM calls:** ~$2.80 per run (8 candidate ideas, 3 surviving to Layer 3), based on ~65 LLM calls and ~370K tokens. Search tool costs are additional.
