"""Search tool wrappers for Tavily."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class TavilySearchTool:
    """Wraps the Tavily Python client for async search."""

    def __init__(self) -> None:
        from tavily import TavilyClient  # type: ignore[import]

        self._client = TavilyClient()

    async def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """Run a search query and return results."""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._client.search(query, max_results=max_results),
        )
        return response.get("results", [])


class SearchTool:
    """Facade that tries Tavily with exponential backoff, returns [] on failure."""

    _BACKOFF = [1, 4, 16]

    def __init__(self) -> None:
        self._tavily: TavilySearchTool | None = None
        try:
            self._tavily = TavilySearchTool()
        except Exception as exc:
            logger.warning("Could not initialize Tavily client: %s", exc)

    async def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """Search with retry and backoff. Returns empty list on persistent failure."""
        if self._tavily is None:
            logger.warning("No search backend available, returning empty results")
            return []

        for delay in [0] + self._BACKOFF:
            if delay:
                await asyncio.sleep(delay)
            try:
                results = await self._tavily.search(query, max_results=max_results)
                return results
            except Exception as exc:
                logger.warning("Search failed (will retry): %s", exc)

        logger.error("Search exhausted all retries for query: %s", query)
        return []
