# Nexis — Technical Specification

**Multi-Agent Business Idea Pipeline · LangGraph Orchestrated System for Autonomous Ideation, Evaluation, and Planning**

| | |
|---|---|
| **Version** | 1.0 |
| **Date** | March 2026 |
| **Framework** | LangGraph (LangChain ecosystem) |
| **Runtime** | Python 3.11+ |
| **Status** | Implemented |

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
9. [Run Call Volume](#9-run-call-volume)
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
- **Observability:** Every node emits structured JSON logs with its latency and, for each LLM call, the model, the token counts and the estimated cost. Each run adds up its own tokens, cost and time, and stores the total with the job. See §8.3. Optional LangSmith integration traces the call chain.
- **Async execution model:** The UI triggers jobs via the API; the pipeline runs out-of-band in a Cloud Run Job and writes results to Firestore. The UI polls for completion.
- **Marked trust boundary:** Text that a tool fetched from the web enters a prompt as data inside explicit markers, with a size cap. See §5.7.
- **Measured reviewers:** The review panel is checked against a frozen, hand-labelled dataset, and its run-to-run spread is measured rather than assumed. See §6.4.
- **Stated sampling:** Each agent runs at a temperature the project chooses, not at a provider default. Agents that judge are held steady; the agent that invents is allowed to spread. See §7.3.

### 2.2 High-Level Flow

The system executes as a directed acyclic graph (DAG) with four sequential layers and one conditional retry edge:

1. **Layer 1 — Deep Research:** Research Agent + sub-agents scan the web, identify trends, and produce N candidate business ideas with structured metadata.
2. **Layer 2 — Parallel Review Panel:** Each idea is evaluated in parallel by 6 specialist critic agents. A Synthesis node aggregates scores, ranks ideas, and filters the top K above a configurable threshold.
3. **Layer 3 — MVP Scope & GTM:** For each surviving idea, an MVP Architect and GTM Strategist run concurrently. A Business Plan Composer merges their outputs into a cohesive plan.
4. **Layer 4 — Validation & Output:** A Devil's Advocate agent adversarially stress-tests each plan. A Report Generator produces the final deliverable with idea cards, scores, plans, and rebuttals.

*Conditional retry: If all ideas in Layer 2 score below the minimum threshold, the graph routes back to Layer 1 with a refined research query. Maximum 2 retries before forcing output of best available results.*

End users interact with the pipeline through a React SPA served by the FastAPI container. The API authenticates requests via Firebase ID tokens, persists each job to Firestore, and triggers a Cloud Run Job execution that runs the pipeline described above. See §3.6 for the service/job surface.

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
| **Research Agent** | Primary ideation. Performs web search, synthesizes trends, generates N candidate ideas with structured metadata. | In: research prompt, config · Out: `list[BusinessIdea]` | Tavily search, LLM |
| **Trend Scanner** | Sub-agent. Monitors HN, ProductHunt, and Reddit for emerging patterns. Feeds real-time signals into Research Agent context. | In: keyword seeds · Out: `list[TrendSignal]` | Site-scoped Tavily search (HN, ProductHunt, Reddit), LLM |
| **Niche Validator** | Pre-filter. Identifies obvious incumbents and removes duplicates from the candidate list. | In: `list[BusinessIdea]` · Out: `list[BusinessIdea]` (filtered) | LLM |

The Research Agent and the Trend Scanner are the only agents that read text from the public web. That text enters their prompts as untrusted data under the rules in §5.7.

### 3.3 Layer 2 — Parallel Review Panel

Each idea from Layer 1 is evaluated concurrently by six specialist critic agents using LangGraph's `Send()` API. This creates a dynamic fan-out of N ideas × 6 critics parallel executions, followed by a fan-in at the Review Synthesizer node.

| Agent | Responsibility | Inputs / Outputs | Tools / Model |
|---|---|---|---|
| **Market Analyst** | Evaluates TAM/SAM/SOM, market growth trajectory, timing, and demand signals. | In: `BusinessIdea` · Out: `Review` (score 1–10, rationale) | LLM |
| **Technical Feasibility** | Assesses whether a solo dev or small team can build an MVP in 4–8 weeks. Evaluates stack complexity, API dependencies, infra cost. | In: `BusinessIdea` · Out: `Review` (score 1–10, rationale) | LLM |
| **Competitive Moat** | Scores the defensibility the idea's structure builds toward as the business matures, not the defensibility it holds pre-launch. Credits accumulated operational data, a qualification the business itself must buy, integration depth, and a maintained domain model. Named score anchors set the scale. Flags commodity risk. | In: `BusinessIdea` · Out: `Review` (score 1–10, rationale) | LLM |
| **Financial Viability** | Unit economics sanity check: estimated CAC, LTV, margin structure, path to ramen profitability. | In: `BusinessIdea` · Out: `Review` (score 1–10, rationale) | LLM |
| **Risk Assessor** | Red-teams the idea: regulatory risk, single points of failure, ethical concerns, market timing risk. | In: `BusinessIdea` · Out: `Review` (score 1–10, rationale) | LLM |
| **AI Disruption Analyst** | Evaluates resilience to AI replacement and commoditization: whether a foundation-model provider can replicate the core value, whether the idea builds on top of AI or competes against it, and how fast the AI frontier is moving in the domain. | In: `BusinessIdea` · Out: `Review` (score 1–10, rationale) | LLM |
| **Review Synthesizer** | Fan-in node. Aggregates all reviewer scores using a weighted formula. Ranks ideas, drops those below threshold, passes top K to Layer 3. | In: `list[Review]` · Out: `top_ideas[]`, `scores[]` | Scoring algorithm (no LLM) |

### 3.4 Layer 3 — MVP Scope & GTM Strategy

For each idea that passed Layer 2's filter, two agents run concurrently (via `asyncio.gather()` inside each per-idea node), then a composer merges their outputs.

| Agent | Responsibility | Inputs / Outputs | Tools / Model |
|---|---|---|---|
| **MVP Architect** | Defines core features (MoSCoW), tech stack recommendation, data model sketch, 4–8 week sprint plan, and estimated build cost. | In: `BusinessIdea` + `Reviews` · Out: `MVPPlan` | LLM |
| **GTM Strategist** | Defines ICP, positioning, channel strategy (SEO/community/paid), pricing model, launch sequence, first 100 customers playbook. | In: `BusinessIdea` + `Reviews` · Out: `GTMPlan` | LLM |
| **Business Plan Composer** | Merges MVP scope + GTM into a cohesive plan per idea. Adds executive summary, key assumptions, success metrics. | In: `BusinessIdea` + `MVPPlan` + `GTMPlan` · Out: `BusinessPlan` | LLM |

### 3.5 Layer 4 — Validation & Output

The final layer stress-tests plans and generates the deliverable. Fully autonomous with no human gate.

| Agent | Responsibility | Inputs / Outputs | Tools / Model |
|---|---|---|---|
| **Devil's Advocate** | Adversarial review. Challenges every plan: "What if a big player copies this in 2 weeks?" Forces plans to address weaknesses or get downranked. | In: `BusinessPlan` · Out: `Rebuttal` | LLM |
| **Report Generator** | Formats all artifacts into a structured deliverable: markdown or JSON report with idea cards, scores, MVP specs, GTM plans, and rebuttals. | In: `PipelineState` (full) · Out: `Report` (markdown/JSON) | Jinja2 templates |

### 3.6 Service Layer and Job Execution

Beyond the LangGraph pipeline itself, the system exposes a small web surface that lets authenticated users submit jobs and read back results:

- **FastAPI Service** (`src/nexis/server.py`) — serves three JSON endpoints (`POST /api/jobs`, `GET /api/jobs`, `GET /api/jobs/{id}`), `GET /health`, `GET /config.json` (unauthenticated Firebase Web SDK config composed from backend env), and the built React SPA (mounted from `frontend/dist/`). All `/api/*` endpoints require a Firebase ID token, verified by `src/nexis/auth.py`.
- **Firestore** (`src/nexis/firestore.py`) — the `jobs/` collection holds `JobRecord` documents (`id`, `user_id`, `status`, `config`, `created_at`, `started_at`, `completed_at`, `error`, `result`, `metrics`). The Service writes the initial `pending` record; the Cloud Run Job updates status and writes the final result.
- **Cloud Run Job** (`src/nexis/job_runner.py`) — invoked as `python -m nexis.job_runner`. Reads `JOB_ID` and per-run pipeline parameters from env overrides, builds the graph with MemorySaver, invokes it, and persists the resulting `list[Report]` on success (or an `error` string on failure). It writes the run metrics of §8.3 in both cases, and uses `JOB_ID` as the run ID.
- **Job Trigger** (`src/nexis/job_trigger.py`) — the Service calls `trigger_job_execution()`, which issues a `run_v2.RunJobRequest` with per-run env overrides for the primary container. The returned LRO is intentionally not awaited — progress is observed via Firestore status transitions written by `job_runner`.
- **React SPA** (`frontend/`) — login page + dashboard + per-job detail page. At startup it fetches `/config.json` and initialises the Firebase Web SDK with the returned config, so no Firebase values are baked into the static bundle. Authenticates against Firebase, polls `/api/jobs*` while any job is in `pending`/`running` state, and renders the markdown report on completion.

---

## 4. Data Contracts

All inter-agent communication uses typed Pydantic models. The shared LangGraph state is a `TypedDict` containing these models. Any agent that returns malformed output triggers a structured retry (up to 2 attempts) before the pipeline logs the failure and continues with partial data.

### 4.1 Pipeline State

The top-level state object that flows through the entire graph:

| Field | Populated By | Description |
|---|---|---|
| `config: PipelineConfig` | Invocation | Configuration parameters passed at pipeline start |
| `research_prompt: str` | Supervisor node | Current research prompt; updated on each retry with refinement suffix |
| `iteration: int` | Orchestrator | Retry loop counter (max `config.max_retries`) |
| `ideas: list[BusinessIdea]` | Layer 1 output | Candidate ideas with structured metadata |
| `reviews: list[Review]` | Layer 2 intermediate | Flat list of all critic reviews (accumulated via `operator.add` reducer) |
| `scores: dict[str, float]` | Layer 2 output | Weighted aggregate score per idea (0.0–1.0) |
| `top_ideas: list[str]` | Layer 2 output | IDs of ideas passing the filter threshold |
| `mvp_plans: dict[str, MVPPlan]` | Layer 3 output | MVP specification per surviving idea |
| `gtm_plans: dict[str, GTMPlan]` | Layer 3 output | Go-to-market strategy per surviving idea |
| `business_plans: dict[str, BusinessPlan]` | Layer 3 output | Combined MVP + GTM plan per surviving idea |
| `rebuttals: dict[str, Rebuttal]` | Layer 4 intermediate | Devil's advocate challenges per plan |
| `final_reports: list[Report]` | Layer 4 output | Formatted deliverable documents |

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
| `iteration` | `int` | Pipeline retry iteration that produced this idea (0-based) |
| `failure_reason` | `str \| None` | Populated on persistent LLM failure; downstream nodes handle gracefully |

#### 4.2.2 Review

| Field | Type | Description |
|---|---|---|
| `idea_id` | `str` | Reference to the evaluated BusinessIdea |
| `reviewer_role` | `str (enum)` | One of: market, technical, moat, financial, risk, ai_resilience |
| `score` | `int (1–10)` | Numeric rating for this dimension |
| `rationale` | `str` | Structured reasoning for the score |
| `red_flags` | `list[str]` | Specific concerns or dealbreakers |
| `confidence` | `float (0–1)` | Reviewer's self-assessed confidence |
| `failure_reason` | `str \| None` | Populated on persistent LLM failure; downstream nodes handle gracefully |

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
| `failure_reason` | `str \| None` | Populated on persistent LLM failure; downstream nodes handle gracefully |

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
| `failure_reason` | `str \| None` | Populated on persistent LLM failure; downstream nodes handle gracefully |

#### 4.2.5 Rebuttal

| Field | Type | Description |
|---|---|---|
| `idea_id` | `str` | Reference to the BusinessIdea |
| `challenges` | `list[Challenge]` | Specific adversarial arguments against the plan |
| `severity` | `str (enum)` | low \| medium \| high \| critical |
| `suggested_mitigations` | `list[str]` | Recommended responses to each challenge |
| `overall_survivability` | `float (0–1)` | Probability the plan survives real-world pressure |
| `failure_reason` | `str \| None` | Populated on persistent LLM failure; downstream nodes handle gracefully |

#### 4.2.6 BusinessPlan

| Field | Type | Description |
|---|---|---|
| `idea_id` | `str` | Reference to the BusinessIdea |
| `executive_summary` | `str` | High-level overview combining MVP scope and GTM strategy |
| `key_assumptions` | `list[str]` | Critical assumptions the plan depends on |
| `success_metrics` | `list[str]` | Measurable outcomes to track progress |
| `mvp_plan` | `MVPPlan` | Full MVP specification (embedded) |
| `gtm_plan` | `GTMPlan` | Full go-to-market strategy (embedded) |
| `failure_reason` | `str \| None` | Populated on persistent LLM failure; downstream nodes handle gracefully |

---

## 5. LangGraph Implementation Patterns

### 5.1 Graph Composition

Each layer is implemented as an independent LangGraph `StateGraph` (subgraph) with its own nodes and edges. The parent graph composes these subgraphs as nodes, passing the shared `PipelineState` between them. This enables independent testing, deployment, and versioning of each layer.

The parent graph structure is:

```
START → supervisor → research → review → [should_retry] → planning → output → END
                         ↑                     ↓
                   supervisor ← increment_iteration   (retry path)
                                               ↓
                                          force_pass → planning   (retries exhausted)
```

After the `review` node, a conditional edge routes to one of three targets based on whether ideas passed the threshold and whether retries remain (see §5.4 for details).

### 5.2 Fan-Out with Send()

Layer 2 uses LangGraph's `Send()` API to dynamically spawn parallel review tasks. The review subgraph's entry node iterates over all ideas and all reviewer roles, emitting a `Send()` call for each combination. This creates N × 6 parallel executions that write their `Review` objects into the shared state.

The fan-in is handled by the Review Synthesizer node, which has a conditional edge that only activates once all `Send()` tasks have completed (LangGraph manages this automatically via its internal task counter).

```python
def route_to_reviewers(state: ReviewLayerState) -> list[Send]:
    sends = []
    for idea in state["ideas"]:
        for role in ReviewerRole:
            sends.append(Send("review_node", {
                **state,
                "idea_to_review": idea,
                "reviewer_role_to_use": role,
            }))
    return sends
```

### 5.3 Concurrent Planning with asyncio.gather()

Layer 3 uses a `Send()` fan-out to create one planning node per surviving idea. Inside each `plan_idea_node`, the MVP Architect and GTM Strategist are invoked concurrently using `asyncio.gather()`, keeping both calls within a single LangGraph node to avoid the write-conflict complexity of parallel branches. The Business Plan Composer then merges their outputs into a `BusinessPlan`.

```python
async def plan_idea_node(state: PlanningLayerState) -> dict:
    idea_id = state["idea_to_plan_id"]
    idea = next(i for i in state["ideas"] if i.id == idea_id)
    idea_reviews = [r for r in state["reviews"] if r.idea_id == idea_id]
    config = state["config"]

    mvp_architect = MVPArchitect(
        model_name=config.model_for("mvp_architect"),
        temperature=config.temperature_for("mvp_architect"),
    )
    gtm_strategist = GTMStrategist(
        model_name=config.model_for("gtm_strategist"),
        temperature=config.temperature_for("gtm_strategist"),
    )

    mvp_result, gtm_result = await asyncio.gather(
        mvp_architect.invoke_mvp(idea, idea_reviews),
        gtm_strategist.invoke_gtm(idea, idea_reviews),
        return_exceptions=True,
    )
    mvp_plan = _or_failure(mvp_result, mvp_architect, idea_id)
    gtm_plan = _or_failure(gtm_result, gtm_strategist, idea_id)

    composer = BusinessPlanComposer(
        model_name=config.model_for("business_plan_composer"),
        temperature=config.temperature_for("business_plan_composer"),
    )
    business_plan = await composer.invoke_plan(idea, mvp_plan, gtm_plan)

    return {
        "mvp_plans": {idea_id: mvp_plan},
        "gtm_plans": {idea_id: gtm_plan},
        "business_plans": {idea_id: business_plan},
    }
```

**One branch of a fan-out must never sink the others.** Every `asyncio.gather()` in the pipeline follows this rule, in one of two ways. Either the coroutine catches its own errors, as `TrendScraperTool` does per source, or the `gather()` passes `return_exceptions=True` and the caller handles each branch. Layer 3 turns a raised branch into a failure result through `BaseAgent.failure_result()`, which is the same partial result the agent builds for itself when it runs out of retries (ADR-0007). An agent whose schema has no minimal value cannot build that result; Layer 3 then drops the one idea and Layer 4 reports on the ideas that survived.

### 5.4 Conditional Retry Edge

After the Review Synthesizer runs, a `should_retry` function evaluates the state and returns one of three routing keys:

- `"planning"` — `top_ideas` is non-empty; proceed to Layer 3 normally.
- `"retry"` — `top_ideas` is empty AND `iteration < config.max_retries`; route to `increment_iteration` → `supervisor` → Layer 1 with a refined prompt (appending "previous ideas were too generic, focus on underserved niches" and an explicit exclusion list of previously generated idea titles). Ideas are tagged with their `iteration` number so that the review layer only fans out over ideas from the current iteration.
- `"force_pass"` — `top_ideas` is empty AND retries are exhausted; route to `force_pass` node which selects the top `config.top_k` ideas by raw score regardless of threshold, then proceeds to Layer 3.

```python
def should_retry(state: PipelineState) -> str:
    if state["top_ideas"]:
        return "planning"
    if state["iteration"] < state["config"].max_retries:
        return "retry"
    return "force_pass"
```

### 5.5 Structured Output Enforcement

All LLM-backed agents use LangChain's `with_structured_output()` to bind Pydantic models to the LLM call. If the LLM returns output that fails validation, the framework automatically retries with the validation error appended to the prompt (up to 2 retries). On persistent failure, the agent writes a partial result with a `failure_reason` field that downstream nodes can handle gracefully.

**Schema complexity constraint:** Some LLM providers reject deeply nested JSON schemas that compile to large grammars. The `BusinessPlanComposer` works around this by using a lightweight `BusinessPlanSynthesis` output schema (containing only the composer-generated fields: `executive_summary`, `key_assumptions`, `success_metrics`) and assembling the full `BusinessPlan` (with embedded `MVPPlan` and `GTMPlan`) in application code. This avoids sending the entire nested schema tree through the structured output grammar compiler.

### 5.6 Checkpointing and Persistence

The graph uses a `MemorySaver` checkpointer. State is held in memory for the duration of a single pipeline run and is not persisted across runs. This is appropriate for the Cloud Run execution model where each job runs to completion in an isolated container.

### 5.7 Untrusted Web Content in Prompts

Text that a tool fetched from the web is untrusted data. Text that an agent produced is pipeline data. This is the trust boundary; ADR-0016 records the decision and its limits.

`src/nexis/untrusted.py` holds the boundary and every agent that reads web text uses it:

- **Marked.** The text sits between `<<<UNTRUSTED_WEB_CONTENT>>>` and `<<<END_UNTRUSTED_WEB_CONTENT>>>`, never merged into the surrounding instructions.
- **Cleaned.** Both markers and all control characters are removed from the text, so a page cannot forge a marker and close the block early.
- **Capped.** Each result is cut to `MAX_UNTRUSTED_CHARS` (500) and the cut is noted in the text. `max_results` caps the number of results; this caps their size.
- **Governed.** The system prompt of the agent carries one paragraph, `UNTRUSTED_DATA_RULE`, which names both markers and states that the text between them is data to analyze and never instructions to follow.

`TrendScraperTool` applies the same cap to `TrendSignal.signal`, because Firestore stores that string and the report renders it.

The rule is a convention, not a control: a model can still obey text inside the block. The block bounds what an attacker can spend and states the contract; it does not prove the model honours it.

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

### 6.4 Reviewer Calibration and Variance

§6.1 to §6.3 treat a reviewer score as a measurement. Two evals check that assumption. Both run from `nexis/evals` (ADR-0018).

**Calibration** asks whether a reviewer agrees with a human. `tests/evals/dataset.jsonl` holds frozen `BusinessIdea` objects. Each carries the score band one or more roles are expected to land in, and the written reasoning behind those bands. A score inside its band is correct, and the error is the distance to the nearest edge, which is zero inside. Each role must reach a minimum share of in-band scores; the default is 70%.

A label is a band and never a single value. A human can say that an obviously commoditised idea must not score 8 for moat, and cannot say whether it is a 2 or a 3. A role carries a band only where the label writer holds a firm opinion, so an unlabelled pair is reviewed but does not gate.

**Variance** asks whether a reviewer agrees with itself. The same ideas run N times, and the report gives the standard deviation of the score per role. This needs at least two repeats; one repeat produces an empty variance report rather than a zero.

**Collection is separate from analysis.** `collect` calls the models and appends every answer to `reviews.jsonl` as it arrives. `report` reads that directory, calls no API, and exits non-zero when a role misses the gate. It also names any role whose answers came from a prompt, a model, or a temperature that the code no longer uses, because an answer is evidence about what produced it and about nothing else; that note explains the numbers rather than judging them, so it leaves the exit code alone. The manifest records the temperature per role for this reason. A manifest written before that field existed records none and makes no claim, so the check skips it. Changing a metric, a band or a threshold therefore costs nothing, and an interrupted run keeps the answers it paid for. A manifest is written before the first call, so a run that dies halfway stays analysable.

**An eval never runs Layer 1.** The ideas are frozen, which holds every variable except the reviewer and keeps the search API out of the loop.

**Spending is capped in code.** The collector projects the cost from the price table (§8.3) and refuses to start above a limit passed on the command line. A model with no price stops the projection instead of counting as free. The manifest stores the projected and the measured cost side by side.

The workflow that runs the evals in CI is manual and never fires on a push or a pull request. The formula in §6.2 needs no LLM, and is frozen separately in a regression test that runs in the ordinary CI job.

---

## 7. Configuration

### 7.1 PipelineConfig

All pipeline behavior is controlled via a `PipelineConfig` Pydantic model passed at invocation time:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `research_prompt` | `str` | *(required)* | The seed prompt describing the domain/constraints for idea generation |
| `num_ideas` | `int` | `8` | Number of candidate ideas for Layer 1 to generate |
| `top_k` | `int` | `3` | Maximum number of ideas to pass from Layer 2 to Layer 3 |
| `score_threshold` | `float` | `0.55` | Minimum aggregate score to pass Layer 2 filter |
| `max_retries` | `int` | `2` | Maximum retry loops if no ideas pass the threshold |
| `reviewer_weights` | `dict` | See §6.1 | Custom weights for the scoring formula |
| `agent_models` | `dict[str, str]` | Per-agent defaults from `nexis/models.py` | Maps agent keys (e.g. `"research_agent"`, `"reviewer_market"`) to OpenRouter model IDs. All LLM calls are routed through OpenRouter — `OPENROUTER_API_KEY` must be set. |
| `agent_temperatures` | `dict[str, float \| None]` | Per-agent defaults from `nexis/sampling.py` | Maps the same agent keys to a sampling temperature. `None` sends no temperature and takes the provider default. Must cover exactly the keys in `agent_models`, or the config refuses to build. See §7.3. |
| `output_format` | `str` | `markdown` | Final report format: `markdown` \| `json` |
| `llm_timeout` | `int` | `300` | Per-LLM-call timeout in seconds (enforced via `asyncio.wait_for`) |
| `fallback_model` | `str` | `google/gemini-3.7-flash` | Fallback model used when primary model times out (switched for remaining retries) |

### 7.2 Environment Variables

The backend and frontend both read configuration from environment variables. In Cloud Run, non-secret values come from Terraform (`infrastructure/terraform/cloud_run_service.tf`, `cloud_run_job.tf`); API keys come from Secret Manager. Locally, put the required entries in `.env` (see `.env.example`).

**Backend — required (no default).** Must be set for both the Cloud Run Service and the Cloud Run Job:

| Variable | Read in | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | `src/nexis/agents/base.py` | OpenRouter API key for all LLM calls |
| `TAVILY_API_KEY` | Tavily SDK (picked up from env) | Tavily web search API key |
| `GCP_PROJECT_ID` | `src/nexis/auth.py`, `firestore.py`, `job_trigger.py` | GCP project ID; also used as the Firebase project ID by the Admin SDK and as the Web SDK `projectId` returned by `/config.json` |
| `GCP_REGION` | `src/nexis/job_trigger.py` | Region of the Cloud Run Job (e.g. `us-central1`) |
| `FIREBASE_API_KEY` | `src/nexis/server.py` (`/config.json`) | Firebase Web SDK `apiKey`; served to the SPA at bootstrap. Safe to expose — real auth is enforced by the backend's ID-token check |

**Backend — optional.**

| Variable | Default | Purpose |
|---|---|---|
| `FIREBASE_AUTH_DOMAIN` | `<GCP_PROJECT_ID>.firebaseapp.com` | Firebase Web SDK `authDomain`; override only if using a custom auth domain |
| `LANGCHAIN_TRACING_V2` | `false` | Enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | *(unset)* | Required only when `LANGCHAIN_TRACING_V2=true` |
| `LANGCHAIN_PROJECT` | `nexis` | LangSmith project name |

**Cloud Run Job overrides.** Set per-run by `job_trigger.trigger_job_execution()` via `run_v2.RunJobRequest` container overrides. The operator does not set these — they come from the `JobConfig` submitted to `POST /api/jobs`.

| Variable | Default | Source |
|---|---|---|
| `JOB_ID` | *(required)* | Firestore document ID written by the Service |
| `RESEARCH_PROMPT` | *(required)* | `JobConfig.research_prompt` |
| `NUM_IDEAS` | `8` | `JobConfig.num_ideas` |
| `TOP_K` | `3` | `JobConfig.top_k` |
| `SCORE_THRESHOLD` | `0.55` | `JobConfig.score_threshold` |
| `OUTPUT_FORMAT` | `markdown` | `JobConfig.output_format` |

**Frontend.** The SPA has no build-time env vars. At startup it fetches `/config.json` from the backend, which returns `{apiKey, authDomain, projectId}` composed from the backend env vars above. This keeps all Firebase config on the server side, managed by Terraform alongside the rest of the Cloud Run env.

Do **not** set `FIREBASE_PROJECT_ID`; the Firebase Admin SDK is initialised from `GCP_PROJECT_ID` (the same GCP project hosts both), and `/config.json` reuses it for the Web SDK `projectId`. The Cloud Run Job name (`nexis-job`) is hardcoded in `job_trigger.py` and Terraform — it is not configurable per deployment.

### 7.3 Sampling Policy

Every agent runs at a temperature named in `src/nexis/sampling.py`. The pipeline holds two kinds of agent and they take opposite settings: an agent that judges is an instrument and must not move on its own, while an agent that invents exists to return what the last run did not.

| Band | Value | Agents |
|---|---|---|
| `MEASUREMENT` | `0.0` | the six reviewers, Trend Scanner, Niche Validator |
| `BALANCED` | `0.5` | MVP Architect, GTM Strategist, Business Plan Composer, Devil's Advocate |
| `DIVERGENCE` | `1.0` | Research Agent |

The split does not follow the layer boundary. Layer 1 holds both kinds: the Research Agent invents ideas, while the Trend Scanner lists signals in pages it is handed and the Niche Validator answers yes or no.

`build_llm()` and every agent constructor take `temperature` with no default, so an agent whose author never chose a value fails to construct. `_switch_to_fallback()` carries the same temperature to the fallback client, so a timeout cannot re-sample a reviewer at a different setting. `None` means "send no temperature", which is the way to handle a model that rejects the parameter.

Lower temperature narrows the spread; it does not remove it. Read these settings as reduced variance, never as a repeatable result. See ADR-0019.

---

## 8. Observability and Error Handling

### 8.1 Tracing

Every node emits structured JSON events via the `nexis.telemetry` logger. Each event includes: node name, layer ID, latency (ms), input/output state keys, and errors. LLM call events additionally capture agent name, model name, layer ID, token usage (input/output/total), estimated cost (USD), prompt version, attempt number, and success status. A null cost means no price is known for that model, not a free call. Every event of a run carries the same `run_id`, and each run closes with one `run_complete` event holding the totals of §8.3. When `LANGCHAIN_TRACING_V2=true`, LangChain's built-in integration forwards all traces to LangSmith automatically.

### 8.2 Error Handling Strategy

- **LLM validation failure:** Retry with error context appended to prompt (max 2 retries). On persistent failure, write partial result with `failure_reason` field populated.
- **Tool failure (search, API):** Immediate first attempt, then exponential backoff (1s, 4s, 16s). On persistent failure, agent proceeds with available data and logs a warning.
- **Timeout:** Per-LLM-call timeout configurable via `config.llm_timeout` (default 300s, enforced in `BaseAgent` via `asyncio.wait_for`). On timeout, the agent switches to `config.fallback_model` (default: `google/gemini-3.7-flash`) for remaining retries, keeping its sampling temperature (§7.3). If all retries are exhausted, a partial result with `failure_reason` is returned.
- **Full pipeline failure:** Failed runs are logged with full state snapshot for debugging.
- **Job trigger failure:** The Service marks the job `failed` and returns 503. The stored `error` and the response body both carry a fixed message. The exception detail stays in the log, because the client can read `JobRecord.error`.

### 8.3 Run Metrics

Each run adds up what it spent. `RunMetrics` (`src/nexis/metrics.py`) counts calls, input and output tokens, estimated cost and LLM seconds, in three views: run totals, per layer, and per agent. It also holds the wall time of the run, the prompt version of each agent, and the models it could not price.

| Property | Rule |
|---|---|
| **Scoped** | One `RunMetrics` per run, held in a context variable. asyncio copies the context into every task, so a fan-out adds to the run that started it and never to another run in the same process. |
| **Attributed** | `instrument_node()` publishes the layer it wraps, so an LLM call several frames below the node lands in the right layer bucket. A call outside any node lands in the `unattributed` bucket. |
| **Complete** | A call that failed validation counts, because the retry pays for both attempts. The metrics answer what a run cost, not what it bought. |
| **Honest** | Cost comes from a dated price table in `src/nexis/pricing.py`, so it is an estimate. A model missing from the table is named in `unpriced_models`, and its tokens still count. |
| **Persistent** | The Cloud Run Job writes the totals to `JobRecord.metrics` for a failed run as well as a completed one, and the SPA renders them beside the report. |

`llm_seconds` is the sum over calls and exceeds `wall_seconds` whenever a layer fans out. The two are reported separately: the ratio shows what concurrency saved.

The prompt version is the first 12 hex characters of the SHA-256 digest of an agent's system prompt. Two runs that report the same digest for an agent ran the same instructions. The rationale for all of this is in ADR-0017.

---

## 9. Run Call Volume

Cost is driven by how many LLM calls a run makes. The call count follows from the pipeline shape and the `num_ideas` / `top_k` settings, so it holds regardless of which models are assigned.

Assuming 8 candidate ideas with 3 surviving to Layer 3:

| Layer | LLM Calls |
|---|---|
| Layer 1 (Research) | 3 |
| Layer 2 (Review) | 8 × 6 + 1 = 49 |
| Layer 3 (Planning) | 3 × 3 = 9 |
| Layer 4 (Validation) | 3 + 1 = 4 |
| **Total** | **~65** |

Retries add to this. A failed structured-output validation re-invokes the same agent, and a Layer 2 retry re-runs Layers 1 and 2 for the newly generated ideas.

An eval run has a different shape: ideas × 6 roles × repeats, with Layer 1 never starting. The frozen dataset of 15 ideas therefore costs 90 calls per repeat (§6.4).

This specification does not price these calls. The per-call price depends on the model assigned to each agent and on that model's current OpenRouter rate, both of which change without any commit to this repository. See `nexis/models.py` for the current assignments and `nexis/pricing.py` for the dated price table the pipeline estimates with. Every run reports its own cost (§8.3), which is the number to trust over any figure written here. Tavily search is billed separately and is not in that total.

---

## 10. Technology Stack

| Component | Technology |
|---|---|
| Orchestration | LangGraph 1.1+ (StateGraph, Send, subgraphs, checkpointing) |
| LLM Provider | OpenRouter — all LLM calls route through `openrouter.ai/api/v1` (`OPENROUTER_API_KEY` required); per-agent model IDs defined in `nexis/models.py` |
| Structured Output | LangChain `with_structured_output()` + Pydantic v2 models |
| Web Search | Tavily Search API |
| Checkpointing | MemorySaver (in-memory, ephemeral per run) |
| Tracing | Structured logging via `nexis.telemetry`; LangSmith (opt-in via `LANGCHAIN_TRACING_V2`) |
| Runtime | Python 3.11+, asyncio for parallel execution |
| Package Management | uv |
| Configuration | Pydantic Settings with `.env` file support |
| Report Generation | Jinja2 templates (markdown + JSON output) |
| Web UI | React 18 + Vite 5 + TypeScript; served as static assets by the FastAPI container |
| Auth | Firebase Auth (email/password): Firebase Admin SDK server-side, Firebase Web SDK client-side |
| Job State | Firestore (native mode), `jobs/` collection with a composite index on (`user_id`, `created_at desc`) |
| Infrastructure as Code | Terraform with a GCS state backend |
| Deployment | Google Cloud Run Service (API + SPA) and Cloud Run Job (pipeline). `--allow-unauthenticated` at the platform level; Firebase Auth enforced at the app level. Image built and pushed to GHCR by GitHub Actions, pulled via an Artifact Registry pull-through cache. |

---

## 11. Project Structure

```
nexis/
├── docs/
│   ├── specification.md           # This document
│   ├── deployment.md              # Terraform + Firebase + Cloud Run runbook
│   └── adr/                       # Architecture Decision Records (19 ADRs)
├── infrastructure/
│   └── terraform/                 # Declarative GCP infrastructure (ADR-0012)
├── .github/workflows/             # CI (lint/test/build/push), deploy, and the manual eval workflow
├── src/nexis/
│   ├── layers/                    # Four LangGraph subgraphs (research, review, planning, output)
│   ├── agents/                    # Per-agent LLM wrappers and shared BaseAgent
│   ├── tools/                     # External tool integrations (Tavily search, trend scraping)
│   ├── evals/                     # Reviewer calibration and variance harness (ADR-0018)
│   └── templates/                 # Jinja2 templates for report generation
├── frontend/                      # React + Vite SPA (ADR-0015)
│   └── src/
│       ├── api/                   # HTTP client (Firebase Bearer token injection) and typed job calls
│       ├── auth/                  # Firebase Web SDK init, React auth context and hooks
│       ├── components/            # Layout, protected routes, job cards, forms, report viewer
│       ├── pages/                 # Login, dashboard, job detail
│       ├── lib/                   # Shared utilities (polling hook, formatting helpers)
│       └── test/                  # Vitest setup
├── tests/
│   ├── test_agents/               # Per-agent unit tests (mocked LLM)
│   ├── test_layers/               # Per-layer subgraph tests
│   ├── test_tools/                # Search and trend tool tests
│   ├── test_evals/                # Eval harness tests (stand-in reviewer, no API)
│   └── evals/                     # Frozen eval data: labelled dataset and scoring fixture
├── Dockerfile                     # Multi-stage: Node builds SPA → Python runtime
├── pyproject.toml
├── .env.example                   # Mandatory no-default backend env vars
├── CLAUDE.md                      # Claude Code development instructions
└── README.md
```

---

## 12. Future Extensions

Potential enhancements for subsequent iterations:

- **Memory across runs:** Persist idea history in a vector store to avoid regenerating similar ideas across runs and to track how the idea landscape evolves over time.
- **Domain specialization:** Add pluggable domain adapters (e.g., SaaS, marketplace, developer tools, Web3) that customize each agent's prompts and evaluation criteria for specific verticals.
- **Competitive intelligence layer:** Add a dedicated agent between Layer 1 and Layer 2 that performs deep competitive analysis (Crunchbase funding data, app store rankings, SEO analysis) and enriches each idea with competitive landscape data.
- **Automated validation:** After Layer 4, optionally trigger a Landing Page Generator agent that creates a simple validation page and a Distribution Agent that posts to relevant communities to test demand signal before any code is written.
- **A2A protocol integration:** Expose each layer as an A2A-compatible agent, enabling external systems to invoke individual layers or swap in alternative implementations built with other frameworks.
- **Tool enrichment:** Replace current LLM-only reviewer and validator agents with dedicated data-source integrations — e.g., market data APIs for the Market Analyst, Crunchbase for the Competitive Moat reviewer, regulatory databases for the Risk Assessor, and Google Trends / SimilarWeb for the Niche Validator. Add X/Twitter as an additional trend source alongside HN, ProductHunt, and Reddit.
- **Push-based job completion:** Replace the SPA's polling loop with a Firestore real-time listener or a Cloud Run Service push endpoint, so the dashboard updates instantly when a Cloud Run Job finishes.
