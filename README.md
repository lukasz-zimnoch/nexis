# Nexis

Autonomous multi-agent pipeline that generates, evaluates, and plans business ideas end-to-end. Orchestrated by LangGraph, runs without human intervention, and produces a structured report for the operator to review.

## How it works

The pipeline executes as a directed acyclic graph across four sequential layers:

1. **Deep Research** — A Research Agent scans the web, identifies trends, and generates N candidate business ideas with structured metadata. A Trend Scanner monitors HN, ProductHunt, Reddit, and X for real-time signals. A Niche Validator pre-filters duplicates and obvious incumbents.

2. **Parallel Review Panel** — Each idea is evaluated concurrently by five specialist critics (Market Analyst, Technical Feasibility, Competitive Moat, Financial Viability, Risk Assessor) using LangGraph's `Send()` API. A Review Synthesizer aggregates weighted scores and filters the top K ideas above a configurable threshold.

3. **MVP Scope & GTM Strategy** — For each surviving idea, an MVP Architect and GTM Strategist run in parallel. A Business Plan Composer merges their outputs into a cohesive plan.

4. **Validation & Output** — A Devil's Advocate agent adversarially stress-tests each plan. A Report Generator produces the final deliverable.

If all ideas in Layer 2 score below the threshold, the graph routes back to Layer 1 with a refined prompt (max 2 retries before force-passing the best available results).

## Setup

**Requirements:** Python 3.11+, [uv](https://docs.astral.sh/uv/)

```bash
uv sync
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and TAVILY_API_KEY
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
    model_name="claude-sonnet-4-6",
    num_ideas=8,
    top_k=3,
)

reports = run_pipeline(config)
```

Or via CLI:

```bash
uv run nexis \
  --prompt "B2B SaaS tools for small construction companies" \
  --model claude-sonnet-4-6
```

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `research_prompt` | *(required)* | Seed prompt describing the domain/constraints |
| `num_ideas` | `8` | Number of candidate ideas for Layer 1 to generate |
| `top_k` | `3` | Max ideas passed from Layer 2 to Layer 3 |
| `score_threshold` | `0.55` | Minimum aggregate score to pass Layer 2 filter |
| `max_retries` | `2` | Max retry loops if no ideas pass the threshold |
| `model_name` | *(required)* | LLM model for all agents |
| `output_format` | `markdown` | Final report format: `markdown` \| `json` |

## Project structure

```
nexis/
├── docs/
│   └── specification.md      # Full technical specification
├── src/nexis/
│   ├── __init__.py            # run_pipeline / arun_pipeline API
│   ├── __main__.py            # CLI entry point
│   ├── config.py              # PipelineConfig settings
│   ├── state.py               # PipelineState TypedDict + Pydantic models
│   ├── graph.py               # Parent graph (retry logic, supervisor)
│   ├── layers/                # Layer subgraphs
│   │   ├── research.py        # Layer 1: trend scanning + idea generation
│   │   ├── review.py          # Layer 2: Send() fan-out to 5 critics
│   │   ├── planning.py        # Layer 3: MVP + GTM concurrent planning
│   │   └── output.py          # Layer 4: validation + report generation
│   ├── agents/                # Agent implementations
│   │   ├── base.py            # BaseAgent (retry, structured output, timeout)
│   │   ├── research.py        # ResearchAgent, TrendScanner, NicheValidator
│   │   ├── reviewers.py       # 5 critic agents + ReviewSynthesizer
│   │   ├── planners.py        # MVPArchitect, GTMStrategist, BusinessPlanComposer
│   │   └── validators.py      # DevilsAdvocate, ReportGenerator
│   ├── tools/
│   │   ├── search.py          # Tavily search wrapper with backoff
│   │   └── trends.py          # Site-scoped trend scraper
│   └── templates/             # Jinja2 report templates
└── tests/
    ├── test_agents/           # Per-agent unit tests (mocked LLM)
    ├── test_layers/           # Per-layer subgraph tests
    ├── test_graph.py          # Parent graph routing tests
    ├── test_cli.py            # CLI argument parsing tests
    └── test_integration.py    # Full pipeline smoke test (mocked + live)
```

## Tech stack

- **Orchestration:** LangGraph 1.1+ (StateGraph, Send, subgraphs, checkpointing)
- **LLM:** configurable via `model_name`
- **Structured output:** LangChain `with_structured_output()` + Pydantic v2
- **Web search:** Tavily (primary), Serper (fallback)
- **Checkpointing:** PostgresSaver via `langgraph-checkpoint-postgres` (production), SqliteSaver via `langgraph-checkpoint-sqlite` (development)
- **Tracing:** LangSmith
- **Reports:** Jinja2 templates (markdown + JSON)

## Cost estimate

~$2.50 per run (8 candidate ideas, 3 surviving to Layer 3), based on ~57 LLM calls and ~330K tokens. Search tool costs are additional.

## Documentation

See [`docs/specification.md`](docs/specification.md) for the full technical specification, data contracts, scoring formula, and implementation patterns.
