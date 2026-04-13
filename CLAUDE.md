# Nexis — Claude Code Instructions

## Project overview

Nexis is an autonomous multi-agent business idea pipeline built on LangGraph. It runs end-to-end without human intervention, producing a structured report of evaluated and planned business ideas. The full technical specification is in [`docs/specification.md`](docs/specification.md).

## Architecture

See the [specification](docs/specification.md) for full architecture, data contracts, configuration reference, project structure, and technology stack. Key source files:

- `graph.py` — parent graph (retry logic, supervisor, force-pass)
- `layers/` — four subgraphs: `research.py`, `review.py`, `planning.py`, `output.py`
- `server.py` — FastAPI Cloud Run Service: `/api/jobs` endpoints (Firebase-authenticated) and serves the built React SPA from `frontend/dist/`
- `job_runner.py` — Cloud Run Job entry point (`python -m nexis.job_runner`); reads job config from env overrides, writes results to Firestore
- `job_trigger.py` — triggers the Cloud Run Job from the Service via `run_v2.RunJobRequest`
- `auth.py` — Firebase ID token verification middleware
- `firestore.py` — `JobRecord` CRUD on the Firestore `jobs/` collection
- `frontend/` — React + Vite SPA (Firebase Web SDK, calls `/api/*`)
- `infrastructure/terraform/` — declarative GCP infrastructure

## Key conventions

- All inter-agent data uses Pydantic models defined in `src/nexis/state.py` — never use plain dicts for agent I/O
- Use `with_structured_output()` for every LLM call that returns structured data
- Agents must handle `failure_reason` fields gracefully — don't crash on partial results
- Each layer subgraph must be independently testable without running the full pipeline
- Async-first: all agent methods should be `async def` and use `asyncio.gather()` for concurrency

## Checkpointer

All code paths (CLI, Cloud Run Service, Cloud Run Job) use `MemorySaver`. State is in-memory and ephemeral per run. There is no SQLite dependency.

## Frontend

The SPA lives in `frontend/` (React + Vite, TypeScript). Auth uses the Firebase Web SDK; all API calls inject the Firebase ID token as a Bearer token via `frontend/src/api/client.ts`. Dashboard and detail pages poll `/api/jobs*` while any job is in `pending` or `running` state. The production build (`npm run build`) writes to `frontend/dist/`, which the FastAPI server mounts as static files. Vite proxies `/api` and `/health` to `localhost:8000` during local dev.

## Deployment

See [`docs/deployment.md`](docs/deployment.md).

## Infrastructure

All GCP resources are managed by Terraform under `infrastructure/terraform/` (Cloud Run Service + Job, Firestore, Secret Manager, IAM, Workload Identity Federation, Artifact Registry pull-through cache). Do not change deployed Cloud Run config via `gcloud run services update` — the deploy workflow only touches the image; everything else belongs in `.tf` files. See ADR-0012 and `docs/deployment.md`.

## Architecture Decision Records

Design decisions are documented as ADRs in `docs/adr/`. Use the template at `docs/adr/0000-template.md` when adding new ones.

## Testing

- Unit tests live in `tests/test_agents/` — test each agent in isolation with mocked LLM calls
- Layer tests live in `tests/test_layers/` — test subgraph routing and state transitions
- `tests/test_integration.py` has a mocked smoke test (runs in CI) and a `@pytest.mark.live` test (real APIs, skipped in CI)
- Frontend tests use Vitest + React Testing Library under `frontend/src/**/__tests__/`; run with `cd frontend && npm test`
