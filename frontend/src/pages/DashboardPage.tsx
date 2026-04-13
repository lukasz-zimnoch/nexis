import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createJob,
  isActiveStatus,
  listJobs,
  type JobConfig,
  type JobRecord,
} from "../api/jobs";
import JobCard from "../components/JobCard";
import JobForm from "../components/JobForm";
import { jsonEqual } from "../lib/equal";
import { usePoll } from "../lib/usePoll";

const POLL_INTERVAL_MS = 10_000;

export default function DashboardPage() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState<JobRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await listJobs();
      setJobs((prev) => (jsonEqual(prev, data) ? prev : data));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load jobs");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const hasActive = jobs?.some((j) => isActiveStatus(j.status)) ?? false;
  usePoll(hasActive, refresh, POLL_INTERVAL_MS);

  async function handleCreate(config: JobConfig) {
    setSubmitting(true);
    setError(null);
    try {
      const job = await createJob(config);
      setShowForm(false);
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create job");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <div className="row" style={{ marginBottom: "1rem" }}>
        <h1 style={{ margin: 0 }}>Jobs</h1>
        <div className="spacer" />
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => setShowForm((s) => !s)}
        >
          {showForm ? "Cancel" : "New job"}
        </button>
      </div>

      {showForm ? (
        <JobForm onSubmit={handleCreate} submitting={submitting} />
      ) : null}

      {error ? <div className="error">{error}</div> : null}

      {jobs === null ? (
        <p className="muted">Loading jobs…</p>
      ) : jobs.length === 0 ? (
        <p className="muted">No jobs yet. Click "New job" to get started.</p>
      ) : (
        jobs.map((job) => <JobCard key={job.id} job={job} />)
      )}
    </div>
  );
}
