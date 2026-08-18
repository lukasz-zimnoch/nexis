"""Nexis — Autonomous multi-agent business idea pipeline."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from nexis.config import PipelineConfig
from nexis.state import Report


async def arun_pipeline(
    config: PipelineConfig, *, run_id: str | None = None
) -> list[Report]:
    """Run the Nexis pipeline asynchronously.

    `run_id` labels every telemetry event of this run and names its checkpoint
    thread. A random id stands in when the caller has none.
    """
    from nexis.graph import build_graph
    from nexis.telemetry import run_context

    run_id = run_id or uuid4().hex

    initial_state = {
        "config": config,
        "research_prompt": config.research_prompt,
        "iteration": 0,
        "ideas": [],
        "reviews": [],
        "scores": {},
        "top_ideas": [],
        "mvp_plans": {},
        "gtm_plans": {},
        "business_plans": {},
        "rebuttals": {},
        "final_reports": [],
    }
    thread_config = {"configurable": {"thread_id": run_id}}

    graph = build_graph()
    with run_context(run_id):
        final_state = await graph.ainvoke(initial_state, config=thread_config)

    return final_state.get("final_reports", [])


def run_pipeline(config: PipelineConfig, *, run_id: str | None = None) -> list[Report]:
    """Run the Nexis pipeline synchronously."""
    return asyncio.run(arun_pipeline(config, run_id=run_id))


__all__ = ["PipelineConfig", "Report", "arun_pipeline", "run_pipeline"]
