# ADR-0014: Firebase Auth and Firestore for Auth and Job Persistence

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-04-10 |
| **Deciders** | Łukasz Zimnoch |
| **Supersedes** | Parts of [ADR-0011](0011-cloud-run-scale-to-zero-iam-auth.md) (IAM-only authentication) |

## Context

ADR-0011 used Cloud Run's built-in IAM authentication (`--no-allow-unauthenticated`)
as the sole access control mechanism. Callers authenticated by generating a Google
identity token with `gcloud auth print-identity-token`. This is adequate for
developer access via `curl` but is not viable for a browser-based UI: it requires
users to have a GCP project IAM role, a `gcloud` CLI installation, and knowledge of
how to generate identity tokens.

The new web UI requires:
1. **Email/password login** that works in a browser without GCP CLI tooling
2. **Job state persistence** so results can be retrieved after the async pipeline
   completes, and so the dashboard survives browser refreshes

The tool is a closed internal tool; no self-signup is needed.

## Decision

We adopt **Firebase Authentication** (email/password provider, accounts created
manually by the administrator) for browser-based auth, and **Firestore** (native mode,
default database) for job state persistence.

Firebase Auth is initialized on the server side with the Firebase Admin SDK using
Application Default Credentials (ADC), verifying ID tokens in a FastAPI `Depends()`
middleware. On the client side, the Firebase JS SDK (`firebase/app`, `firebase/auth`)
handles login and ID token refresh. Every API request carries the token as
`Authorization: Bearer <id_token>`.

Firestore stores `jobs/{job_id}` documents with status, config, timestamps, and
results. The runtime SA (`nexis-runtime`) has `roles/datastore.user` which covers
all Firestore read/write operations.

Cloud Run's built-in IAM auth is removed (`--allow-unauthenticated`), replaced by
Firebase token verification in the application layer.

## Considered Alternatives

### Option A: Custom JWT auth + Cloud SQL (PostgreSQL)

Build a username/password login system from scratch backed by Cloud SQL.

**Pros**
- No Firebase dependency; fully self-contained within GCP
- SQL schema gives flexible query capabilities for job state

**Cons**
- Significant implementation effort: password hashing, JWT generation/verification,
  refresh token rotation, session management
- Cloud SQL minimum cost ~$7/month for a `db-f1-micro`; Firestore is free for this
  usage level
- Auth is a security-critical component; rolling it from scratch introduces risk

### Option B: Auth0 or Clerk

Use a managed third-party identity provider.

**Pros**
- Polished login UIs out of the box
- Advanced features (MFA, SSO) without extra code

**Cons**
- External dependency beyond GCP; adds another vendor and billing relationship
- Free tiers are limited; paid tiers start at ~$23/month (Auth0) for features
  not needed here
- Token verification requires an additional HTTP call to the provider's JWKS endpoint

### Option C: Retain IAM auth + add a thin proxy

Keep Cloud Run IAM auth and put a small OAuth2 proxy (e.g., `oauth2-proxy`) in front
of the service.

**Pros**
- No change to the Cloud Run auth model
- Works with Google Accounts without Firebase

**Cons**
- Adds another service to operate, deploy, and secure
- Identity tokens expire in one hour; the proxy must handle refresh transparently
- Doesn't provide a job persistence store — a separate database is still needed

### Option D: Cloud Firestore vs. Cloud SQL for persistence

For the persistence layer specifically: Cloud SQL (PostgreSQL) was considered as an
alternative to Firestore.

**Pros of Cloud SQL**
- Relational schema; easier ad-hoc queries
- Familiar SQL tooling

**Cons of Cloud SQL**
- Minimum cost ~$7/month; Firestore free tier covers 50k reads/day and 1k writes/day
  (well above the ~10 jobs/month usage)
- Requires VPC connector or Cloud SQL Auth Proxy for secure access from Cloud Run
- More operational overhead (backups, version upgrades, connection pooling)

## Consequences

### Positive
- Firebase Auth free tier (Spark plan) covers unlimited email/password accounts
- Firestore free tier (1 GiB storage, 50k reads/day, 20k writes/day) is more than
  sufficient for ~10 jobs/month
- Firebase Admin SDK + ADC means no additional credentials — the same service account
  that runs the container verifies tokens
- Firebase JS SDK handles ID token auto-refresh transparently in the browser
- Firestore's document model maps naturally to the `JobRecord` schema (no migrations)

### Negative
- Firebase is a Google-specific dependency; migrating off Firebase Auth would require
  implementing a new auth layer and migrating user accounts
- Email/password accounts must be created manually by the administrator via the
  Firebase Console — there is no self-signup (by design for this closed tool)
- Firestore does not support multi-field sorting without a composite index; the
  `(user_id ASC, created_at DESC)` index must be provisioned in Terraform

### Trade-offs
- Firebase Auth sits in front of the GCP IAM layer: Cloud Run is now public
  (`--allow-unauthenticated`) and relies on the application to reject unauthenticated
  requests. A bug in the auth middleware could expose the API. This risk is acceptable
  for an internal tool, and the middleware is covered by unit tests.
- Firestore's synchronous Python SDK performs I/O on the event loop thread. For the
  small number of single-doc reads/writes per request, this is acceptable; wrapping
  calls in `asyncio.to_thread()` is straightforward if latency becomes a concern.
