from __future__ import annotations

import math
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from nexis import models as _models


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
    agent_models: dict[str, str] = Field(
        default_factory=_models.DEFAULT_AGENT_MODELS.copy
    )
    output_format: Literal["markdown", "json"] = "markdown"
    llm_timeout: int = 300
    fallback_model: str = "google/gemini-3.7-flash"

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
