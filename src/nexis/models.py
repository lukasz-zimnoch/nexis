"""
Per-agent model assignments. This is the single place to change which model
powers each agent. Uses OpenRouter model IDs (provider/model-name).

All LLM calls are routed through OpenRouter — set OPENROUTER_API_KEY in .env.
See https://openrouter.ai/models for available IDs.

Every assignment below cites the evidence behind it. Read the two cautions in
the Sources block before you change one.
"""

# ── Sources and cautions ─────────────────────────────────────────────────────
# Benchmark claims below are quoted from these pages, all read on 2026-08-14.
#
#   [A1] Claude Opus 5      https://www.anthropic.com/news/claude-opus-5
#   [A2] Claude Sonnet 5    https://www.anthropic.com/news/claude-sonnet-5
#   [A3] Claude Haiku 4.5   https://www.anthropic.com/news/claude-haiku-4-5
#   [O1] GPT-5.6 series     https://openai.com/index/gpt-5-6/
#   [G1] Gemini 3.7 Flash   https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-3-7-flash/
#   [P1] Prices and context windows: OpenRouter /api/v1/models, read 2026-08-14.
#
# Caution 1: every benchmark quoted here is published by the vendor that sells
# the model. Vendors choose benchmarks that flatter their model. Treat these
# numbers as a starting point, not as proof, and confirm on your own task.
#
# Caution 2: prices are OpenRouter rates per million tokens, input/output.
# They do not always match the provider's own list price, so check OpenRouter
# and not the vendor page. Some models also charge more for very long prompts;
# where that applies it is noted on the assignment.

# ── Layer 1: Research ────────────────────────────────────────────────────────

TREND_SCANNER = "google/gemini-3.7-flash"
# Reads long, noisy web pages and pulls trend signals out of them.
# Google reports 34.0% on GDP.pdf, a benchmark for processing complex
# documents, against 22.0% for Gemini 3.6 Flash. Its context window is
# 1,048,576 tokens, so a wide batch of search results fits in one call.
# At 0.375/1.875 it is the cheapest model in this file, which matters because
# this node runs against every trend source. [G1] [P1]
# Alt: anthropic/claude-sonnet-5 (more reliable structured output, 5x the price)

RESEARCH_AGENT = "anthropic/claude-opus-5"
# Highest-leverage node — idea quality is set here.
# Anthropic reports Opus 5 about 3x above the next-best model on ARC-AGI 3,
# which measures solving problems the model has not seen before, and about
# 1.5x its pass rate on Zapier AutomationBench. Anthropic positions it for
# long-horizon work. Generating N distinct, non-obvious ideas in one pass is
# that shape of task. Price 5.00/25.00. [A1] [P1]
# Alt: openai/gpt-5.6-sol (evidence under GTM_STRATEGIST)

NICHE_VALIDATOR = "anthropic/claude-haiku-4.5"
# Binary classification: is this idea a duplicate, or incumbent-dominated?
# Haiku 4.5 scores 73.3% on SWE-bench Verified and reaches about 90% of
# Sonnet 4.5 in Augment's agentic coding eval. That is far more capability
# than a yes/no call needs, which is the point: Anthropic reports it 4-5x
# faster than Sonnet 4.5 at 1.00/5.00.
# Haiku has no version 5; 4.5 is the current small Claude model.  [A3] [P1]
# Alt: openai/gpt-5.6-luna (0.10/0.60, the cheapest model in the catalog)

# ── Layer 2: Review Panel ────────────────────────────────────────────────────

REVIEWER_MARKET = "openai/gpt-5.6-terra"
# Quantitative market reasoning: TAM/SAM/SOM, demand signals.
# OpenAI positions Terra as the balanced tier for everyday reasoning work,
# between the Sol flagship and the high-volume Luna tier. Every reviewer emits
# a score and a rationale that feed the weighted formula in ReviewSynthesizer,
# so the cheap tier is not enough here.
# Price 1.00/6.00, rising to 2.00/9.00 once a prompt passes 272k tokens.
# [O1] [P1]
# Alt: anthropic/claude-sonnet-5

