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

### The graph

Each layer is its own LangGraph subgraph. It compiles alone and it runs in a
test alone. The parent `StateGraph` wires the four together and owns the state
they share.

Nothing crosses a node boundary as a loose dict. Every agent takes a Pydantic
model and returns one, and every call that must come back structured binds to
that model with `with_structured_output()`. The graph state is a `TypedDict`,
and a reducer on each field says how two parallel branches merge into it.

An agent is more than a prompt. Each one names its own model and its own
sampling temperature, in one table each. The reviewers sit at 0.0 because they
measure. The research agent sits at 1.0 because it invents. An agent with no
temperature assigned fails to construct, so the two tables cannot drift apart.

Parallelism comes in two forms, because the two problems differ. `Send()` fans
out graph nodes, so Layer 2 opens one node per idea and per role: eight ideas
start 48 reviewer calls at once. `asyncio.gather()` fans out coroutines inside
a single node, which is how one idea gets its MVP plan and its GTM plan at the
same time.

### Failure is the normal case

A run makes tens of model calls, so some call fails in most runs. Nothing here
treats that as exceptional.

An agent that returns bad output gets the validation error appended to its own
message list. It then answers the specific complaint, not the same prompt
twice. An agent that times out rebuilds its client on a fallback model and
spends the tries it has left there, at the same temperature. An agent that runs
out of tries returns a partial result with `failure_reason` set. It never
raises, and every consumer reads that field before it uses the result.

The graph solves the layer-level version of the same problem. When no idea
clears the score threshold, the run returns to research with the titles it
already saw marked as exclusions. When the retries run out it force-passes the
best of what it has, so a run always ends in a report.

### Numbers you can check

The review panel is the one part whose output no type can check, so two
separate mechanisms hold it down.

The ranking runs no model at all. The synthesizer is a weighted average over
the reviewer scores, so one set of reviews always gives one ranking. A
regression test freezes the formula against stored values.

The reviewers are measured against a hand-labelled dataset. Each label is a
score **band**, not a number. Two people who agree that an idea is
commoditised still disagree on whether that is a 2 or a 3. Calibration asks
whether a reviewer agrees with a human. Variance asks whether it agrees with
itself. Both call real models, so both are manual, spend-capped, and never run
on a pull request.

Every model call lands in a run total. Tokens, cost and wall time, split by
layer and by agent, land with the job and appear next to the report.

### Around the pipeline

Web text is untrusted data. Anyone who can publish a page can otherwise write
instructions into a prompt. Search results are cleaned, capped, and wrapped in
markers a page cannot forge, under a rule that the agent's system prompt
carries.

The deployment is declared, not clicked. Terraform holds every GCP resource. A
push to `master` builds the image, and GitHub Actions deploys it through
Workload Identity Federation with no long-lived key. The API and the SPA share
one Cloud Run Service that scales to zero. The pipeline runs apart from it, as
a Cloud Run Job that writes to Firestore. A ten-minute run does not belong
inside an HTTP request.

Nothing under `tests/` calls a real model, so the suite runs in CI with no API
key and no spend.

Every choice above has an Architecture Decision Record in
[`docs/adr/`](docs/adr/), with the alternatives that lost and the trade-off
accepted. [`docs/specification.md`](docs/specification.md) holds the full
detail.

## Documentation

| Document | What it holds |
|---|---|
| [`docs/specification.md`](docs/specification.md) | The single source of truth: what the pipeline does and how it is built. Architecture, data contracts, scoring, configuration, observability. |
| [`docs/deployment.md`](docs/deployment.md) | How to deploy the system on Google Cloud Run with Terraform. |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records. Each states the context, the alternatives and the trade-off accepted. Append-only. |
| [`CLAUDE.md`](CLAUDE.md) | Working instructions for AI agents on this codebase. |
