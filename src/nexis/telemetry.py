"""Structured telemetry for per-node and per-LLM-call instrumentation."""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import time
from typing import Any, Callable

logger = logging.getLogger("nexis.telemetry")


def instrument_node(node_fn: Callable, *, layer_id: str) -> Callable:
    """Wrap a LangGraph node function to emit a structured telemetry event on completion."""
    if asyncio.iscoroutinefunction(node_fn):
        @functools.wraps(node_fn)
        async def async_wrapper(state: Any) -> Any:
            return await _run_node(node_fn, state, layer_id)
        return async_wrapper
    else:
        @functools.wraps(node_fn)
        def sync_wrapper(state: Any) -> Any:
            node_name = node_fn.__name__
            input_keys = list(state.keys()) if hasattr(state, "keys") else []
            start = time.perf_counter()
            error_msg: str | None = None
            output_keys: list[str] = []
            try:
                result = node_fn(state)
                output_keys = list(result.keys()) if isinstance(result, dict) else []
                return result
            except Exception as exc:
                error_msg = str(exc)
                raise
            finally:
                _emit(node_name, layer_id, start, input_keys, output_keys, error_msg)
        return sync_wrapper


async def _run_node(node_fn: Callable, state: Any, layer_id: str) -> Any:
    node_name = node_fn.__name__
    input_keys = list(state.keys()) if hasattr(state, "keys") else []
    start = time.perf_counter()
    error_msg: str | None = None
    output_keys: list[str] = []
    try:
        result = await node_fn(state)
        output_keys = list(result.keys()) if isinstance(result, dict) else []
        return result
    except Exception as exc:
        error_msg = str(exc)
        raise
    finally:
        _emit(node_name, layer_id, start, input_keys, output_keys, error_msg)


def _emit(
    node_name: str,
    layer_id: str,
    start: float,
    input_keys: list[str],
    output_keys: list[str],
    error_msg: str | None,
) -> None:
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        json.dumps({
            "event": "node_complete",
            "node": node_name,
            "layer": layer_id,
            "latency_ms": latency_ms,
            "input_keys": input_keys,
            "output_keys": output_keys,
            "error": error_msg,
        })
    )


def log_llm_call(
    *,
    agent: str,
    model: str,
    latency_ms: float,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    attempt: int,
    success: bool,
) -> None:
    """Emit a structured telemetry event for an LLM call."""
    logger.info(
        json.dumps({
            "event": "llm_call",
            "agent": agent,
            "model": model,
            "latency_ms": round(latency_ms, 2),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "attempt": attempt,
            "success": success,
        })
    )
