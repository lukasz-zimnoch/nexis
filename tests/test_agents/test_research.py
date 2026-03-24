"""Unit tests for research agents with mocked LLM calls."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _wrap(parsed):
    """Wrap a parsed result in the include_raw=True dict format."""
    raw = MagicMock()
    raw.usage_metadata = {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}
    return {"parsed": parsed, "raw": raw, "parsing_error": None}

from nexis.agents.research import (
    NicheValidator,
    NicheValidatorOutput,
    ResearchAgent,
    ResearchOutput,
    TrendScanner,
    TrendScannerOutput,
)
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


# ---------------------------------------------------------------------------
# ResearchAgent tests
# ---------------------------------------------------------------------------


class TestResearchAgent:
    @pytest.mark.asyncio
    async def test_returns_research_output_with_ideas(self, sample_config):
        """ResearchAgent should return ResearchOutput containing 3 ideas."""
        expected_ideas = [
            make_business_idea("Idea A"),
            make_business_idea("Idea B"),
            make_business_idea("Idea C"),
        ]
        expected_output = ResearchOutput(ideas=expected_ideas)

        with patch("nexis.agents.base.init_chat_model") as mock_init:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value = mock_llm
            mock_llm.with_structured_output.return_value = mock_llm
            mock_llm.ainvoke = AsyncMock(return_value=_wrap(expected_output))
            mock_init.return_value = mock_llm

            with patch.object(
                ResearchAgent,
                "_ResearchAgent__init__",
                side_effect=None,
                create=True,
            ):
                agent = ResearchAgent.__new__(ResearchAgent)
                agent.model_name = "claude-sonnet-4-6"
                agent.output_schema = ResearchOutput
                agent.system_prompt = "test"
                agent.max_retries = 0
                agent._llm = mock_llm
                # Mock the search tool
                agent._search = MagicMock()
                agent._search.search = AsyncMock(return_value=[])

                result = await agent.invoke(
                    research_prompt="Find SaaS opportunities",
                    trend_signals=[make_trend_signal()],
                    config=sample_config,
                )

        assert isinstance(result, ResearchOutput)
        assert len(result.ideas) == 3

    @pytest.mark.asyncio
    async def test_uses_search_tool_for_context(self, sample_config):
        """ResearchAgent should call SearchTool.search before invoking LLM."""
        expected_output = ResearchOutput(ideas=[make_business_idea()])

        with patch("nexis.agents.base.init_chat_model") as mock_init:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value = mock_llm
            mock_llm.with_structured_output.return_value = mock_llm
            mock_llm.ainvoke = AsyncMock(return_value=_wrap(expected_output))
            mock_init.return_value = mock_llm

            agent = ResearchAgent.__new__(ResearchAgent)
            agent.model_name = "claude-sonnet-4-6"
            agent.output_schema = ResearchOutput
            agent.system_prompt = "test"
            agent.max_retries = 0
            agent._llm = mock_llm
            mock_search = MagicMock()
            mock_search.search = AsyncMock(
                return_value=[{"title": "AI tools", "content": "trending"}]
            )
            agent._search = mock_search

            await agent.invoke(
                research_prompt="developer tools",
                trend_signals=[],
                config=sample_config,
            )

        mock_search.search.assert_called_once()


# ---------------------------------------------------------------------------
# TrendScanner tests
# ---------------------------------------------------------------------------


class TestTrendScanner:
    @pytest.mark.asyncio
    async def test_returns_trend_scanner_output_with_signals(self, sample_config):
        """TrendScanner should return TrendScannerOutput with trend signals."""
        expected_signals = [
            make_trend_signal("AI tools growing"),
            make_trend_signal("No-code platforms rising"),
        ]
        expected_output = TrendScannerOutput(signals=expected_signals)

        with patch("nexis.agents.base.init_chat_model") as mock_init:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value = mock_llm
            mock_llm.with_structured_output.return_value = mock_llm
            mock_llm.ainvoke = AsyncMock(return_value=_wrap(expected_output))
            mock_init.return_value = mock_llm

            agent = TrendScanner.__new__(TrendScanner)
            agent.model_name = "claude-sonnet-4-6"
            agent.output_schema = TrendScannerOutput
            agent.system_prompt = "test"
            agent.max_retries = 0
            agent._llm = mock_llm
            mock_scraper = MagicMock()
            mock_scraper.scrape = AsyncMock(return_value=[make_trend_signal("raw")])
            agent._scraper = mock_scraper

            result = await agent.invoke(keywords=["SaaS", "developer", "tools"])

        assert isinstance(result, TrendScannerOutput)
        assert len(result.signals) == 2

    @pytest.mark.asyncio
    async def test_calls_scraper_with_keywords(self, sample_config):
        """TrendScanner should pass keywords to TrendScraperTool.scrape."""
        expected_output = TrendScannerOutput(signals=[make_trend_signal()])

        with patch("nexis.agents.base.init_chat_model") as mock_init:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value = mock_llm
            mock_llm.with_structured_output.return_value = mock_llm
            mock_llm.ainvoke = AsyncMock(return_value=_wrap(expected_output))
            mock_init.return_value = mock_llm

            agent = TrendScanner.__new__(TrendScanner)
            agent.model_name = "claude-sonnet-4-6"
            agent.output_schema = TrendScannerOutput
            agent.system_prompt = "test"
            agent.max_retries = 0
            agent._llm = mock_llm
            mock_scraper = MagicMock()
            mock_scraper.scrape = AsyncMock(return_value=[])
            agent._scraper = mock_scraper

            keywords = ["AI", "SaaS", "developer"]
            await agent.invoke(keywords=keywords)

        mock_scraper.scrape.assert_called_once_with(keywords)


# ---------------------------------------------------------------------------
# NicheValidator tests
# ---------------------------------------------------------------------------


class TestNicheValidator:
    @pytest.mark.asyncio
    async def test_returns_filtered_ideas(self, sample_config):
        """NicheValidator should filter out dominated ideas."""
        all_ideas = [
            make_business_idea("AI Email Client"),  # dominated by Google/Microsoft
            make_business_idea("Niche DevTool"),    # viable niche
            make_business_idea("AI Code Review"),   # dominated
        ]
        # LLM filters to only the viable one
        filtered_ideas = [make_business_idea("Niche DevTool")]
        expected_output = NicheValidatorOutput(ideas=filtered_ideas)

        with patch("nexis.agents.base.init_chat_model") as mock_init:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value = mock_llm
            mock_llm.with_structured_output.return_value = mock_llm
            mock_llm.ainvoke = AsyncMock(return_value=_wrap(expected_output))
            mock_init.return_value = mock_llm

            agent = NicheValidator.__new__(NicheValidator)
            agent.model_name = "claude-sonnet-4-6"
            agent.output_schema = NicheValidatorOutput
            agent.system_prompt = "test"
            agent.max_retries = 0
            agent._llm = mock_llm

            result = await agent.invoke(ideas=all_ideas)

        assert isinstance(result, NicheValidatorOutput)
        assert len(result.ideas) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_all_filtered(self, sample_config):
        """NicheValidator should return empty list when all ideas are dominated."""
        all_ideas = [
            make_business_idea("Gmail clone"),
            make_business_idea("AWS S3 clone"),
        ]
        expected_output = NicheValidatorOutput(ideas=[])

        with patch("nexis.agents.base.init_chat_model") as mock_init:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value = mock_llm
            mock_llm.with_structured_output.return_value = mock_llm
            mock_llm.ainvoke = AsyncMock(return_value=_wrap(expected_output))
            mock_init.return_value = mock_llm

            agent = NicheValidator.__new__(NicheValidator)
            agent.model_name = "claude-sonnet-4-6"
            agent.output_schema = NicheValidatorOutput
            agent.system_prompt = "test"
            agent.max_retries = 0
            agent._llm = mock_llm

            result = await agent.invoke(ideas=all_ideas)

        assert isinstance(result, NicheValidatorOutput)
        assert result.ideas == []
