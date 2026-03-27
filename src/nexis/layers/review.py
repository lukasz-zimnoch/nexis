"""Layer 2: Review Panel — Send() fan-out across N ideas × 6 critics."""

from __future__ import annotations

import logging
import operator
from typing import Annotated

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from typing_extensions import TypedDict

from nexis.agents.reviewers import ReviewerAgent, ReviewSynthesizer, create_reviewer
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
    ReviewerRole,
    merge_dicts,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State definitions
# ---------------------------------------------------------------------------


class ReviewLayerState(TypedDict):
    """Full pipeline state extended with temporary per-task keys for Send()."""

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


class ReviewNodeState(TypedDict):
    """State passed to each individual review_node task via Send()."""

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
    # Per-task fields injected by Send()
    idea_to_review: BusinessIdea
    reviewer_role_to_use: ReviewerRole


# ---------------------------------------------------------------------------
# Routing function
# ---------------------------------------------------------------------------


def route_to_reviewers(state: ReviewLayerState) -> list[Send]:
    """Fan-out: send each (idea, role) pair to review_node."""
    sends = []
    for idea in state["ideas"]:
        for role in ReviewerRole:
            sends.append(
                Send(
                    "review_node",
                    {
                        **state,
                        "idea_to_review": idea,
                        "reviewer_role_to_use": role,
                    },
                )
            )
    return sends


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------


async def review_node(state: ReviewNodeState) -> dict:
    """Invoke the appropriate reviewer for a single (idea, role) pair."""
    config: PipelineConfig = state["config"]
    idea: BusinessIdea = state["idea_to_review"]
    role: ReviewerRole = state["reviewer_role_to_use"]

    agent: ReviewerAgent = create_reviewer(
        role=role,
        model_name=config.model_for(f"reviewer_{role.value}"),
        max_retries=config.max_retries,
    )

    logger.debug("Reviewing idea '%s' with role '%s'", idea.title, role.value)
    review = await agent.invoke_review(idea)

    return {"reviews": [review]}


async def synthesize_node(state: ReviewLayerState) -> dict:
    """Synthesize all reviews into scores and a ranked top_ideas list."""
    synthesizer = ReviewSynthesizer()
    scores, top_ideas = synthesizer.synthesize(
        reviews=state["reviews"],
        config=state["config"],
        ideas=state["ideas"],
    )
    logger.info(
        "Synthesized %d reviews → %d ideas above threshold",
        len(state["reviews"]),
        len(top_ideas),
    )
    return {"scores": scores, "top_ideas": top_ideas}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_review_subgraph():
    """Build and compile the Layer 2 review subgraph."""
    builder = StateGraph(ReviewLayerState)

    builder.add_node("review_node", instrument_node(review_node, layer_id="review"))
    builder.add_node(
        "synthesize_node", instrument_node(synthesize_node, layer_id="review")
    )

    builder.add_conditional_edges(START, route_to_reviewers, ["review_node"])
    builder.add_edge("review_node", "synthesize_node")
    builder.add_edge("synthesize_node", END)

    return builder.compile()
