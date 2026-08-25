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

The model call is the easy part of an agent system. That call can return the
wrong shape, time out, or disagree with the last one. It can also cost real
money and carry text a stranger wrote on a web page. Most of the code here
answers one of those.

**A model returns text, not a type.** Every agent takes a Pydantic model and
returns one, and `with_structured_output()` binds that schema to the call. The
bounds live in the type rather than in the prompt, so a `Review` with a score
of 11 fails before any code reads it. A rejected answer is not retried blind.
The agent appends the validation error to its own message list and asks again:

```python
messages.append(HumanMessage(
    content=f"The previous response failed validation: {last_error}\nPlease fix and retry."
))
```

The second attempt answers the specific complaint, not the same prompt twice.

**The pipeline does not know its own width until it runs.** Layer 1 decides how
many ideas exist, so the graph cannot declare its shape when it compiles. Layer
2 emits one `Send()` per idea and per role, which turns eight ideas into 48
reviewer nodes in one step. Those branches write to the same state at the same
time and never collide, because each field declares how to merge:

```python
class PipelineState(TypedDict):
    ideas: Annotated[list[BusinessIdea], operator.add]
    reviews: Annotated[list[Review], operator.add]
    scores: Annotated[dict[str, float], merge_dicts]
```

`asyncio.gather()` covers the other case, a fixed set of calls that one node
needs before it continues. The MVP Architect and the GTM Strategist run
together inside a single node, because the composer needs both plans.

**A call fails more often than you would like.** No model failure raises. An
agent that times out rebuilds its client on a fallback model. It spends the
tries it has left there, at the same temperature, so a degraded run does not
also become a differently calibrated one. An agent that runs out of tries
returns a valid instance with `failure_reason` set, and every consumer reads
that field before the result. A failed reviewer drops out of the weighted
average, and its idea keeps the scores that did arrive. The same rule holds one
level up: when no idea clears the threshold, the graph retries research with
the titles it already saw excluded, then force-passes the best of what it has.
A run always ends in a report.

**A judgement drifts, and nobody notices.** The ranking never asks a model. It
is a weighted average over the reviewer scores:

```
score = Σ (weight × score × confidence) / 10
```

A regression test freezes that formula against a stored panel, so one set of
reviews always gives one ranking. Temperature is a per-agent policy for the
same reason. The reviewers sit at 0.0 because they measure, and the research
agent sits at 1.0 because it invents. An agent whose author picked no
temperature fails to construct.

The reviewers are the part no type can check, so they are measured against a
hand-labelled dataset. Each label is a score band, never a number. Two people
who agree that an idea is commoditised still disagree on whether that is a 2 or
a 3. Calibration measures a reviewer against the human label. Variance measures
the same reviewer against its own repeats. Both call real models, so both stay
manual, spend-capped and off the pull request path.

**A web page can talk to your model.** Text a tool fetched is untrusted data.
Text an agent produced is pipeline data. That is the boundary, and web text
crosses it through one module. The text loses every control character and every
copy of the marker strings. That module then cuts it to a fixed length and
wraps it in markers it can no longer forge. The agent's system prompt carries a
rule that names both markers. It states that the text between them is data to
read, never instructions to follow. The rule raises the cost of an injection.
It does not prove the model obeys, and the specification says so.

**Every run accounts for itself.** Tokens, cost and wall time land in one total
per run, split by layer and by agent. The job stores that total, and the UI
renders it beside the report. Cost comes from a dated price table. A model the
table does not list is named in the output, never counted as free. Each
agent's system prompt is hashed, and the digest travels with the run, so two
runs compare only when they ran the same instructions.

**And it ships.** Terraform declares every GCP resource. A push to `master`
builds the image, and GitHub Actions deploys it through Workload Identity
Federation with no long-lived key. The API and the SPA share one Cloud Run
Service that scales to zero. The pipeline runs beside it as a Cloud Run Job
that writes to Firestore, because a ten-minute run does not belong inside an
HTTP request. Nothing under `tests/` calls a real model, so the whole suite
runs in CI with no API key and no spend.

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
