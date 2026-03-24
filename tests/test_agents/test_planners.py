"""Tests for MVPArchitect, GTMStrategist, and BusinessPlanComposer agents."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _wrap(parsed):
    """Wrap a parsed result in the include_raw=True dict format."""
    raw = MagicMock()
    raw.usage_metadata = {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}
    return {"parsed": parsed, "raw": raw, "parsing_error": None}

from nexis.agents.planners import BusinessPlanComposer, GTMStrategist, MVPArchitect
from nexis.state import (
    BusinessPlan,
    Channel,
    ComplexityRating,
    Feature,
    GTMPlan,
    LaunchPhase,
    MoSCoWPriority,
    MVPPlan,
    PricingModel,
    Sprint,
    TechStack,
)


# ---------------------------------------------------------------------------
# Shared mock LLM fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm_chain():
    """Patch init_chat_model so no real LLM is instantiated."""
    with patch("nexis.agents.base.ChatOpenAI") as mock_init:
        chain = MagicMock()
        mock_init.return_value.with_structured_output.return_value = chain
        yield chain


# ---------------------------------------------------------------------------
# MVPArchitect tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mvp_architect_returns_mvp_plan(
    mock_llm_chain, sample_business_idea, sample_review
):
    expected = MVPPlan(
        idea_id=sample_business_idea.id,
        core_features=[
            Feature(name="Auth", description="User login", priority=MoSCoWPriority.must)
        ],
        tech_stack=TechStack(
            languages=["Python"],
            frameworks=["FastAPI"],
            databases=["PostgreSQL"],
            infrastructure=["AWS"],
            external_apis=[],
        ),
        data_model="User -> Project",
        sprint_plan=[Sprint(number=1, duration_weeks=2, deliverables=["Auth"])],
        estimated_cost_usd=3000.0,
        complexity_rating=ComplexityRating.low,
    )
    mock_llm_chain.ainvoke = AsyncMock(return_value=_wrap(expected))

    architect = MVPArchitect(model_name="claude-sonnet-4-6", max_retries=0)
    result = await architect.invoke_mvp(sample_business_idea, [sample_review])

    assert isinstance(result, MVPPlan)
    assert result.idea_id == sample_business_idea.id
    assert result.failure_reason is None
    mock_llm_chain.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_mvp_architect_handles_llm_failure(
    mock_llm_chain, sample_business_idea, sample_mvp_plan
):
    """When the LLM returns a plan with failure_reason set, invoke_mvp surfaces it."""
    failed_plan = sample_mvp_plan.model_copy(update={"failure_reason": "LLM unavailable"})
    mock_llm_chain.ainvoke = AsyncMock(return_value=_wrap(failed_plan))

    architect = MVPArchitect(model_name="claude-sonnet-4-6", max_retries=0)
    result = await architect.invoke_mvp(sample_business_idea, [])

    assert isinstance(result, MVPPlan)
    assert result.failure_reason == "LLM unavailable"


# ---------------------------------------------------------------------------
# GTMStrategist tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gtm_strategist_returns_gtm_plan(
    mock_llm_chain, sample_business_idea, sample_review
):
    expected = GTMPlan(
        idea_id=sample_business_idea.id,
        icp="10-50 person engineering teams",
        positioning="AI-powered code review for fast-moving teams",
        channels=[Channel(name="HackerNews", rationale="Tech audience", estimated_cost_usd=0.0)],
        pricing_model=PricingModel(
            strategy="per-seat",
            tiers=[{"name": "starter", "price": 29}],
            notes="Monthly and annual",
        ),
        launch_sequence=[
            LaunchPhase(
                name="Beta",
                duration="4 weeks",
                activities=["Recruit beta users"],
                success_metrics=["50 signups"],
            )
        ],
        first_100_playbook="Post on HN, offer lifetime deal to first 100",
    )
    mock_llm_chain.ainvoke = AsyncMock(return_value=_wrap(expected))

    strategist = GTMStrategist(model_name="claude-sonnet-4-6", max_retries=0)
    result = await strategist.invoke_gtm(sample_business_idea, [sample_review])

    assert isinstance(result, GTMPlan)
    assert result.idea_id == sample_business_idea.id
    assert result.failure_reason is None
    mock_llm_chain.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_gtm_strategist_handles_llm_failure(
    mock_llm_chain, sample_business_idea, sample_gtm_plan
):
    """When the LLM returns a plan with failure_reason set, invoke_gtm surfaces it."""
    failed_plan = sample_gtm_plan.model_copy(update={"failure_reason": "timeout"})
    mock_llm_chain.ainvoke = AsyncMock(return_value=_wrap(failed_plan))

    strategist = GTMStrategist(model_name="claude-sonnet-4-6", max_retries=0)
    result = await strategist.invoke_gtm(sample_business_idea, [])

    assert isinstance(result, GTMPlan)
    assert result.failure_reason == "timeout"


# ---------------------------------------------------------------------------
# BusinessPlanComposer tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_composer_returns_business_plan(
    mock_llm_chain, sample_business_idea, sample_mvp_plan, sample_gtm_plan
):
    expected = BusinessPlan(
        idea_id=sample_business_idea.id,
        executive_summary="A promising AI code review SaaS targeting engineering teams.",
        key_assumptions=["Market willing to pay $29/seat/month"],
        success_metrics=["100 paying customers in 6 months"],
        mvp_plan=sample_mvp_plan,
        gtm_plan=sample_gtm_plan,
    )
    mock_llm_chain.ainvoke = AsyncMock(return_value=_wrap(expected))

    composer = BusinessPlanComposer(model_name="claude-sonnet-4-6", max_retries=0)
    result = await composer.invoke_plan(sample_business_idea, sample_mvp_plan, sample_gtm_plan)

    assert isinstance(result, BusinessPlan)
    assert result.idea_id == sample_business_idea.id
    assert result.failure_reason is None
    mock_llm_chain.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_composer_with_partial_mvp_input_does_not_crash(
    mock_llm_chain, sample_business_idea, sample_mvp_plan, sample_gtm_plan
):
    """Composer should proceed (and log a warning) when mvp_plan has a failure_reason."""
    failed_mvp = sample_mvp_plan.model_copy(update={"failure_reason": "LLM timed out"})

    expected = BusinessPlan(
        idea_id=sample_business_idea.id,
        executive_summary="Partial plan — MVP data unavailable.",
        key_assumptions=["GTM data only"],
        success_metrics=["First 100 customers"],
        mvp_plan=failed_mvp,
        gtm_plan=sample_gtm_plan,
    )
    mock_llm_chain.ainvoke = AsyncMock(return_value=_wrap(expected))

    composer = BusinessPlanComposer(model_name="claude-sonnet-4-6", max_retries=0)
    # Must not raise
    result = await composer.invoke_plan(sample_business_idea, failed_mvp, sample_gtm_plan)

    assert isinstance(result, BusinessPlan)
    # The mvp_plan embedded in the result reflects the partial data
    assert result.mvp_plan.failure_reason == "LLM timed out"


@pytest.mark.asyncio
async def test_composer_with_partial_gtm_input_does_not_crash(
    mock_llm_chain, sample_business_idea, sample_mvp_plan, sample_gtm_plan
):
    """Composer should proceed (and log a warning) when gtm_plan has a failure_reason."""
    failed_gtm = sample_gtm_plan.model_copy(update={"failure_reason": "Rate limit exceeded"})

    expected = BusinessPlan(
        idea_id=sample_business_idea.id,
        executive_summary="Partial plan — GTM data unavailable.",
        key_assumptions=["MVP data only"],
        success_metrics=["Ship MVP in 8 weeks"],
        mvp_plan=sample_mvp_plan,
        gtm_plan=failed_gtm,
    )
    mock_llm_chain.ainvoke = AsyncMock(return_value=_wrap(expected))

    composer = BusinessPlanComposer(model_name="claude-sonnet-4-6", max_retries=0)
    result = await composer.invoke_plan(sample_business_idea, sample_mvp_plan, failed_gtm)

    assert isinstance(result, BusinessPlan)
    assert result.gtm_plan.failure_reason == "Rate limit exceeded"
