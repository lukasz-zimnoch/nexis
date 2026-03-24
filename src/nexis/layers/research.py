"""Layer 1: Research subgraph — trend scanning, idea generation, niche validation."""
from __future__ import annotations

import logging
import operator
from typing import Annotated

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from nexis.agents.research import NicheValidator, ResearchAgent, TrendScanner
from nexis.config import PipelineConfig
from nexis.telemetry import instrument_node
from nexis.state import (
    BusinessIdea,
    BusinessPlan,
    GTMPlan,
    MVPPlan,
    Rebuttal,
    Report,
    Review,
    TrendSignal,
    merge_dicts,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Subgraph-local state
#
# - `trend_signals_buffer`: accumulates signals from TrendScanner
# - `raw_ideas_buffer`:     accumulates raw ideas from ResearchAgent
# - `ideas`:                receives only validated ideas from NicheValidator
#                           (written once, not accumulated)
# ---------------------------------------------------------------------------


class ResearchLayerState(TypedDict):
    # ---- PipelineState fields ----
    config: PipelineConfig
    research_prompt: str
    iteration: int
    ideas: Annotated[list[BusinessIdea], operator.add]
    reviews: Annotated[list[Review], operator.add]
    scores: Annotated[dict[str, float], merge_dicts]
    top_ideas: list[str]
    mvp_plans: Annotated[dict[str, MVPPlan], merge_dicts]
    gtm_plans: Annotated[dict[str, GTMPlan], merge_dicts]
    business_plans: Annotated[dict[str, BusinessPlan], merge_dicts]
    rebuttals: Annotated[dict[str, Rebuttal], merge_dicts]
    final_reports: Annotated[list[Report], operator.add]
    # ---- Layer-local buffers ----
    trend_signals_buffer: Annotated[list[TrendSignal], operator.add]
    raw_ideas_buffer: Annotated[list[BusinessIdea], operator.add]


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------


async def trend_scanner_node(state: ResearchLayerState) -> dict:
    """Run TrendScanner and store signals in trend_signals_buffer."""
    config: PipelineConfig = state["config"]
    research_prompt: str = state["research_prompt"]

    # Extract simple keyword seeds from the research prompt
    keywords = [w for w in research_prompt.replace(",", " ").split() if len(w) > 3][:8]
    if not keywords:
        keywords = [research_prompt[:50]]

    agent = TrendScanner(
        model_name=config.model_for("trend_scanner"),
        max_retries=config.max_retries,
    )

    try:
        output = await agent.invoke(keywords=keywords)
        signals = output.signals
        logger.info("TrendScanner produced %d signals", len(signals))
    except Exception as exc:
        logger.warning("TrendScanner failed: %s — continuing with empty signals", exc)
        signals = []

    return {"trend_signals_buffer": signals}


async def research_agent_node(state: ResearchLayerState) -> dict:
    """Run ResearchAgent and store raw ideas in raw_ideas_buffer."""
    config: PipelineConfig = state["config"]
    research_prompt: str = state["research_prompt"]
    trend_signals: list[TrendSignal] = state.get("trend_signals_buffer", [])

    agent = ResearchAgent(
        model_name=config.model_for("research_agent"),
        max_retries=config.max_retries,
    )

    try:
        output = await agent.invoke(
            research_prompt=research_prompt,
            trend_signals=trend_signals,
            config=config,
        )
        ideas = output.ideas
        logger.info("ResearchAgent generated %d ideas", len(ideas))
    except Exception as exc:
        logger.warning("ResearchAgent failed: %s — continuing with empty ideas", exc)
        ideas = []

    # Store in buffer; NicheValidator will write validated subset to `ideas`
    return {"raw_ideas_buffer": ideas}


async def niche_validator_node(state: ResearchLayerState) -> dict:
    """Run NicheValidator on raw_ideas_buffer and write validated ideas to `ideas`."""
    config: PipelineConfig = state["config"]
    raw_ideas: list[BusinessIdea] = state.get("raw_ideas_buffer", [])

    if not raw_ideas:
        logger.info("NicheValidator: no ideas to validate, skipping")
        return {}

    agent = NicheValidator(
        model_name=config.model_for("niche_validator"),
        max_retries=config.max_retries,
    )

    try:
        output = await agent.invoke(ideas=raw_ideas)
        validated = output.ideas
        logger.info(
            "NicheValidator filtered %d ideas down to %d", len(raw_ideas), len(validated)
        )
    except Exception as exc:
        logger.warning("NicheValidator failed: %s — keeping original ideas", exc)
        validated = raw_ideas

    # `ideas` uses operator.add — write the validated list here so the
    # parent graph accumulates it correctly
    return {"ideas": validated}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_research_subgraph():
    """Build and compile the Layer 1 research subgraph."""
    graph = StateGraph(ResearchLayerState)

    graph.add_node("trend_scanner_node", instrument_node(trend_scanner_node, layer_id="research"))
    graph.add_node("research_agent_node", instrument_node(research_agent_node, layer_id="research"))
    graph.add_node("niche_validator_node", instrument_node(niche_validator_node, layer_id="research"))

    graph.add_edge(START, "trend_scanner_node")
    graph.add_edge("trend_scanner_node", "research_agent_node")
    graph.add_edge("research_agent_node", "niche_validator_node")
    graph.add_edge("niche_validator_node", END)

    return graph.compile()
