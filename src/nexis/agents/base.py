"""Base agent abstraction with structured output and retry."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from nexis.telemetry import log_llm_call, prompt_version

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def build_llm(model_name: str):
    """Build an LLM client routed through OpenRouter."""
    return ChatOpenAI(
        model=model_name,
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/lukasz-zimnoch/nexis",
            "X-Title": "Nexis",
        },
    )


class BaseAgent:
    """LLM-backed agent with structured output and automatic retry."""

    def __init__(
        self,
        model_name: str,
        output_schema: type[T],
        system_prompt: str,
        tools: list | None = None,
        max_retries: int = 2,
        timeout: int = 120,
        fallback_model: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.output_schema = output_schema
        self.system_prompt = system_prompt
        self.prompt_version = prompt_version(system_prompt)
        self.max_retries = max_retries
        self.timeout = timeout
        self.fallback_model = fallback_model
        self._tools = tools
        self._switched_to_fallback = False

        llm = build_llm(model_name)
        if tools:
            llm = llm.bind_tools(tools)
        self._llm = llm.with_structured_output(output_schema, include_raw=True)

    async def invoke(self, input_data: dict[str, Any]) -> T:
        """Invoke the agent with retry on validation failure."""
        messages: list = [SystemMessage(content=self.system_prompt)]
        human_content = self._format_input(input_data)
        messages.append(HumanMessage(content=human_content))

        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            if last_error is not None:
                logger.warning(
                    "%s retry %d/%d after error: %s",
                    self.__class__.__name__,
                    attempt,
                    self.max_retries,
                    last_error,
                )
                messages.append(
                    HumanMessage(
                        content=f"The previous response failed validation: {last_error}\nPlease fix and retry."
                    )
                )

            try:
                logger.debug(
                    "%s invoking LLM (attempt %d/%d)",
                    self.__class__.__name__,
                    attempt + 1,
                    self.max_retries + 1,
                )
                t0 = time.perf_counter()
                raw_result = await asyncio.wait_for(
                    self._llm.ainvoke(messages),
                    timeout=self.timeout,
                )
                latency_ms = (time.perf_counter() - t0) * 1000

                parsed = raw_result["parsed"]
                raw_msg = raw_result["raw"]
                parsing_error = raw_result.get("parsing_error")

                usage = getattr(raw_msg, "usage_metadata", None) or {}
                if isinstance(usage, dict):
                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)
                    total_tokens = usage.get("total_tokens", 0)
                else:
                    input_tokens = getattr(usage, "input_tokens", 0)
                    output_tokens = getattr(usage, "output_tokens", 0)
                    total_tokens = getattr(usage, "total_tokens", 0)

                log_llm_call(
                    agent=self.__class__.__name__,
                    model=self.model_name,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    attempt=attempt + 1,
                    success=parsing_error is None,
                    prompt_version=self.prompt_version,
                )

                if parsing_error is not None:
                    last_error = str(parsing_error)
                    logger.warning(
                        "%s parsing error on attempt %d: %s",
                        self.__class__.__name__,
                        attempt + 1,
                        parsing_error,
                    )
                    continue

                logger.debug(
                    "%s succeeded on attempt %d", self.__class__.__name__, attempt + 1
                )
                return parsed  # type: ignore[return-value]
            except asyncio.TimeoutError:
                last_error = f"Request timed out after {self.timeout} seconds"
                logger.error(
                    "%s timed out on attempt %d", self.__class__.__name__, attempt + 1
                )
                self._switch_to_fallback()
            except Exception as exc:
                last_error = str(exc)
                logger.error(
                    "%s error on attempt %d: %s",
                    self.__class__.__name__,
                    attempt + 1,
                    exc,
                )

        # All retries exhausted — return partial result with failure_reason
        logger.error(
            "%s exhausted all retries, returning failure result",
            self.__class__.__name__,
        )
        return self._failure_result(last_error or "Unknown error")

    def _switch_to_fallback(self) -> None:
        """Switch to fallback model for remaining retries after a timeout."""
        if self._switched_to_fallback or not self.fallback_model:
            return
        if self.fallback_model == self.model_name:
            return
        logger.warning(
            "%s switching from %s to fallback model %s",
            self.__class__.__name__,
            self.model_name,
            self.fallback_model,
        )
        self._switched_to_fallback = True
        self.model_name = self.fallback_model
        llm = build_llm(self.fallback_model)
        if self._tools:
            llm = llm.bind_tools(self._tools)
        self._llm = llm.with_structured_output(self.output_schema, include_raw=True)

    def _format_input(self, input_data: dict[str, Any]) -> str:
        """Format input dict into a human message string."""
        parts = []
        for key, value in input_data.items():
            if hasattr(value, "model_dump_json"):
                parts.append(f"{key}:\n{value.model_dump_json(indent=2)}")
            elif (
                isinstance(value, list)
                and value
                and hasattr(value[0], "model_dump_json")
            ):
                items = "\n".join(v.model_dump_json(indent=2) for v in value)
                parts.append(f"{key}:\n{items}")
            else:
                parts.append(f"{key}: {value}")
        return "\n\n".join(parts)

    def _failure_result(self, reason: str) -> T:
        """Build a minimal valid instance with failure_reason set."""
        # Try to construct with failure_reason; fall back to a dict-based attempt
        schema = self.output_schema
        fields = schema.model_fields
        kwargs: dict[str, Any] = {}

        for field_name, field_info in fields.items():
            if field_name == "failure_reason":
                kwargs["failure_reason"] = reason
            elif not field_info.is_required():
                pass
            else:
                # Provide minimal valid values for required fields
                annotation = field_info.annotation
                kwargs[field_name] = _minimal_value(annotation)

        try:
            return schema(**kwargs)
        except Exception as exc:
            logger.error(
                "Could not construct failure result for %s: %s", schema.__name__, exc
            )
            raise RuntimeError(
                f"Agent {self.__class__.__name__} failed and cannot construct failure result: {reason}"
            ) from exc


def _minimal_value(annotation: Any) -> Any:
    """Return a minimal valid value for the given type annotation."""
    import enum

    origin = getattr(annotation, "__origin__", None)
    if annotation is list or origin is list:
        return []
    if annotation is dict or origin is dict:
        return {}
    if annotation is str or annotation == "str":
        return ""
    if annotation is int or annotation == "int":
        return 1
    if annotation is float or annotation == "float":
        return 0.0
    if annotation is bool or annotation == "bool":
        return False
    # Enum types — return the first member
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        members = list(annotation)
        return members[0] if members else None
    # Pydantic BaseModel subclasses — construct with minimal values
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        kwargs: dict[str, Any] = {}
        for fn, fi in annotation.model_fields.items():
            if fi.is_required():
                kwargs[fn] = _minimal_value(fi.annotation)
        try:
            return annotation(**kwargs)
        except Exception:
            return None
    # For Union/Optional types — pick first non-None arg
    if origin is type(None):
        return None
    args = getattr(annotation, "__args__", None)
    if args:
        for arg in args:
            if arg is not type(None):
                return _minimal_value(arg)
    return None
