"""Nexis HTTP server (Cloud Run) and LangGraph dev entrypoint."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from nexis.auth import CurrentUser, get_current_user
from nexis.firestore import (
    JobConfig,
    JobRecord,
    JobStatus,
    create_job,
    get_firestore_client,
    get_job,
    list_jobs,
    update_job_status,
)
from nexis.graph import build_graph
from nexis.job_trigger import trigger_job_execution
from nexis.state import Report  # noqa: F401 — kept for `langgraph dev` graph export

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LangGraph Platform / `langgraph dev` entrypoint
# ---------------------------------------------------------------------------

graph = build_graph(checkpointer=None)

# ---------------------------------------------------------------------------
# FastAPI app for Cloud Run
# ---------------------------------------------------------------------------

app = FastAPI(title="Nexis AI")

# SPA static file directory (populated by Docker multi-stage build)
STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

JOB_START_FAILED_MESSAGE = "Failed to start job execution"


# ---------------------------------------------------------------------------
# Health endpoint (no auth)
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Firebase Web SDK config (no auth — values are public by design)
# ---------------------------------------------------------------------------


@app.get("/config.json")
async def firebase_web_config() -> dict[str, str]:
    """Runtime Firebase Web SDK config consumed by the SPA at bootstrap.

    The three fields identify the Firebase project to the browser client;
    actual auth is enforced by the backend ID-token check.
    """
    api_key = os.environ.get("FIREBASE_API_KEY")
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not api_key or not project_id:
        raise HTTPException(status_code=500, detail="Firebase config unavailable")
    auth_domain = (
        os.environ.get("FIREBASE_AUTH_DOMAIN") or f"{project_id}.firebaseapp.com"
    )
    return {
        "apiKey": api_key,
        "authDomain": auth_domain,
        "projectId": project_id,
    }


# ---------------------------------------------------------------------------
# Job API endpoints (all require auth)
# ---------------------------------------------------------------------------


@app.post("/api/jobs", status_code=201, response_model=JobRecord)
async def create_job_endpoint(
    body: JobConfig,
    user: CurrentUser = Depends(get_current_user),
) -> JobRecord:
    """Create a new pipeline job and trigger a Cloud Run Job execution."""
    job_id = str(uuid.uuid4())
    job = JobRecord(
        id=job_id,
        user_id=user.uid,
        status=JobStatus.pending,
        config=body,
        created_at=datetime.now(timezone.utc),
    )

    fs_client = get_firestore_client()
    create_job(fs_client, job)

    try:
        await asyncio.to_thread(trigger_job_execution, job_id, body)
    except Exception:
        # The client reads JobRecord.error, and the exception text can carry
        # project IDs, resource names or quota detail. Keep it in the log.
        logger.exception("Failed to trigger Cloud Run Job for %s", job_id)
        update_job_status(
            fs_client, job_id, JobStatus.failed, error=JOB_START_FAILED_MESSAGE
        )
        raise HTTPException(status_code=503, detail=JOB_START_FAILED_MESSAGE)

    return job


@app.get("/api/jobs", response_model=list[JobRecord])
async def list_jobs_endpoint(
    user: CurrentUser = Depends(get_current_user),
) -> list[JobRecord]:
    """List all jobs for the authenticated user."""
    fs_client = get_firestore_client()
    return list_jobs(fs_client, user.uid)


@app.get("/api/jobs/{job_id}", response_model=JobRecord)
async def get_job_endpoint(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> JobRecord:
    """Get a single job by ID."""
    fs_client = get_firestore_client()
    job = get_job(fs_client, job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_id != user.uid:
        raise HTTPException(status_code=403, detail="Forbidden")

    return job


# ---------------------------------------------------------------------------
# SPA serving (registered LAST so API routes take priority)
# ---------------------------------------------------------------------------


def register_spa_routes(app: FastAPI, static_dir: Path) -> None:
    """Serve the built SPA from `static_dir`, which must exist.

    A source checkout has no `frontend/dist`; only the Docker build creates it.
    """
    app.mount(
        "/assets",
        StaticFiles(directory=str(static_dir / "assets")),
        name="assets",
    )
    root = static_dir.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        # Starlette passes `full_path` already URL-decoded, so an encoded
        # "../" arrives here as a real parent-directory step. Resolve the path
        # and refuse anything that lands outside the SPA directory.
        candidate = (root / full_path).resolve()
        if not candidate.is_relative_to(root):
            raise HTTPException(status_code=404)
        # Serve an existing file directly (e.g. favicon.ico, robots.txt);
        # fall back to index.html for all other paths so client-side routing works.
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(root / "index.html"))


if STATIC_DIR.is_dir():
    register_spa_routes(app, STATIC_DIR)
