"""Tests for BaseAgent."""
from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, ValidationError

from nexis.agents.base import BaseAgent, _minimal_value, build_llm


class SimpleOutput(BaseModel):
    answer: str
    score: int = 0
    failure_reason: str | None = None


class RequiredOutput(BaseModel):
    name: str
    count: int
    failure_reason: str | None = None


def _make_raw_msg(input_tokens=10, output_tokens=20, total_tokens=30):
    msg = MagicMock()
    msg.usage_metadata = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
    return msg


def _wrap(parsed, raw=None):
    """Wrap a parsed result in the include_raw=True dict format."""
    return {"parsed": parsed, "raw": raw or _make_raw_msg(), "parsing_error": None}


@pytest.fixture
def mock_llm():
    """Patch init_chat_model to return a mock LLM."""
    with patch("nexis.agents.base.ChatOpenAI") as mock_init:
        mock_chain = MagicMock()
        mock_init.return_value.with_structured_output.return_value = mock_chain
        yield mock_chain


def make_agent(mock_llm) -> BaseAgent:
    return BaseAgent(
        model_name="claude-sonnet-4-6",
        output_schema=SimpleOutput,
        system_prompt="You are a test agent.",
        max_retries=2,
    )


@pytest.mark.asyncio
async def test_happy_path(mock_llm):
    expected = SimpleOutput(answer="Paris", score=9)
    mock_llm.ainvoke = AsyncMock(return_value=_wrap(expected))

    agent = make_agent(mock_llm)
    result = await agent.invoke({"question": "Capital of France?"})

    assert result.answer == "Paris"
    assert result.score == 9
    assert result.failure_reason is None
    mock_llm.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_retry_on_failure_then_success(mock_llm):
    good = SimpleOutput(answer="OK", score=5)
    mock_llm.ainvoke = AsyncMock(
        side_effect=[Exception("LLM error"), _wrap(good)]
    )

    agent = make_agent(mock_llm)
    result = await agent.invoke({"q": "test"})

    assert result.answer == "OK"
    assert mock_llm.ainvoke.call_count == 2


@pytest.mark.asyncio
async def test_exhausted_retries_returns_failure_reason(mock_llm):
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("always fails"))

    agent = make_agent(mock_llm)
    result = await agent.invoke({"q": "test"})

    assert result.failure_reason is not None
    assert "always fails" in result.failure_reason
    assert mock_llm.ainvoke.call_count == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_timeout_results_in_failure_reason(mock_llm):
    async def slow_invoke(*args, **kwargs):
        await asyncio.sleep(200)  # longer than 120s timeout
        return SimpleOutput(answer="late")

    mock_llm.ainvoke = slow_invoke

    agent = make_agent(mock_llm)
    with patch("nexis.agents.base.asyncio.wait_for", side_effect=asyncio.TimeoutError):
        result = await agent.invoke({"q": "test"})

    assert result.failure_reason is not None
    assert "timed out" in result.failure_reason.lower()


def test_minimal_value_types():
    assert _minimal_value(str) == ""
    assert _minimal_value(int) == 0
    assert _minimal_value(float) == 0.0
    assert _minimal_value(bool) is False
    assert _minimal_value(list) == []
    assert _minimal_value(dict) == {}


def test_format_input_with_pydantic_model():
    with patch("nexis.agents.base.ChatOpenAI"):
        agent = BaseAgent(
            model_name="test",
            output_schema=SimpleOutput,
            system_prompt="test",
        )

    class M(BaseModel):
        x: int = 1

    result = agent._format_input({"key": "value", "model": M()})
    assert "key: value" in result
    assert "model:" in result


def test_build_llm_uses_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    with patch("nexis.agents.base.ChatOpenAI") as mock:
        import nexis.agents.base as base
        base.build_llm("anthropic/claude-opus-4-6")
    mock.assert_called_once()
    assert mock.call_args.kwargs["base_url"] == "https://openrouter.ai/api/v1"
    assert mock.call_args.kwargs["api_key"] == "sk-or-test"


@pytest.mark.asyncio
async def test_token_usage_logged(mock_llm, caplog):
    raw_msg = _make_raw_msg(input_tokens=100, output_tokens=50, total_tokens=150)
    mock_llm.ainvoke = AsyncMock(return_value=_wrap(SimpleOutput(answer="ok"), raw_msg))

    agent = make_agent(mock_llm)
    with caplog.at_level(logging.INFO, logger="nexis.telemetry"):
        await agent.invoke({"q": "test"})

    llm_events = [
        json.loads(r.message)
        for r in caplog.records
        if r.name == "nexis.telemetry"
        and "llm_call" in r.message
    ]
    assert len(llm_events) == 1
    event = llm_events[0]
    assert event["input_tokens"] == 100
    assert event["output_tokens"] == 50
    assert event["total_tokens"] == 150
    assert event["success"] is True
    assert event["attempt"] == 1
