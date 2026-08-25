"""
Per-agent sampling temperature. This is the single place to change how much
spread an agent is allowed in its answers.

Temperature controls how widely a model samples among the words it thinks are
likely. At 0.0 it takes the most likely word every time, so the same input
gives close to the same answer. Higher values let it reach for less likely
words, so answers spread out.

The pipeline holds two kinds of agent and they want opposite settings:

  - An agent that judges is an instrument. Two runs over one idea should give
    one score, because a score that moves on its own cannot be compared with
    anything. These sit at MEASUREMENT.
  - An agent that invents is a generator. Its value is that it returns what
    the last run did not. These sit at DIVERGENCE.

The split does not follow the layer boundary. The research layer holds both
kinds: ResearchAgent invents ideas, while TrendScanner pulls signals out of
pages it is handed and NicheValidator answers yes or no. Only the first one
wants spread.

Caution 1: lower temperature narrows the spread, it does not remove it. A
provider can still return two different answers for one input at 0.0. Read
these settings as reduced variance, never as a repeatable result.

Caution 2: the exact number inside a band is a judgement call, not a measured
optimum. The evidence behind this file supports the ordering of the bands, not
0.5 over 0.4.

Caution 3: a few models reject a temperature setting and fail the call. Map an
agent to None to send no setting and take whatever the provider defaults to.
"""

# ── Bands ────────────────────────────────────────────────────────────────────

MEASUREMENT = 0.0
# The agent grades, extracts, or classifies. Spread here is measurement noise.

BALANCED = 0.5
# The agent builds something new but must stay tied to its input. Plans and
# rebuttals are wrong when invented, and dull when identical every run.

DIVERGENCE = 1.0
# The agent exists to produce variety. Spread here is the product.

# ── Canonical agent-key → temperature mapping (single source of truth) ───────
#
# The keys match DEFAULT_AGENT_MODELS in models.py exactly. PipelineConfig
# rejects a mapping where the two key sets differ, so a half-finished override
# fails at startup instead of mid-run.

DEFAULT_AGENT_TEMPERATURES: dict[str, float | None] = {
    # Layer 1: research. Two instruments and one generator.
    "trend_scanner": MEASUREMENT,
    # Reads pages it is given and lists the signals in them. Nothing here is
    # invention, so spread would only make the same page yield different lists.
    "research_agent": DIVERGENCE,
    # The one agent whose job is variety. It must return several ideas that
    # differ from each other, and the retry branch runs it a second time asking
    # for ideas unlike the ones already seen. Narrow sampling fights both.
    "niche_validator": MEASUREMENT,
    # Answers whether an idea is a duplicate or incumbent-owned. A yes or no
    # that changes between runs on one idea is a broken filter.
    # Layer 2: review panel. Every score feeds the weighted formula in
    # ReviewSynthesizer, and the eval harness compares those scores against
    # human labels. Both uses need the panel to behave as an instrument.
    "reviewer_market": MEASUREMENT,
    "reviewer_technical": MEASUREMENT,
    "reviewer_moat": MEASUREMENT,
    "reviewer_financial": MEASUREMENT,
    "reviewer_risk": MEASUREMENT,
    "reviewer_ai_resilience": MEASUREMENT,
    # Layer 3: planning. Construction work, held to its input.
    "mvp_architect": BALANCED,
    # Emits the most deeply nested output in the pipeline. Drift inside a
    # nested shape is expensive, but a sprint plan is design work, not a
    # reading of the idea.
    "gtm_strategist": BALANCED,
    # A channel plan that never varies is a template. One that ignores the
    # idea is useless.
    "business_plan_composer": BALANCED,
    # Merges two plans and has to keep them consistent, which argues low.
    # It also writes the narrative a reader sees, which argues against 0.0.
    # Layer 4: output.
    "devils_advocate": BALANCED,
    # Looks for the flaw that kills a plan. It has to find a real one, so it
    # stays tied to the plan, but a single fixed angle of attack would make it
    # miss everything that angle does not cover.
}

AGENT_TEMPERATURE_KEYS = tuple(DEFAULT_AGENT_TEMPERATURES)
