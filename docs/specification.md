# Nexis — Technical Specification

**Multi-Agent Business Idea Pipeline · LangGraph Orchestrated System for Autonomous Ideation, Evaluation, and Planning**

| | |
|---|---|
| **Version** | 1.0 |
| **Date** | March 2026 |
| **Framework** | LangGraph (LangChain ecosystem) |
| **Runtime** | Python 3.11+ |
| **Status** | Draft |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Overview](#2-system-overview)
3. [Architecture](#3-architecture)
4. [Data Contracts](#4-data-contracts)
5. [LangGraph Implementation Patterns](#5-langgraph-implementation-patterns)
6. [Scoring and Filtering](#6-scoring-and-filtering)
7. [Configuration](#7-configuration)
8. [Observability and Error Handling](#8-observability-and-error-handling)
9. [Cost Estimation](#9-cost-estimation)
10. [Technology Stack](#10-technology-stack)
11. [Project Structure](#11-project-structure)
12. [Future Extensions](#12-future-extensions)

---

## 1. Executive Summary

This document specifies the architecture, agent design, data contracts, and implementation plan for an autonomous multi-agent system that generates, evaluates, and plans business ideas end-to-end. The system is orchestrated by LangGraph and runs without human intervention, producing a final report for the operator to review.

The pipeline consists of four layers: Deep Research (idea generation), Parallel Review Panel (multi-angle evaluation), MVP Scope and GTM Strategy (actionable planning), and Validation and Output (adversarial stress-testing and report generation). Each layer is implemented as a LangGraph subgraph composed into a single parent graph with shared typed state.

---

## 2. System Overview

### 2.1 Design Goals

- **Full autonomy:** The pipeline runs unattended from trigger to final report. No human-in-the-loop gates.
- **Parallel evaluation:** Multiple critic agents review each idea concurrently, reducing wall-clock time.
- **Typed contracts:** All agent inputs/outputs are Pydantic models. Malformed output triggers structured retry, not silent failure.
- **Composability:** Each layer is an independently testable subgraph. Layers can be swapped, extended, or bypassed.
- **Observability:** Every node emits structured logs. LangSmith integration for tracing, latency tracking, and cost attribution.

### 2.2 High-Level Flow

The system executes as a directed acyclic graph (DAG) with four sequential layers and one conditional retry edge:

1. **Layer 1 — Deep Research:** Research Agent + sub-agents scan the web, identify trends, and produce N candidate business ideas with structured metadata.
2. **Layer 2 — Parallel Review Panel:** Each idea is evaluated in parallel by 5 specialist critic agents. A Synthesis node aggregates scores, ranks ideas, and filters the top K above a configurable threshold.
3. **Layer 3 — MVP Scope & GTM:** For each surviving idea, an MVP Architect and GTM Strategist run concurrently. A Business Plan Composer merges their outputs into a cohesive plan.
4. **Layer 4 — Validation & Output:** A Devil's Advocate agent adversarially stress-tests each plan. A Report Generator produces the final deliverable with idea cards, scores, plans, and rebuttals.

*Conditional retry: If all ideas in Layer 2 score below the minimum threshold, the graph routes back to Layer 1 with a refined research query. Maximum 2 retries before forcing output of best available results.*

---

## 3. Architecture

### 3.1 Orchestration Layer

A single LangGraph `StateGraph` serves as the parent orchestrator. It owns the global `PipelineState` (a `TypedDict`) and routes execution between layer subgraphs via conditional edges. The Supervisor node is responsible for:

- Initializing state with the user-provided research prompt and configuration parameters.
- Invoking each layer subgraph in sequence, passing the shared state.
- Evaluating the conditional retry edge after Layer 2 (checking if any idea exceeds the score threshold).
- Tracking the iteration counter to enforce the maximum retry limit.
- Emitting structured telemetry events at each transition for LangSmith tracing.

### 3.2 Layer 1 — Deep Research

This layer is responsible for scanning external sources, identifying market opportunities, and producing structured business idea candidates.

| Agent | Responsibility | Inputs / Outputs | Tools / Model |
|---|---|---|---|
| **Research Agent** | Primary ideation. Performs web search, synthesizes trends, generates N candidate ideas with structured metadata. | In: research prompt, config · Out: `list[BusinessIdea]` | Tavily/Serper search, web scraper, LLM |
| **Trend Scanner** | Sub-agent. Monitors HN, ProductHunt, Reddit, X for emerging patterns. Feeds real-time signals into Research Agent context. | In: keyword seeds · Out: `list[TrendSignal]` | RSS feeds, API scrapers, social listeners |
| **Niche Validator** | Pre-filter. Checks search volume, identifies obvious incumbents, flags duplicates from prior runs. | In: `list[BusinessIdea]` · Out: `list[BusinessIdea]` (filtered) | Google Trends API, SimilarWeb, dedup cache |

### 3.3 Layer 2 — Parallel Review Panel

Each idea from Layer 1 is evaluated concurrently by six specialist critic agents using LangGraph's `Send()` API. This creates a dynamic fan-out of (N ideas × 6 critics) parallel executions, followed by a fan-in at the Review Synthesizer node.

| Agent | Responsibility | Inputs / Outputs | Tools / Model |
|---|---|---|---|
| **Market Analyst** | Evaluates TAM/SAM/SOM, market growth trajectory, timing, and demand signals. | In: `BusinessIdea` · Out: `Review` (score 1–10, rationale) | Web search, market data APIs, LLM |
| **Technical Feasibility** | Assesses whether a solo dev or small team can build an MVP in 4–8 weeks. Evaluates stack complexity, API dependencies, infra cost. | In: `BusinessIdea` · Out: `Review` (score 1–10, rationale) | GitHub trending, StackShare, LLM |
| **Competitive Moat** | Analyzes defensibility: network effects, data moats, switching costs, regulatory barriers. Flags commodity risk. | In: `BusinessIdea` · Out: `Review` (score 1–10, rationale) | Crunchbase, patent search, LLM |
| **Financial Viability** | Unit economics sanity check: estimated CAC, LTV, margin structure, path to ramen profitability. | In: `BusinessIdea` · Out: `Review` (score 1–10, rationale) | Pricing benchmarks, LLM |
| **Risk Assessor** | Red-teams the idea: regulatory risk, single points of failure, ethical concerns, market timing risk. | In: `BusinessIdea` · Out: `Review` (score 1–10, rationale) | Regulatory databases, LLM |
| **AI Disruption Analyst** | Evaluates resilience to AI replacement and commoditization: whether a foundation-model provider can replicate the core value, whether the idea builds on top of AI or competes against it, and how fast the AI frontier is moving in the domain. | In: `BusinessIdea` · Out: `Review` (score 1–10, rationale) | LLM |
| **Review Synthesizer** | Fan-in node. Aggregates all reviewer scores using a weighted formula. Ranks ideas, drops those below threshold, passes top K to Layer 3. | In: `list[Review]` · Out: `top_ideas[]`, `scores[]` | Scoring algorithm (no LLM) |

### 3.4 Layer 3 — MVP Scope & GTM Strategy

For each idea that passed Layer 2's filter, two agents run concurrently (via `asyncio.gather()` inside each per-idea node), then a composer merges their outputs.

| Agent | Responsibility | Inputs / Outputs | Tools / Model |
|---|---|---|---|
| **MVP Architect** | Defines core features (MoSCoW), tech stack recommendation, data model sketch, 4–8 week sprint plan, and estimated build cost. | In: `BusinessIdea` + `Reviews` · Out: `MVPPlan` | LLM, tech stack DB |
| **GTM Strategist** | Defines ICP, positioning, channel strategy (SEO/community/paid), pricing model, launch sequence, first 100 customers playbook. | In: `BusinessIdea` + `Reviews` · Out: `GTMPlan` | LLM, pricing benchmarks |
| **Business Plan Composer** | Merges MVP scope + GTM into a cohesive plan per idea. Adds executive summary, key assumptions, success metrics. | In: `MVPPlan` + `GTMPlan` · Out: `BusinessPlan` | LLM |

### 3.5 Layer 4 — Validation & Output

The final layer stress-tests plans and generates the deliverable. Fully autonomous with no human gate.

| Agent | Responsibility | Inputs / Outputs | Tools / Model |
|---|---|---|---|
| **Devil's Advocate** | Adversarial review. Challenges every plan: "What if a big player copies this in 2 weeks?" Forces plans to address weaknesses or get downranked. | In: `BusinessPlan` · Out: `Rebuttal` | LLM |
| **Report Generator** | Formats all artifacts into a structured deliverable: markdown or JSON report with idea cards, scores, MVP specs, GTM plans, and rebuttals. | In: `PipelineState` (full) · Out: `Report` (markdown/JSON) | Jinja2 templates |

---

## 4. Data Contracts

All inter-agent communication uses typed Pydantic models. The shared LangGraph state is a `TypedDict` containing these models. Any agent that returns malformed output triggers a structured retry (up to 2 attempts) before the pipeline logs the failure and continues with partial data.

### 4.1 Pipeline State

The top-level state object that flows through the entire graph:

| Field | Populated By | Description |
|---|---|---|
| `ideas: list[BusinessIdea]` | Layer 1 output | Candidate ideas with structured metadata |
| `reviews: list[Review]` | Layer 2 intermediate | Flat list of all critic reviews (accumulated via `operator.add` reducer) |
| `scores: dict[str, float]` | Layer 2 output | Weighted aggregate score per idea (0.0–1.0) |
| `top_ideas: list[str]` | Layer 2 output | IDs of ideas passing the filter threshold |
| `mvp_plans: dict[str, MVPPlan]` | Layer 3 output | MVP specification per surviving idea |
| `gtm_plans: dict[str, GTMPlan]` | Layer 3 output | Go-to-market strategy per surviving idea |
| `rebuttals: dict[str, Rebuttal]` | Layer 4 intermediate | Devil's advocate challenges per plan |
| `final_reports: list[Report]` | Layer 4 output | Formatted deliverable documents |
| `iteration: int` | Orchestrator | Retry loop counter (max 2) |

### 4.2 Core Models

#### 4.2.1 BusinessIdea

| Field | Type | Description |
|---|---|---|
| `id` | `str (uuid4)` | Unique identifier |
| `title` | `str` | Short descriptive title (max 80 chars) |
| `problem_statement` | `str` | The pain point this idea addresses |
| `target_market` | `str` | Primary customer segment |
| `revenue_model` | `str` | How the product generates revenue |
| `estimated_tam` | `str \| None` | Total addressable market estimate |
| `confidence` | `float (0–1)` | Research agent's self-assessed confidence |
| `sources` | `list[str]` | URLs of supporting research |
| `trend_signals` | `list[TrendSignal]` | Related trends from Trend Scanner |

#### 4.2.2 Review

| Field | Type | Description |
|---|---|---|
| `idea_id` | `str` | Reference to the evaluated BusinessIdea |
| `reviewer_role` | `str (enum)` | One of: market, technical, moat, financial, risk |
| `score` | `int (1–10)` | Numeric rating for this dimension |
| `rationale` | `str` | Structured reasoning for the score |
| `red_flags` | `list[str]` | Specific concerns or dealbreakers |
| `confidence` | `float (0–1)` | Reviewer's self-assessed confidence |

#### 4.2.3 MVPPlan

| Field | Type | Description |
|---|---|---|
| `idea_id` | `str` | Reference to the BusinessIdea |
| `core_features` | `list[Feature]` | MoSCoW-prioritized feature list |
| `tech_stack` | `TechStack` | Recommended languages, frameworks, infra |
| `data_model` | `str` | Textual description of key entities and relations |
| `sprint_plan` | `list[Sprint]` | 4–8 week breakdown with deliverables per sprint |
| `estimated_cost_usd` | `float` | Estimated total build cost (compute + APIs + labor) |
| `complexity_rating` | `str (enum)` | low \| medium \| high |

#### 4.2.4 GTMPlan

| Field | Type | Description |
|---|---|---|
| `idea_id` | `str` | Reference to the BusinessIdea |
| `icp` | `str` | Ideal Customer Profile description |
| `positioning` | `str` | One-line value proposition |
| `channels` | `list[Channel]` | Ranked acquisition channels with rationale |
| `pricing_model` | `PricingModel` | Pricing structure and suggested tiers |
| `launch_sequence` | `list[LaunchPhase]` | Phased launch plan with milestones |
| `first_100_playbook` | `str` | Specific tactics to acquire first 100 customers |

#### 4.2.5 Rebuttal

| Field | Type | Description |
|---|---|---|
| `idea_id` | `str` | Reference to the BusinessIdea |
| `challenges` | `list[Challenge]` | Specific adversarial arguments against the plan |
| `severity` | `str (enum)` | low \| medium \| high \| critical |
| `suggested_mitigations` | `list[str]` | Recommended responses to each challenge |
| `overall_survivability` | `float (0–1)` | Probability the plan survives real-world pressure |

---

## 5. LangGraph Implementation Patterns

### 5.1 Graph Composition

Each layer is implemented as an independent LangGraph `StateGraph` (subgraph) with its own nodes and edges. The parent graph composes these subgraphs as nodes, passing the shared `PipelineState` between them. This enables independent testing, deployment, and versioning of each layer.

The parent graph structure is:

```
START → supervisor → research_subgraph → review_subgraph → planning_subgraph → output_subgraph → END
```

Conditional edge from `review_subgraph`: if `max(scores) < threshold` AND `iteration < max_retries`, route back to `research_subgraph` with incremented iteration counter.

### 5.2 Fan-Out with Send()

Layer 2 uses LangGraph's `Send()` API to dynamically spawn parallel review tasks. The review subgraph's entry node iterates over all ideas and all reviewer roles, emitting a `Send()` call for each combination. This creates N × 5 parallel executions that write their `Review` objects into the shared state.

The fan-in is handled by the Review Synthesizer node, which has a conditional edge that only activates once all `Send()` tasks have completed (LangGraph manages this automatically via its internal task counter).

```python
def route_to_reviewers(state: PipelineState) -> list[Send]:
    sends = []
    for idea in state["ideas"]:
        for role in ReviewerRole:
            sends.append(Send("review_node", {
                "idea": idea,
                "reviewer_role": role,
            }))
    return sends
```

### 5.3 Concurrent Planning with asyncio.gather()

Layer 3 uses a `Send()` fan-out to create one planning node per surviving idea. Inside each `plan_idea_node`, the MVP Architect and GTM Strategist are invoked concurrently using `asyncio.gather()`, keeping both calls within a single LangGraph node to avoid the write-conflict complexity of parallel branches. The Business Plan Composer then merges their outputs into a `BusinessPlan`.

```python
async def plan_idea_node(state: PlanningNodeState) -> dict:
    mvp_plan, gtm_plan = await asyncio.gather(
        mvp_architect.invoke_mvp(idea, reviews),
        gtm_strategist.invoke_gtm(idea, reviews),
    )
    business_plan = await composer.invoke_plan(idea, mvp_plan, gtm_plan)
    return {"mvp_plans": {idea.id: mvp_plan}, "gtm_plans": {idea.id: gtm_plan}, ...}
```

### 5.4 Conditional Retry Edge

After the Review Synthesizer runs, a conditional edge evaluates:

- `len(top_ideas) == 0 AND iteration < 2`: route back to Layer 1's entry node with a refined prompt (appending "previous ideas were too generic, focus on underserved niches").
- `len(top_ideas) == 0 AND iteration >= 2`: force-pass the top 3 by score regardless of threshold, log a warning.
- `len(top_ideas) > 0`: proceed to Layer 3 normally.

```python
def should_retry(state: PipelineState) -> str:
    if len(state["top_ideas"]) > 0:
        return "planning_subgraph"
    if state["iteration"] < 2:
        return "research_subgraph"  # retry
    return "planning_subgraph"  # force-pass best available
```

### 5.5 Structured Output Enforcement

All LLM-backed agents use LangChain's `with_structured_output()` to bind Pydantic models to the LLM call. If the LLM returns output that fails validation, the framework automatically retries with the validation error appended to the prompt (up to 2 retries). On persistent failure, the agent writes a partial result with a `failure_reason` field that downstream nodes can handle gracefully.

### 5.6 Checkpointing and Persistence

The graph uses an `SqliteSaver` checkpointer. This enables full state persistence at every node transition, allowing the pipeline to be resumed from any point after a crash, and providing a complete audit trail for debugging and analysis.

---

## 6. Scoring and Filtering

### 6.1 Reviewer Weights

The Review Synthesizer computes a weighted aggregate score for each idea. Default weights (configurable via pipeline parameters):

| Reviewer | Weight | Rationale |
|---|---|---|
| **Market Analyst** | 0.25 | Market size and timing are the strongest predictors of startup success. |
| **Technical Feasibility** | 0.20 | Critical for a solo/small team constraint. Infeasible ideas waste all downstream compute. |
| **Financial Viability** | 0.20 | Unit economics must be plausible even at the idea stage. |
| **Competitive Moat** | 0.15 | Defensibility determines long-term value; reduced from 0.20 since AI-specific commodity risk is now covered separately. |
| **Risk Assessor** | 0.10 | Risk is a modifier, not a primary driver. Reduced from 0.15 since AI disruption risk is now covered separately. |
| **AI Disruption Analyst** | 0.10 | Meaningful but not dominant; ensures ideas exposed to AI commoditization are systematically penalized. |

### 6.2 Score Formula

For each idea, the aggregate score is:

```
score = Σ (weight_i × reviewer_score_i × reviewer_confidence_i) / 10
```

This normalizes to a 0.0–1.0 range. The confidence multiplier penalizes low-confidence reviews, preventing a reviewer from tanking an idea based on uncertain information.

### 6.3 Filter Threshold

Default threshold: **0.55** (configurable). Ideas scoring below this are dropped. The top K ideas (default K=3) proceed to Layer 3. If fewer than K ideas pass the threshold, all passing ideas proceed.

---

## 7. Configuration

All pipeline behavior is controlled via a `PipelineConfig` Pydantic model passed at invocation time:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `research_prompt` | `str` | *(required)* | The seed prompt describing the domain/constraints for idea generation |
| `num_ideas` | `int` | `8` | Number of candidate ideas for Layer 1 to generate |
| `top_k` | `int` | `3` | Maximum number of ideas to pass from Layer 2 to Layer 3 |
| `score_threshold` | `float` | `0.55` | Minimum aggregate score to pass Layer 2 filter |
| `max_retries` | `int` | `2` | Maximum retry loops if no ideas pass the threshold |
| `reviewer_weights` | `dict` | See §6.1 | Custom weights for the scoring formula |
| `model_name` | `str` | *(required)* | LLM model for all agents (overridable per agent) |
| `output_format` | `str` | `markdown` | Final report format: `markdown` \| `json` |

---

## 8. Observability and Error Handling

### 8.1 Tracing

Every node emits structured JSON events via the `nexis.telemetry` logger. Each event includes: node name, layer ID, latency (ms), input/output state keys, and errors. LLM call events additionally capture agent name, model name, token usage (input/output/total), attempt number, and success status. When `LANGCHAIN_TRACING_V2=true`, LangChain's built-in integration forwards all traces to LangSmith automatically.

### 8.2 Error Handling Strategy

- **LLM validation failure:** Retry with error context appended to prompt (max 2 retries). On persistent failure, write partial result with `failure_reason` field populated.
- **Tool failure (search, API):** Retry with exponential backoff (1s, 4s, 16s). On persistent failure, agent proceeds with available data and logs a warning.
- **Timeout:** Per-node timeout of 120 seconds. On timeout, the node is marked as failed and the pipeline continues with partial state.
- **Full pipeline failure:** Checkpointed state allows manual resume from the last successful node. Failed runs are logged with full state snapshot for debugging.

---

## 9. Cost Estimation

Approximate per-run cost assuming 8 candidate ideas with 3 surviving to Layer 3 (actual cost depends on the configured model):

| Layer | LLM Calls | Est. Tokens | Est. Cost |
|---|---|---|---|
| Layer 1 (Research) | 3 agents | ~40K tokens | ~$0.30 |
| Layer 2 (Review) | 8 × 5 + 1 = 41 calls | ~200K tokens | ~$1.50 |
| Layer 3 (Planning) | 3 × 3 = 9 calls | ~60K tokens | ~$0.45 |
| Layer 4 (Validation) | 3 + 1 = 4 calls | ~30K tokens | ~$0.25 |
| **Total** | **~57 LLM calls** | **~330K tokens** | **~$2.50** |

*Note: Costs are approximate based on March 2026 Anthropic API pricing. Actual costs vary with prompt complexity and retry frequency. Search tool costs (Tavily/Serper) are additional.*

---

## 10. Technology Stack

| Component | Technology |
|---|---|
| Orchestration | LangGraph 1.1+ (StateGraph, Send, subgraphs, checkpointing) |
| LLM Provider | Configurable via `model_name` |
| Structured Output | LangChain `with_structured_output()` + Pydantic v2 models |
| Web Search | Tavily Search API (primary), Serper API (fallback) |
| Checkpointing | SqliteSaver via `langgraph-checkpoint-sqlite` |
| Tracing | Structured logging via `nexis.telemetry`; LangSmith (opt-in via `LANGCHAIN_TRACING_V2`) |
| Runtime | Python 3.11+, asyncio for parallel execution |
| Package Management | uv |
| Configuration | Pydantic Settings with `.env` file support |
| Report Generation | Jinja2 templates (markdown + JSON output) |
| Deployment | Docker container (uv-based), triggered via CLI, API endpoint, or cron |

---

## 11. Project Structure

```
nexis/
├── pyproject.toml
├── .env.example
├── src/
│   ├── config.py              # PipelineConfig + settings
│   ├── state.py               # PipelineState TypedDict + Pydantic models
│   ├── graph.py               # Parent graph composition
│   ├── layers/
│   │   ├── research.py        # Layer 1 subgraph + agents
│   │   ├── review.py          # Layer 2 subgraph + critic agents
│   │   ├── planning.py        # Layer 3 subgraph + planning agents
│   │   └── output.py          # Layer 4 subgraph + report generator
│   ├── agents/
│   │   ├── base.py            # BaseAgent with retry + structured output
│   │   ├── research.py        # ResearchAgent, TrendScanner, NicheValidator
│   │   ├── reviewers.py       # All 5 critic agents
│   │   ├── planners.py        # MVPArchitect, GTMStrategist, Composer
│   │   └── validators.py      # DevilsAdvocate, ReportGenerator
│   ├── tools/
│   │   ├── search.py          # Tavily/Serper wrappers
│   │   └── trends.py          # HN, ProductHunt, Reddit scrapers
│   └── templates/
│       ├── report.md.j2       # Markdown report template
│       └── idea_card.md.j2    # Per-idea card template
├── tests/
│   ├── test_layers/           # Per-layer subgraph tests
│   ├── test_agents/           # Per-agent unit tests
│   └── test_integration.py    # Full pipeline integration test
├── Dockerfile
└── README.md
```

---

## 12. Future Extensions

Potential enhancements for subsequent iterations:

- **Memory across runs:** Persist idea history in a vector store to avoid regenerating similar ideas across runs and to track how the idea landscape evolves over time.
- **Domain specialization:** Add pluggable domain adapters (e.g., SaaS, marketplace, developer tools, Web3) that customize each agent's prompts and evaluation criteria for specific verticals.
- **Competitive intelligence layer:** Add a dedicated agent between Layer 1 and Layer 2 that performs deep competitive analysis (Crunchbase funding data, app store rankings, SEO analysis) and enriches each idea with competitive landscape data.
- **Automated validation:** After Layer 4, optionally trigger a Landing Page Generator agent that creates a simple validation page and a Distribution Agent that posts to relevant communities to test demand signal before any code is written.
- **Multi-model routing:** Use cheaper/faster models (Haiku) for pre-filtering and simple scoring, and route only complex reasoning tasks (research synthesis, GTM strategy) to more capable models (Sonnet/Opus).
- **A2A protocol integration:** Expose each layer as an A2A-compatible agent, enabling external systems to invoke individual layers or swap in alternative implementations built with other frameworks.
