# Nexis

Nexis turns one sentence about a market into a set of researched, scored and
planned business ideas. You give it a prompt. It searches the web for openings
and invents candidates. It puts each candidate in front of a six-reviewer
panel, plans the ones that survive, attacks those plans, and writes a report.

Specialist LLM agents do that work across four layers of a
[LangGraph](https://langchain-ai.github.io/langgraph/) graph. A run needs no
human input from the prompt to the report.

```mermaid
flowchart LR
    P([prompt]) --> L1["Layer 1<br/>Research"]
    L1 --> L2["Layer 2<br/>Review panel"]
    L2 -->|"an idea passed"| L3["Layer 3<br/>Planning"]
    L2 -.->|"none did"| L1
    L3 --> L4["Layer 4<br/>Output"]
    L4 --> R([report])
```

| Layer | What happens |
|---|---|
| **1. Research** | A trend scanner reads HackerNews, ProductHunt and Reddit. A research agent searches the web and writes candidate ideas. A validator drops the duplicates and the ideas an incumbent already owns. |
| **2. Review panel** | Six reviewers score every idea at once: market, technical, moat, financial, risk, AI resilience. A synthesizer weights the scores and keeps the ones above a threshold. |
| **3. Planning** | An MVP architect and a GTM strategist plan each survivor together. A composer merges the two into one business plan. |
| **4. Output** | A devil's advocate attacks each plan. A generator writes the deliverable. |

When no idea clears the threshold, the graph goes back to research with the
titles it already saw listed as exclusions. After the retries run out it
force-passes the best of what it has, so a run always ends in a report.

## Quick start

You need Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env      # then fill in the keys it lists
```

Run the pipeline:

```bash
uv run nexis --prompt "B2B SaaS tools for small construction companies"
```

Or from Python:

```python
from nexis import run_pipeline
from nexis.config import PipelineConfig

reports = run_pipeline(PipelineConfig(
    research_prompt="B2B SaaS tools for small construction companies",
    num_ideas=8,
    top_k=3,
))
```

To try the shape of a run cheaply, point every agent at one small model:

```bash
uv run nexis --prompt "..." --model anthropic/claude-haiku-4.5
```

Run the tests. They need no API key, because nothing under `tests/` calls a
real model:

```bash
uv run pytest tests/ -k "not live"
```

### Web UI

A FastAPI server exposes an authenticated job API and serves a React SPA.
Locally:

```bash
uv run uvicorn nexis.server:app --host 0.0.0.0 --port 8000
cd frontend && npm run dev    # Vite proxies /api, /health and /config.json to :8000
```

`GET /health` needs no token. Every `/api/*` route needs a Firebase ID token.
A job runs out of band in a Cloud Run Job and writes its result to Firestore.
The UI submits the job, then polls until it ends.

## How it is built

One Python package, three entry points. `nexis.__main__` is the CLI,
`nexis.server` is the FastAPI app, and `nexis.job_runner` is the batch job.
All three build the same graph and invoke it.

### Stack

| Concern | Choice |
|---|---|
| Orchestration | LangGraph `StateGraph`, one compiled subgraph per layer |
| Model access | OpenRouter, one key and one base URL for every vendor |
| Structured output | LangChain `with_structured_output()` over Pydantic v2 models |
| Web search | Tavily |
| API | FastAPI, which also serves the built SPA |
| UI | React 18, Vite 5, TypeScript |
| Auth | Firebase Auth, Admin SDK server side, Web SDK in the browser |
| Job state | Firestore, native mode |
| Hosting | Cloud Run Service for the API and SPA, Cloud Run Job for a run |
| Infrastructure | Terraform, state in GCS |
| Packages | uv, Python 3.11+ |

### Source map

| Path | Holds |
|---|---|
| `graph.py` | The parent graph, the supervisor, and the retry and force-pass nodes |
| `layers/` | One module per layer, each with a `build_*_subgraph()` |
| `agents/` | `BaseAgent` plus the agent classes, grouped by role |
| `state.py` | Every Pydantic contract and `PipelineState` |
| `models.py`, `sampling.py` | The model and the temperature per agent |
| `pricing.py`, `metrics.py`, `telemetry.py` | The price table, the run totals, the JSON events |
| `untrusted.py` | The only route web text takes into a prompt |
| `tools/` | Tavily search and the trend scraper |
| `evals/` | Reviewer calibration and variance, run by hand |
| `templates/` | Jinja2 templates for the report |
| `server.py`, `auth.py`, `firestore.py`, `job_trigger.py`, `job_runner.py` | The web surface and the batch job |
| `frontend/` | The React SPA |

### The graph

`build_graph()` in `graph.py` compiles seven nodes into one `StateGraph`:

| Node | Type | Does |
|---|---|---|
| `supervisor` | function | Sets the research prompt, refreshes it on a retry |
| `research`, `review`, `planning`, `output` | subgraph | The four layers, each compiled by its own module in `layers/` |
| `increment_iteration` | function | Bumps the retry counter on the way back to the supervisor |
| `force_pass` | function | Picks the best ideas when the retries run out |

The edges are linear except after `review`, where the conditional edge
`should_retry` reads `top_ideas` and `iteration` and returns one of three
routes: `planning`, `retry` or `force_pass`.

State is a `TypedDict`. Each field that parallel branches write to declares its
own reducer, so the branches never overwrite each other:

```python
class PipelineState(TypedDict):
    ideas: Annotated[list[BusinessIdea], operator.add]
    reviews: Annotated[list[Review], operator.add]
    scores: Annotated[dict[str, float], merge_dicts]
```

Fan-out uses two mechanisms. Layer 2 emits one `Send()` per idea and per role,
and Layer 3 emits one per idea that passed. The branch count is therefore a
run-time value. Inside a single node, `asyncio.gather()` runs a fixed set of
calls: the MVP Architect and the GTM Strategist, whose results the composer
both needs.

### An agent

Every agent subclasses `BaseAgent`, which owns the call:

1. `build_llm(model, temperature)` returns a `ChatOpenAI` client aimed at
   OpenRouter. Neither argument has a default. `models.py` and `sampling.py`
   hold the value per agent.
2. `with_structured_output(Model)` binds the Pydantic schema to the call, so
   the answer arrives as a validated object or not at all.
3. The call runs under `asyncio.wait_for`, up to `max_retries + 1` attempts.
   Before a retry, the agent appends the validation error to its own message
   list, so the next attempt reads the specific complaint.
4. A timeout rebuilds the client on `fallback_model` at the same temperature.
5. Exhausted attempts return a minimal valid instance with `failure_reason`
   set. `BaseAgent` never raises at a caller.

Every call also records tokens, cost and latency into the `RunMetrics` held in
a context variable for the run.

### Scoring

`ReviewSynthesizer` in `agents/reviewers.py` calls no model. For each idea it
computes a weighted average over that idea's reviews:

```
score = Σ (weight × score × confidence) / 10
```

It drops every idea below `score_threshold` and passes the top `top_k` to
Layer 3. A review with `failure_reason` set is left out of its idea's average.
`tests/test_scoring_regression.py` freezes the formula against a stored panel.

### Web text in prompts

`untrusted.py` is the only route from a tool result into a prompt. It exports
two functions and one rule:

- `sanitize_untrusted()` strips control characters and every copy of the two
  marker strings, then cuts the text to `MAX_UNTRUSTED_CHARS`.
- `wrap_untrusted()` puts the result between `BEGIN_MARKER` and `END_MARKER`.
- `UNTRUSTED_DATA_RULE` goes on the system prompt of any agent that reads web
  text. It names both markers and states that what sits between them is data.

### The web surface

`POST /api/jobs` writes a Firestore document and starts a Cloud Run Job
execution, with the config as environment overrides. It does not wait for the
run. The job runner builds the graph, invokes it, and writes the reports and
the run metrics back to the same document. The SPA polls `GET /api/jobs/{id}`
while the status is `pending` or `running`.

Every `/api/*` route needs a Firebase ID token, which `auth.py` verifies with
the Admin SDK. `/health` and `/config.json` do not.

### Deployment

Terraform declares every GCP resource, and keeps its state in a GCS bucket. CI
builds the image and pushes it to GHCR. The deploy workflow authenticates
through Workload Identity Federation, with no long-lived key, and points the
Service and the Job at the new image. It changes nothing else: every other
field belongs to Terraform.

The Service scales to zero when idle. The pipeline runs in the Job instead of
the Service, because a run takes minutes and an HTTP request should not.

### Tests

`tests/` mirrors the package. `test_agents/`, `test_layers/` and `test_tools/`
hold the unit tests. `test_evals/` drives the eval harness against a stand-in
reviewer, and one module per top-level file covers the rest. No test calls a
real model, so the suite runs in CI with no API key.

The reviewer evals are the exception. They live behind
`python -m nexis.evals`, call the real panel, and run by hand under a spend cap
that the collector checks before the first call.

## Documentation

| Document | What it holds |
|---|---|
| [`docs/specification.md`](docs/specification.md) | The single source of truth: what the pipeline does and how it is built. Architecture, data contracts, scoring, configuration, observability. |
| [`docs/deployment.md`](docs/deployment.md) | How to deploy the system on Google Cloud Run with Terraform. |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records. Each states the context, the alternatives and the trade-off accepted. Append-only. |
| [`CLAUDE.md`](CLAUDE.md) | Working instructions for AI agents on this codebase. |
