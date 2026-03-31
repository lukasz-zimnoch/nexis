# Nexis

Autonomous multi-agent pipeline that generates, evaluates, and plans business ideas end-to-end. Orchestrated by LangGraph, runs without human intervention, and produces a structured report for the operator to review.

## How it works

The pipeline executes as a directed acyclic graph across four sequential layers:

1. **Deep Research** — A Research Agent scans the web, identifies trends, and generates N candidate business ideas with structured metadata. A Trend Scanner monitors HN, ProductHunt, and Reddit for real-time signals. A Niche Validator pre-filters duplicates and obvious incumbents.

2. **Parallel Review Panel** — Each idea is evaluated concurrently by six specialist critics (Market Analyst, Technical Feasibility, Competitive Moat, Financial Viability, Risk Assessor, AI Disruption Analyst) using LangGraph's `Send()` API. A Review Synthesizer aggregates weighted scores and filters the top K ideas above a configurable threshold.

3. **MVP Scope & GTM Strategy** — For each surviving idea, an MVP Architect and GTM Strategist run in parallel. A Business Plan Composer merges their outputs into a cohesive plan.

4. **Validation & Output** — A Devil's Advocate agent adversarially stress-tests each plan. A Report Generator produces the final deliverable.

If all ideas in Layer 2 score below the threshold, the graph routes back to Layer 1 with a refined prompt (max 2 retries before force-passing the best available results).

## Setup

**Requirements:** Python 3.11+, [uv](https://docs.astral.sh/uv/)

```bash
uv sync
cp .env.example .env
# Fill in OPENROUTER_API_KEY and TAVILY_API_KEY
```

**Run tests:**

```bash
uv run pytest tests/ -k "not live"
```

## Usage

```python
from nexis import run_pipeline
from nexis.config import PipelineConfig

config = PipelineConfig(
    research_prompt="B2B SaaS tools for small construction companies",
    num_ideas=8,
    top_k=3,
)

reports = run_pipeline(config)
```

Or via CLI:

```bash
uv run nexis --prompt "B2B SaaS tools for small construction companies"
```

To override all agents with a single model for quick testing:

```bash
uv run nexis --prompt "..." --model anthropic/claude-haiku-4-5
```

## Specification

[`docs/specification.md`](docs/specification.md) — Full technical specification covering architecture, data contracts, scoring formula, configuration reference, project structure, technology stack, and implementation patterns.

## Deployment

[`docs/deployment.md`](docs/deployment.md) — Infrastructure setup, CI/CD pipeline, required secrets, access control, and cost estimates.

## Architecture Decision Records

[`docs/adr/`](docs/adr/) — Records of key design decisions (orchestration framework, parallelism strategy, scoring approach, deployment model, etc.) with context, alternatives considered, and trade-offs.
