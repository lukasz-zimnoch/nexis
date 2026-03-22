"""Integration tests for the full pipeline."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexis.config import PipelineConfig
from nexis.state import (
    BusinessPlan,
    Challenge,
    OutputFormat,
    Rebuttal,
    Report,
    Severity,
)


@pytest.fixture
def integration_config():
    return PipelineConfig(
        research_prompt="Find SaaS ideas for developer tools",
        model_name="claude-sonnet-4-6",
        num_ideas=4,
        top_k=2,
        score_threshold=0.55,
        max_retries=2,
    )


@pytest.mark.asyncio
async def test_mocked_smoke_test(
    integration_config,
    sample_business_idea,
    sample_review,
    sample_mvp_plan,
    sample_gtm_plan,
):
    """Full pipeline smoke test with ALL LLM calls mocked."""
    with patch("nexis.layers.research.TrendScanner") as mock_ts, \
         patch("nexis.layers.research.ResearchAgent") as mock_ra, \
         patch("nexis.layers.research.NicheValidator") as mock_nv, \
         patch("nexis.layers.review.create_reviewer") as mock_cr, \
         patch("nexis.layers.planning.MVPArchitect") as mock_mvp, \
         patch("nexis.layers.planning.GTMStrategist") as mock_gtm, \
         patch("nexis.layers.planning.BusinessPlanComposer") as mock_composer, \
         patch("nexis.layers.output.DevilsAdvocate") as mock_da, \
         patch("nexis.layers.output.ReportGenerator") as mock_rg:

        from nexis.agents.research import TrendScannerOutput, ResearchOutput, NicheValidatorOutput
        from nexis.state import TrendSignal

        mock_ts.return_value.invoke = AsyncMock(
            return_value=TrendScannerOutput(signals=[
                TrendSignal(
                    source="HN",
                    signal="AI dev tools trending",
                    url="https://hn.com/1",
                    timestamp="2026-03-22T00:00:00Z",
                )
            ])
        )
        mock_ra.return_value.invoke = AsyncMock(
            return_value=ResearchOutput(ideas=[sample_business_idea])
        )
        mock_nv.return_value.invoke = AsyncMock(
            return_value=NicheValidatorOutput(ideas=[sample_business_idea])
        )

        reviewer_mock = MagicMock()
        reviewer_mock.invoke_review = AsyncMock(return_value=sample_review)
        mock_cr.return_value = reviewer_mock

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
            content="# Report\n## AI Code Reviewer\n",
            format=OutputFormat.markdown,
        )
        mock_rg.return_value.generate = MagicMock(return_value=report)

        from nexis.graph import build_graph
        graph = build_graph()  # uses MemorySaver by default
        initial_state = {
            "config": integration_config,
            "research_prompt": integration_config.research_prompt,
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
        thread_config = {"configurable": {"thread_id": "test-integration"}}
        final_state = await graph.ainvoke(initial_state, config=thread_config)
        reports = final_state.get("final_reports", [])

        # Verify output
        assert len(reports) >= 1
        assert reports[0].ideas_evaluated >= 1
        assert reports[0].format == OutputFormat.markdown
        assert len(reports[0].content) > 0


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_pipeline():
    """
    Live end-to-end test against real APIs.
    Excluded from default suite — run with:
        uv run pytest tests/test_integration.py -v -k live
    Requires: ANTHROPIC_API_KEY, TAVILY_API_KEY
    """
    import os

    if not os.getenv("ANTHROPIC_API_KEY") or not os.getenv("TAVILY_API_KEY"):
        pytest.skip("Live test requires ANTHROPIC_API_KEY and TAVILY_API_KEY")

    config = PipelineConfig(
        research_prompt="Find underserved SaaS opportunities for solo developers",
        model_name="claude-haiku-4-5-20251001",  # cheapest model for live tests
        num_ideas=3,
        top_k=1,
        score_threshold=0.4,
        max_retries=1,
    )

    from nexis import arun_pipeline
    reports = await arun_pipeline(config)

    assert len(reports) >= 1
    assert reports[0].ideas_evaluated >= 1
    print(f"\nLive test: {reports[0].ideas_evaluated} ideas evaluated, {reports[0].ideas_selected} selected")
    print(reports[0].content[:500])
