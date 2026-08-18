"""Cloud Run Job entry point: reads config from env, runs pipeline, writes to Firestore."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

from nexis.firestore import JobStatus, get_firestore_client, update_job_status
from nexis.metrics import RunMetrics
from nexis.telemetry import run_context

logger = logging.getLogger(__name__)


async def run_job() -> None:
    """Execute the pipeline for a single job and persist results to Firestore."""
    from nexis.config import PipelineConfig
    from nexis.graph import build_graph

    job_id = os.environ["JOB_ID"]

    fs_client = get_firestore_client()

    # Mark as running
    update_job_status(
        fs_client,
        job_id,
        JobStatus.running,
        started_at=datetime.now(timezone.utc),
    )

    # Bound before the run, so the failure path can report what the run spent.
    metrics: RunMetrics | None = None

    try:
        config = PipelineConfig(
            research_prompt=os.environ["RESEARCH_PROMPT"],
            num_ideas=int(os.environ.get("NUM_IDEAS", "8")),
            top_k=int(os.environ.get("TOP_K", "3")),
            score_threshold=float(os.environ.get("SCORE_THRESHOLD", "0.55")),
            output_format=os.environ.get("OUTPUT_FORMAT", "markdown"),
        )

        graph = build_graph()

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
        thread_config = {"configurable": {"thread_id": job_id}}

        with run_context(job_id) as metrics:
            final_state = await graph.ainvoke(initial_state, config=thread_config)
        reports = final_state.get("final_reports", [])

        serialized = [r.model_dump(mode="json") for r in reports]

        update_job_status(
            fs_client,
            job_id,
            JobStatus.completed,
            completed_at=datetime.now(timezone.utc),
            result=serialized,
            metrics=metrics.model_dump(mode="json"),
        )
        logger.info(
            "job %s completed with %d reports, %d LLM calls, %.4f USD",
            job_id,
            len(reports),
            metrics.totals.calls,
            metrics.totals.cost_usd,
        )

    except Exception as exc:
        logger.exception("job %s failed: %s", job_id, exc)
        update_job_status(
            fs_client,
            job_id,
            JobStatus.failed,
            completed_at=datetime.now(timezone.utc),
            error=str(exc),
            metrics=metrics.model_dump(mode="json") if metrics is not None else None,
        )
        sys.exit(1)


def main() -> None:
    asyncio.run(run_job())


if __name__ == "__main__":
    main()
