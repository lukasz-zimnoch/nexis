"""Shared pytest fixtures for all tests."""

from __future__ import annotations

import pytest

from nexis.config import PipelineConfig
from nexis.state import (
    BusinessIdea,
    GTMPlan,
    MVPPlan,
    Channel,
    ComplexityRating,
    Feature,
    LaunchPhase,
    MoSCoWPriority,
    PricingModel,
    Review,
    ReviewerRole,
    Sprint,
    TechStack,
    TrendSignal,
)


@pytest.fixture(autouse=True)
def set_openrouter_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")


@pytest.fixture
def sample_config() -> PipelineConfig:
    return PipelineConfig(
        research_prompt="Find SaaS opportunities in developer tools",
        num_ideas=4,
        top_k=2,
        score_threshold=0.55,
        max_retries=2,
    )


@pytest.fixture
def sample_trend_signal() -> TrendSignal:
    return TrendSignal(
        source="HackerNews",
        signal="Rising interest in AI-powered dev tools",
        url="https://news.ycombinator.com/item?id=12345",
        timestamp="2026-03-22T00:00:00Z",
    )


@pytest.fixture
def sample_business_idea(sample_trend_signal: TrendSignal) -> BusinessIdea:
    return BusinessIdea(
        id="idea-001",
        title="AI Code Reviewer",
        problem_statement="Code review is slow and inconsistent",
        target_market="Software engineering teams",
        revenue_model="SaaS subscription",
        estimated_tam="$5B",
        confidence=0.8,
        sources=["https://example.com"],
        trend_signals=[sample_trend_signal],
    )


@pytest.fixture
def sample_review(sample_business_idea: BusinessIdea) -> Review:
    return Review(
        idea_id=sample_business_idea.id,
        reviewer_role=ReviewerRole.market,
        score=7,
        rationale="Large and growing market",
        red_flags=["Crowded space"],
        confidence=0.85,
    )


@pytest.fixture
def sample_mvp_plan(sample_business_idea: BusinessIdea) -> MVPPlan:
    return MVPPlan(
        idea_id=sample_business_idea.id,
        core_features=[
            Feature(
                name="PR Review",
                description="Automated PR review with comments",
                priority=MoSCoWPriority.must,
            )
        ],
        tech_stack=TechStack(
            languages=["Python"],
            frameworks=["FastAPI"],
            databases=["PostgreSQL"],
            infrastructure=["AWS"],
            external_apis=["GitHub API", "Anthropic API"],
        ),
        data_model="User -> Repository -> PullRequest -> Review",
        sprint_plan=[
            Sprint(number=1, duration_weeks=2, deliverables=["Auth", "GitHub OAuth"])
        ],
        estimated_cost_usd=5000.0,
        complexity_rating=ComplexityRating.medium,
    )


@pytest.fixture
def sample_gtm_plan(sample_business_idea: BusinessIdea) -> GTMPlan:
    return GTMPlan(
        idea_id=sample_business_idea.id,
        icp="Engineering teams at 10-200 person startups",
        positioning="AI code reviewer that catches bugs humans miss",
        channels=[
            Channel(
                name="HackerNews",
                rationale="Technical founders hang out here",
                estimated_cost_usd=0.0,
            )
        ],
        pricing_model=PricingModel(
            strategy="per-seat",
            tiers=[{"name": "starter", "price": "29", "description": "Up to 5 seats"}],
            notes="Annual discount available",
        ),
        launch_sequence=[
            LaunchPhase(
                name="Beta",
                duration="4 weeks",
                activities=["Recruit 10 beta users"],
                success_metrics=["10 active repos"],
            )
        ],
        first_100_playbook="Post on HN Show HN, offer free first month",
    )


@pytest.fixture
def sample_pipeline_state(
    sample_config: PipelineConfig,
    sample_business_idea: BusinessIdea,
    sample_review: Review,
    sample_mvp_plan: MVPPlan,
    sample_gtm_plan: GTMPlan,
) -> dict:
    return {
        "config": sample_config,
        "research_prompt": sample_config.research_prompt,
        "iteration": 0,
        "ideas": [sample_business_idea],
        "reviews": [sample_review],
        "scores": {sample_business_idea.id: 0.70},
        "top_ideas": [sample_business_idea.id],
        "mvp_plans": {sample_business_idea.id: sample_mvp_plan},
        "gtm_plans": {sample_business_idea.id: sample_gtm_plan},
        "business_plans": {},
        "rebuttals": {},
        "final_reports": [],
    }
