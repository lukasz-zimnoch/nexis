"""Tests for the Cloud Run Job trigger module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nexis.firestore import JobConfig
from nexis.job_trigger import trigger_job_execution


@pytest.fixture(autouse=True)
def gcp_env(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("GCP_REGION", "us-central1")
    monkeypatch.setenv("CLOUD_RUN_JOB_NAME", "nexis-job")


def test_trigger_calls_run_job_with_correct_path():
    config = JobConfig(
        research_prompt="Find AI ideas",
        num_ideas=5,
        top_k=2,
        score_threshold=0.6,
        output_format="json",
    )

    with patch("nexis.job_trigger.run_v2") as mock_run_v2:
        mock_client = MagicMock()
        mock_run_v2.JobsClient.return_value = mock_client

        trigger_job_execution("job-001", config)

        mock_client.run_job.assert_called_once()
        # Check the name passed to RunJobRequest constructor
        _, kwargs = mock_run_v2.RunJobRequest.call_args
        assert (
            kwargs["name"]
            == "projects/test-project/locations/us-central1/jobs/nexis-job"
        )


def test_trigger_passes_env_overrides():
    config = JobConfig(
        research_prompt="Find AI ideas",
        num_ideas=5,
        top_k=2,
        score_threshold=0.6,
        output_format="json",
    )

    with patch("nexis.job_trigger.run_v2") as mock_run_v2:
        mock_client = MagicMock()
        mock_run_v2.JobsClient.return_value = mock_client

        # Capture the EnvVar constructor calls
        env_var_calls = []

        def capture_env_var(**kwargs):
            env_var_calls.append(kwargs)
            return MagicMock()

        mock_run_v2.EnvVar.side_effect = capture_env_var

        trigger_job_execution("job-abc", config)

        names = [c["name"] for c in env_var_calls]
        assert "JOB_ID" in names
        assert "RESEARCH_PROMPT" in names
        assert "NUM_IDEAS" in names
        assert "TOP_K" in names
        assert "SCORE_THRESHOLD" in names
        assert "OUTPUT_FORMAT" in names

        # Verify specific values
        by_name = {c["name"]: c["value"] for c in env_var_calls}
        assert by_name["JOB_ID"] == "job-abc"
        assert by_name["RESEARCH_PROMPT"] == "Find AI ideas"
        assert by_name["NUM_IDEAS"] == "5"
        assert by_name["TOP_K"] == "2"
        assert by_name["SCORE_THRESHOLD"] == "0.6"
        assert by_name["OUTPUT_FORMAT"] == "json"
