"""Tests for the trend scraper tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from nexis.tools.trends import TrendScraperTool
from nexis.untrusted import MAX_UNTRUSTED_CHARS


def _tool(results: list[dict]) -> TrendScraperTool:
    tool = TrendScraperTool.__new__(TrendScraperTool)
    tool._search = MagicMock()
    tool._search.search = AsyncMock(return_value=results)
    return tool


@pytest.mark.asyncio
async def test_caps_the_stored_signal():
    """A long title cannot grow the report or the prompt without limit."""
    tool = _tool([{"title": "t" * 5000, "url": "https://example.com/1"}])

    signals = await tool.scrape(["SaaS"])

    assert signals
    for signal in signals:
        assert len(signal.signal) <= MAX_UNTRUSTED_CHARS + len(" [truncated]")
        assert signal.signal.endswith("[truncated]")


@pytest.mark.asyncio
async def test_keeps_a_short_title_unchanged():
    tool = _tool([{"title": "Show HN: a new tool", "url": "https://example.com/1"}])

    signals = await tool.scrape(["SaaS"])

    assert {s.signal for s in signals} == {"Show HN: a new tool"}
    assert {s.url for s in signals} == {"https://example.com/1"}


@pytest.mark.asyncio
async def test_scrapes_every_source():
    """One query per trend source, all run together."""
    tool = _tool([{"title": "Post", "url": "https://example.com/1"}])

    signals = await tool.scrape(["SaaS"])

    assert tool._search.search.await_count == 3
    assert {s.source for s in signals} == {"HackerNews", "ProductHunt", "Reddit"}
