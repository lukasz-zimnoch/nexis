# ADR-0011: Cloud Run with Scale-to-Zero and IAP Auth

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-03-30 |
| **Deciders** | Łukasz Zimnoch |

## Context

The Nexis CI pipeline builds a Docker image via `langgraph build` and pushes it
to GHCR. The deploy workflow (`deploy.yml`) currently has TODO placeholder steps.
The pipeline needs a runtime environment with the following constraints:

- **Zero idle cost**: runs ~10 times per month, each taking ~10 minutes;
  always-on infrastructure is wasteful
- **No new application code**: the existing GHCR image must deploy as-is
- **Email-based access control**: only authorized users should be able to trigger
  pipeline runs; a standalone auth system is not worth building for a personal
  project
- **Keyless CI/CD**: no long-lived service account keys stored in GitHub Actions
  secrets
- **HTTP endpoint**: the LangGraph Platform server exposes an HTTP API; the
  deployment target must serve HTTP traffic

## Decision

We deploy to **Google Cloud Run** with:

- `min-instances=0` (true scale-to-zero; zero cost when idle)
- `max-instances=1` (batch pipeline; no horizontal scaling needed)
- `timeout=600s` (10-minute pipeline runs)
- **Workload Identity Federation** for keyless GitHub Actions deployment (no
  long-lived service account key)
- **Identity-Aware Proxy (IAP)** on the default `run.app` URL for email-gated
  access without a load balancer
- Secrets (API keys) passed as environment variables via `--set-env-vars` in
  the deploy command; stored in GitHub Actions environment secrets

## Considered Alternatives

### Option A: AWS Lambda + API Gateway

Use AWS Lambda for serverless execution with API Gateway as the HTTP endpoint.

**Pros**
- Mature platform with extensive tooling
- Similar scale-to-zero economics

**Cons**
- Lambda's maximum execution timeout is 15 minutes; a 10-minute pipeline run is
  dangerously close to the limit and leaves no headroom for slow LLM calls
- Container image size limit is 10 GB; LangGraph Platform images may approach
  this
- API Gateway auth (Cognito) is significantly more complex to configure than
  Cloud Run's IAP

### Option B: GKE / EKS (Managed Kubernetes)

Deploy the container on a managed Kubernetes cluster.

**Pros**
- Full control over networking, scaling, and scheduling
- Suitable for high-volume production workloads

**Cons**
- Minimum ~$70/month for a single-node cluster (always-on control plane)
- Significant operational overhead (node upgrades, cluster maintenance) for a
  batch pipeline that runs 10 times per month
- Overkill: Kubernetes features (pod scheduling, service meshes, horizontal pod
  autoscaling) provide no benefit for a single-container batch workload

### Option C: Fly.io

Deploy to [Fly.io](https://fly.io) using their Docker-native deployment.

**Pros**
- Simple deploy model (`fly deploy`); excellent developer experience
- Scale-to-zero available on paid plans
- No GCP lock-in

**Cons**
- No built-in IAP equivalent; email-based auth would require an additional
  service (Cloudflare Access, Authelia) or custom middleware
- Workload Identity Federation (keyless CI/CD) is GCP-specific; Fly.io would
  require a stored deploy token
- Less mature than Cloud Run for production workloads

### Option D: Self-Hosted VM (Always-On)

Run the container on a small always-on VM (e.g., GCP `e2-micro` free tier or
Hetzner CX11).

**Pros**
- Simple; no serverless cold start latency
- Full control over the environment

**Cons**
- Always-on cost (~$5–10/month) for a service that is idle 99% of the time
- Requires OS maintenance, security patching, and uptime monitoring
- No automatic scaling if workload increases

### Option E: Cloud Run Jobs (Batch)

Use Cloud Run Jobs instead of Cloud Run Services for batch execution.

**Pros**
- Designed for batch workloads; no HTTP server required
- Job executions are triggered and monitored independently

**Cons**
- No HTTP endpoint; the LangGraph Platform server exposes an HTTP API that
  clients use to trigger and monitor pipeline runs — a job-only deployment
  would require a separate mechanism to invoke and stream results
- LangGraph Server is designed to run as a persistent HTTP service, not as a
  one-shot batch job

## Consequences

### Positive
- **$0/month** within Google Cloud's free tier (50 CPU-hours/month, 2M requests;
  10 runs × 10 minutes × 2 vCPU = 3.3 CPU-hours/month)
- True scale-to-zero: zero instances when idle; no idle cost
- Workload Identity Federation eliminates long-lived service account keys from
  GitHub Actions secrets
- IAP provides email-gated access with Google account authentication at no
  additional cost, without deploying a load balancer

### Negative
- Cold starts of ~5–10 seconds occur after the service scales to zero; for a
  10-minute pipeline run this is acceptable but noticeable
- IAP requires all users to have Google accounts; access for non-Google users
  would require a different auth mechanism
- Secrets passed as environment variables are visible to principals with
  `roles/run.admin`; for a personal project this is acceptable, but a
  multi-tenant deployment would need Cloud Secret Manager

### Trade-offs
- Cloud Run creates a GCP dependency. If Google changes pricing, deprecates the
  service, or restricts the free tier, migration to another platform is required.
  For a personal project, this risk is acceptable given the $0 current cost and
  the availability of equivalent services (Fly.io, Railway, Render) as fallbacks.
