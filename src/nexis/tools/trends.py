"""Trend scraping via site-scoped search queries."""
from __future__ import annotations

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

    async def scrape(self, keywords: list[str], max_per_source: int = 3) -> list[TrendSignal]:
        """Scrape trend signals for the given keyword seeds."""
        signals: list[TrendSignal] = []
        keyword_str = " OR ".join(f'"{kw}"' for kw in keywords[:5])

        for source_name, site_query in _TREND_SOURCES:
            query = f"{site_query} {keyword_str}"
            try:
                results = await self._search.search(query, max_results=max_per_source)
                for r in results:
                    signals.append(
                        TrendSignal(
                            source=source_name,
                            signal=r.get("title", r.get("content", "")[:120]),
                            url=r.get("url", ""),
                            timestamp=datetime.now(tz=timezone.utc).isoformat(),
                        )
                    )
            except Exception as exc:
                logger.warning("Failed to scrape %s: %s", source_name, exc)

        return signals
