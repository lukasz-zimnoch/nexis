"""Nexis HTTP server (Cloud Run) and LangGraph dev entrypoint."""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI
from pydantic import BaseModel

from nexis.config import PipelineConfig
from nexis.graph import build_graph
from nexis.state import Report

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LangGraph Platform / `langgraph dev` entrypoint
# ---------------------------------------------------------------------------

graph = build_graph(checkpointer=None)

# ---------------------------------------------------------------------------
# FastAPI app for Cloud Run
# ---------------------------------------------------------------------------

app = FastAPI(title="Nexis Pipeline")


class RunRequest(BaseModel):
    research_prompt: str
    num_ideas: int = 8
    top_k: int = 3
    score_threshold: float = 0.55
    output_format: str = "markdown"


class RunResponse(BaseModel):
    reports: list[Report]


@app.post("/run", response_model=RunResponse)
async def run(request: RunRequest) -> RunResponse:
    """Run the full Nexis pipeline and return generated reports."""
    config = PipelineConfig(
        research_prompt=request.research_prompt,
        num_ideas=request.num_ideas,
        top_k=request.top_k,
        score_threshold=request.score_threshold,
        output_format=request.output_format,
    )

    pipeline = build_graph()  # defaults to MemorySaver

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
    thread_config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    final_state = await pipeline.ainvoke(initial_state, config=thread_config)
    reports = final_state.get("final_reports", [])

    return RunResponse(reports=reports)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