REVIEWER_TECHNICAL = "anthropic/claude-sonnet-5"
# Judges stack choice and build feasibility.
# Anthropic calls Sonnet 5 its most agentic Sonnet and reports performance
# close to Opus 4.8 at a lower price. It also reports a lower hallucination
# rate than Sonnet 4.6, which matters for a reviewer that would otherwise
# invent plausible technical detail. Price 2.00/10.00, a third below Sonnet
# 4.6. [A2] [P1]
# Alt: openai/gpt-5.6-sol

REVIEWER_MOAT = "anthropic/claude-sonnet-5"
# Qualitative strategic reasoning: network effects, switching costs, data moats.
# Same evidence as REVIEWER_TECHNICAL. [A2]
# Alt: openai/gpt-5.6-sol

REVIEWER_FINANCIAL = "openai/gpt-5.6-terra"
# Unit economics: CAC, LTV, margin structure.
# Same tier reasoning as REVIEWER_MARKET. [O1]
# Alt: anthropic/claude-sonnet-5

REVIEWER_RISK = "anthropic/claude-sonnet-5"
# Adversarial review of regulatory and ethical risk.
# Anthropic reports Sonnet 5 refuses malicious requests more reliably and
# resists prompt injection better than Sonnet 4.6. This reviewer reads web
# text collected by the research layer, so injection resistance decides this
# assignment, not raw reasoning power. [A2]
# Alt: openai/gpt-5.6-sol

REVIEWER_AI_RESILIENCE = "anthropic/claude-sonnet-5"
# Judges whether the next frontier model release would erase the idea.
# Same evidence as REVIEWER_TECHNICAL. Note the bias this creates: a Claude
# model rates how exposed a business is to AI progress, so it judges its own
# ecosystem. If these scores look consistently optimistic, cross-check this
# role against openai/gpt-5.6-sol first. [A2]
# Alt: openai/gpt-5.6-sol

# ── Layer 3: Planning ────────────────────────────────────────────────────────

MVP_ARCHITECT = "anthropic/claude-opus-5"
# Emits the most deeply nested structured output in the pipeline: sprints,
# features, tech stack.
# Anthropic reports Opus 5 above every other model on Frontier-Bench v0.1 and
# ahead of Fable 5 on OSWorld 2.0. Both measure multi-step tasks where an early
# mistake spoils everything after it. A nested schema fails the same way.
# Price 5.00/25.00. [A1] [P1]
# Alt: anthropic/claude-sonnet-5 (acceptable for simpler ideas)

GTM_STRATEGIST = "openai/gpt-5.6-sol"
# Marketing strategy: ICP, channel plan, first-100 playbook.
# OpenAI reports Sol at 53.6 on Agents' Last Exam, 13.1 points above the next
# model, and 92.2% on BrowseComp. Both measure long, multi-step knowledge work,
# which is what a go-to-market plan is.
# This is the most expensive call in the pipeline: 5.00/30.00, rising to
# 10.00/45.00 above 272k prompt tokens. [O1] [P1]
# Alt: anthropic/claude-sonnet-5 (a third of the output price)

BUSINESS_PLAN_COMPOSER = "anthropic/claude-opus-5"
# Merges the MVP plan and the GTM plan into one narrative.
# Chosen for the long-horizon behaviour Anthropic reports for Opus 5: this node
# holds two full plans at once and has to keep them consistent. [A1]
# Alt: anthropic/claude-sonnet-5

# ── Layer 4: Output ──────────────────────────────────────────────────────────

DEVILS_ADVOCATE = "anthropic/claude-opus-5"
# Attacks a finished business plan and looks for the flaw that kills it.
# ARC-AGI 3, where Anthropic reports Opus 5 about 3x above the next-best model,
# measures solving unfamiliar problems. Finding a non-obvious flaw in a plan is
# that same shape of task. [A1]
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
