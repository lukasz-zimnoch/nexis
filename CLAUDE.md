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
- Web text reaches a prompt only through `src/nexis/untrusted.py`: sanitize each result, wrap it with `wrap_untrusted()`, and append `UNTRUSTED_DATA_RULE` to the agent's system prompt (ADR-0016, specification §5.7)
- Every LLM call goes through `BaseAgent`, so it lands in the run totals. Open a run scope with `run_context()` at an entry point, and keep model prices in `src/nexis/pricing.py` (ADR-0017, specification §8.3)
- Nothing under `tests/` may call a real model. Work that needs real answers belongs behind `python -m nexis.evals`, which is manual and spend-capped (ADR-0018, specification §6.4)

## Checkpointer

All code paths (CLI, Cloud Run Service, Cloud Run Job) use `MemorySaver`. State is in-memory and ephemeral per run. There is no SQLite dependency.

## Frontend

The SPA lives in `frontend/` (React + Vite, TypeScript). Auth uses the Firebase Web SDK, which is bootstrapped at runtime from the backend's `/config.json` endpoint (`apiKey`, `authDomain`, `projectId`) — no Firebase values are baked into the static bundle. All API calls inject the Firebase ID token as a Bearer token via `frontend/src/api/client.ts`. Dashboard and detail pages poll `/api/jobs*` while any job is in `pending` or `running` state. The detail page renders `JobRecord.metrics` in a cost panel whenever the job carries one. The production build (`npm run build`) writes to `frontend/dist/`, which the FastAPI server mounts as static files. Vite proxies `/api`, `/health`, and `/config.json` to `localhost:8000` during local dev.

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
- `tests/test_scoring_regression.py` freezes the weighted formula against `tests/evals/scoring_regression.json`. Change the weights or the formula and update the frozen values in the same commit
- `tests/test_evals/` covers the eval harness with a stand-in reviewer, so it is free and runs in the normal CI job
- Frontend tests use Vitest + React Testing Library under `frontend/src/**/__tests__/`; run with `cd frontend && npm test`

## Evals

The reviewer evals call real models and cost money, so they are manual. Collect first, then report:

```bash
uv run python -m nexis.evals collect --out eval-run --repeats 1 --max-usd 1.00
uv run python -m nexis.evals report --run eval-run --min-hit-rate 0.7
```

`collect` refuses to start above `--max-usd`. Use `--repeats 5` to measure variance and `--model openai/gpt-5.6-luna` to debug the harness cheaply; never publish numbers from a run that used a stand-in model. `report` reads the collected directory, calls no API, and exits non-zero when a role misses the gate, so re-reading the same answers with different bands or thresholds is free. `.github/workflows/evals.yml` runs the same two commands and is `workflow_dispatch` only. See ADR-0018 and specification §6.4.
