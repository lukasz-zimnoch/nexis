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

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `research_prompt` | *(required)* | Seed prompt describing the domain/constraints |
| `num_ideas` | `8` | Number of candidate ideas for Layer 1 to generate |
| `top_k` | `3` | Max ideas passed from Layer 2 to Layer 3 |
| `score_threshold` | `0.55` | Minimum aggregate score to pass Layer 2 filter |
| `max_retries` | `2` | Max retry loops if no ideas pass the threshold |
| `agent_models` | *(per-agent defaults from `nexis/models.py`)* | Dict mapping agent keys to OpenRouter model IDs; use `--model` CLI flag to override all agents at once |
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
│   ├── models.py              # Per-agent model assignments (single source of truth)
│   ├── state.py               # PipelineState TypedDict + Pydantic models
│   ├── graph.py               # Parent graph (retry logic, supervisor)
│   ├── layers/                # Layer subgraphs
│   │   ├── research.py        # Layer 1: trend scanning + idea generation
│   │   ├── review.py          # Layer 2: Send() fan-out to 6 critics
│   │   ├── planning.py        # Layer 3: MVP + GTM concurrent planning
│   │   └── output.py          # Layer 4: validation + report generation
│   ├── agents/                # Agent implementations
│   │   ├── base.py            # BaseAgent (retry, structured output, timeout, OpenRouter routing)
│   │   ├── research.py        # ResearchAgent, TrendScanner, NicheValidator
│   │   ├── reviewers.py       # 6 critic agents + ReviewSynthesizer
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
- **LLM:** per-agent model assignments in `nexis/models.py`; all calls routed through OpenRouter (`OPENROUTER_API_KEY` required)
- **Structured output:** LangChain `with_structured_output()` + Pydantic v2
- **Web search:** Tavily
- **Checkpointing:** SqliteSaver via `langgraph-checkpoint-sqlite`
- **Tracing:** Structured logging (nexis.telemetry); LangSmith (opt-in via env vars)
- **Reports:** Jinja2 templates (markdown + JSON)

## Deployment

Nexis deploys to [Google Cloud Run](https://cloud.google.com/run) on every push to `master` that passes CI. It uses IAP (Identity-Aware Proxy) for email-based access control and scales to zero when idle.

### One-time GCP setup

```bash
export BILLING_ACCOUNT_ID=<your-billing-account-id>
bash scripts/setup-gcp.sh
```

The script creates the GCP project, enables APIs, sets up a deploy service account with Workload Identity Federation (keyless auth for GitHub Actions), and prints the secret values you need to add to GitHub.

### GitHub secrets required

| Secret | Value |
|---|---|
| `GCP_WIF_PROVIDER` | Output of `scripts/setup-gcp.sh` (step 6) |
| `GCP_SA_EMAIL` | `nexis-deploy@nexis-pipeline.iam.gserviceaccount.com` |
| `OPENROUTER_API_KEY` | Your OpenRouter API key |
| `TAVILY_API_KEY` | Your Tavily API key |
| `LANGCHAIN_API_KEY` | Your LangSmith API key (optional) |

Add these at: **Settings → Secrets and variables → Actions**

### GHCR package visibility

Cloud Run pulls the image from GHCR at deploy time using GCP credentials, not a GitHub token. The package must be **public**:

> GitHub → Settings → Packages → nexis → Change visibility → Public

### IAP access (after first deploy)

After the first successful deploy, grant access to specific emails:

```bash
gcloud beta iap web add-iam-policy-binding \
  --resource-type=cloud-run --service=nexis --region=us-central1 \
  --member="user:your-email@example.com" \
  --role="roles/iap.httpsResourceAccessor"
```

Enable IAP for the first time via the Cloud Console (Security → Identity-Aware Proxy) to auto-generate the OAuth consent screen.

### Cost

Cloud Run free tier covers typical pipeline usage (~10 runs/month × 10 min × 1 CPU = 1.7 CPU-hours, well within the 50 CPU-hour free limit). **Expected monthly cost: $0.**

## Cost estimate

~$2.80 per run (8 candidate ideas, 3 surviving to Layer 3), based on ~65 LLM calls and ~370K tokens. Search tool costs are additional.

## Documentation

See [`docs/specification.md`](docs/specification.md) for the full technical specification, data contracts, scoring formula, and implementation patterns.
