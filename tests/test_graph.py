"""Tests for the parent graph routing and retry logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexis.graph import (
    build_graph,
    force_pass_node,
    increment_iteration_node,
    should_retry,
    supervisor_node,
)


def make_state(
    *,
    top_ideas=None,
    iteration=0,
    scores=None,
    research_prompt="test",
    top_k=3,
    max_retries=2,
):
    from nexis.config import PipelineConfig

    config = PipelineConfig(
        research_prompt=research_prompt,
        top_k=top_k,
        max_retries=max_retries,
    )
    return {
        "config": config,
        "research_prompt": research_prompt,
        "iteration": iteration,
        "ideas": [],
        "reviews": [],
        "scores": scores or {},
        "top_ideas": top_ideas or [],
        "mvp_plans": {},
        "gtm_plans": {},
        "business_plans": {},
        "rebuttals": {},
        "final_reports": [],
    }


# ---------------------------------------------------------------------------
# should_retry tests
# ---------------------------------------------------------------------------


def test_should_retry_with_top_ideas_goes_to_planning():
    state = make_state(top_ideas=["id1", "id2"])
    assert should_retry(state) == "planning"


def test_should_retry_no_ideas_below_max_retries_returns_retry():
    state = make_state(top_ideas=[], iteration=0, max_retries=2)
    assert should_retry(state) == "retry"


def test_should_retry_no_ideas_at_max_retries_returns_force_pass():
    state = make_state(top_ideas=[], iteration=2, max_retries=2)
    assert should_retry(state) == "force_pass"


def test_should_retry_no_ideas_one_below_max():
    state = make_state(top_ideas=[], iteration=1, max_retries=2)
    assert should_retry(state) == "retry"


# ---------------------------------------------------------------------------
# supervisor_node tests
# ---------------------------------------------------------------------------


def test_supervisor_node_first_run_no_prompt_change():
    state = make_state(iteration=0, research_prompt="Find SaaS ideas")
    result = supervisor_node(state)
    assert result["research_prompt"] == "Find SaaS ideas"
    assert result["iteration"] == 0


def test_supervisor_node_retry_appends_to_prompt():
    state = make_state(iteration=1, research_prompt="Find SaaS ideas")
    result = supervisor_node(state)
    assert "focus on underserved niches" in result["research_prompt"]
    assert result["research_prompt"].startswith("Find SaaS ideas")


# ---------------------------------------------------------------------------
# force_pass_node tests
# ---------------------------------------------------------------------------


def test_force_pass_node_selects_top_k():
    state = make_state(
        scores={"id1": 0.5, "id2": 0.4, "id3": 0.3, "id4": 0.2},
        top_k=2,
    )
    result = force_pass_node(state)
    assert result["top_ideas"] == ["id1", "id2"]


def test_force_pass_node_fewer_than_k_available():
    state = make_state(scores={"id1": 0.4}, top_k=3)
    result = force_pass_node(state)
    assert result["top_ideas"] == ["id1"]


def test_force_pass_node_empty_scores():
    state = make_state(scores={}, top_k=3)
    result = force_pass_node(state)
    assert result["top_ideas"] == []


# ---------------------------------------------------------------------------
# increment_iteration_node tests
# ---------------------------------------------------------------------------


def test_increment_iteration_node():
    state = make_state(iteration=0)
    result = increment_iteration_node(state)
    assert result["iteration"] == 1


def test_increment_iteration_node_from_one():
    state = make_state(iteration=1)
    result = increment_iteration_node(state)
    assert result["iteration"] == 2


# ---------------------------------------------------------------------------
# Graph topology test
# ---------------------------------------------------------------------------


def test_graph_compiles():
    """Verify the graph compiles without errors."""
    graph = build_graph()
    assert graph is not None
    # Inspect nodes
    nodes = list(graph.get_graph().nodes.keys())
    assert "supervisor" in nodes
    assert "research" in nodes
    assert "review" in nodes
    assert "planning" in nodes
    assert "output" in nodes


# ---------------------------------------------------------------------------
# Full pipeline smoke test (all agents mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_happy_path(
    sample_config, sample_business_idea, sample_review, sample_mvp_plan, sample_gtm_plan
):
    """End-to-end mocked smoke test: verify data flows through all layers."""
    from nexis.state import (
        BusinessPlan,
        Challenge,
        OutputFormat,
        Rebuttal,
        Report,
        Severity,
    )
    from datetime import datetime, timezone

    # Patch research layer
    with (
        patch("nexis.layers.research.TrendScanner") as mock_ts,
        patch("nexis.layers.research.ResearchAgent") as mock_ra,
        patch("nexis.layers.research.NicheValidator") as mock_nv,
        patch("nexis.layers.review.create_reviewer") as mock_cr,
        patch("nexis.layers.planning.MVPArchitect") as mock_mvp,
        patch("nexis.layers.planning.GTMStrategist") as mock_gtm,
        patch("nexis.layers.planning.BusinessPlanComposer") as mock_composer,
        patch("nexis.layers.output.DevilsAdvocate") as mock_da,
        patch("nexis.layers.output.ReportGenerator") as mock_rg,
    ):
        # Research layer mocks
        from nexis.agents.research import (
            TrendScannerOutput,
            ResearchOutput,
            NicheValidatorOutput,
        )

        mock_ts.return_value.invoke = AsyncMock(
            return_value=TrendScannerOutput(signals=[])
        )
        mock_ra.return_value.invoke = AsyncMock(
            return_value=ResearchOutput(ideas=[sample_business_idea])
        )
        mock_nv.return_value.invoke = AsyncMock(
            return_value=NicheValidatorOutput(ideas=[sample_business_idea])
        )

        # Review layer mocks (score above threshold)
        reviewer_mock = MagicMock()
        reviewer_mock.invoke_review = AsyncMock(return_value=sample_review)
        mock_cr.return_value = reviewer_mock

        # Planning layer mocks
        mock_mvp.return_value.invoke_mvp = AsyncMock(return_value=sample_mvp_plan)
        mock_gtm.return_value.invoke_gtm = AsyncMock(return_value=sample_gtm_plan)

        business_plan = BusinessPlan(
            idea_id=sample_business_idea.id,
            executive_summary="Strong plan",
            key_assumptions=["Users will pay"],
            success_metrics=["10 customers"],
            mvp_plan=sample_mvp_plan,
            gtm_plan=sample_gtm_plan,
        )
        mock_composer.return_value.invoke_plan = AsyncMock(return_value=business_plan)

        # Output layer mocks
        rebuttal = Rebuttal(
            idea_id=sample_business_idea.id,
            challenges=[Challenge(argument="Hard to scale", evidence="Market data")],
            severity=Severity.medium,
            suggested_mitigations=["Partner with enterprises"],
            overall_survivability=0.7,
        )
        mock_da.return_value.invoke_rebuttal = AsyncMock(return_value=rebuttal)

        report = Report(
            title="Nexis Report",
            generated_at=datetime.now(tz=timezone.utc),
            ideas_evaluated=1,
            ideas_selected=1,
            content="# Report",
            format=OutputFormat.markdown,
        )
        mock_rg.return_value.generate = MagicMock(return_value=report)

        # Run the graph
        graph = build_graph()
        initial_state = {
            "config": sample_config,
            "research_prompt": sample_config.research_prompt,
            "iteration": 0,
            "ideas": [],
            "reviews": [],
            "scores": {},
            "top_ideas": [],
            "mvp_plans": {},
            "gtm_plans": {},
            "business_plans": {},
            "rebuttals": {},
            "final_reports": [],
        }
        thread_config = {"configurable": {"thread_id": "test-smoke"}}
        final_state = await graph.ainvoke(initial_state, config=thread_config)

        assert len(final_state["final_reports"]) >= 1
        assert len(final_state["ideas"]) >= 1


@pytest.mark.asyncio
async def test_retry_edge_fires_when_no_ideas_pass_threshold(sample_config):
    """Verify that routing goes research→review→retry→research when all below threshold."""
    calls = []

    def track_should_retry(state):
        calls.append(state.get("iteration", 0))
        # First call: iteration=0, no top_ideas → retry
        # After increment: iteration=1, no top_ideas → retry
        # After increment: iteration=2 = max_retries → force_pass
        if state.get("iteration", 0) < sample_config.max_retries:
            return "retry"
        return "force_pass"

    with (
        patch("nexis.graph.should_retry", side_effect=track_should_retry),
        patch("nexis.layers.research.TrendScanner") as mock_ts,
        patch("nexis.layers.research.ResearchAgent") as mock_ra,
        patch("nexis.layers.research.NicheValidator") as mock_nv,
        patch("nexis.layers.review.create_reviewer") as mock_cr,
        patch("nexis.layers.planning.MVPArchitect") as mock_mvpa,
        patch("nexis.layers.planning.GTMStrategist") as mock_gtms,
        patch("nexis.layers.planning.BusinessPlanComposer") as mock_comp,
        patch("nexis.layers.output.DevilsAdvocate") as mock_da,
        patch("nexis.layers.output.ReportGenerator") as mock_rg,
    ):
        from nexis.agents.research import (
            TrendScannerOutput,
            ResearchOutput,
            NicheValidatorOutput,
        )
        from nexis.state import OutputFormat, Report
        from datetime import datetime, timezone

        mock_ts.return_value.invoke = AsyncMock(
            return_value=TrendScannerOutput(signals=[])
        )
        mock_ra.return_value.invoke = AsyncMock(return_value=ResearchOutput(ideas=[]))
        mock_nv.return_value.invoke = AsyncMock(
            return_value=NicheValidatorOutput(ideas=[])
        )
        mock_cr.return_value.invoke_review = AsyncMock(
            side_effect=Exception("no reviews")
        )
        mock_mvpa.return_value.invoke_mvp = AsyncMock(side_effect=Exception("no plan"))
        mock_gtms.return_value.invoke_gtm = AsyncMock(side_effect=Exception("no plan"))
        mock_comp.return_value.invoke_plan = AsyncMock(side_effect=Exception("no plan"))
        mock_da.return_value.invoke_rebuttal = AsyncMock(
            side_effect=Exception("no rebuttal")
        )

        report = Report(
            title="No ideas",
            generated_at=datetime.now(tz=timezone.utc),
            ideas_evaluated=0,
            ideas_selected=0,
            content="No viable ideas found.",
            format=OutputFormat.markdown,
        )
        mock_rg.return_value.generate = MagicMock(return_value=report)

        graph = build_graph()
        initial_state = {
            "config": sample_config,
            "research_prompt": sample_config.research_prompt,
            "iteration": 0,
            "ideas": [],
            "reviews": [],
            "scores": {},
            "top_ideas": [],
            "mvp_plans": {},
            "gtm_plans": {},
            "business_plans": {},
            "rebuttals": {},
            "final_reports": [],
        }
        thread_config = {"configurable": {"thread_id": "test-retry"}}
        final_state = await graph.ainvoke(initial_state, config=thread_config)

        # should_retry was called at least once
        assert len(calls) > 0
        # Final state has a report (no-ideas fallback)
        assert len(final_state["final_reports"]) >= 1
