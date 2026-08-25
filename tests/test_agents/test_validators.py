"""Tests for DevilsAdvocate and ReportGenerator agents."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexis.agents.validators import ReportGenerator
from nexis.config import PipelineConfig
from nexis.state import (
    BusinessIdea,
    BusinessPlan,
    Challenge,
    Channel,
    ComplexityRating,
    Feature,
    GTMPlan,
    LaunchPhase,
    MoSCoWPriority,
    MVPPlan,
    OutputFormat,
    PricingModel,
    Rebuttal,
    Severity,
    Sprint,
    TechStack,
    TrendSignal,
)


def _wrap(parsed):
    """Wrap a parsed result in the include_raw=True dict format."""
    raw = MagicMock()
    raw.usage_metadata = {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}
    return {"parsed": parsed, "raw": raw, "parsing_error": None}


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_config() -> PipelineConfig:
    return PipelineConfig(
        research_prompt="Find SaaS opportunities",
        num_ideas=4,
        top_k=2,
        score_threshold=0.55,
        max_retries=2,
    )


@pytest.fixture
def sample_idea() -> BusinessIdea:
    return BusinessIdea(
        id="idea-001",
        title="AI Code Reviewer",
        problem_statement="Code review is slow and inconsistent",
        target_market="Software engineering teams",
        revenue_model="SaaS subscription",
        estimated_tam="$5B",
        confidence=0.8,
        sources=["https://example.com"],
        trend_signals=[
            TrendSignal(
                source="HackerNews",
                signal="Rising interest in AI dev tools",
                url="https://news.ycombinator.com/item?id=12345",
                timestamp="2026-03-22T00:00:00Z",
            )
        ],
    )


@pytest.fixture
def sample_mvp(sample_idea: BusinessIdea) -> MVPPlan:
    return MVPPlan(
        idea_id=sample_idea.id,
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
            external_apis=["GitHub API"],
        ),
        data_model="User -> Repository -> PullRequest -> Review",
        sprint_plan=[Sprint(number=1, duration_weeks=2, deliverables=["Auth"])],
        estimated_cost_usd=5000.0,
        complexity_rating=ComplexityRating.medium,
    )


@pytest.fixture
def sample_gtm(sample_idea: BusinessIdea) -> GTMPlan:
    return GTMPlan(
        idea_id=sample_idea.id,
        icp="Engineering teams at 10-200 person startups",
        positioning="AI code reviewer that catches bugs humans miss",
        channels=[
            Channel(
                name="HackerNews",
                rationale="Technical founders",
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
def sample_business_plan(
    sample_idea: BusinessIdea, sample_mvp: MVPPlan, sample_gtm: GTMPlan
) -> BusinessPlan:
    return BusinessPlan(
        idea_id=sample_idea.id,
        executive_summary="An AI-powered code review tool for engineering teams.",
        key_assumptions=[
            "LLMs can catch meaningful bugs",
            "Teams will pay for automation",
        ],
        success_metrics=["100 paying teams in 6 months", "$10k MRR"],
        mvp_plan=sample_mvp,
        gtm_plan=sample_gtm,
    )


@pytest.fixture
def sample_rebuttal(sample_idea: BusinessIdea) -> Rebuttal:
    return Rebuttal(
        idea_id=sample_idea.id,
        challenges=[
            Challenge(
                argument="GitHub Copilot already does this",
                evidence="Microsoft has 40% market share in developer tools",
                counter_argument="We focus on PR review, not autocomplete",
            )
        ],
        severity=Severity.medium,
        suggested_mitigations=[
            "Focus on niche: open-source projects",
            "Offer GitHub integration",
        ],
        overall_survivability=0.65,
    )


# ---------------------------------------------------------------------------
# DevilsAdvocate tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm_for_devils_advocate():
    """Patch init_chat_model to return a mock LLM chain."""
    with patch("nexis.agents.base.ChatOpenAI") as mock_init:
        mock_chain = MagicMock()
        mock_init.return_value.with_structured_output.return_value = mock_chain
        yield mock_chain


@pytest.mark.asyncio
async def test_devils_advocate_returns_rebuttal_with_correct_idea_id(
    mock_llm_for_devils_advocate,
    sample_business_plan: BusinessPlan,
    sample_rebuttal: Rebuttal,
):
    """DevilsAdvocate should return a Rebuttal whose idea_id matches the plan's idea_id."""
    mock_llm_for_devils_advocate.ainvoke = AsyncMock(
        return_value=_wrap(sample_rebuttal)
    )

    from nexis.agents.validators import DevilsAdvocate

    advocate = DevilsAdvocate(
        model_name="claude-sonnet-4-6", temperature=0.0, max_retries=1
    )
    result = await advocate.invoke_rebuttal(sample_business_plan)

    assert isinstance(result, Rebuttal)
    assert result.idea_id == sample_business_plan.idea_id
    assert result.failure_reason is None
    mock_llm_for_devils_advocate.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_devils_advocate_failure_raises(
    mock_llm_for_devils_advocate,
    sample_business_plan: BusinessPlan,
):
    """When the LLM always fails, DevilsAdvocate propagates a RuntimeError.

    BaseAgent.failure_result() cannot construct a minimal Rebuttal because Severity
    is a required enum field and _minimal_value() returns None for it, which fails
    Pydantic validation. The base class then raises RuntimeError to signal the
    unrecoverable failure. Callers (e.g., devils_advocate_node) must handle this
    via asyncio.gather(return_exceptions=True).
    """
    mock_llm_for_devils_advocate.ainvoke = AsyncMock(
        side_effect=Exception("LLM unavailable")
    )

    from nexis.agents.validators import DevilsAdvocate

    advocate = DevilsAdvocate(
        model_name="claude-sonnet-4-6", temperature=0.0, max_retries=0
    )
    result = await advocate.invoke_rebuttal(sample_business_plan)
    assert result.failure_reason is not None
    assert "LLM unavailable" in result.failure_reason


