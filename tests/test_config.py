"""Tests for PipelineConfig."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from nexis.config import PipelineConfig


def test_valid_construction():
    config = PipelineConfig(
        research_prompt="Find SaaS ideas",
        model_name="claude-sonnet-4-6",
    )
    assert config.num_ideas == 8
    assert config.top_k == 3
    assert config.score_threshold == 0.55
    assert config.max_retries == 2
    assert config.output_format == "markdown"
    assert config.checkpoint_db_path == "./nexis_dev.db"


def test_default_weights_sum_to_one():
    config = PipelineConfig(
        research_prompt="test",
        model_name="claude-sonnet-4-6",
    )
    assert abs(sum(config.reviewer_weights.values()) - 1.0) < 1e-6


def test_missing_research_prompt_raises():
    with pytest.raises(ValidationError):
        PipelineConfig(model_name="claude-sonnet-4-6")  # type: ignore[call-arg]


def test_missing_model_name_raises():
    with pytest.raises(ValidationError):
        PipelineConfig(research_prompt="test")  # type: ignore[call-arg]


def test_weights_not_summing_to_one_raises():
    with pytest.raises(ValidationError, match="sum to 1.0"):
        PipelineConfig(
            research_prompt="test",
            model_name="claude-sonnet-4-6",
            reviewer_weights={"market": 0.5, "technical": 0.5, "risk": 0.5},
        )


def test_custom_weights_accepted():
    weights = {
        "market": 0.30,
        "technical": 0.20,
        "financial": 0.20,
        "moat": 0.15,
        "risk": 0.05,
        "ai_resilience": 0.10,
    }
    config = PipelineConfig(
        research_prompt="test",
        model_name="claude-sonnet-4-6",
        reviewer_weights=weights,
    )
    assert config.reviewer_weights == weights


def test_output_format_validation():
    config = PipelineConfig(
        research_prompt="test",
        model_name="claude-sonnet-4-6",
        output_format="json",
    )
    assert config.output_format == "json"

    with pytest.raises(ValidationError):
        PipelineConfig(
            research_prompt="test",
            model_name="claude-sonnet-4-6",
            output_format="pdf",  # type: ignore[arg-type]
        )
