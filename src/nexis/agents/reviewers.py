"""Review layer agents: six critic ReviewerAgents and a ReviewSynthesizer."""

from __future__ import annotations

import logging

from nexis.agents.base import BaseAgent
from nexis.config import PipelineConfig
from nexis.state import BusinessIdea, Review, ReviewerRole

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompts per reviewer role
# ---------------------------------------------------------------------------

REVIEWER_PROMPTS: dict[ReviewerRole, str] = {
    ReviewerRole.market: (
        "You are a Market Analyst. Evaluate the business idea's total addressable market "
        "(TAM/SAM/SOM), market growth trajectory, demand signals, and timing. "
        "Score 1-10 and provide structured rationale."
    ),
    ReviewerRole.technical: (
        "You are a Technical Feasibility Analyst. Assess whether a solo developer or small team "
        "can build an MVP of this idea in 4-8 weeks. Consider stack complexity, API dependencies, "
        "and infrastructure costs. Score 1-10."
    ),
    # Long by design. A short moat prompt with no scale anchors scores every
    # idea near the floor, because a pre-launch idea holds no moat yet and the
    # reviewer reads that as the answer. The anchors and the three traps are
    # what separate a durable niche business from a commodity one, so
    # shortening this undoes the calibration.
    ReviewerRole.moat: (
        "You are a Competitive Moat Analyst. Score how defensible this business becomes "
        "if it succeeds, from 1 to 10.\n\n"
        "Every idea you see is pre-launch, so none of them holds a moat yet. Judge "
        "whether the structure described builds one as the business matures. Do not "
        "score the defensibility that exists on day one, and do not let ease of building "
        "or early demand raise the score.\n\n"
        "Credit these where the description supports them:\n"
        "- operational data that piles up from ordinary use and cannot be bought\n"
        "- a qualification, certification or audited process this business must pay for "
        "before it can sell at all, and that every new entrant must pay for again\n"
        "- depth of integration into a workflow the customer runs the business on\n"
        "- a maintained model of a domain that takes years to assemble and is painful to "
        "abandon\n"
        "- network effects and switching costs where they genuinely apply\n\n"
        "Three traps:\n"
        "- Selling compliance help is not a regulatory barrier. A barrier counts only "
        "when it raises the cost of entering this business, not when somebody else's "
        "obligation is the subject of the product.\n"
        "- A network effect that has to be rebuilt in every new city or segment is weak, "
        "however real it is inside one.\n"
        "- Where an established competitor already holds this position, the moat is "
        "theirs. Undercutting them on price is not a moat.\n\n"
        "A narrow business can be highly defensible, and most durable business-to-business "
        "moats are unglamorous. Do not judge against consumer platform network effects.\n\n"
        "Score anchors:\n"
        "1-3: a competent team rebuilds this in weeks on a foundation model with no "
        "proprietary input, or the platform vendor ships it as a built-in feature.\n"
        "4-6: real friction to copy, but it comes from execution, from being early, or "
        "from hard engineering that a funded competitor can also do.\n"
        "7-9: copying it means repeating years of data collection, qualification or "
        "integration work that money alone does not shorten.\n"
        "10: a barrier effectively closed to a new entrant. Rare, so justify it.\n\n"
        "Name the commodity risk explicitly whenever the score sits at 1-3."
    ),
    ReviewerRole.financial: (
        "You are a Financial Viability Analyst. Check unit economics sanity: estimated CAC, LTV, "
        "margin structure, path to ramen profitability. Score 1-10."
    ),
    ReviewerRole.risk: (
        "You are a Risk Assessor. Red-team this business idea: regulatory risk, single points of "
        "failure, ethical concerns, market timing risk. Score 1-10."
    ),
    ReviewerRole.ai_resilience: (
        "You are an AI Disruption Analyst. Evaluate this business idea's resilience to AI "
        "replacement and commoditization. Consider: Can a foundation-model provider (OpenAI, "
        "Anthropic, Google) replicate the core value proposition as a built-in feature or API "
        "endpoint? Does the idea's value come from proprietary data, unique workflows, or "
        "domain-specific integration rather than raw AI capability? How fast is the AI capability "
        "frontier moving in this problem domain? Is the idea building on top of AI (leveraged) "
        "or competing against AI (exposed)? Score 1-10 where 10 means highly AI-resilient."
    ),
}


