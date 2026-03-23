"""Tests for nexis.telemetry."""
from __future__ import annotations

import json
import logging

import pytest

from nexis.telemetry import instrument_node, log_llm_call


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


def _find_event(caplog, event_type: str) -> dict:
    for record in caplog.records:
        try:
            data = json.loads(record.message)
            if data.get("event") == event_type:
                return data
        except (json.JSONDecodeError, AttributeError):
            pass
    raise AssertionError(f"No '{event_type}' event found in log records")
