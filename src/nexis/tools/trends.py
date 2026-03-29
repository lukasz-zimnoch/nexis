"""Trend scraping via site-scoped search queries."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from nexis.state import TrendSignal
from nexis.tools.search import SearchTool

logger = logging.getLogger(__name__)

_TREND_SOURCES = [
    ("HackerNews", "site:news.ycombinator.com"),
    ("ProductHunt", "site:producthunt.com"),
    ("Reddit", "site:reddit.com r/entrepreneur OR r/SaaS OR r/startups"),
]


class TrendScraperTool:
    """Scrapes trend signals using site-scoped Tavily queries."""

    def __init__(self) -> None:
        self._search = SearchTool()

    async def scrape(
        self, keywords: list[str], max_per_source: int = 3
    ) -> list[TrendSignal]:
        """Scrape trend signals for the given keyword seeds."""
        keyword_str = " OR ".join(f'"{kw}"' for kw in keywords[:5])

        async def _scrape_source(
            source_name: str, site_query: str
        ) -> list[TrendSignal]:
            query = f"{site_query} {keyword_str}"
            try:
                results = await self._search.search(query, max_results=max_per_source)
                return [
                    TrendSignal(
                        source=source_name,
                        signal=r.get("title", r.get("content", "")[:120]),
                        url=r.get("url", ""),
                        timestamp=datetime.now(tz=timezone.utc).isoformat(),
                    )
                    for r in results
                ]
            except Exception as exc:
                logger.warning("Failed to scrape %s: %s", source_name, exc)
                return []

        results = await asyncio.gather(
            *[_scrape_source(name, query) for name, query in _TREND_SOURCES]
        )
        return [signal for source_signals in results for signal in source_signals]