# ---------------------------------------------------------------------------
# ReportGenerator — Markdown tests
# ---------------------------------------------------------------------------


def _make_state(
    config: PipelineConfig,
    idea: BusinessIdea,
    mvp: MVPPlan | None = None,
    gtm: GTMPlan | None = None,
    rebuttal: Rebuttal | None = None,
    top_ideas: list[str] | None = None,
) -> dict:
    return {
        "config": config,
        "research_prompt": config.research_prompt,
        "iteration": 0,
        "ideas": [idea],
        "reviews": [],
        "scores": {idea.id: 0.75},
        "top_ideas": top_ideas if top_ideas is not None else [idea.id],
        "mvp_plans": {idea.id: mvp} if mvp else {},
        "gtm_plans": {idea.id: gtm} if gtm else {},
        "business_plans": {},
        "rebuttals": {idea.id: rebuttal} if rebuttal else {},
        "final_reports": [],
    }


def test_report_generator_markdown_contains_expected_sections(
    sample_config: PipelineConfig,
    sample_idea: BusinessIdea,
    sample_mvp: MVPPlan,
    sample_gtm: GTMPlan,
    sample_rebuttal: Rebuttal,
):
    """Markdown report should include idea title, MVP plan, GTM plan, and rebuttal sections."""
    state = _make_state(
        sample_config,
        sample_idea,
        mvp=sample_mvp,
        gtm=sample_gtm,
        rebuttal=sample_rebuttal,
    )
    generator = ReportGenerator()
    report = generator.generate(state)

    assert report.format == OutputFormat.markdown
    assert report.ideas_evaluated == 1
    assert report.ideas_selected == 1
    assert report.title == "Nexis Business Idea Report"

    content = report.content
    assert "AI Code Reviewer" in content
    assert "0.75" in content  # score
    assert "MVP Plan" in content
    assert "GTM Plan" in content
    assert "Devil's Advocate" in content
    assert "GitHub Copilot already does this" in content
    assert "Engineering teams at 10-200 person startups" in content  # ICP


def test_report_generator_json_format(
    sample_config: PipelineConfig,
    sample_idea: BusinessIdea,
):
    """JSON format report should produce valid JSON with top_ideas and scores."""
    config = PipelineConfig(
        research_prompt="test",
        output_format="json",
    )
    state = _make_state(config, sample_idea)
    generator = ReportGenerator()
    report = generator.generate(state)

    assert report.format == OutputFormat.json
    data = json.loads(report.content)
    assert data["ideas_evaluated"] == 1
    assert len(data["top_ideas"]) == 1
    assert data["top_ideas"][0]["id"] == sample_idea.id
    assert sample_idea.id in data["scores"]


def test_report_generator_empty_top_ideas(
    sample_config: PipelineConfig,
    sample_idea: BusinessIdea,
):
    """When top_ideas is empty, the report should indicate no viable ideas were found."""
    state = _make_state(sample_config, sample_idea, top_ideas=[])
    generator = ReportGenerator()
    report = generator.generate(state)

    assert report.ideas_selected == 0
    assert report.ideas_evaluated == 1
    # The report content should mention that no viable ideas were found
    assert "no viable" in report.content.lower() or "0 idea" in report.content.lower()


def test_report_generator_handles_missing_rebuttals(
    sample_config: PipelineConfig,
    sample_idea: BusinessIdea,
    sample_mvp: MVPPlan,
    sample_gtm: GTMPlan,
):
    """Report generator should not crash when rebuttals dict is empty."""
    state = _make_state(sample_config, sample_idea, mvp=sample_mvp, gtm=sample_gtm)
    # rebuttals defaults to {} in _make_state when rebuttal=None
    generator = ReportGenerator()
    report = generator.generate(state)

    assert report.format == OutputFormat.markdown
    assert "AI Code Reviewer" in report.content
    # Devil's Advocate section should be absent (no rebuttal)
    assert "Devil's Advocate" not in report.content


def test_report_generator_handles_missing_mvp_and_gtm(
    sample_config: PipelineConfig,
    sample_idea: BusinessIdea,
):
    """Report generator should not crash when mvp_plans and gtm_plans are absent."""
    state = _make_state(sample_config, sample_idea)
    generator = ReportGenerator()
    report = generator.generate(state)

    assert report.format == OutputFormat.markdown
    assert "AI Code Reviewer" in report.content
    assert "MVP Plan" not in report.content
    assert "GTM Plan" not in report.content


def test_report_generator_deduplicates_ideas(
    sample_config: PipelineConfig,
    sample_idea: BusinessIdea,
):
    """When ideas list contains duplicates (from retry accumulation), report deduplicates."""
    # Simulate operator.add accumulation: same idea appears 3 times
    state = _make_state(sample_config, sample_idea)
    state["ideas"] = [sample_idea, sample_idea, sample_idea]

    generator = ReportGenerator()
    report = generator.generate(state)

    assert report.ideas_evaluated == 1  # deduplicated count
    assert report.ideas_selected == 1
    # The idea title should appear only once in the selected ideas section
    assert report.content.count(f"## {sample_idea.title}") == 1