# ---------------------------------------------------------------------------
# ReviewerAgent
# ---------------------------------------------------------------------------


class ReviewerAgent(BaseAgent):
    """Critic agent that evaluates a BusinessIdea from a specific perspective."""

    def __init__(
        self,
        role: ReviewerRole,
        model_name: str,
        max_retries: int = 2,
        timeout: int = 120,
        fallback_model: str | None = None,
    ) -> None:
        super().__init__(
            model_name=model_name,
            output_schema=Review,
            system_prompt=REVIEWER_PROMPTS[role],
            max_retries=max_retries,
            timeout=timeout,
            fallback_model=fallback_model,
        )
        self.role = role

    async def invoke_review(self, idea: BusinessIdea) -> Review:
        """Invoke the reviewer for a given idea and return a Review."""
        review = await self.invoke({"idea": idea})
        review = review.model_copy(
            update={"idea_id": idea.id, "reviewer_role": self.role}
        )
        return review


def create_reviewer(
    role: ReviewerRole,
    model_name: str,
    max_retries: int = 2,
    timeout: int = 120,
    fallback_model: str | None = None,
) -> ReviewerAgent:
    """Factory function to create a ReviewerAgent for the given role."""
    return ReviewerAgent(
        role=role,
        model_name=model_name,
        max_retries=max_retries,
        timeout=timeout,
        fallback_model=fallback_model,
    )


# ---------------------------------------------------------------------------
# ReviewSynthesizer
# ---------------------------------------------------------------------------


class ReviewSynthesizer:
    """Pure Python (no LLM) synthesizer that scores and ranks business ideas."""

    def synthesize(
        self,
        reviews: list[Review],
        config: PipelineConfig,
        ideas: list[BusinessIdea],
    ) -> tuple[dict[str, float], list[str]]:
        """Compute weighted scores, filter by threshold, and return top_k ideas.

        Scoring formula (spec §6.2):
            score = sum(weight_i * score_i * confidence_i) / 10

        Returns:
            (scores, top_ideas) where scores maps idea_id -> weighted_score
            and top_ideas is a list of idea_ids ordered by score descending.
        """
        # Group reviews by idea_id — always reset top_ideas for retry correctness
        reviews_by_idea: dict[str, list[Review]] = {}
        for idea in ideas:
            reviews_by_idea[idea.id] = []

        for review in reviews:
            if review.idea_id in reviews_by_idea:
                reviews_by_idea[review.idea_id].append(review)
            else:
                # Review for an idea not in the ideas list — still track it
                reviews_by_idea.setdefault(review.idea_id, []).append(review)

        scores: dict[str, float] = {}

        for idea_id, idea_reviews in reviews_by_idea.items():
            # Filter out failed reviews
            valid_reviews = [r for r in idea_reviews if r.failure_reason is None]

            if not valid_reviews:
                logger.warning(
                    "All reviews for idea %s failed — assigning score 0.0", idea_id
                )
                scores[idea_id] = 0.0
                continue

            weighted_sum = 0.0
            for review in valid_reviews:
                weight = config.reviewer_weights.get(review.reviewer_role.value, 0.0)
                weighted_sum += weight * review.score * review.confidence

            scores[idea_id] = weighted_sum / 10.0

        # Rank by score descending
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

        # Filter by threshold and select top_k
        top_ideas: list[str] = []
        for idea_id, score in ranked:
            if score >= config.score_threshold:
                top_ideas.append(idea_id)
            if len(top_ideas) >= config.top_k:
                break

        return scores, top_ideas
