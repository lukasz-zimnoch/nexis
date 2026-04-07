"""Layer 3: Planning — parallel MVP + GTM branches per top idea."""

from __future__ import annotations

import asyncio
import logging

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from nexis.agents.planners import BusinessPlanComposer, GTMStrategist, MVPArchitect
from nexis.telemetry import instrument_node
from nexis.state import BusinessIdea, PipelineState, Review

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Planning node state
# ---------------------------------------------------------------------------


class PlanningNodeState(PipelineState):
    """PipelineState extended with per-idea routing key used by Send()."""

    idea_to_plan_id: str


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def route_to_planners(state: PipelineState) -> list[Send]:
    """Fan-out: one Send per top idea."""
    top_ideas: list[str] = state.get("top_ideas", [])
    return [
        Send("plan_idea_node", {**state, "idea_to_plan_id": idea_id})
        for idea_id in top_ideas
    ]


async def plan_idea_node(state: PlanningNodeState) -> dict:
    """Run MVP + GTM planners concurrently, then compose the business plan."""
    idea_id: str = state["idea_to_plan_id"]
    ideas: list[BusinessIdea] = state["ideas"]
    reviews: list[Review] = state["reviews"]
    config = state["config"]

    idea = next(i for i in ideas if i.id == idea_id)
    idea_reviews = [r for r in reviews if r.idea_id == idea_id]

    logger.info("Planning idea %s (%s)", idea_id, idea.title)

    mvp_architect = MVPArchitect(
        model_name=config.model_for("mvp_architect"),
        max_retries=config.max_retries,
        timeout=config.llm_timeout,
        fallback_model=config.fallback_model,
    )
    gtm_strategist = GTMStrategist(
        model_name=config.model_for("gtm_strategist"),
        max_retries=config.max_retries,
        timeout=config.llm_timeout,
        fallback_model=config.fallback_model,
    )

    mvp, gtm = await asyncio.gather(
        mvp_architect.invoke_mvp(idea, idea_reviews),
        gtm_strategist.invoke_gtm(idea, idea_reviews),
    )

    composer = BusinessPlanComposer(
        model_name=config.model_for("business_plan_composer"),
        max_retries=config.max_retries,
        timeout=config.llm_timeout,
        fallback_model=config.fallback_model,
    )
    plan = await composer.invoke_plan(idea, mvp, gtm)

    logger.info("Finished planning idea %s", idea_id)

    return {
        "mvp_plans": {idea_id: mvp},
        "gtm_plans": {idea_id: gtm},
        "business_plans": {idea_id: plan},
    }


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_planning_subgraph() -> StateGraph:
    """Build and compile the Layer 3 planning subgraph."""
    builder = StateGraph(PipelineState)

    builder.add_node(
        "plan_idea_node", instrument_node(plan_idea_node, layer_id="planning")
    )

    # Conditional fan-out from START: if top_ideas is empty, goes straight to END
    builder.add_conditional_edges(START, route_to_planners, ["plan_idea_node"])
    builder.add_edge("plan_idea_node", END)

    return builder.compile()
