"""Cloud Run Job trigger for async pipeline execution."""

from __future__ import annotations

import os

from google.cloud import run_v2  # type: ignore[import-untyped]

from nexis.firestore import JobConfig

_jobs_client: run_v2.JobsClient | None = None


def _get_jobs_client() -> run_v2.JobsClient:
    global _jobs_client
    if _jobs_client is None:
        _jobs_client = run_v2.JobsClient()
    return _jobs_client


def trigger_job_execution(job_id: str, config: JobConfig) -> None:
    """Trigger a Cloud Run Job execution with config passed as env var overrides."""
    project_id = os.environ["GCP_PROJECT_ID"]
    region = os.environ["GCP_REGION"]
    job_name = os.environ["CLOUD_RUN_JOB_NAME"]

    client = _get_jobs_client()
    job_path = f"projects/{project_id}/locations/{region}/jobs/{job_name}"

    overrides = run_v2.RunJobRequest.Overrides(
        container_overrides=[
            run_v2.RunJobRequest.Overrides.ContainerOverride(
                env=[
                    run_v2.EnvVar(name="JOB_ID", value=job_id),
                    run_v2.EnvVar(name="RESEARCH_PROMPT", value=config.research_prompt),
                    run_v2.EnvVar(name="NUM_IDEAS", value=str(config.num_ideas)),
                    run_v2.EnvVar(name="TOP_K", value=str(config.top_k)),
                    run_v2.EnvVar(
                        name="SCORE_THRESHOLD", value=str(config.score_threshold)
                    ),
                    run_v2.EnvVar(name="OUTPUT_FORMAT", value=config.output_format),
                ]
            )
        ]
    )

    request = run_v2.RunJobRequest(name=job_path, overrides=overrides)
    client.run_job(request=request)
