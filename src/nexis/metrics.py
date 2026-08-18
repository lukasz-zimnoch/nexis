"""Token, cost and time totals for one pipeline run.

These models only hold numbers and add to them. The run scope that feeds them
lives in nexis/telemetry.py.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Bucket for a call made outside an instrumented node, which has no layer to
# charge it to.
UNATTRIBUTED_LAYER = "unattributed"


class CallMetrics(BaseModel):
    """Totals over a set of LLM calls."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    # Summed time spent inside LLM calls. A layer runs its calls concurrently,
    # so this exceeds the wall time of the run.
    llm_seconds: float = 0.0

    def add(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        seconds: float,
    ) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_usd += cost_usd
        self.llm_seconds += seconds


class RunMetrics(BaseModel):
    """What one run of the pipeline spent, in total and per layer and agent."""

    run_id: str
    wall_seconds: float = 0.0
    totals: CallMetrics = Field(default_factory=CallMetrics)
    by_layer: dict[str, CallMetrics] = Field(default_factory=dict)
    by_agent: dict[str, CallMetrics] = Field(default_factory=dict)
    # Maps an agent to the digest of the system prompt it sent. Two runs with the
    # same digest for an agent ran the same instructions.
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    # Models that nexis/pricing.py holds no price for. Their tokens count in the
    # totals, their cost does not, so cost_usd is a floor while this is not empty.
    unpriced_models: list[str] = Field(default_factory=list)

    def record_call(
        self,
        *,
        agent: str,
        layer: str | None,
        model: str,
        input_tokens: int,
        output_tokens: int,
        seconds: float,
        cost_usd: float | None,
        prompt_version: str | None = None,
    ) -> None:
        """Add one LLM call to the totals.

        Pass `cost_usd=None` when no price is known for `model`. A call that
        failed validation belongs here too, because a retry pays for both
        attempts.
        """
        if cost_usd is None:
            if model not in self.unpriced_models:
                self.unpriced_models.append(model)
            cost_usd = 0.0

        buckets = (
            self.totals,
            self.by_layer.setdefault(layer or UNATTRIBUTED_LAYER, CallMetrics()),
            self.by_agent.setdefault(agent, CallMetrics()),
        )
        for bucket in buckets:
            bucket.add(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                seconds=seconds,
            )

        if prompt_version is not None:
            self.prompt_versions[agent] = prompt_version
