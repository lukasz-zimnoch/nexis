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
    ReviewerRole.moat: (
        "You are a Competitive Moat Analyst. Analyze the defensibility of this business idea: "
        "network effects, data moats, switching costs, and regulatory barriers. "
        "Flag commodity risk. Score 1-10."
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
    ) -> None:
        super().__init__(
            model_name=model_name,
            output_schema=Review,
            system_prompt=REVIEWER_PROMPTS[role],
            max_retries=max_retries,
        )
        self.role = role

    async def invoke_review(self, idea: BusinessIdea) -> Review:
        """Invoke the reviewer for a given idea and return a Review."""
        review = await self.invoke({"idea": idea})
        # Ensure the reviewer_role and idea_id are set correctly
        if review.failure_reason is None:
            review = Review(
                idea_id=idea.id,
                reviewer_role=self.role,
                score=review.score,
                rationale=review.rationale,
                red_flags=review.red_flags,
                confidence=review.confidence,
                failure_reason=review.failure_reason,
            )
        return review


def create_reviewer(
    role: ReviewerRole,
    model_name: str,
    max_retries: int = 2,
) -> ReviewerAgent:
    """Factory function to create a ReviewerAgent for the given role."""
    return ReviewerAgent(role=role, model_name=model_name, max_retries=max_retries)


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
