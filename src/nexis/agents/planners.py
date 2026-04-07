"""Planning layer agents: MVPArchitect, GTMStrategist, BusinessPlanComposer."""

from __future__ import annotations

import logging

from nexis.agents.base import BaseAgent
from nexis.state import BusinessIdea, BusinessPlan, GTMPlan, MVPPlan, Review

logger = logging.getLogger(__name__)


class MVPArchitect(BaseAgent):
    """Defines the minimum viable product for a business idea."""

    def __init__(
        self,
        model_name: str,
        max_retries: int = 2,
        timeout: int = 120,
        fallback_model: str | None = None,
    ) -> None:
        super().__init__(
            model_name=model_name,
            output_schema=MVPPlan,
            system_prompt=(
                "You are an MVP Architect. Given a business idea and its reviews, define the "
                "minimum viable product: core features using MoSCoW prioritization, recommended "
                "tech stack, data model description, 4-8 week sprint plan, and estimated build cost."
            ),
            max_retries=max_retries,
            timeout=timeout,
            fallback_model=fallback_model,
        )

    async def invoke_mvp(self, idea: BusinessIdea, reviews: list[Review]) -> MVPPlan:
        """Generate an MVP plan for the given idea and reviews."""
        input_data = {
            "idea": idea,
            "reviews": reviews,
        }
        result = await super().invoke(input_data)
        return result  # type: ignore[return-value]


class GTMStrategist(BaseAgent):
    """Defines the go-to-market strategy for a business idea."""

    def __init__(
        self,
        model_name: str,
        max_retries: int = 2,
        timeout: int = 120,
        fallback_model: str | None = None,
    ) -> None:
        super().__init__(
            model_name=model_name,
            output_schema=GTMPlan,
            system_prompt=(
                "You are a GTM Strategist. Given a business idea and its reviews, define the "
                "go-to-market strategy: Ideal Customer Profile (ICP), positioning statement, "
                "acquisition channels, pricing model, phased launch sequence, and first 100 "
                "customers playbook."
            ),
            max_retries=max_retries,
            timeout=timeout,
            fallback_model=fallback_model,
        )

    async def invoke_gtm(self, idea: BusinessIdea, reviews: list[Review]) -> GTMPlan:
        """Generate a GTM plan for the given idea and reviews."""
        input_data = {
            "idea": idea,
            "reviews": reviews,
        }
        result = await super().invoke(input_data)
        return result  # type: ignore[return-value]


class BusinessPlanComposer(BaseAgent):
    """Merges MVP and GTM plans into a cohesive business plan."""

    def __init__(
        self,
        model_name: str,
        max_retries: int = 2,
        timeout: int = 120,
        fallback_model: str | None = None,
    ) -> None:
        super().__init__(
            model_name=model_name,
            output_schema=BusinessPlan,
            system_prompt=(
                "You are a Business Plan Composer. Merge the MVP plan and GTM plan into a "
                "cohesive business plan with an executive summary, key assumptions, and "
                "success metrics."
            ),
            max_retries=max_retries,
            timeout=timeout,
            fallback_model=fallback_model,
        )

    async def invoke_plan(
        self, idea: BusinessIdea, mvp_plan: MVPPlan, gtm_plan: GTMPlan
    ) -> BusinessPlan:
        """Compose a business plan from MVP and GTM plans.

        Handles partial input gracefully: if mvp_plan.failure_reason is set,
        logs a warning and proceeds with the available data.
        """
        if mvp_plan.failure_reason:
            logger.warning(
                "BusinessPlanComposer: mvp_plan for idea %s has failure_reason: %s — "
                "proceeding with partial data",
                idea.id,
                mvp_plan.failure_reason,
            )
        if gtm_plan.failure_reason:
            logger.warning(
                "BusinessPlanComposer: gtm_plan for idea %s has failure_reason: %s — "
                "proceeding with partial data",
                idea.id,
                gtm_plan.failure_reason,
            )

        input_data = {
            "idea": idea,
            "mvp_plan": mvp_plan,
            "gtm_plan": gtm_plan,
        }
        result = await super().invoke(input_data)
        return result  # type: ignore[return-value]
