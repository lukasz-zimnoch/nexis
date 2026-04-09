"""Firestore client and job state models for Nexis."""

from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Enums and models
# ---------------------------------------------------------------------------


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class JobConfig(BaseModel):
    research_prompt: str
    num_ideas: int = 8
    top_k: int = 3
    score_threshold: float = 0.55
    output_format: str = "markdown"


class JobRecord(BaseModel):
    id: str
    user_id: str
    status: JobStatus
    config: JobConfig
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    result: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Firestore client
# ---------------------------------------------------------------------------

_JOBS_COLLECTION = "jobs"
_firestore_client = None


def get_firestore_client():
    """Return a shared Firestore client (created once, reused across calls)."""
    global _firestore_client
    if _firestore_client is None:
        from google.cloud import firestore  # type: ignore[import-untyped]

        project_id = os.environ.get("GCP_PROJECT_ID")
        _firestore_client = firestore.Client(project=project_id)
    return _firestore_client


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def create_job(client, job: JobRecord) -> None:
    """Write a new job document to Firestore."""
    doc = client.collection(_JOBS_COLLECTION).document(job.id)
    doc.set(_serialize_job(job))


def get_job(client, job_id: str) -> JobRecord | None:
    """Read a single job document. Returns None if not found."""
    doc = client.collection(_JOBS_COLLECTION).document(job_id).get()
    if not doc.exists:
        return None
    return _deserialize_job(doc.to_dict())


def list_jobs(client, user_id: str, limit: int = 20) -> list[JobRecord]:
    """List jobs for a user, ordered by created_at descending."""
    query = (
        client.collection(_JOBS_COLLECTION)
        .where("user_id", "==", user_id)
        .order_by("created_at", direction="DESCENDING")
        .limit(limit)
    )
    return [_deserialize_job(doc.to_dict()) for doc in query.stream()]


def update_job_status(
    client,
    job_id: str,
    status: JobStatus,
    *,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    error: str | None = None,
    result: list[dict[str, Any]] | None = None,
) -> None:
    """Partially update a job document (status + optional timestamp/result fields)."""
    updates: dict[str, Any] = {"status": status.value}
    if started_at is not None:
        updates["started_at"] = started_at
    if completed_at is not None:
        updates["completed_at"] = completed_at
    if error is not None:
        updates["error"] = error
    if result is not None:
        updates["result"] = result
    client.collection(_JOBS_COLLECTION).document(job_id).update(updates)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_job(job: JobRecord) -> dict[str, Any]:
    data = job.model_dump()
    data["status"] = job.status.value
    return data


def _deserialize_job(data: dict[str, Any]) -> JobRecord:
    # Firestore may return DatetimeWithNanoseconds — normalise to datetime
    for field in ("created_at", "started_at", "completed_at"):
        val = data.get(field)
        if val is not None and not isinstance(val, datetime):
            data[field] = datetime.fromisoformat(str(val))
    data["status"] = JobStatus(data["status"])
    data["config"] = JobConfig(**data["config"])
    return JobRecord(**data)
