from __future__ import annotations

import math
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from nexis import models as _models


def _default_agent_models() -> dict[str, str]:
    return {
        "trend_scanner": _models.TREND_SCANNER,
        "research_agent": _models.RESEARCH_AGENT,
        "niche_validator": _models.NICHE_VALIDATOR,
        "reviewer_market": _models.REVIEWER_MARKET,
        "reviewer_technical": _models.REVIEWER_TECHNICAL,
        "reviewer_moat": _models.REVIEWER_MOAT,
        "reviewer_financial": _models.REVIEWER_FINANCIAL,
        "reviewer_risk": _models.REVIEWER_RISK,
        "reviewer_ai_resilience": _models.REVIEWER_AI_RESILIENCE,
        "mvp_architect": _models.MVP_ARCHITECT,
        "gtm_strategist": _models.GTM_STRATEGIST,
        "business_plan_composer": _models.BUSINESS_PLAN_COMPOSER,
        "devils_advocate": _models.DEVILS_ADVOCATE,
    }


class PipelineConfig(BaseSettings):
    research_prompt: str
    num_ideas: int = 8
    top_k: int = 3
    score_threshold: float = 0.55
    max_retries: int = 2
    reviewer_weights: dict[str, float] = {
        "market": 0.25,
        "technical": 0.20,
        "financial": 0.20,
        "moat": 0.15,
        "risk": 0.10,
        "ai_resilience": 0.10,
    }
    agent_models: dict[str, str] = Field(default_factory=_default_agent_models)
    output_format: Literal["markdown", "json"] = "markdown"
    checkpoint_db_path: str = "./nexis_dev.db"

    @model_validator(mode="after")
    def validate_weights_sum(self) -> "PipelineConfig":
        total = sum(self.reviewer_weights.values())
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(f"reviewer_weights must sum to 1.0, got {total:.6f}")
        return self

    def model_for(self, agent_key: str) -> str:
        try:
            return self.agent_models[agent_key]
        except KeyError:
            raise ValueError(
                f"Unknown agent key {agent_key!r}. Valid keys: {sorted(self.agent_models)}"
            )
