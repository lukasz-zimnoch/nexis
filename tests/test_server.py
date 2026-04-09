"""Tests for the Nexis FastAPI server."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from nexis.auth import CurrentUser, get_current_user
from nexis.firestore import JobConfig, JobRecord, JobStatus
from nexis.server import app

# ---------------------------------------------------------------------------
# Override auth dependency for all tests
# ---------------------------------------------------------------------------

FAKE_USER = CurrentUser(uid="user-test-001", email="test@example.com")


def override_auth():
    return FAKE_USER


app.dependency_overrides[get_current_user] = override_auth

client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_job_record() -> JobRecord:
    return JobRecord(
        id="job-001",
        user_id="user-test-001",
        status=JobStatus.pending,
        config=JobConfig(
            research_prompt="Find AI ideas",
            num_ideas=4,
            top_k=2,
            score_threshold=0.55,
            output_format="markdown",
        ),
        created_at=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /api/jobs
# ---------------------------------------------------------------------------


def test_create_job_returns_201(sample_job_record: JobRecord):
    with (
        patch("nexis.server.get_firestore_client"),
        patch("nexis.server.create_job") as mock_create,
        patch("nexis.server.trigger_job_execution") as mock_trigger,
    ):
        resp = client.post(
            "/api/jobs",
            json={
                "research_prompt": "Find AI ideas",
                "num_ideas": 4,
                "top_k": 2,
                "score_threshold": 0.55,
                "output_format": "markdown",
            },
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["user_id"] == "user-test-001"
    assert data["status"] == "pending"
    assert data["config"]["research_prompt"] == "Find AI ideas"
    mock_create.assert_called_once()
    mock_trigger.assert_called_once()


def test_create_job_returns_503_when_trigger_fails():
    with (
        patch("nexis.server.get_firestore_client"),
        patch("nexis.server.create_job"),
        patch("nexis.server.update_job_status") as mock_update_status,
        patch(
            "nexis.server.trigger_job_execution",
            side_effect=RuntimeError("quota exceeded"),
        ),
    ):
        resp = client.post("/api/jobs", json={"research_prompt": "Test prompt"})

    assert resp.status_code == 503
    mock_update_status.assert_called_once()
    _, kwargs = mock_update_status.call_args
    assert kwargs.get("error") is not None


def test_create_job_triggers_with_job_id(sample_job_record: JobRecord):
    with (
        patch("nexis.server.get_firestore_client"),
        patch("nexis.server.create_job"),
        patch("nexis.server.trigger_job_execution") as mock_trigger,
    ):
        resp = client.post(
            "/api/jobs",
            json={"research_prompt": "Test prompt"},
        )

    assert resp.status_code == 201
    job_id = resp.json()["id"]
    triggered_id = mock_trigger.call_args[0][0]
    assert triggered_id == job_id


# ---------------------------------------------------------------------------
# GET /api/jobs
# ---------------------------------------------------------------------------


def test_list_jobs_returns_user_jobs(sample_job_record: JobRecord):
    with (
        patch("nexis.server.get_firestore_client"),
        patch("nexis.server.list_jobs", return_value=[sample_job_record]),
    ):
        resp = client.get("/api/jobs")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "job-001"


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}
# ---------------------------------------------------------------------------


def test_get_job_returns_job(sample_job_record: JobRecord):
    with (
        patch("nexis.server.get_firestore_client"),
        patch("nexis.server.get_job", return_value=sample_job_record),
    ):
        resp = client.get("/api/jobs/job-001")

    assert resp.status_code == 200
    assert resp.json()["id"] == "job-001"


def test_get_job_returns_404_when_missing():
    with (
        patch("nexis.server.get_firestore_client"),
        patch("nexis.server.get_job", return_value=None),
    ):
        resp = client.get("/api/jobs/nonexistent")

    assert resp.status_code == 404


def test_get_job_returns_403_for_wrong_user(sample_job_record: JobRecord):
    other_user_job = sample_job_record.model_copy(update={"user_id": "other-user-999"})
    with (
        patch("nexis.server.get_firestore_client"),
        patch("nexis.server.get_job", return_value=other_user_job),
    ):
        resp = client.get("/api/jobs/job-001")

    assert resp.status_code == 403
