"""Tests for nexis.telemetry."""

from __future__ import annotations

import asyncio
import json
import logging

import pytest

from nexis.metrics import UNATTRIBUTED_LAYER
from nexis.telemetry import (
    current_run,
    instrument_node,
    log_llm_call,
    prompt_version,
    run_context,
)

# A model that nexis/pricing.py has a price for, so a cost is expected.
PRICED_MODEL = "anthropic/claude-opus-5"


@pytest.mark.asyncio
async def test_instrument_node_logs_event(caplog):
    async def my_node(state):
        return {"result": "done"}

    wrapped = instrument_node(my_node, layer_id="test")

    with caplog.at_level(logging.INFO, logger="nexis.telemetry"):
        result = await wrapped({"input_key": "value"})

    assert result == {"result": "done"}
    event = _find_event(caplog, "node_complete")
    assert event["node"] == "my_node"
    assert event["layer"] == "test"
    assert "input_key" in event["input_keys"]
    assert "result" in event["output_keys"]
    assert event["error"] is None


@pytest.mark.asyncio
async def test_instrument_node_logs_error(caplog):
    async def failing_node(state):
        raise ValueError("boom")

    wrapped = instrument_node(failing_node, layer_id="test")

    with caplog.at_level(logging.INFO, logger="nexis.telemetry"):
        with pytest.raises(ValueError, match="boom"):
            await wrapped({"key": "val"})

    event = _find_event(caplog, "node_complete")
    assert event["error"] == "boom"


def test_instrument_node_sync_function(caplog):
    def sync_node(state):
        return {"sync_result": True}

    wrapped = instrument_node(sync_node, layer_id="test")

    with caplog.at_level(logging.INFO, logger="nexis.telemetry"):
        result = wrapped({"key": "val"})

    assert result == {"sync_result": True}
    event = _find_event(caplog, "node_complete")
    assert event["node"] == "sync_node"
    assert event["layer"] == "test"


@pytest.mark.asyncio
async def test_instrument_node_preserves_return_value():
    expected = {"a": 1, "b": [1, 2, 3]}

    async def node(state):
        return expected

    wrapped = instrument_node(node, layer_id="test")
    result = await wrapped({})
    assert result == expected


def _log_call(**overrides) -> None:
    call = {
        "agent": "ResearchAgent",
        "model": PRICED_MODEL,
        "latency_ms": 1_500.0,
        "input_tokens": 1_000,
        "output_tokens": 200,
        "total_tokens": 1_200,
        "attempt": 1,
        "success": True,
    }
    call.update(overrides)
    log_llm_call(**call)


class TestPromptVersion:
    def test_same_prompt_gives_the_same_digest(self):
        assert prompt_version("You are a critic.") == prompt_version(
            "You are a critic."
        )

    def test_one_changed_character_changes_the_digest(self):
        assert prompt_version("You are a critic.") != prompt_version(
            "You are a critic!"
        )

    def test_digest_is_twelve_hex_characters(self):
        digest = prompt_version("You are a critic.")
        assert len(digest) == 12
        assert all(c in "0123456789abcdef" for c in digest)


class TestRunContext:
    def test_yields_metrics_and_measures_wall_time(self):
        with run_context("run-1") as metrics:
            assert current_run() is metrics
            assert metrics.run_id == "run-1"
        assert metrics.wall_seconds > 0

    def test_closes_the_scope_on_exit(self):
        with run_context("run-1"):
            pass
        assert current_run() is None

    def test_keeps_the_totals_of_a_failed_run(self):
        with pytest.raises(RuntimeError, match="boom"):
            with run_context("run-1") as metrics:
                _log_call()
                raise RuntimeError("boom")

        assert metrics.totals.calls == 1
        assert metrics.wall_seconds > 0

    def test_emits_a_summary_event(self, caplog):
        with caplog.at_level(logging.INFO, logger="nexis.telemetry"):
            with run_context("run-1"):
                _log_call()

        event = _find_event(caplog, "run_complete")
        assert event["run_id"] == "run-1"
        assert event["totals"]["calls"] == 1
        assert event["by_agent"]["ResearchAgent"]["calls"] == 1


class TestLlmCallEvent:
    def test_carries_the_run_id_and_the_estimated_cost(self, caplog):
        with caplog.at_level(logging.INFO, logger="nexis.telemetry"):
            with run_context("run-1"):
                _log_call(prompt_version="abc123abc123")

        event = _find_event(caplog, "llm_call")
        assert event["run_id"] == "run-1"
        assert event["prompt_version"] == "abc123abc123"
        # 1000 input tokens at 5.00 and 200 output tokens at 25.00 per million.
        assert event["cost_usd"] == pytest.approx(0.01)

    def test_reports_no_cost_for_a_model_without_a_price(self, caplog):
        with caplog.at_level(logging.INFO, logger="nexis.telemetry"):
            with run_context("run-1") as metrics:
                _log_call(model="acme/unreleased-model")

        event = _find_event(caplog, "llm_call")
        assert event["cost_usd"] is None
        assert metrics.unpriced_models == ["acme/unreleased-model"]

    def test_works_without_a_run_scope(self, caplog):
        with caplog.at_level(logging.INFO, logger="nexis.telemetry"):
            _log_call()

        event = _find_event(caplog, "llm_call")
        assert event["run_id"] is None
        assert event["layer"] is None


class TestLayerAttribution:
    @pytest.mark.asyncio
    async def test_a_call_inside_a_node_belongs_to_that_layer(self):
        async def node(state):
            _log_call()
            return {}

        wrapped = instrument_node(node, layer_id="review")

        with run_context("run-1") as metrics:
            await wrapped({})

        assert metrics.by_layer["review"].calls == 1

    @pytest.mark.asyncio
    async def test_a_call_outside_a_node_is_unattributed(self):
        with run_context("run-1") as metrics:
            _log_call()
        assert metrics.by_layer[UNATTRIBUTED_LAYER].calls == 1

    @pytest.mark.asyncio
    async def test_concurrent_nodes_keep_their_own_layer(self):
        """Two nodes run at once must not read each other's layer.

        This is the reason the layer travels in a context variable: asyncio copies
        the context into each task, so a task sees only what its own node set.
        """

        async def node(state):
            await asyncio.sleep(0)
            _log_call()
            await asyncio.sleep(0)
            _log_call()
            return {}

        review_node = instrument_node(node, layer_id="review")
        planning_node = instrument_node(node, layer_id="planning")

        with run_context("run-1") as metrics:
            await asyncio.gather(review_node({}), planning_node({}))

        assert metrics.by_layer["review"].calls == 2
        assert metrics.by_layer["planning"].calls == 2
        assert metrics.totals.calls == 4
        assert UNATTRIBUTED_LAYER not in metrics.by_layer

    @pytest.mark.asyncio
    async def test_node_event_carries_the_run_id(self, caplog):
        async def node(state):
            return {}

        wrapped = instrument_node(node, layer_id="review")

        with caplog.at_level(logging.INFO, logger="nexis.telemetry"):
            with run_context("run-1"):
                await wrapped({})

        assert _find_event(caplog, "node_complete")["run_id"] == "run-1"


def _find_event(caplog, event_type: str) -> dict:
    for record in caplog.records:
        try:
            data = json.loads(record.message)
            if data.get("event") == event_type:
                return data
        except (json.JSONDecodeError, AttributeError):
            pass
    raise AssertionError(f"No '{event_type}' event found in log records")
