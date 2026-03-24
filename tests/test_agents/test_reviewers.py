"""Tests for ReviewerAgent and ReviewSynthesizer."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _wrap(parsed):
    """Wrap a parsed result in the include_raw=True dict format."""
    raw = MagicMock()
    raw.usage_metadata = {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}
    return {"parsed": parsed, "raw": raw, "parsing_error": None}

from nexis.agents.reviewers import ReviewSynthesizer, ReviewerAgent, create_reviewer
from nexis.config import PipelineConfig
from nexis.state import BusinessIdea, Review, ReviewerRole


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> PipelineConfig:
    return PipelineConfig(
        research_prompt="Test prompt",
        num_ideas=4,
        top_k=3,
        score_threshold=0.55,
        max_retries=2,
    )


@pytest.fixture
def idea_a() -> BusinessIdea:
    return BusinessIdea(
        id="idea-a",
        title="Idea A",
        problem_statement="Problem A",
        target_market="Market A",
        revenue_model="SaaS",
        confidence=0.8,
    )


@pytest.fixture
def idea_b() -> BusinessIdea:
    return BusinessIdea(
        id="idea-b",
        title="Idea B",
        problem_statement="Problem B",
        target_market="Market B",
        revenue_model="Marketplace",
        confidence=0.7,
    )


@pytest.fixture
def idea_c() -> BusinessIdea:
    return BusinessIdea(
        id="idea-c",
        title="Idea C",
        problem_statement="Problem C",
        target_market="Market C",
        revenue_model="Usage-based",
        confidence=0.6,
    )


@pytest.fixture
def mock_llm_chain():
    """Patch init_chat_model to return a controllable mock chain."""
    with patch("nexis.agents.base.init_chat_model") as mock_init:
        mock_chain = MagicMock()
        mock_init.return_value.with_structured_output.return_value = mock_chain
        yield mock_chain


def make_review(idea_id: str, role: ReviewerRole, score: int = 7, confidence: float = 0.9) -> Review:
    return Review(
        idea_id=idea_id,
        reviewer_role=role,
        score=score,
        rationale="Test rationale",
        red_flags=[],
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# ReviewerAgent tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reviewer_returns_correct_role_market(mock_llm_chain, idea_a):
    """Market reviewer sets reviewer_role=market on the returned Review."""
    expected_review = Review(
        idea_id=idea_a.id,
        reviewer_role=ReviewerRole.market,
        score=8,
        rationale="Big market",
        confidence=0.9,
    )
    mock_llm_chain.ainvoke = AsyncMock(return_value=_wrap(expected_review))

    agent = ReviewerAgent(role=ReviewerRole.market, model_name="claude-sonnet-4-6")
    result = await agent.invoke_review(idea_a)

    assert result.reviewer_role == ReviewerRole.market
    assert result.idea_id == idea_a.id
    assert result.score == 8
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_reviewer_returns_correct_role_technical(mock_llm_chain, idea_a):
    """Technical reviewer sets reviewer_role=technical on the returned Review."""
    expected_review = Review(
        idea_id=idea_a.id,
        reviewer_role=ReviewerRole.technical,
        score=6,
        rationale="Moderate complexity",
        confidence=0.8,
    )
    mock_llm_chain.ainvoke = AsyncMock(return_value=_wrap(expected_review))

    agent = ReviewerAgent(role=ReviewerRole.technical, model_name="claude-sonnet-4-6")
    result = await agent.invoke_review(idea_a)

    assert result.reviewer_role == ReviewerRole.technical
    assert result.idea_id == idea_a.id


@pytest.mark.asyncio
async def test_reviewer_all_roles_via_factory(mock_llm_chain, idea_a):
    """create_reviewer factory produces a working agent for every role."""
    for role in ReviewerRole:
        expected_review = Review(
            idea_id=idea_a.id,
            reviewer_role=role,
            score=5,
            rationale=f"Review for {role.value}",
            confidence=0.75,
        )
        mock_llm_chain.ainvoke = AsyncMock(return_value=_wrap(expected_review))

        agent = create_reviewer(role=role, model_name="claude-sonnet-4-6")
        result = await agent.invoke_review(idea_a)

        assert result.reviewer_role == role
        assert result.idea_id == idea_a.id


@pytest.mark.asyncio
async def test_reviewer_enforces_idea_id_and_role_on_success(mock_llm_chain, idea_a):
    """Even if the LLM returns wrong idea_id/role, invoke_review enforces them."""
    wrong_review = Review(
        idea_id="wrong-id",
        reviewer_role=ReviewerRole.risk,  # wrong role
        score=9,
        rationale="Good",
        confidence=0.95,
    )
    mock_llm_chain.ainvoke = AsyncMock(return_value=_wrap(wrong_review))

    agent = ReviewerAgent(role=ReviewerRole.financial, model_name="claude-sonnet-4-6")
    result = await agent.invoke_review(idea_a)

    assert result.idea_id == idea_a.id
    assert result.reviewer_role == ReviewerRole.financial


# ---------------------------------------------------------------------------
# ReviewSynthesizer tests
# ---------------------------------------------------------------------------


def test_synthesizer_correct_weighted_calculation(config, idea_a):
    """Weighted score = sum(weight_i * score_i * confidence_i) / 10."""
    # market: weight=0.25, score=8, confidence=1.0  → 0.25 * 8 * 1.0 = 2.0
    # technical: weight=0.20, score=6, confidence=1.0 → 0.20 * 6 * 1.0 = 1.2
    # moat: weight=0.15, score=7, confidence=1.0 → 0.15 * 7 * 1.0 = 1.05
    # financial: weight=0.20, score=5, confidence=1.0 → 0.20 * 5 * 1.0 = 1.0
    # risk: weight=0.10, score=4, confidence=1.0 → 0.10 * 4 * 1.0 = 0.4
    # ai_resilience: weight=0.10, score=6, confidence=1.0 → 0.10 * 6 * 1.0 = 0.6
    # total = (2.0 + 1.2 + 1.05 + 1.0 + 0.4 + 0.6) / 10 = 6.25 / 10 = 0.625
    reviews = [
        make_review(idea_a.id, ReviewerRole.market, score=8, confidence=1.0),
        make_review(idea_a.id, ReviewerRole.technical, score=6, confidence=1.0),
        make_review(idea_a.id, ReviewerRole.moat, score=7, confidence=1.0),
        make_review(idea_a.id, ReviewerRole.financial, score=5, confidence=1.0),
        make_review(idea_a.id, ReviewerRole.risk, score=4, confidence=1.0),
        make_review(idea_a.id, ReviewerRole.ai_resilience, score=6, confidence=1.0),
    ]

    synthesizer = ReviewSynthesizer()
    scores, top_ideas = synthesizer.synthesize(reviews, config, [idea_a])

    expected_score = (0.25 * 8 + 0.20 * 6 + 0.15 * 7 + 0.20 * 5 + 0.10 * 4 + 0.10 * 6) / 10
    assert abs(scores[idea_a.id] - expected_score) < 1e-9
    assert idea_a.id in top_ideas  # 0.625 >= 0.55 threshold


def test_synthesizer_missing_reviews_for_some_ideas(config, idea_a, idea_b):
    """Ideas with no reviews get score 0.0 and are excluded from top_ideas."""
    reviews = [
        make_review(idea_a.id, ReviewerRole.market, score=8, confidence=1.0),
    ]

    synthesizer = ReviewSynthesizer()
    scores, top_ideas = synthesizer.synthesize(reviews, config, [idea_a, idea_b])

    assert idea_a.id in scores
    assert idea_b.id in scores
    assert scores[idea_b.id] == 0.0
    assert idea_b.id not in top_ideas


def test_synthesizer_all_below_threshold_returns_empty(config, idea_a):
    """When all ideas score below threshold, top_ideas is an empty list."""
    # Score: market weight=0.25 * score=1 * confidence=0.1 / 10 = 0.0025 (way below 0.55)
    reviews = [
        make_review(idea_a.id, ReviewerRole.market, score=1, confidence=0.1),
    ]

    synthesizer = ReviewSynthesizer()
    scores, top_ideas = synthesizer.synthesize(reviews, config, [idea_a])

    assert top_ideas == []
    assert idea_a.id in scores


def test_synthesizer_top_k_filtering(config, idea_a, idea_b, idea_c):
    """Only the top_k ideas are returned even if more pass the threshold."""
    # config has top_k=3, but we'll verify top_k=2 with a modified config
    cfg_top2 = PipelineConfig(
        research_prompt="test",
        num_ideas=4,
        top_k=2,
        score_threshold=0.55,
        max_retries=2,
    )

    # All three ideas have high scores, but top_k=2 should only return 2
    reviews = []
    for idea in [idea_a, idea_b, idea_c]:
        for role in ReviewerRole:
            reviews.append(make_review(idea.id, role, score=9, confidence=1.0))

    synthesizer = ReviewSynthesizer()
    scores, top_ideas = synthesizer.synthesize(reviews, cfg_top2, [idea_a, idea_b, idea_c])

    assert len(top_ideas) == 2
    assert len(scores) == 3


def test_synthesizer_confidence_zero_yields_score_zero(config, idea_a):
    """Reviews with confidence=0 contribute 0 to the weighted sum → score=0."""
    reviews = [
        make_review(idea_a.id, ReviewerRole.market, score=10, confidence=0.0),
        make_review(idea_a.id, ReviewerRole.technical, score=10, confidence=0.0),
        make_review(idea_a.id, ReviewerRole.moat, score=10, confidence=0.0),
        make_review(idea_a.id, ReviewerRole.financial, score=10, confidence=0.0),
        make_review(idea_a.id, ReviewerRole.risk, score=10, confidence=0.0),
        make_review(idea_a.id, ReviewerRole.ai_resilience, score=10, confidence=0.0),
    ]

    synthesizer = ReviewSynthesizer()
    scores, top_ideas = synthesizer.synthesize(reviews, config, [idea_a])

    assert scores[idea_a.id] == 0.0
    assert top_ideas == []


def test_synthesizer_reviews_with_failure_reason_are_skipped(config, idea_a):
    """Reviews with failure_reason set are excluded from the score calculation."""
    failed_review = Review(
        idea_id=idea_a.id,
        reviewer_role=ReviewerRole.market,
        score=1,
        rationale="",
        confidence=0.0,
        failure_reason="LLM timed out",
    )
    good_review = make_review(idea_a.id, ReviewerRole.technical, score=10, confidence=1.0)

    reviews = [failed_review, good_review]

    synthesizer = ReviewSynthesizer()
    scores, _ = synthesizer.synthesize(reviews, config, [idea_a])

    # Only technical contributes: 0.20 * 10 * 1.0 / 10 = 0.20
    expected = (0.20 * 10 * 1.0) / 10
    assert abs(scores[idea_a.id] - expected) < 1e-9


def test_synthesizer_all_reviews_failed_score_zero(config, idea_a):
    """When all reviews for an idea have failure_reason, score=0.0."""
    reviews = [
        Review(
            idea_id=idea_a.id,
            reviewer_role=role,
            score=1,
            rationale="",
            confidence=0.0,
            failure_reason="Agent failed",
        )
        for role in ReviewerRole
    ]

    synthesizer = ReviewSynthesizer()
    scores, top_ideas = synthesizer.synthesize(reviews, config, [idea_a])

    assert scores[idea_a.id] == 0.0
    assert top_ideas == []


def test_synthesizer_ranking_order(config, idea_a, idea_b):
    """Ideas are returned in descending score order."""
    # idea_b gets higher score than idea_a
    reviews_a = [make_review(idea_a.id, ReviewerRole.market, score=6, confidence=1.0)]
    reviews_b = [make_review(idea_b.id, ReviewerRole.market, score=9, confidence=1.0)]

    synthesizer = ReviewSynthesizer()
    scores, top_ideas = synthesizer.synthesize(
        reviews_a + reviews_b, config, [idea_a, idea_b]
    )

    assert scores[idea_b.id] > scores[idea_a.id]
    # idea_b should appear first in top_ideas
    if len(top_ideas) >= 2:
        assert top_ideas[0] == idea_b.id
