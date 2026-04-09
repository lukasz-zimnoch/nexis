"""Tests for Firestore client and job state models."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from nexis.firestore import (
    JobConfig,
    JobRecord,
    JobStatus,
    _serialize_job,
    _deserialize_job,
    create_job,
    get_job,
    list_jobs,
    update_job_status,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_config() -> JobConfig:
    return JobConfig(
        research_prompt="Find SaaS ideas",
        num_ideas=4,
        top_k=2,
        score_threshold=0.6,
        output_format="markdown",
    )


@pytest.fixture
def sample_job(sample_config: JobConfig) -> JobRecord:
    return JobRecord(
        id="job-001",
        user_id="user-abc",
        status=JobStatus.pending,
        config=sample_config,
        created_at=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# Model serialisation
# ---------------------------------------------------------------------------


def test_serialize_job_status_is_string(sample_job: JobRecord):
    data = _serialize_job(sample_job)
    assert data["status"] == "pending"


def test_serialize_job_config_is_dict(sample_job: JobRecord):
    data = _serialize_job(sample_job)
    assert isinstance(data["config"], dict)
    assert data["config"]["research_prompt"] == "Find SaaS ideas"


def test_deserialize_round_trip(sample_job: JobRecord):
    data = _serialize_job(sample_job)
    restored = _deserialize_job(data)
    assert restored.id == sample_job.id
    assert restored.status == JobStatus.pending
    assert restored.config.research_prompt == "Find SaaS ideas"


def test_deserialize_with_completed_fields():
    now = datetime(2026, 4, 1, 13, 0, 0, tzinfo=timezone.utc)
    data = {
        "id": "job-002",
        "user_id": "user-xyz",
        "status": "completed",
        "config": {
            "research_prompt": "test",
            "num_ideas": 8,
            "top_k": 3,
            "score_threshold": 0.55,
            "output_format": "json",
        },
        "created_at": now,
        "started_at": now,
        "completed_at": now,
        "error": None,
        "result": [{"title": "Report 1"}],
    }
    job = _deserialize_job(data)
    assert job.status == JobStatus.completed
    assert job.result == [{"title": "Report 1"}]


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def test_create_job_calls_set(mock_client: MagicMock, sample_job: JobRecord):
    create_job(mock_client, sample_job)
    mock_client.collection.assert_called_once_with("jobs")
    mock_client.collection().document.assert_called_once_with("job-001")
    mock_client.collection().document().set.assert_called_once()


def test_get_job_returns_record(mock_client: MagicMock, sample_job: JobRecord):
    doc_mock = MagicMock()
    doc_mock.exists = True
    doc_mock.to_dict.return_value = _serialize_job(sample_job)
    mock_client.collection().document().get.return_value = doc_mock

    result = get_job(mock_client, "job-001")
    assert result is not None
    assert result.id == "job-001"


def test_get_job_returns_none_when_missing(mock_client: MagicMock):
    doc_mock = MagicMock()
    doc_mock.exists = False
    mock_client.collection().document().get.return_value = doc_mock

    result = get_job(mock_client, "nonexistent")
    assert result is None


def test_list_jobs_queries_by_user(mock_client: MagicMock, sample_job: JobRecord):
    doc_mock = MagicMock()
    doc_mock.to_dict.return_value = _serialize_job(sample_job)
    mock_client.collection().where().order_by().limit().stream.return_value = [doc_mock]

    results = list_jobs(mock_client, "user-abc")
    assert len(results) == 1
    assert results[0].user_id == "user-abc"


def test_update_job_status_calls_update(mock_client: MagicMock):
    now = datetime(2026, 4, 1, 13, 0, 0, tzinfo=timezone.utc)
    update_job_status(mock_client, "job-001", JobStatus.running, started_at=now)
    mock_client.collection().document().update.assert_called_once_with(
        {"status": "running", "started_at": now}
    )
