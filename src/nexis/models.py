"""
Per-agent model assignments. This is the single place to change which model
powers each agent. Uses OpenRouter model IDs (provider/model-name).

All LLM calls are routed through OpenRouter — set OPENROUTER_API_KEY in .env.
See https://openrouter.ai/models for available IDs.
"""

# ── Layer 1: Research ────────────────────────────────────────────────────────

TREND_SCANNER = "google/gemini-3-flash"
# Pro-level extraction at Flash speed; strong on long noisy web context.
# Alt: anthropic/claude-sonnet-4-6 (more reliable structured output)

RESEARCH_AGENT = "anthropic/claude-opus-4-6"
# Highest-leverage node — idea quality is set here. Best creative synthesis.
# Alt: openai/gpt-5.4 (strong ideation), google/gemini-3.1-pro (good synthesis)

NICHE_VALIDATOR = "anthropic/claude-haiku-4-5"
# Simple binary classification (duplicate / incumbent-dominated). Haiku suffices.
# Alt: openai/gpt-5.4-nano

# ── Layer 2: Review Panel ────────────────────────────────────────────────────

REVIEWER_MARKET = "openai/gpt-5.3-instant"
# Strong quantitative market reasoning: TAM/SAM/SOM, demand signals.
# Alt: anthropic/claude-sonnet-4-6

REVIEWER_TECHNICAL = "anthropic/claude-sonnet-4-6"
# Deep software engineering knowledge for stack/feasibility assessment.
# Alt: openai/gpt-5.4

REVIEWER_MOAT = "anthropic/claude-sonnet-4-6"
# Qualitative strategic reasoning: network effects, switching costs, data moats.
# Alt: openai/gpt-5.4

REVIEWER_FINANCIAL = "openai/gpt-5.3-instant"
# Unit economics, CAC/LTV, margin structure — GPT-5.x excels at financial ratios.
# Alt: anthropic/claude-sonnet-4-6

REVIEWER_RISK = "anthropic/claude-sonnet-4-6"
# Adversarial red-teaming; Claude is thorough on regulatory/ethical edge cases.
# Alt: openai/gpt-5.4

REVIEWER_AI_RESILIENCE = "anthropic/claude-sonnet-4-6"
# AI frontier awareness; Claude understands its own ecosystem and adjacent models.
# Alt: openai/gpt-5.4

# ── Layer 3: Planning ────────────────────────────────────────────────────────

MVP_ARCHITECT = "anthropic/claude-opus-4-6"
# Complex nested structured output (sprints, features, tech stack). Opus most reliable.
# Alt: anthropic/claude-sonnet-4-6 (acceptable for simpler ideas)

GTM_STRATEGIST = "openai/gpt-5.4"
# Marketing domain: ICP, channel strategy, first-100 playbooks. GPT-5.4 strongest here.
# Alt: anthropic/claude-sonnet-4-6

BUSINESS_PLAN_COMPOSER = "anthropic/claude-opus-4-6"
# Coherent long-form synthesis of MVP + GTM. Opus produces tightest narrative.
# Alt: anthropic/claude-sonnet-4-6

# ── Layer 4: Output ──────────────────────────────────────────────────────────

DEVILS_ADVOCATE = "anthropic/claude-opus-4-6"
# Deep adversarial reasoning over a full business plan; needs full context + nuance.
# Alt: openai/gpt-5.4

# ── Role → model mapping (keyed by ReviewerRole string values) ───────────────

REVIEWER_MODELS: dict[str, str] = {
    "market": REVIEWER_MARKET,
    "technical": REVIEWER_TECHNICAL,
    "moat": REVIEWER_MOAT,
    "financial": REVIEWER_FINANCIAL,
    "risk": REVIEWER_RISK,
    "ai_resilience": REVIEWER_AI_RESILIENCE,
}

AGENT_MODEL_KEYS = tuple([
    "trend_scanner", "research_agent", "niche_validator",
    "reviewer_market", "reviewer_technical", "reviewer_moat",
    "reviewer_financial", "reviewer_risk", "reviewer_ai_resilience",
    "mvp_architect", "gtm_strategist", "business_plan_composer",
    "devils_advocate",
])
