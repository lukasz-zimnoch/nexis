"""Tests for search tools."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexis.tools.search import SearchTool, TavilySearchTool


@pytest.fixture
def mock_tavily_client():
    with patch("nexis.tools.search.TavilySearchTool") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.mark.asyncio
async def test_search_tool_returns_results(mock_tavily_client):
    expected_results = [{"title": "Result 1", "url": "https://example.com"}]
    mock_tavily_client.search = AsyncMock(return_value=expected_results)

    with patch("nexis.tools.search.TavilySearchTool") as mock_cls:
        mock_cls.return_value.search = AsyncMock(return_value=expected_results)
        tool = SearchTool()
        tool._tavily = MagicMock()
        tool._tavily.search = AsyncMock(return_value=expected_results)
        results = await tool.search("test query")

    assert results == expected_results


@pytest.mark.asyncio
async def test_search_tool_returns_empty_on_all_failures():
    tool = SearchTool.__new__(SearchTool)
    tool._tavily = MagicMock()
    tool._tavily.search = AsyncMock(side_effect=Exception("network error"))

    with patch("nexis.tools.search.asyncio.sleep", new_callable=AsyncMock):
        results = await tool.search("test query")

    assert results == []


@pytest.mark.asyncio
async def test_search_tool_no_backend():
    tool = SearchTool.__new__(SearchTool)
    tool._tavily = None

    results = await tool.search("test query")
    assert results == []


@pytest.mark.asyncio
async def test_tavily_search_tool_extracts_results():
    with patch("nexis.tools.search.TavilySearchTool.__init__", return_value=None):
        tool = TavilySearchTool.__new__(TavilySearchTool)
        tool._client = MagicMock()
        tool._client.search.return_value = {
            "results": [{"title": "HN Post", "url": "https://hn.com/1"}]
        }

        results = await tool.search("AI tools", max_results=3)

    assert len(results) == 1
    assert results[0]["title"] == "HN Post"
