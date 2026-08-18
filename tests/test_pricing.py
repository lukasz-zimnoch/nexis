"""Tests for nexis.pricing."""

from __future__ import annotations

import pytest

from nexis.config import PipelineConfig
from nexis.models import DEFAULT_AGENT_MODELS
from nexis.pricing import MODEL_PRICES, estimate_cost_usd


class TestEstimateCostUsd:
    def test_prices_input_and_output_separately(self):
        # claude-opus-5 costs 5.00 per million input and 25.00 per million output.
        cost = estimate_cost_usd("anthropic/claude-opus-5", 1_000_000, 1_000_000)
        assert cost == pytest.approx(30.00)

    def test_scales_with_token_count(self):
        cost = estimate_cost_usd("anthropic/claude-sonnet-5", 2_000, 500)
        assert cost == pytest.approx(2_000 * 2.00 / 1e6 + 500 * 10.00 / 1e6)

    def test_zero_tokens_cost_nothing(self):
        assert estimate_cost_usd("anthropic/claude-opus-5", 0, 0) == 0.0

    def test_unknown_model_has_no_price(self):
        assert estimate_cost_usd("acme/unreleased-model", 1_000, 1_000) is None


class TestPriceTableCoverage:
    """Every model the pipeline reaches for by default must have a price."""

    @pytest.mark.parametrize(
        "model", sorted(set(DEFAULT_AGENT_MODELS.values())), ids=lambda m: m
    )
    def test_assigned_model_has_a_price(self, model: str):
        assert model in MODEL_PRICES

    def test_fallback_model_has_a_price(self):
        fallback = PipelineConfig.model_fields["fallback_model"].default
        assert fallback in MODEL_PRICES

    def test_every_price_is_positive(self):
        for model, price in MODEL_PRICES.items():
            assert price.input_usd_per_mtok > 0, model
            assert price.output_usd_per_mtok > 0, model
