"""Collect reviews for the frozen dataset. This is the only part that costs money.

Collection writes raw reviews to disk and stops there. Every number in the
reports comes from `nexis.evals.metrics`, which reads that file and calls no API,
so correcting a metric never means paying for the same answers again.

The collector runs the review panel alone. Layer 1 never starts, because the
ideas are frozen, and that is what makes the reviewer the only variable under
test.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from pydantic import BaseModel, Field

from nexis.agents.reviewers import ReviewerAgent, create_reviewer
from nexis.config import PipelineConfig
from nexis.evals.dataset import LabelledIdea
from nexis.pricing import PRICE_TABLE_DATE, estimate_cost_usd
from nexis.state import Review, ReviewerRole
from nexis.telemetry import run_context

logger = logging.getLogger(__name__)

# Assumed size of one reviewer call. Only the spend guard reads these. Both come
# from a measured run rather than from counting the prompts, because the output
# figure is about twice the JSON the reviewer returns: a reasoning model bills
# thinking tokens that never reach the answer, and output costs five times input.
# Sizing this from visible text alone put the guard at half the real spend. The
# manifest records the tokens a finished run really used, so the next run can
# correct these without a token count by hand.
ASSUMED_INPUT_TOKENS = 550
ASSUMED_OUTPUT_TOKENS = 900

MANIFEST_NAME = "manifest.json"
REVIEWS_NAME = "reviews.jsonl"


class SpendLimitExceeded(RuntimeError):
    """Raised before the first call when the run projects above the spend limit."""


class ReviewRecord(BaseModel):
    """One reviewer's answer about one idea in one repeat."""

    idea_id: str
    repeat: int
    role: ReviewerRole
    model: str
    prompt_version: str
    # None when the review failed. The metrics drop these instead of reading a
    # substitute value as an opinion the reviewer never gave.
    score: int | None = None
    confidence: float | None = None
    red_flags: list[str] = Field(default_factory=list)
    rationale: str = ""
    failure_reason: str | None = None


class RunManifest(BaseModel):
    """What produced a set of records, written before the first call.

    Writing this first means a run that dies halfway still leaves an analysable
    directory. The measured fields stay None in that case.
    """

    run_id: str
    dataset: str
    ideas: int
    repeats: int
    models: dict[str, str]
    temperatures: dict[str, float | None] = {}
    # Empty when the run predates this field. A manifest that never recorded a
    # temperature cannot report one, so the staleness check skips it.
    price_table_date: str
    started_at: str
    projected_calls: int
    projected_cost_usd: float
    measured_calls: int | None = None
    measured_cost_usd: float | None = None
    # What the run really sent and received. These are what ASSUMED_INPUT_TOKENS
    # and ASSUMED_OUTPUT_TOKENS should be set from. None when the run predates
    # these fields.
    measured_input_tokens: int | None = None
    measured_output_tokens: int | None = None
    wall_seconds: float | None = None
    completed_at: str | None = None


def models_for_roles(
    config: PipelineConfig, override: str | None = None
) -> dict[str, str]:
    """Return the model each reviewer role uses, or `override` for every role."""
    if override:
        return {role.value: override for role in ReviewerRole}
    return {
        role.value: config.model_for(f"reviewer_{role.value}") for role in ReviewerRole
    }


def temperatures_for_roles(config: PipelineConfig) -> dict[str, float | None]:
    """Return the sampling temperature each reviewer role uses."""
    return {
        role.value: config.temperature_for(f"reviewer_{role.value}")
        for role in ReviewerRole
    }


def project_cost(models: dict[str, str], ideas: int, repeats: int) -> tuple[int, float]:
    """Estimate calls and USD before spending anything.

    Raises ValueError when a model has no price. An unpriced model would make the
    spend guard read a real cost as zero, which defeats the guard.
    """
    calls = ideas * len(models) * repeats
    per_repeat_idea = 0.0
    for role, model in models.items():
        cost = estimate_cost_usd(model, ASSUMED_INPUT_TOKENS, ASSUMED_OUTPUT_TOKENS)
        if cost is None:
            raise ValueError(
                f"No price for {model!r} (role {role}). Add it to src/nexis/pricing.py "
                "before running the eval, or the spend guard cannot hold."
            )
        per_repeat_idea += cost
    return calls, round(per_repeat_idea * ideas * repeats, 6)


