"""Layer 2: Review Panel — Send() fan-out across N ideas × 6 critics."""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from nexis.agents.reviewers import ReviewerAgent, ReviewSynthesizer, create_reviewer
from nexis.config import PipelineConfig
from nexis.telemetry import instrument_node
from nexis.state import BusinessIdea, PipelineState, ReviewerRole

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State definitions
# ---------------------------------------------------------------------------


class ReviewNodeState(PipelineState):
    """PipelineState extended with per-task fields injected by Send()."""

    idea_to_review: BusinessIdea
    reviewer_role_to_use: ReviewerRole


# ---------------------------------------------------------------------------
# Routing function
# ---------------------------------------------------------------------------


def route_to_reviewers(state: PipelineState) -> list[Send]:
    """Fan-out: send each (idea, role) pair to review_node.

    Only fans out over ideas from the current iteration to avoid
    re-reviewing ideas from previous retry iterations.
    """
    current_iteration = state.get("iteration", 0)
    current_ideas = [
        idea for idea in state["ideas"] if idea.iteration == current_iteration
    ]
    sends = []
    for idea in current_ideas:
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
        temperature=config.temperature_for(f"reviewer_{role.value}"),
        max_retries=config.max_retries,
        timeout=config.llm_timeout,
        fallback_model=config.fallback_model,
    )

    logger.debug("Reviewing idea '%s' with role '%s'", idea.title, role.value)
    review = await agent.invoke_review(idea)

    if review.failure_reason:
        logger.warning(
            "Review failed for idea '%s' (role=%s): %s",
            idea.title,
            role.value,
            review.failure_reason,
        )

    return {"reviews": [review]}


async def synthesize_node(state: PipelineState) -> dict:
    """Synthesize all reviews into scores and a ranked top_ideas list.

    Filters ideas and reviews to the current iteration to avoid
    scoring stale data from previous retry iterations.
    """
    current_iteration = state.get("iteration", 0)
    current_ideas = [
        idea for idea in state["ideas"] if idea.iteration == current_iteration
    ]
    current_idea_ids = {idea.id for idea in current_ideas}
    current_reviews = [r for r in state["reviews"] if r.idea_id in current_idea_ids]

    synthesizer = ReviewSynthesizer()
    scores, top_ideas = synthesizer.synthesize(
        reviews=current_reviews,
        config=state["config"],
        ideas=current_ideas,
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
    builder = StateGraph(PipelineState)

    builder.add_node("review_node", instrument_node(review_node, layer_id="review"))
    builder.add_node(
        "synthesize_node", instrument_node(synthesize_node, layer_id="review")
    )

    builder.add_conditional_edges(START, route_to_reviewers, ["review_node"])
    builder.add_edge("review_node", "synthesize_node")
    builder.add_edge("synthesize_node", END)

    return builder.compile()
