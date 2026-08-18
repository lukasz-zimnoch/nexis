"""Structured telemetry for per-node and per-LLM-call instrumentation."""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator

from nexis.metrics import RunMetrics
from nexis.pricing import estimate_cost_usd

logger = logging.getLogger("nexis.telemetry")

# The run and the layer travel in context variables instead of arguments,
# because an agent sits several frames below the node that knows them. asyncio
# copies the context into every task it starts, so a fan-out inherits both.
_current_run: ContextVar[RunMetrics | None] = ContextVar("nexis_run", default=None)
_current_layer: ContextVar[str | None] = ContextVar("nexis_layer", default=None)


def current_run() -> RunMetrics | None:
    """Return the metrics of the running pipeline, or None outside a run scope."""
    return _current_run.get()


@contextmanager
def run_context(run_id: str) -> Iterator[RunMetrics]:
    """Open the metrics scope for one run and close it with a summary event.

    The caller keeps the yielded object after the scope ends, so a failed run can
    still report what it spent. `wall_seconds` covers the body of the scope.
    """
    metrics = RunMetrics(run_id=run_id)
    token = _current_run.set(metrics)
    start = time.perf_counter()
    try:
        yield metrics
    finally:
        metrics.wall_seconds = round(time.perf_counter() - start, 6)
        _current_run.reset(token)
        logger.info(
            json.dumps({"event": "run_complete", **metrics.model_dump(mode="json")})
        )


def prompt_version(system_prompt: str) -> str:
    """Return a short digest of a system prompt.

    The digest names the instructions a run used, so a change in output quality
    can be tied to a change of prompt. 12 hex characters of SHA-256 separate the
    handful of prompt versions one project produces.
    """
    return hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:12]


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
            layer_token = _current_layer.set(layer_id)
            try:
                result = node_fn(state)
                output_keys = list(result.keys()) if isinstance(result, dict) else []
                return result
            except Exception as exc:
                error_msg = str(exc)
                raise
            finally:
                _current_layer.reset(layer_token)
                _emit(node_name, layer_id, start, input_keys, output_keys, error_msg)

        return sync_wrapper


async def _run_node(node_fn: Callable, state: Any, layer_id: str) -> Any:
    node_name = node_fn.__name__
    input_keys = list(state.keys()) if hasattr(state, "keys") else []
    start = time.perf_counter()
    error_msg: str | None = None
    output_keys: list[str] = []
    layer_token = _current_layer.set(layer_id)
    try:
        result = await node_fn(state)
        output_keys = list(result.keys()) if isinstance(result, dict) else []
        return result
    except Exception as exc:
        error_msg = str(exc)
        raise
    finally:
        _current_layer.reset(layer_token)
        _emit(node_name, layer_id, start, input_keys, output_keys, error_msg)


def _run_id() -> str | None:
    run = _current_run.get()
    return run.run_id if run is not None else None


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
        json.dumps(
            {
                "event": "node_complete",
                "run_id": _run_id(),
                "node": node_name,
                "layer": layer_id,
                "latency_ms": latency_ms,
                "input_keys": input_keys,
                "output_keys": output_keys,
                "error": error_msg,
            }
        )
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
    prompt_version: str | None = None,
) -> None:
    """Emit a structured telemetry event for an LLM call and add it to the run totals.

    A null `cost_usd` in the event means nexis/pricing.py holds no price for the
    model, not that the call was free.
    """
    cost_usd = estimate_cost_usd(model, input_tokens, output_tokens)
    layer = _current_layer.get()

    run = _current_run.get()
    if run is not None:
        run.record_call(
            agent=agent,
            layer=layer,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            seconds=latency_ms / 1000,
            cost_usd=cost_usd,
            prompt_version=prompt_version,
        )

    logger.info(
        json.dumps(
            {
                "event": "llm_call",
                "run_id": _run_id(),
                "agent": agent,
                "layer": layer,
                "model": model,
                "prompt_version": prompt_version,
                "latency_ms": round(latency_ms, 2),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "cost_usd": round(cost_usd, 6) if cost_usd is not None else None,
                "attempt": attempt,
                "success": success,
            }
        )
    )
