"""Tests for the Cloud Run Job runner."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexis.firestore import JobStatus


@pytest.fixture(autouse=True)
def job_env(monkeypatch):
    monkeypatch.setenv("JOB_ID", "job-test-001")
    monkeypatch.setenv("RESEARCH_PROMPT", "Find SaaS ideas")
    monkeypatch.setenv("NUM_IDEAS", "4")
    monkeypatch.setenv("TOP_K", "2")
    monkeypatch.setenv("SCORE_THRESHOLD", "0.55")
    monkeypatch.setenv("OUTPUT_FORMAT", "markdown")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")


async def test_run_job_happy_path():
    from nexis.state import OutputFormat, Report

    mock_report = Report(
        title="Test Report",
        generated_at=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
        ideas_evaluated=4,
        ideas_selected=2,
        content="# Report",
        format=OutputFormat.markdown,
    )
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {"final_reports": [mock_report]}

    mock_fs = MagicMock()

    with (
        patch("nexis.job_runner.get_firestore_client", return_value=mock_fs),
        patch("nexis.job_runner.update_job_status") as mock_update,
        patch("nexis.graph.build_graph", return_value=mock_graph),
    ):
        from nexis.job_runner import run_job

        await run_job()

    statuses = [call.args[2] for call in mock_update.call_args_list]
    assert JobStatus.running in statuses
    assert JobStatus.completed in statuses

    completed_call = next(
        c for c in mock_update.call_args_list if c.args[2] == JobStatus.completed
    )
    assert completed_call.kwargs.get("result") is not None

    metrics = completed_call.kwargs.get("metrics")
    assert metrics is not None
    assert metrics["run_id"] == "job-test-001"
    assert metrics["wall_seconds"] > 0


async def test_run_job_failure_sets_failed_status():
    mock_graph = AsyncMock()
    mock_graph.ainvoke.side_effect = RuntimeError("pipeline exploded")

    mock_fs = MagicMock()

    with (
        patch("nexis.job_runner.get_firestore_client", return_value=mock_fs),
        patch("nexis.job_runner.update_job_status") as mock_update,
        patch("nexis.graph.build_graph", return_value=mock_graph),
        pytest.raises(SystemExit),
    ):
        from nexis.job_runner import run_job

        await run_job()

    statuses = [call.args[2] for call in mock_update.call_args_list]
    assert JobStatus.running in statuses
    assert JobStatus.failed in statuses

    failed_call = next(
        c for c in mock_update.call_args_list if c.args[2] == JobStatus.failed
    )
    assert "pipeline exploded" in failed_call.kwargs.get("error", "")

    # A run that broke halfway still spent money, so it reports what it spent.
    metrics = failed_call.kwargs.get("metrics")
    assert metrics is not None
    assert metrics["run_id"] == "job-test-001"
