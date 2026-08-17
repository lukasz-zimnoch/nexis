"""Tests for the Nexis FastAPI server."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexis.auth import CurrentUser, get_current_user
from nexis.firestore import JobConfig, JobRecord, JobStatus
from nexis.server import app, register_spa_routes

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
# GET /config.json
# ---------------------------------------------------------------------------


def test_config_json_composes_from_env(monkeypatch):
    monkeypatch.setenv("FIREBASE_API_KEY", "web-api-key")
    monkeypatch.setenv("GCP_PROJECT_ID", "nexis-ai")
    monkeypatch.delenv("FIREBASE_AUTH_DOMAIN", raising=False)

    resp = client.get("/config.json")

    assert resp.status_code == 200
    assert resp.json() == {
        "apiKey": "web-api-key",
        "authDomain": "nexis-ai.firebaseapp.com",
        "projectId": "nexis-ai",
    }


def test_config_json_respects_auth_domain_override(monkeypatch):
    monkeypatch.setenv("FIREBASE_API_KEY", "web-api-key")
    monkeypatch.setenv("GCP_PROJECT_ID", "nexis-ai")
    monkeypatch.setenv("FIREBASE_AUTH_DOMAIN", "auth.example.com")

    resp = client.get("/config.json")

    assert resp.status_code == 200
    assert resp.json()["authDomain"] == "auth.example.com"


def test_config_json_returns_500_when_missing(monkeypatch):
    monkeypatch.delenv("FIREBASE_API_KEY", raising=False)
    monkeypatch.setenv("GCP_PROJECT_ID", "nexis-ai")

    resp = client.get("/config.json")

    assert resp.status_code == 500


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


# ---------------------------------------------------------------------------
# SPA serving
# ---------------------------------------------------------------------------

SECRET_TEXT = "server-side secret"


@pytest.fixture
def spa_client(tmp_path: Path) -> TestClient:
    """Client for an app serving a throwaway SPA directory.

    The real STATIC_DIR only exists after the frontend build, so the routes are
    registered here against a directory the test controls.
    """
    static_dir = tmp_path / "dist"
    (static_dir / "assets").mkdir(parents=True)
    (static_dir / "index.html").write_text("<!doctype html><title>Nexis</title>")
    (static_dir / "robots.txt").write_text("User-agent: *")
    (tmp_path / "secret.txt").write_text(SECRET_TEXT)

    spa_app = FastAPI()
    register_spa_routes(spa_app, static_dir)
    return TestClient(spa_app, raise_server_exceptions=False)


def test_spa_fallback_serves_index_for_client_route(spa_client: TestClient):
    resp = spa_client.get("/jobs/job-001")

    assert resp.status_code == 200
    assert "<title>Nexis</title>" in resp.text


def test_spa_fallback_serves_existing_file(spa_client: TestClient):
    resp = spa_client.get("/robots.txt")

    assert resp.status_code == 200
    assert resp.text == "User-agent: *"


def test_spa_fallback_rejects_api_paths(spa_client: TestClient):
    resp = spa_client.get("/api/unknown")

    assert resp.status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/%2e%2e%2fsecret.txt",
        "/%2e%2e%2f%2e%2e%2fsecret.txt",
        "/assets/%2e%2e%2f%2e%2e%2fsecret.txt",
    ],
)
def test_spa_fallback_rejects_encoded_traversal(spa_client: TestClient, path: str):
    resp = spa_client.get(path)

    assert resp.status_code == 404
    assert SECRET_TEXT not in resp.text
