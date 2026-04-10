# ADR-0012: Terraform for Infrastructure Management

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-04-10 |
| **Deciders** | Łukasz Zimnoch |

## Context

The original GCP setup was performed by `scripts/setup-gcp.sh`: an imperative bash script
that created the project, enabled APIs, provisioned service accounts, and configured
Workload Identity Federation. The script worked around idempotency by checking for
"already exists" conditions before each step, but it could not detect or repair drift
— if a resource was changed or deleted outside the script, re-running it would not
restore it correctly.

Adding Firebase Auth, Firestore, Cloud Run Jobs, and Secret Manager to the
infrastructure further increases the complexity the script must manage imperatively.
A declarative tool that tracks desired state and computes diffs is warranted.

## Decision

We adopt **Terraform** (HashiCorp, `hashicorp/google` provider `~> 7.0`) for all GCP
infrastructure management. The `infrastructure/terraform/` directory replaces
`scripts/setup-gcp.sh`.

State is stored in a GCS backend (`nexis-pipeline-tfstate` bucket, pre-created
manually once). Terraform manages: API enablement, Artifact Registry, IAM service
accounts, Workload Identity Federation, Secret Manager secrets, Firestore, Cloud Run
Service, and Cloud Run Job. CI/CD still handles image updates via
`google-github-actions/deploy-cloudrun`.

## Considered Alternatives

### Option A: Continue with bash scripts

Extend `setup-gcp.sh` to cover the new resources.

**Pros**
- No new tooling; everyone who can run `gcloud` can run the script
- No state file to manage or lose

**Cons**
- No drift detection: if a resource is changed manually, the script does not restore it
- Idempotency must be hand-coded for every resource type (`describe && skip || create`)
- Complex dependency ordering between resources requires careful manual sequencing
- No plan preview before applying changes

### Option B: Pulumi

Use Pulumi with TypeScript or Python SDKs.

**Pros**
- Real programming language: loops, conditionals, and abstractions without HCL
- First-class support for GCP via `@pulumi/gcp`

**Cons**
- Smaller ecosystem than Terraform for GCP; fewer community examples
- Requires Node.js or Python runtime and additional package management
- State backend setup is similar complexity to Terraform

### Option C: gcloud CLI in GitHub Actions

Run `gcloud` commands directly in CI/CD workflows to provision resources.

**Pros**
- No additional tools; gcloud is already authenticated in the deploy workflow
- Changes are visible in the workflow YAML alongside the deploy steps

**Cons**
- Same non-idempotency problems as bash scripts
- No plan step; changes apply immediately without preview
- Infrastructure and application deployment are mixed in a single workflow, making
  rollbacks harder

## Consequences

### Positive
- `terraform plan` provides a preview of changes before applying
- Drift detection: `terraform plan` reveals when live state diverges from declared state
- Dependency graph: Terraform resolves resource ordering automatically
- Single source of truth for all GCP infrastructure (excluding CI/CD image deploys)
- State stored in GCS is shared between collaborators without a separate backend service

### Negative
- New tooling dependency: operators must install Terraform (`>= 1.9`) locally
- GCS state bucket must be created manually before `terraform init` (bootstrap step)
- Existing resources must be imported via `terraform import` before Terraform
  can manage them

### Trade-offs
- Terraform HCL is less expressive than a general-purpose language, but it is
  sufficiently expressive for the resource types used here (no complex loops required)
- Terraform state is a new artifact to protect; GCS versioning and IAM on the state
  bucket guard against accidental loss
