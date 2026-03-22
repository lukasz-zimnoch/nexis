from __future__ import annotations

import math
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings


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
        "moat": 0.20,
        "risk": 0.15,
    }
    model_name: str
    output_format: Literal["markdown", "json"] = "markdown"
    checkpoint_db_path: str = "./nexis_dev.db"

    @model_validator(mode="after")
    def validate_weights_sum(self) -> "PipelineConfig":
        total = sum(self.reviewer_weights.values())
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(
                f"reviewer_weights must sum to 1.0, got {total:.6f}"
            )
        return self
