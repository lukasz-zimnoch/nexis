"""Nexis — Autonomous multi-agent business idea pipeline."""

from __future__ import annotations

import asyncio

from nexis.config import PipelineConfig
from nexis.state import Report


async def arun_pipeline(config: PipelineConfig) -> list[Report]:
    """Run the Nexis pipeline asynchronously."""
    from langgraph.checkpoint.sqlite import SqliteSaver
    from nexis.graph import build_graph

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
    thread_config = {"configurable": {"thread_id": "nexis-run"}}

    with SqliteSaver.from_conn_string(config.checkpoint_db_path) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        final_state = await graph.ainvoke(initial_state, config=thread_config)

    return final_state.get("final_reports", [])


def run_pipeline(config: PipelineConfig) -> list[Report]:
    """Run the Nexis pipeline synchronously."""
    return asyncio.run(arun_pipeline(config))


__all__ = ["PipelineConfig", "Report", "arun_pipeline", "run_pipeline"]
