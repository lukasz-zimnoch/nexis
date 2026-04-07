"""Tests for the Layer 4 output subgraph."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexis.config import PipelineConfig
from nexis.state import (
    BusinessIdea,
    BusinessPlan,
    Challenge,
    ComplexityRating,
    Feature,
    GTMPlan,
    LaunchPhase,
    MoSCoWPriority,
    MVPPlan,
    OutputFormat,
    PricingModel,
    Rebuttal,
    Report,
    Severity,
    Sprint,
    TechStack,
    TrendSignal,
    Channel,
)

from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_config() -> PipelineConfig:
    return PipelineConfig(
        research_prompt="Find SaaS opportunities in developer tools",
        num_ideas=4,
        top_k=2,
        score_threshold=0.55,
        max_retries=1,
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
        key_assumptions=["LLMs can catch meaningful bugs"],
        success_metrics=["100 paying teams in 6 months"],
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
                evidence="Microsoft dominates dev tools",
            )
        ],
        severity=Severity.medium,
        suggested_mitigations=["Focus on niche: open-source projects"],
        overall_survivability=0.65,
    )


def _make_report(format: OutputFormat = OutputFormat.markdown) -> Report:
    return Report(
        title="Nexis Business Idea Report",
        generated_at=datetime.now(tz=timezone.utc),
        ideas_evaluated=1,
        ideas_selected=1,
        content="# Test Report",
        format=format,
    )


def _make_state(
    config: PipelineConfig,
    idea: BusinessIdea,
    business_plan: BusinessPlan | None = None,
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
        "mvp_plans": {},
        "gtm_plans": {},
        "business_plans": {idea.id: business_plan} if business_plan else {},
        "rebuttals": {},
        "final_reports": [],
    }


# ---------------------------------------------------------------------------
# devils_advocate_node tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_devils_advocate_node_produces_rebuttals_for_top_ideas(
    sample_config: PipelineConfig,
    sample_idea: BusinessIdea,
    sample_business_plan: BusinessPlan,
    sample_rebuttal: Rebuttal,
):
    """devils_advocate_node should produce a rebuttal for each top idea with a business plan."""
    state = _make_state(sample_config, sample_idea, business_plan=sample_business_plan)

    with patch("nexis.layers.output.DevilsAdvocate") as MockAdvocate:
        mock_instance = MagicMock()
        mock_instance.invoke_rebuttal = AsyncMock(return_value=sample_rebuttal)
        MockAdvocate.return_value = mock_instance

        from nexis.layers.output import devils_advocate_node

        result = await devils_advocate_node(state)

    assert "rebuttals" in result
    assert sample_idea.id in result["rebuttals"]
    assert result["rebuttals"][sample_idea.id] is sample_rebuttal
    mock_instance.invoke_rebuttal.assert_called_once_with(sample_business_plan)


@pytest.mark.asyncio
async def test_devils_advocate_node_skips_when_no_top_ideas(
    sample_config: PipelineConfig,
    sample_idea: BusinessIdea,
):
    """devils_advocate_node should return empty rebuttals when top_ideas is empty."""
    state = _make_state(sample_config, sample_idea, top_ideas=[])

    with patch("nexis.layers.output.DevilsAdvocate") as MockAdvocate:
        from nexis.layers.output import devils_advocate_node

        result = await devils_advocate_node(state)

    assert result == {"rebuttals": {}}
    MockAdvocate.assert_not_called()


@pytest.mark.asyncio
async def test_devils_advocate_node_handles_exception_gracefully(
    sample_config: PipelineConfig,
    sample_idea: BusinessIdea,
    sample_business_plan: BusinessPlan,
):
    """When DevilsAdvocate raises, the node should skip that idea and not crash."""
    state = _make_state(sample_config, sample_idea, business_plan=sample_business_plan)

    with patch("nexis.layers.output.DevilsAdvocate") as MockAdvocate:
        mock_instance = MagicMock()
        mock_instance.invoke_rebuttal = AsyncMock(
            side_effect=RuntimeError("LLM timeout")
        )
        MockAdvocate.return_value = mock_instance

        from nexis.layers.output import devils_advocate_node

        result = await devils_advocate_node(state)

    # The exception is caught via return_exceptions=True — the idea gets no rebuttal
    assert "rebuttals" in result
    assert sample_idea.id not in result["rebuttals"]


# ---------------------------------------------------------------------------
# report_generator_node tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_report_generator_node_adds_report_to_final_reports(
    sample_config: PipelineConfig,
    sample_idea: BusinessIdea,
):
    """report_generator_node should append one Report to final_reports."""
    state = _make_state(sample_config, sample_idea)
    mock_report = _make_report()

    with patch("nexis.layers.output.ReportGenerator") as MockGenerator:
        mock_instance = MagicMock()
        mock_instance.generate.return_value = mock_report
        MockGenerator.return_value = mock_instance

        from nexis.layers.output import report_generator_node

        result = await report_generator_node(state)

    assert "final_reports" in result
    assert len(result["final_reports"]) == 1
    assert result["final_reports"][0] is mock_report
    mock_instance.generate.assert_called_once_with(state)


@pytest.mark.asyncio
async def test_report_generator_node_empty_top_ideas(
    sample_config: PipelineConfig,
    sample_idea: BusinessIdea,
):
    """report_generator_node should still produce a report even when top_ideas is empty."""
    state = _make_state(sample_config, sample_idea, top_ideas=[])
    empty_report = _make_report()
    empty_report = Report(
        title="Nexis Business Idea Report",
        generated_at=datetime.now(tz=timezone.utc),
        ideas_evaluated=1,
        ideas_selected=0,
        content="No viable ideas found.",
        format=OutputFormat.markdown,
    )

    with patch("nexis.layers.output.ReportGenerator") as MockGenerator:
        mock_instance = MagicMock()
        mock_instance.generate.return_value = empty_report
        MockGenerator.return_value = mock_instance

        from nexis.layers.output import report_generator_node

        result = await report_generator_node(state)

    assert len(result["final_reports"]) == 1
    assert result["final_reports"][0].ideas_selected == 0


# ---------------------------------------------------------------------------
# Integration: build_output_subgraph smoke test
# ---------------------------------------------------------------------------


def test_build_output_subgraph_compiles():
    """build_output_subgraph should return a compiled graph without raising."""
    from nexis.layers.output import build_output_subgraph

    graph = build_output_subgraph()
    # A compiled LangGraph has a .invoke or .ainvoke method
    assert hasattr(graph, "ainvoke")
