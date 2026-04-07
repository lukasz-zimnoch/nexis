# ADR-0005: Per-Agent Model Specialization

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-03-29 |
| **Deciders** | Łukasz Zimnoch |

## Context

Nexis has 13 agents with meaningfully different cognitive demands:

- **Creative synthesis** (ResearchAgent): generating novel business ideas from
  trend signals — benefits from the highest-capability model available
- **Binary classification** (NicheValidator): deciding "duplicate or not" —
  a task that a fast, cheap model handles well
- **Domain-specific analysis** (ReviewerAgents): six specialized critics each
  requiring different reasoning strengths (quantitative financial reasoning,
  software engineering knowledge, strategic qualitative judgment)
- **Complex nested structured output** (MVPArchitect, BusinessPlanComposer):
  producing deeply nested Pydantic models with strict constraints — requires
  models with strong instruction-following reliability

Using the same model for all 13 agents would mean either overspending (using
Opus everywhere) or accepting lower quality (using a fast model everywhere).

## Decision

Each agent is assigned a specific model in `models.py`, which serves as the
single source of truth for all model assignments. `PipelineConfig` stores the
mapping as `agent_models: dict[str, str]`, allowing runtime overrides without
code changes. The default assignments are:

| Agent | Model | Rationale |
|-------|-------|-----------|
| `trend_scanner` | `google/gemini-3-flash-preview` | Fast extraction from long web context |
| `research_agent` | `anthropic/claude-opus-4-6` | Highest-leverage creative synthesis node |
| `niche_validator` | `anthropic/claude-haiku-4-5` | Simple binary classification |
| `reviewer_market` | `openai/gpt-5.3-instant` | Quantitative TAM/SAM/SOM reasoning |
| `reviewer_technical` | `anthropic/claude-sonnet-4-6` | Software engineering feasibility |
| `reviewer_moat` | `anthropic/claude-sonnet-4-6` | Strategic qualitative reasoning |
| `reviewer_financial` | `openai/gpt-5.3-instant` | Unit economics and margin structure |
| `reviewer_risk` | `anthropic/claude-sonnet-4-6` | Adversarial red-teaming |
| `reviewer_ai_resilience` | `anthropic/claude-sonnet-4-6` | AI ecosystem awareness |
| `mvp_architect` | `anthropic/claude-opus-4-6` | Complex nested structured output |
| `gtm_strategist` | `openai/gpt-5.4` | Marketing domain; channel and ICP strategy |
| `business_plan_composer` | `anthropic/claude-opus-4-6` | Long-form coherent synthesis |
| `devils_advocate` | `anthropic/claude-opus-4-6` | Deep adversarial reasoning |

## Considered Alternatives

### Option A: Single Model for All Agents

Use one model (e.g., `anthropic/claude-opus-4-6`) for all 13 agents.

**Pros**
- No configuration complexity; one API key, one model version to track
- Consistent behavior and failure modes across all agents

**Cons**
- Estimated cost per pipeline run: ~$3–5 using Opus everywhere vs. ~$1–2 with
  specialization
- Capabilities are mismatched: NicheValidator's binary task wastes Opus tokens;
  ResearchAgent's creative synthesis is underserved by Haiku

### Option B: Two-Tier (Strong / Weak)

Assign each agent to one of two tiers: a "strong" model (Opus) for complex
tasks and a "weak" model (Haiku) for simple ones.

**Pros**
- Simpler than per-agent assignment; only two models to manage

**Cons**
- Coarse-grained: ReviewerAgents span a wide range of reasoning demands that
  don't fit cleanly into two buckets
- Misses domain-specific strengths: GPT's financial reasoning and Gemini's
  long-context extraction are only accessible with provider diversity

### Option C: Dynamic Model Selection via LLM Router

Have a meta-agent select the best model for each task at runtime based on the
task description.

**Pros**
- Self-adapting; could use cheaper models as capabilities improve

**Cons**
- Adds latency (an extra LLM call before each agent invocation)
- The routing LLM itself needs to be chosen and trusted
- Non-deterministic: debugging becomes harder when the model assignment changes
  between runs

## Consequences

### Positive
- Estimated 40–60% cost reduction compared to all-Opus, with equal or better
  quality on domain-specific tasks
- Model assignments are readable documentation of which tasks are considered
  high-stakes
- Per-agent overrides in `PipelineConfig.agent_models` allow A/B testing model
  choices without code changes

### Negative
- 13 distinct model assignments mean 13 potential points of API contract change
  when providers release new versions
- Developers must understand the OpenRouter model ID format and check
  availability before assigning a new model

### Trade-offs
- Coupling to specific model versions (e.g., `gpt-5.3-instant` vs. `gpt-5.4`)
  creates drift risk as providers deprecate older versions. This is mitigated by
  centralizing all assignments in one file and documenting alternatives in inline
  comments.
