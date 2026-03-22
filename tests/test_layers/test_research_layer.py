"""Integration tests for the Layer 1 research subgraph."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from nexis.agents.research import (
    NicheValidatorOutput,
    ResearchOutput,
    TrendScannerOutput,
)
from nexis.layers.research import build_research_subgraph
from nexis.state import BusinessIdea, TrendSignal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_business_idea(title: str = "Test Idea") -> BusinessIdea:
    return BusinessIdea(
        title=title,
        problem_statement="Test problem",
        target_market="Test market",
        revenue_model="SaaS subscription",
        confidence=0.75,
    )


def make_trend_signal(signal: str = "Test trend") -> TrendSignal:
    return TrendSignal(
        source="HackerNews",
        signal=signal,
        url="https://news.ycombinator.com/item?id=1",
        timestamp="2026-03-22T00:00:00Z",
    )


def make_initial_state(sample_config) -> dict:
    return {
        "config": sample_config,
        "research_prompt": "Find SaaS opportunities in developer tools",
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
        "trend_signals_buffer": [],
        "raw_ideas_buffer": [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_layer_full_flow(sample_config):
    """Full pipeline: trend_scanner → research_agent → niche_validator populates ideas."""
    trend_signals = [make_trend_signal("AI dev tools"), make_trend_signal("No-code rising")]
    generated_ideas = [
        make_business_idea("AI Linter"),
        make_business_idea("DevOps Copilot"),
        make_business_idea("API Mocking Tool"),
    ]
    validated_ideas = [
        make_business_idea("AI Linter"),
        make_business_idea("API Mocking Tool"),
    ]

    trend_output = TrendScannerOutput(signals=trend_signals)
    research_output = ResearchOutput(ideas=generated_ideas)
    niche_output = NicheValidatorOutput(ideas=validated_ideas)

    with (
        patch("nexis.agents.research.TrendScanner.invoke", new=AsyncMock(return_value=trend_output)),
        patch("nexis.agents.research.ResearchAgent.invoke", new=AsyncMock(return_value=research_output)),
        patch("nexis.agents.research.NicheValidator.invoke", new=AsyncMock(return_value=niche_output)),
        patch("nexis.agents.base.init_chat_model"),
    ):
        graph = build_research_subgraph()
        state = await graph.ainvoke(make_initial_state(sample_config))

    assert len(state["ideas"]) > 0
    assert len(state["ideas"]) == 2  # niche_validator filtered to 2


@pytest.mark.asyncio
async def test_research_layer_node_order(sample_config):
    """Nodes must execute in order: trend_scanner → research_agent → niche_validator."""
    call_order: list[str] = []

    async def mock_trend_scanner_invoke(self, **kwargs):
        call_order.append("trend_scanner")
        return TrendScannerOutput(signals=[make_trend_signal()])

    async def mock_research_agent_invoke(self, **kwargs):
        call_order.append("research_agent")
        return ResearchOutput(ideas=[make_business_idea()])

    async def mock_niche_validator_invoke(self, **kwargs):
        call_order.append("niche_validator")
        return NicheValidatorOutput(ideas=[make_business_idea()])

    with (
        patch("nexis.agents.research.TrendScanner.invoke", mock_trend_scanner_invoke),
        patch("nexis.agents.research.ResearchAgent.invoke", mock_research_agent_invoke),
        patch("nexis.agents.research.NicheValidator.invoke", mock_niche_validator_invoke),
        patch("nexis.agents.base.init_chat_model"),
    ):
        graph = build_research_subgraph()
        await graph.ainvoke(make_initial_state(sample_config))

    assert call_order == ["trend_scanner", "research_agent", "niche_validator"]


@pytest.mark.asyncio
async def test_research_layer_empty_ideas_from_research(sample_config):
    """When ResearchAgent returns 0 ideas, NicheValidator is skipped and ideas stays empty."""
    trend_output = TrendScannerOutput(signals=[make_trend_signal()])
    research_output = ResearchOutput(ideas=[])
    # NicheValidator should not be called (skipped), but even if mocked it won't matter
    niche_output = NicheValidatorOutput(ideas=[])

    with (
        patch("nexis.agents.research.TrendScanner.invoke", new=AsyncMock(return_value=trend_output)),
        patch("nexis.agents.research.ResearchAgent.invoke", new=AsyncMock(return_value=research_output)),
        patch("nexis.agents.research.NicheValidator.invoke", new=AsyncMock(return_value=niche_output)),
        patch("nexis.agents.base.init_chat_model"),
    ):
        graph = build_research_subgraph()
        state = await graph.ainvoke(make_initial_state(sample_config))

    assert state["ideas"] == []


@pytest.mark.asyncio
async def test_research_layer_trend_signals_stored_in_buffer(sample_config):
    """Trend signals produced by TrendScanner should be in trend_signals_buffer."""
    signals = [make_trend_signal("Signal A"), make_trend_signal("Signal B")]
    trend_output = TrendScannerOutput(signals=signals)
    research_output = ResearchOutput(ideas=[make_business_idea()])
    niche_output = NicheValidatorOutput(ideas=[make_business_idea()])

    with (
        patch("nexis.agents.research.TrendScanner.invoke", new=AsyncMock(return_value=trend_output)),
        patch("nexis.agents.research.ResearchAgent.invoke", new=AsyncMock(return_value=research_output)),
        patch("nexis.agents.research.NicheValidator.invoke", new=AsyncMock(return_value=niche_output)),
        patch("nexis.agents.base.init_chat_model"),
    ):
        graph = build_research_subgraph()
        state = await graph.ainvoke(make_initial_state(sample_config))

    assert len(state["trend_signals_buffer"]) == 2


@pytest.mark.asyncio
async def test_research_layer_niche_validator_receives_raw_ideas(sample_config):
    """NicheValidator.invoke must be called with the raw ideas from ResearchAgent."""
    generated_ideas = [make_business_idea("Idea A"), make_business_idea("Idea B")]
    trend_output = TrendScannerOutput(signals=[])
    research_output = ResearchOutput(ideas=generated_ideas)

    niche_invoke = AsyncMock(return_value=NicheValidatorOutput(ideas=generated_ideas))

    with (
        patch("nexis.agents.research.TrendScanner.invoke", new=AsyncMock(return_value=trend_output)),
        patch("nexis.agents.research.ResearchAgent.invoke", new=AsyncMock(return_value=research_output)),
        patch("nexis.agents.research.NicheValidator.invoke", niche_invoke),
        patch("nexis.agents.base.init_chat_model"),
    ):
        graph = build_research_subgraph()
        await graph.ainvoke(make_initial_state(sample_config))

    niche_invoke.assert_called_once()
    # ideas should be passed as keyword argument
    call_kwargs = niche_invoke.call_args
    passed_ideas = call_kwargs.kwargs.get("ideas")
    if passed_ideas is None and len(call_kwargs.args) > 1:
        passed_ideas = call_kwargs.args[1]
    assert passed_ideas is not None
    assert len(passed_ideas) == 2
