"""
Per-agent model assignments. This is the single place to change which model
powers each agent. Uses OpenRouter model IDs (provider/model-name).

All LLM calls are routed through OpenRouter — set OPENROUTER_API_KEY in .env.
See https://openrouter.ai/models for available IDs.
"""

# ── Layer 1: Research ────────────────────────────────────────────────────────

TREND_SCANNER = "google/gemini-3.7-flash"
# Pro-level extraction at Flash speed; strong on long noisy web context.
# Alt: anthropic/claude-sonnet-5 (more reliable structured output)

RESEARCH_AGENT = "anthropic/claude-opus-5"
# Highest-leverage node — idea quality is set here. Best creative synthesis.
# Alt: openai/gpt-5.6-sol (strong ideation)

NICHE_VALIDATOR = "anthropic/claude-haiku-4.5"
# Simple binary classification (duplicate / incumbent-dominated). Haiku suffices.
# Haiku has no version 5; 4.5 is the current small Claude model.
# Alt: openai/gpt-5.6-luna

# ── Layer 2: Review Panel ────────────────────────────────────────────────────

REVIEWER_MARKET = "openai/gpt-5.6-terra"
# Strong quantitative market reasoning: TAM/SAM/SOM, demand signals.
# Alt: anthropic/claude-sonnet-5

REVIEWER_TECHNICAL = "anthropic/claude-sonnet-5"
# Deep software engineering knowledge for stack/feasibility assessment.
# Alt: openai/gpt-5.6-sol

REVIEWER_MOAT = "anthropic/claude-sonnet-5"
# Qualitative strategic reasoning: network effects, switching costs, data moats.
# Alt: openai/gpt-5.6-sol

REVIEWER_FINANCIAL = "openai/gpt-5.6-terra"
# Unit economics, CAC/LTV, margin structure — GPT-5.x excels at financial ratios.
# Alt: anthropic/claude-sonnet-5

REVIEWER_RISK = "anthropic/claude-sonnet-5"
# Adversarial red-teaming; Claude is thorough on regulatory/ethical edge cases.
# Alt: openai/gpt-5.6-sol

REVIEWER_AI_RESILIENCE = "anthropic/claude-sonnet-5"
# AI frontier awareness; Claude understands its own ecosystem and adjacent models.
# Alt: openai/gpt-5.6-sol

# ── Layer 3: Planning ────────────────────────────────────────────────────────

MVP_ARCHITECT = "anthropic/claude-opus-5"
# Complex nested structured output (sprints, features, tech stack). Opus most reliable.
# Alt: anthropic/claude-sonnet-5 (acceptable for simpler ideas)

GTM_STRATEGIST = "openai/gpt-5.6-sol"
# Marketing domain: ICP, channel strategy, first-100 playbooks. Sol is the
# flagship GPT-5.6 tier and is strongest here.
# Alt: anthropic/claude-sonnet-5

BUSINESS_PLAN_COMPOSER = "anthropic/claude-opus-5"
# Coherent long-form synthesis of MVP + GTM. Opus produces tightest narrative.
# Alt: anthropic/claude-sonnet-5

# ── Layer 4: Output ──────────────────────────────────────────────────────────

DEVILS_ADVOCATE = "anthropic/claude-opus-5"
# Deep adversarial reasoning over a full business plan; needs full context + nuance.
# Alt: openai/gpt-5.6-sol

# ── Canonical agent-key → model mapping (single source of truth) ─────────────

DEFAULT_AGENT_MODELS: dict[str, str] = {
    "trend_scanner": TREND_SCANNER,
    "research_agent": RESEARCH_AGENT,
    "niche_validator": NICHE_VALIDATOR,
    "reviewer_market": REVIEWER_MARKET,
    "reviewer_technical": REVIEWER_TECHNICAL,
    "reviewer_moat": REVIEWER_MOAT,
    "reviewer_financial": REVIEWER_FINANCIAL,
    "reviewer_risk": REVIEWER_RISK,
    "reviewer_ai_resilience": REVIEWER_AI_RESILIENCE,
    "mvp_architect": MVP_ARCHITECT,
    "gtm_strategist": GTM_STRATEGIST,
    "business_plan_composer": BUSINESS_PLAN_COMPOSER,
    "devils_advocate": DEVILS_ADVOCATE,
}

AGENT_MODEL_KEYS = tuple(DEFAULT_AGENT_MODELS)
