import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getJob, isActiveStatus, type JobRecord } from "../api/jobs";
import StatusBadge from "../components/StatusBadge";
import MetricsPanel from "../components/MetricsPanel";
import ReportView from "../components/ReportView";
import { jsonEqual } from "../lib/equal";
import { formatDate } from "../lib/format";
import { usePoll } from "../lib/usePoll";

const POLL_INTERVAL_MS = 5_000;

export default function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [job, setJob] = useState<JobRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!jobId) return;
    try {
      const data = await getJob(jobId);
      setJob((prev) => (jsonEqual(prev, data) ? prev : data));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load job");
    }
  }, [jobId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  usePoll(job !== null && isActiveStatus(job.status), refresh, POLL_INTERVAL_MS);

  return (
    <div>
      <p>
        <Link to="/">← Back to jobs</Link>
      </p>

      {error ? <div className="error">{error}</div> : null}

      {job === null ? (
        <p className="muted">Loading job…</p>
      ) : (
        <>
          <div className="row">
            <h1 style={{ margin: 0 }}>Job {job.id.slice(0, 8)}</h1>
            <div className="spacer" />
            <StatusBadge status={job.status} />
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>Configuration</h3>
            <div className="muted">
              Prompt: <span style={{ color: "#1a1a1a" }}>{job.config.research_prompt}</span>
            </div>
            <div className="muted">
              Ideas: {job.config.num_ideas} · Top K: {job.config.top_k} · Threshold:{" "}
              {job.config.score_threshold} · Format: {job.config.output_format}
            </div>
            <div className="muted" style={{ marginTop: "0.5rem" }}>
              Created {formatDate(job.created_at)} · Started {formatDate(job.started_at)} ·
              Completed {formatDate(job.completed_at)}
            </div>
          </div>

          {job.error ? (
            <div className="error">
              <strong>Error:</strong> {job.error}
            </div>
          ) : null}

          {job.metrics ? <MetricsPanel metrics={job.metrics} /> : null}

          {job.status === "completed" ? (
            <>
              <h2>Reports</h2>
              <ReportView result={job.result} />
            </>
          ) : null}
        </>
      )}
    </div>
  );
}
