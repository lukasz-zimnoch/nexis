"""Base agent abstraction with structured output and retry."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, TypeVar

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class BaseAgent:
    """LLM-backed agent with structured output and automatic retry."""

    def __init__(
        self,
        model_name: str,
        output_schema: type[T],
        system_prompt: str,
        tools: list | None = None,
        max_retries: int = 2,
    ) -> None:
        self.model_name = model_name
        self.output_schema = output_schema
        self.system_prompt = system_prompt
        self.max_retries = max_retries

        llm = init_chat_model(model_name)
        if tools:
            llm = llm.bind_tools(tools)
        self._llm = llm.with_structured_output(output_schema)

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
                result = await asyncio.wait_for(
                    self._llm.ainvoke(messages),
                    timeout=120,
                )
                logger.debug("%s succeeded on attempt %d", self.__class__.__name__, attempt + 1)
                return result  # type: ignore[return-value]
            except asyncio.TimeoutError:
                last_error = "Request timed out after 120 seconds"
                logger.error("%s timed out on attempt %d", self.__class__.__name__, attempt + 1)
            except (ValidationError, Exception) as exc:
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

    def _format_input(self, input_data: dict[str, Any]) -> str:
        """Format input dict into a human message string."""
        parts = []
        for key, value in input_data.items():
            if hasattr(value, "model_dump_json"):
                parts.append(f"{key}:\n{value.model_dump_json(indent=2)}")
            elif isinstance(value, list) and value and hasattr(value[0], "model_dump_json"):
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
                pass  # use default
            else:
                # Provide minimal valid values for required fields
                annotation = field_info.annotation
                kwargs[field_name] = _minimal_value(annotation)

        try:
            return schema(**kwargs)
        except Exception as exc:
            logger.error("Could not construct failure result for %s: %s", schema.__name__, exc)
            raise RuntimeError(
                f"Agent {self.__class__.__name__} failed and cannot construct failure result: {reason}"
            ) from exc


def _minimal_value(annotation: Any) -> Any:
    """Return a minimal valid value for the given type annotation."""
    import typing

    origin = getattr(annotation, "__origin__", None)
    if annotation is list or origin is list:
        return []
    if annotation is dict or origin is dict:
        return {}
    if annotation is str or annotation == "str":
        return ""
    if annotation is int or annotation == "int":
        return 0
    if annotation is float or annotation == "float":
        return 0.0
    if annotation is bool or annotation == "bool":
        return False
    # For Union/Optional types — pick first non-None arg
    if origin is type(None):
        return None
    args = getattr(annotation, "__args__", None)
    if args:
        for arg in args:
            if arg is not type(None):
                return _minimal_value(arg)
    return None
