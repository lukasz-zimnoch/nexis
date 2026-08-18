"""Tests for nexis.metrics."""

from __future__ import annotations

import pytest

from nexis.metrics import UNATTRIBUTED_LAYER, RunMetrics


def _record(metrics: RunMetrics, **overrides) -> None:
    call = {
        "agent": "ResearchAgent",
        "layer": "research",
        "model": "anthropic/claude-opus-5",
        "input_tokens": 1_000,
        "output_tokens": 200,
        "seconds": 1.5,
        "cost_usd": 0.01,
    }
    call.update(overrides)
    metrics.record_call(**call)


class TestRecordCall:
    def test_adds_one_call_to_the_totals(self):
        metrics = RunMetrics(run_id="run-1")
        _record(metrics)

        assert metrics.totals.calls == 1
        assert metrics.totals.input_tokens == 1_000
        assert metrics.totals.output_tokens == 200
        assert metrics.totals.cost_usd == pytest.approx(0.01)
        assert metrics.totals.llm_seconds == pytest.approx(1.5)

    def test_sums_repeated_calls(self):
        metrics = RunMetrics(run_id="run-1")
        _record(metrics)
        _record(
            metrics, input_tokens=500, output_tokens=100, cost_usd=0.02, seconds=0.5
        )

        assert metrics.totals.calls == 2
        assert metrics.totals.input_tokens == 1_500
        assert metrics.totals.cost_usd == pytest.approx(0.03)
        assert metrics.totals.llm_seconds == pytest.approx(2.0)

    def test_splits_by_layer_and_by_agent(self):
        metrics = RunMetrics(run_id="run-1")
        _record(metrics, layer="research", agent="ResearchAgent")
        _record(metrics, layer="review", agent="MarketCritic")
        _record(metrics, layer="review", agent="RiskCritic")

        assert metrics.by_layer["research"].calls == 1
        assert metrics.by_layer["review"].calls == 2
        assert set(metrics.by_agent) == {"ResearchAgent", "MarketCritic", "RiskCritic"}
        assert metrics.totals.calls == 3

    def test_call_without_a_layer_lands_in_one_bucket(self):
        metrics = RunMetrics(run_id="run-1")
        _record(metrics, layer=None)
        assert metrics.by_layer[UNATTRIBUTED_LAYER].calls == 1

    def test_counts_a_failed_call_because_a_retry_pays_twice(self):
        metrics = RunMetrics(run_id="run-1")
        _record(metrics)
        _record(metrics)
        assert metrics.totals.calls == 2
        assert metrics.totals.cost_usd == pytest.approx(0.02)

    def test_records_the_prompt_version_per_agent(self):
        metrics = RunMetrics(run_id="run-1")
        _record(metrics, agent="ResearchAgent", prompt_version="abc123abc123")
        _record(metrics, agent="TrendScanner", prompt_version="def456def456")

        assert metrics.prompt_versions == {
            "ResearchAgent": "abc123abc123",
            "TrendScanner": "def456def456",
        }

    def test_keeps_no_prompt_version_when_none_is_given(self):
        metrics = RunMetrics(run_id="run-1")
        _record(metrics)
        assert metrics.prompt_versions == {}


class TestUnpricedModels:
    def test_names_a_model_with_no_price(self):
        metrics = RunMetrics(run_id="run-1")
        _record(metrics, model="acme/unreleased-model", cost_usd=None)
        assert metrics.unpriced_models == ["acme/unreleased-model"]

    def test_names_it_once_per_run(self):
        metrics = RunMetrics(run_id="run-1")
        _record(metrics, model="acme/unreleased-model", cost_usd=None)
        _record(metrics, model="acme/unreleased-model", cost_usd=None)
        assert metrics.unpriced_models == ["acme/unreleased-model"]
        assert metrics.totals.calls == 2

    def test_counts_the_tokens_of_an_unpriced_call(self):
        metrics = RunMetrics(run_id="run-1")
        _record(metrics, model="acme/unreleased-model", cost_usd=None)
        assert metrics.totals.input_tokens == 1_000
        assert metrics.totals.cost_usd == 0.0


def test_run_metrics_round_trip_json():
    metrics = RunMetrics(run_id="run-1")
    _record(metrics, prompt_version="abc123abc123")
    metrics.wall_seconds = 12.5

    restored = RunMetrics.model_validate_json(metrics.model_dump_json())
    assert restored == metrics
