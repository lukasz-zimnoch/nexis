"""Tests for the Layer 3 planning subgraph."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexis.layers.planning import build_planning_subgraph
from nexis.state import BusinessPlan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pipeline_state(
    sample_config,
    ideas: list,
    reviews: list,
    top_ideas: list[str],
) -> dict:
    return {
        "config": sample_config,
        "research_prompt": sample_config.research_prompt,
        "iteration": 0,
        "ideas": ideas,
        "reviews": reviews,
        "scores": {i.id: 0.75 for i in ideas},
        "top_ideas": top_ideas,
        "mvp_plans": {},
        "gtm_plans": {},
        "business_plans": {},
        "rebuttals": {},
        "final_reports": [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_planning_layer_populates_plans_for_two_ideas(
    sample_config,
    sample_business_idea,
    sample_review,
    sample_mvp_plan,
    sample_gtm_plan,
):
    """Two top ideas should each get an MVPPlan, GTMPlan, and BusinessPlan."""
    from nexis.state import BusinessIdea, Review, ReviewerRole

    idea2 = BusinessIdea(
        id="idea-002",
        title="AI Documentation Writer",
        problem_statement="Writing docs is tedious",
        target_market="Software teams",
        revenue_model="SaaS",
        confidence=0.75,
    )
    review2 = Review(
        idea_id="idea-002",
        reviewer_role=ReviewerRole.market,
        score=8,
        rationale="Huge demand",
        confidence=0.80,
    )

    mvp2 = sample_mvp_plan.model_copy(update={"idea_id": "idea-002"})
    gtm2 = sample_gtm_plan.model_copy(update={"idea_id": "idea-002"})

    business_plan1 = BusinessPlan(
        idea_id=sample_business_idea.id,
        executive_summary="Plan 1",
        key_assumptions=["assumption A"],
        success_metrics=["metric A"],
        mvp_plan=sample_mvp_plan,
        gtm_plan=sample_gtm_plan,
    )
    business_plan2 = BusinessPlan(
        idea_id="idea-002",
        executive_summary="Plan 2",
        key_assumptions=["assumption B"],
        success_metrics=["metric B"],
        mvp_plan=mvp2,
        gtm_plan=gtm2,
    )

    with (
        patch("nexis.layers.planning.MVPArchitect") as MockMVP,
        patch("nexis.layers.planning.GTMStrategist") as MockGTM,
        patch("nexis.layers.planning.BusinessPlanComposer") as MockComposer,
    ):
        # Configure per-idea return values based on idea_id
        async def mvp_side_effect(idea, reviews):
            return sample_mvp_plan if idea.id == sample_business_idea.id else mvp2

        async def gtm_side_effect(idea, reviews):
            return sample_gtm_plan if idea.id == sample_business_idea.id else gtm2

        async def plan_side_effect(idea, mvp, gtm):
            return business_plan1 if idea.id == sample_business_idea.id else business_plan2

        MockMVP.return_value.invoke_mvp = AsyncMock(side_effect=mvp_side_effect)
        MockGTM.return_value.invoke_gtm = AsyncMock(side_effect=gtm_side_effect)
        MockComposer.return_value.invoke_plan = AsyncMock(side_effect=plan_side_effect)

        graph = build_planning_subgraph()
        initial_state = _make_pipeline_state(
            sample_config,
            ideas=[sample_business_idea, idea2],
            reviews=[sample_review, review2],
            top_ideas=[sample_business_idea.id, "idea-002"],
        )

        result = await graph.ainvoke(initial_state)

    assert sample_business_idea.id in result["mvp_plans"]
    assert "idea-002" in result["mvp_plans"]
    assert sample_business_idea.id in result["gtm_plans"]
    assert "idea-002" in result["gtm_plans"]
    assert sample_business_idea.id in result["business_plans"]
    assert "idea-002" in result["business_plans"]

    assert result["business_plans"][sample_business_idea.id].executive_summary == "Plan 1"
    assert result["business_plans"]["idea-002"].executive_summary == "Plan 2"


@pytest.mark.asyncio
async def test_planning_layer_empty_top_ideas_produces_no_plans(
    sample_config,
    sample_business_idea,
    sample_review,
):
    """When top_ideas is empty the graph should finish with no plans generated."""
    with (
        patch("nexis.layers.planning.MVPArchitect") as MockMVP,
        patch("nexis.layers.planning.GTMStrategist") as MockGTM,
        patch("nexis.layers.planning.BusinessPlanComposer") as MockComposer,
    ):
        MockMVP.return_value.invoke_mvp = AsyncMock()
        MockGTM.return_value.invoke_gtm = AsyncMock()
        MockComposer.return_value.invoke_plan = AsyncMock()

        graph = build_planning_subgraph()
        initial_state = _make_pipeline_state(
            sample_config,
            ideas=[sample_business_idea],
            reviews=[sample_review],
            top_ideas=[],
        )

        result = await graph.ainvoke(initial_state)

    assert result["mvp_plans"] == {}
    assert result["gtm_plans"] == {}
    assert result["business_plans"] == {}

    MockMVP.return_value.invoke_mvp.assert_not_called()
    MockGTM.return_value.invoke_gtm.assert_not_called()
    MockComposer.return_value.invoke_plan.assert_not_called()
