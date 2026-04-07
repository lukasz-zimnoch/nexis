"""Research layer agents: ResearchAgent, TrendScanner, NicheValidator."""

from __future__ import annotations

import logging

from pydantic import BaseModel

from nexis.agents.base import BaseAgent
from nexis.config import PipelineConfig
from nexis.state import BusinessIdea, TrendSignal
from nexis.tools.search import SearchTool
from nexis.tools.trends import TrendScraperTool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class ResearchOutput(BaseModel):
    ideas: list[BusinessIdea]


class TrendScannerOutput(BaseModel):
    signals: list[TrendSignal]


class NicheValidatorOutput(BaseModel):
    ideas: list[BusinessIdea]


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


class ResearchAgent(BaseAgent):
    """Generates business ideas using web research and trend signals."""

    def __init__(
        self,
        model_name: str,
        max_retries: int = 2,
        timeout: int = 120,
        fallback_model: str | None = None,
    ) -> None:
        super().__init__(
            model_name=model_name,
            output_schema=ResearchOutput,
            system_prompt=(
                "You are a research agent that generates innovative business ideas. "
                "Generate structured business ideas based on the research prompt and "
                "trend signals provided."
            ),
            max_retries=max_retries,
            timeout=timeout,
            fallback_model=fallback_model,
        )
        self._search = SearchTool()

    async def invoke(  # type: ignore[override]
        self,
        research_prompt: str,
        trend_signals: list[TrendSignal],
        config: PipelineConfig,
    ) -> ResearchOutput:
        """Search for web context then call LLM to generate ideas."""
        search_results = await self._search.search(research_prompt, max_results=5)
        search_context = "\n".join(
            f"- {r.get('title', '')}: {r.get('content', '')[:200]}"
            for r in search_results
        )

        input_data = {
            "research_prompt": research_prompt,
            "num_ideas_requested": config.num_ideas,
            "trend_signals": trend_signals,
            "web_search_context": search_context or "(no search results available)",
        }

        result = await super().invoke(input_data)
        return result  # type: ignore[return-value]


class TrendScanner(BaseAgent):
    """Extracts trend signals from web sources."""

    def __init__(
        self,
        model_name: str,
        max_retries: int = 2,
        timeout: int = 120,
        fallback_model: str | None = None,
    ) -> None:
        super().__init__(
            model_name=model_name,
            output_schema=TrendScannerOutput,
            system_prompt=(
                "You are a trend scanner. Analyze the provided web search results and "
                "extract meaningful trend signals relevant to the research domain."
            ),
            max_retries=max_retries,
            timeout=timeout,
            fallback_model=fallback_model,
        )
        self._scraper = TrendScraperTool()

    async def invoke(  # type: ignore[override]
        self,
        keywords: list[str],
    ) -> TrendScannerOutput:
        """Scrape trend data then synthesize into structured signals."""
        raw_signals = await self._scraper.scrape(keywords)

        input_data = {
            "keywords": keywords,
            "raw_trend_data": raw_signals,
        }

        result = await super().invoke(input_data)
        return result  # type: ignore[return-value]


class NicheValidator(BaseAgent):
    """Filters ideas by removing duplicates and ideas with large incumbents."""

    def __init__(
        self,
        model_name: str,
        max_retries: int = 2,
        timeout: int = 120,
        fallback_model: str | None = None,
    ) -> None:
        super().__init__(
            model_name=model_name,
            output_schema=NicheValidatorOutput,
            system_prompt=(
                "You are a niche validator. Review the list of business ideas and filter out "
                "duplicates and ideas with obvious large incumbents (Google, Amazon, Microsoft, "
                "etc.) that would make it nearly impossible for a small team to compete."
            ),
            max_retries=max_retries,
            timeout=timeout,
            fallback_model=fallback_model,
        )

    async def invoke(  # type: ignore[override]
        self,
        ideas: list[BusinessIdea],
    ) -> NicheValidatorOutput:
        """Pass ideas list to LLM for filtering."""
        input_data = {
            "ideas": ideas,
        }

        result = await super().invoke(input_data)
        return result  # type: ignore[return-value]