async def _review_one(
    agent: ReviewerAgent,
    item: LabelledIdea,
    repeat: int,
) -> ReviewRecord:
    """Run one reviewer and turn the answer, or the error, into a record."""
    base = {
        "idea_id": item.idea.id,
        "repeat": repeat,
        "role": agent.role,
        "model": agent.model_name,
        "prompt_version": agent.prompt_version,
    }
    try:
        review: Review = await agent.invoke_review(item.idea)
    except BaseException as exc:
        logger.warning(
            "reviewer %s raised on idea %s: %s", agent.role.value, item.idea.id, exc
        )
        return ReviewRecord(**base, failure_reason=str(exc))

    if review.failure_reason:
        return ReviewRecord(**base, failure_reason=review.failure_reason)

    return ReviewRecord(
        **base,
        score=review.score,
        confidence=review.confidence,
        red_flags=review.red_flags,
        rationale=review.rationale,
    )


async def collect(
    labelled: list[LabelledIdea],
    config: PipelineConfig,
    out_dir: Path | str,
    *,
    repeats: int = 1,
    model_override: str | None = None,
    max_usd: float = 5.0,
    dataset_name: str = "",
    reviewer_factory: Callable[..., ReviewerAgent] = create_reviewer,
) -> RunManifest:
    """Review every idea with the whole panel, `repeats` times, and write the answers.

    Refuses to start when the projected cost is above `max_usd`. Appends each
    record as it arrives, so an interrupted run keeps the answers it paid for.
    """
    if repeats < 1:
        raise ValueError("repeats must be at least 1")

    models = models_for_roles(config, model_override)
    temperatures = temperatures_for_roles(config)
    projected_calls, projected_usd = project_cost(models, len(labelled), repeats)
    if projected_usd > max_usd:
        raise SpendLimitExceeded(
            f"{projected_calls} calls project to {projected_usd:.2f} USD, above the "
            f"{max_usd:.2f} USD limit. Lower --repeats, shrink the dataset, or raise --max-usd."
        )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Appending to a directory that already holds answers would mix two runs
    # under one manifest, and the report would read the blend as one measurement.
    reviews_path = out_dir / REVIEWS_NAME
    if reviews_path.exists() and reviews_path.stat().st_size > 0:
        raise ValueError(
            f"{reviews_path} already holds answers. Collect into a new directory."
        )

    run_id = f"eval-{uuid4().hex[:12]}"

    manifest = RunManifest(
        run_id=run_id,
        dataset=dataset_name,
        ideas=len(labelled),
        repeats=repeats,
        models=models,
        temperatures=temperatures,
        price_table_date=PRICE_TABLE_DATE,
        started_at=datetime.now(timezone.utc).isoformat(),
        projected_calls=projected_calls,
        projected_cost_usd=projected_usd,
    )
    _write_manifest(out_dir, manifest)

    logger.info(
        "collecting %d calls over %d ideas x %d roles x %d repeats, projected %.2f USD",
        projected_calls,
        len(labelled),
        len(models),
        repeats,
        projected_usd,
    )

    written = 0

    with run_context(run_id) as metrics:
        with reviews_path.open("a", encoding="utf-8") as handle:
            for repeat in range(1, repeats + 1):
                for item in labelled:
                    agents = [
                        reviewer_factory(
                            role=role,
                            model_name=models[role.value],
                            temperature=temperatures[role.value],
                            max_retries=config.max_retries,
                            timeout=config.llm_timeout,
                            fallback_model=config.fallback_model,
                        )
                        for role in ReviewerRole
                    ]
                    records = await asyncio.gather(
                        *(_review_one(agent, item, repeat) for agent in agents)
                    )
                    for record in records:
                        handle.write(record.model_dump_json() + "\n")
                        written += 1
                    handle.flush()
                    logger.info(
                        "repeat %d/%d idea %s done (%d/%d records)",
                        repeat,
                        repeats,
                        item.idea.id,
                        written,
                        projected_calls,
                    )

    manifest.measured_calls = metrics.totals.calls
    manifest.measured_cost_usd = round(metrics.totals.cost_usd, 6)
    manifest.measured_input_tokens = metrics.totals.input_tokens
    manifest.measured_output_tokens = metrics.totals.output_tokens
    manifest.wall_seconds = metrics.wall_seconds
    manifest.completed_at = datetime.now(timezone.utc).isoformat()
    _write_manifest(out_dir, manifest)

    return manifest


def _write_manifest(out_dir: Path, manifest: RunManifest) -> None:
    path = Path(out_dir) / MANIFEST_NAME
    path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_manifest(out_dir: Path | str) -> RunManifest:
    path = Path(out_dir) / MANIFEST_NAME
    return RunManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_records(out_dir: Path | str) -> list[ReviewRecord]:
    """Read every collected record. Raises ValueError on a malformed line."""
    path = Path(out_dir) / REVIEWS_NAME
    records: list[ReviewRecord] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(ReviewRecord.model_validate(json.loads(line)))
            except Exception as exc:
                raise ValueError(
                    f"{path}:{number} is not a valid record: {exc}"
                ) from exc
    return records
