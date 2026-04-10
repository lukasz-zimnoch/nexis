# ADR-0013: Cloud Run Jobs for Async Pipeline Execution

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-04-10 |
| **Deciders** | Łukasz Zimnoch |
| **Supersedes** | Parts of [ADR-0011](0011-cloud-run-scale-to-zero-iam-auth.md) (synchronous execution model) |

## Context

ADR-0011 deployed Nexis as a single Cloud Run Service with a `POST /run` endpoint
that executed the full pipeline synchronously and returned results in the HTTP
response body. This worked for `curl`-based access where callers could hold a
connection open for up to 600 seconds.

With the introduction of a React web UI, the synchronous model has two problems:

1. **Browser timeouts**: browsers typically time out long-lived requests well before
   600 seconds, and there is no native mechanism to stream partial results from a
   LangGraph pipeline run.
2. **Blocked service instances**: a single Cloud Run instance handling a 10-minute
   pipeline run is unavailable for concurrent API requests (job status polls,
   frontend serving) during that time.

The new architecture requires a web UI that submits a job, immediately shows a
"pending" status, and polls for completion. This is an inherently asynchronous pattern.

## Decision

We adopt **Cloud Run Jobs** for pipeline execution. `POST /api/jobs` on the Cloud Run
Service creates a Firestore document and triggers a Cloud Run Job execution with env
var overrides (job ID, research prompt, pipeline config). The job runner reads config
from env vars, executes the pipeline using `MemorySaver`, and writes the result back
to Firestore. The frontend polls `GET /api/jobs/{id}` until the job reaches a terminal
state (`completed` or `failed`).

Key configuration: `max_retries = 0` (pipeline is not idempotent), `timeout = 1800s`
(30 minutes; well above the ~10-minute median runtime).

This supersedes the synchronous `POST /run` pattern described in ADR-0011. The Cloud
Run Service is retained for the API and SPA, but no longer executes the pipeline inline.

## Considered Alternatives

### Option A: Synchronous endpoint with longer timeout

Keep `POST /run`, raise the timeout, and stream results back to the browser.

**Pros**
- Simplest architecture: no Firestore, no job runner, no polling
- No additional GCP resources required

**Cons**
- Cloud Run Service max request timeout is 3600s; streaming LangGraph output reliably
  over a single HTTP response is non-trivial
- Blocked service instances during runs reduce availability for other requests
- Browser compatibility with long-lived streaming responses is inconsistent

### Option B: Cloud Tasks + Pub/Sub

Use Cloud Tasks to enqueue a job, a Cloud Run Service worker to execute it, and
Pub/Sub or Firebase Realtime Database for result streaming.

**Pros**
- Mature queueing primitives with retry, rate limiting, and dead-letter queues
- Real-time push notifications instead of polling

**Cons**
- Significantly more infrastructure: two Cloud Run services, a queue, a topic
- Complex: task handler, queue configuration, push subscription, and result streaming
  all need to be built and maintained
- Overkill for a pipeline that runs at most a few times per day

### Option C: Background thread in the Cloud Run Service

Spawn a `asyncio.create_task()` or `threading.Thread` for the pipeline and return a
job ID immediately.

**Pros**
- No new GCP resources; runs in the existing service
- Simpler code path

**Cons**
- Cloud Run instances scale down to zero when idle; a background task running during
  the scale-down window is killed mid-execution
- Cloud Run does not guarantee instance persistence for background work; the
  container's lifetime is tied to active request handling
- State is in-process only: results are lost if the instance restarts

## Consequences

### Positive
- Clean separation of concerns: the Cloud Run Service handles HTTP I/O; the Cloud Run
  Job handles compute. Each can be sized and scaled independently.
- Cloud Run Jobs are designed for batch workloads: automatic retries (disabled here),
  execution history, and direct integration with Cloud Monitoring
- The asynchronous pattern enables the frontend to show progress and recover from
  browser tab refreshes without losing job state (Firestore persists the result)
- No always-on worker process; the job container runs only when triggered

### Negative
- Cold start latency for the Cloud Run Job (~5–15 seconds for a 2Gi Python container)
  adds to the total pipeline time
- Polling introduces minor latency between pipeline completion and result display
  (up to the polling interval: 5s on the detail page)
- Firestore must be provisioned and the runtime SA must have `datastore.user` role

### Trade-offs
- Per-execution cost for Cloud Run Jobs is slightly higher than in-process execution
  because each job execution incurs its own cold start. For a pipeline that runs
  ~10 times/month, this is negligible (well within the 50 CPU-hour free tier).
- The polling approach (vs. WebSockets or SSE) is simpler to implement and sufficient
  for a job that takes ~10 minutes — a 5-second polling delay is imperceptible.
