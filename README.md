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

Six choices that shape the code more than the rest:

- **Two kinds of parallelism.** `Send()` fans out graph nodes and
  `asyncio.gather()` fans out coroutines inside one node. Eight ideas open 48
  concurrent reviewer calls. See [ADR-0003](docs/adr/0003-hybrid-parallelism-send-and-gather.md).
- **Failure is the normal case.** An agent retries on its own bad output and is
  told what was wrong. A timeout moves it to a fallback model. A spent retry
  budget returns a partial result with `failure_reason` set, never an
  exception. See [ADR-0007](docs/adr/0007-graceful-degradation-failure-reason.md).
- **The ranking runs no LLM.** The synthesizer is arithmetic over the reviewer
  scores, so one set of reviews always gives one ranking. A regression test
  freezes the formula. See [ADR-0010](docs/adr/0010-deterministic-weighted-scoring.md).
- **One model and one temperature per agent.** Both tables live in one file
  each, and an agent with no temperature fails to construct. Reviewers sit at
  0.0 because they measure; the research agent sits at 1.0 because it invents.
  See [ADR-0005](docs/adr/0005-per-agent-model-specialization.md) and
  [ADR-0019](docs/adr/0019-per-agent-sampling-policy.md).
- **Every call lands in a run total.** Tokens, cost and time, split by layer and
  by agent, stored with the job and rendered next to the report. See
  [ADR-0017](docs/adr/0017-per-run-cost-and-token-metrics.md).
- **Web text is untrusted data.** Anyone who can publish a page can otherwise
  write into a prompt. Web text is cleaned, capped and wrapped in markers it
  cannot forge, under a rule the agent's system prompt carries. See
  [ADR-0016](docs/adr/0016-untrusted-web-content-trust-boundary.md).

The review panel is the one part whose output no type can check, so it gets
measured against a hand-labelled dataset. Each label is a score **band**, not a
number. Two people who agree that an idea is commoditised still disagree on
whether that is a 2 or a 3. The evals call real models, so they are manual,
spend-capped, and never run on a pull request. See
[specification §5](docs/specification.md#5-reviewer-evals) and
[ADR-0018](docs/adr/0018-band-gated-reviewer-evals.md).

## Documentation

| Document | What it holds |
|---|---|
| [`docs/specification.md`](docs/specification.md) | The single source of truth: what the pipeline does and how it is built. Architecture, data contracts, scoring, configuration, observability. |
| [`docs/deployment.md`](docs/deployment.md) | How to deploy the system on Google Cloud Run with Terraform. |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records. Each states the context, the alternatives and the trade-off accepted. Append-only. |
| [`CLAUDE.md`](CLAUDE.md) | Working instructions for AI agents on this codebase. |
