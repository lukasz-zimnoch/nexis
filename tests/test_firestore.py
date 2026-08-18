"""Tests for Firestore client and job state models."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from nexis.metrics import RunMetrics
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
from nexis.state import OutputFormat, Report


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
        "result": [
            {
                "title": "Report 1",
                "generated_at": "2026-04-01T13:00:00+00:00",
                "ideas_evaluated": 8,
                "ideas_selected": 3,
                "content": "# Report content",
                "format": "markdown",
            }
        ],
    }
    job = _deserialize_job(data)
    assert job.status == JobStatus.completed
    assert job.result is not None
    assert len(job.result) == 1
    assert job.result[0] == Report(
        title="Report 1",
        generated_at=datetime(2026, 4, 1, 13, 0, 0, tzinfo=timezone.utc),
        ideas_evaluated=8,
        ideas_selected=3,
        content="# Report content",
        format=OutputFormat.markdown,
    )


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


# ---------------------------------------------------------------------------
# Run metrics
# ---------------------------------------------------------------------------


def test_job_metrics_default_to_none(sample_job: JobRecord):
    assert sample_job.metrics is None


def test_metrics_survive_a_round_trip(sample_job: JobRecord):
    metrics = RunMetrics(run_id="job-001", wall_seconds=42.5)
    metrics.record_call(
        agent="ResearchAgent",
        layer="research",
        model="anthropic/claude-opus-5",
        input_tokens=1_000,
        output_tokens=200,
        seconds=1.5,
        cost_usd=0.01,
        prompt_version="abc123abc123",
    )
    job = sample_job.model_copy(update={"metrics": metrics})

    restored = _deserialize_job(_serialize_job(job))
    assert restored.metrics == metrics


def test_deserialize_accepts_a_record_without_metrics(sample_job: JobRecord):
    """A job written before the metrics field existed must still read back."""
    data = _serialize_job(sample_job)
    del data["metrics"]
    assert _deserialize_job(data).metrics is None


def test_update_job_status_writes_metrics(mock_client: MagicMock):
    metrics = RunMetrics(run_id="job-001", wall_seconds=42.5)
    update_job_status(
        mock_client,
        "job-001",
        JobStatus.completed,
        metrics=metrics.model_dump(mode="json"),
    )
    updates = mock_client.collection().document().update.call_args[0][0]
    assert updates["metrics"]["run_id"] == "job-001"
    assert updates["metrics"]["wall_seconds"] == 42.5
