"""Layer 4: Output subgraph — Devil's Advocate validation and report generation."""

from __future__ import annotations

import asyncio
import logging

from langgraph.graph import END, START, StateGraph

from nexis.agents.validators import DevilsAdvocate, ReportGenerator
from nexis.state import PipelineState
from nexis.telemetry import instrument_node

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------


async def devils_advocate_node(state: PipelineState) -> dict:
    """Run DevilsAdvocate over all top ideas' business plans in parallel."""
    config = state["config"]
    top_idea_ids = state.get("top_ideas", [])
    business_plans = state.get("business_plans", {})

    if not top_idea_ids:
        logger.info("devils_advocate_node: no top ideas — skipping validation")
        return {"rebuttals": {}}

    advocate = DevilsAdvocate(
        model_name=config.model_for("devils_advocate"),
        max_retries=config.max_retries,
        timeout=config.llm_timeout,
        fallback_model=config.fallback_model,
    )

    plans = [
        business_plans[idea_id] for idea_id in top_idea_ids if idea_id in business_plans
    ]

    if not plans:
        logger.warning(
            "devils_advocate_node: top_ideas present but no matching business_plans — skipping"
        )
        return {"rebuttals": {}}

    rebuttals_list = await asyncio.gather(
        *[advocate.invoke_rebuttal(plan) for plan in plans],
        return_exceptions=True,
    )

    rebuttals: dict = {}
    for plan, result in zip(plans, rebuttals_list):
        if isinstance(result, Exception):
            logger.warning(
                "DevilsAdvocate failed for idea %s: %s", plan.idea_id, result
            )
        else:
            rebuttals[plan.idea_id] = result

    return {"rebuttals": rebuttals}


async def report_generator_node(state: PipelineState) -> dict:
    """Render the final report from the full pipeline state."""
    generator = ReportGenerator()
    report = generator.generate(state)
    logger.info(
        "report_generator_node: generated %s report (%d ideas evaluated, %d selected)",
        report.format.value,
        report.ideas_evaluated,
        report.ideas_selected,
    )
    return {"final_reports": [report]}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_output_subgraph():
    """Build and compile the Layer 4 output subgraph."""
    builder = StateGraph(PipelineState)
    builder.add_node(
        "devils_advocate", instrument_node(devils_advocate_node, layer_id="output")
    )
    builder.add_node(
        "report_generator", instrument_node(report_generator_node, layer_id="output")
    )
    builder.add_edge(START, "devils_advocate")
    builder.add_edge("devils_advocate", "report_generator")
    builder.add_edge("report_generator", END)
    return builder.compile()
