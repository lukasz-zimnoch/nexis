"""Tests for the Layer 2 review subgraph."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from nexis.config import PipelineConfig
from nexis.layers.review import build_review_subgraph
from nexis.state import BusinessIdea, Review, ReviewerRole


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> PipelineConfig:
    return PipelineConfig(
        research_prompt="Find SaaS opportunities",
        model_name="claude-sonnet-4-6",
        num_ideas=4,
        top_k=3,
        score_threshold=0.55,
        max_retries=2,
    )


@pytest.fixture
def three_ideas() -> list[BusinessIdea]:
    return [
        BusinessIdea(
            id=f"idea-{i}",
            title=f"Idea {i}",
            problem_statement=f"Problem {i}",
            target_market=f"Market {i}",
            revenue_model="SaaS",
            confidence=0.8,
        )
        for i in range(1, 4)
    ]


def _make_review(idea_id: str, role: ReviewerRole) -> Review:
    return Review(
        idea_id=idea_id,
        reviewer_role=role,
        score=8,
        rationale=f"Good {role.value} for {idea_id}",
        red_flags=[],
        confidence=0.9,
    )


# ---------------------------------------------------------------------------
# Layer tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_layer_produces_18_reviews(config, three_ideas):
    """3 ideas × 6 roles = 18 reviews in state after layer runs."""
    # Pre-build the expected reviews
    expected_reviews_map: dict[tuple[str, ReviewerRole], Review] = {
        (idea.id, role): _make_review(idea.id, role)
        for idea in three_ideas
        for role in ReviewerRole
    }

    async def mock_invoke_review(self, idea: BusinessIdea) -> Review:
        return expected_reviews_map[(idea.id, self.role)]

    initial_state = {
        "config": config,
        "research_prompt": config.research_prompt,
        "iteration": 0,
        "ideas": three_ideas,
        "reviews": [],
        "scores": {},
        "top_ideas": [],
        "mvp_plans": {},
        "gtm_plans": {},
        "business_plans": {},
        "rebuttals": {},
        "final_reports": [],
    }

    with patch(
        "nexis.agents.reviewers.ReviewerAgent.invoke_review",
        new=mock_invoke_review,
    ):
        graph = build_review_subgraph()
        result = await graph.ainvoke(initial_state)

    reviews = result["reviews"]
    assert len(reviews) == 18, f"Expected 18 reviews, got {len(reviews)}"


@pytest.mark.asyncio
async def test_review_layer_scores_all_ideas(config, three_ideas):
    """Scores dict is populated for all 3 ideas after layer runs."""

    async def mock_invoke_review(self, idea: BusinessIdea) -> Review:
        return _make_review(idea.id, self.role)

    initial_state = {
        "config": config,
        "research_prompt": config.research_prompt,
        "iteration": 0,
        "ideas": three_ideas,
        "reviews": [],
        "scores": {},
        "top_ideas": [],
        "mvp_plans": {},
        "gtm_plans": {},
        "business_plans": {},
        "rebuttals": {},
        "final_reports": [],
    }

    with patch(
        "nexis.agents.reviewers.ReviewerAgent.invoke_review",
        new=mock_invoke_review,
    ):
        graph = build_review_subgraph()
        result = await graph.ainvoke(initial_state)

    scores = result["scores"]
    for idea in three_ideas:
        assert idea.id in scores, f"Expected score for {idea.id}"
        assert scores[idea.id] > 0.0


@pytest.mark.asyncio
async def test_review_layer_top_ideas_above_threshold(config, three_ideas):
    """top_ideas contains the ideas that passed the score threshold."""

    async def mock_invoke_review(self, idea: BusinessIdea) -> Review:
        return _make_review(idea.id, self.role)

    initial_state = {
        "config": config,
        "research_prompt": config.research_prompt,
        "iteration": 0,
        "ideas": three_ideas,
        "reviews": [],
        "scores": {},
        "top_ideas": [],
        "mvp_plans": {},
        "gtm_plans": {},
        "business_plans": {},
        "rebuttals": {},
        "final_reports": [],
    }

    with patch(
        "nexis.agents.reviewers.ReviewerAgent.invoke_review",
        new=mock_invoke_review,
    ):
        graph = build_review_subgraph()
        result = await graph.ainvoke(initial_state)

    top_ideas = result["top_ideas"]
    scores = result["scores"]

    # All top ideas must be above threshold
    for idea_id in top_ideas:
        assert scores[idea_id] >= config.score_threshold

    # Must not exceed top_k
    assert len(top_ideas) <= config.top_k

    # With score=8, confidence=0.9, the weighted score should be well above threshold
    # so all 3 ideas should appear (top_k=3)
    assert len(top_ideas) == 3


@pytest.mark.asyncio
async def test_review_layer_handles_failed_reviews(config, three_ideas):
    """Layer still produces valid output when some reviews fail."""
    call_count = 0

    async def mock_invoke_review_with_failure(self, idea: BusinessIdea) -> Review:
        nonlocal call_count
        call_count += 1
        # Fail every other review
        if call_count % 3 == 0:
            return Review(
                idea_id=idea.id,
                reviewer_role=self.role,
                score=1,
                rationale="",
                confidence=0.0,
                failure_reason="Simulated failure",
            )
        return _make_review(idea.id, self.role)

    initial_state = {
        "config": config,
        "research_prompt": config.research_prompt,
        "iteration": 0,
        "ideas": three_ideas,
        "reviews": [],
        "scores": {},
        "top_ideas": [],
        "mvp_plans": {},
        "gtm_plans": {},
        "business_plans": {},
        "rebuttals": {},
        "final_reports": [],
    }

    with patch(
        "nexis.agents.reviewers.ReviewerAgent.invoke_review",
        new=mock_invoke_review_with_failure,
    ):
        graph = build_review_subgraph()
        result = await graph.ainvoke(initial_state)

    # All 18 reviews still produced (including failed ones)
    assert len(result["reviews"]) == 18
    # Scores still present for all ideas
    for idea in three_ideas:
        assert idea.id in result["scores"]
