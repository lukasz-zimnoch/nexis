import { Link } from "react-router-dom";
import type { JobRecord } from "../api/jobs";
import { formatDate } from "../lib/format";
import StatusBadge from "./StatusBadge";

interface JobCardProps {
  job: JobRecord;
}

export default function JobCard({ job }: JobCardProps) {
  return (
    <Link to={`/jobs/${job.id}`} className="card" style={{ display: "block" }}>
      <div className="row">
        <strong>{job.config.research_prompt.slice(0, 80) || "(no prompt)"}</strong>
        <div className="spacer" />
        <StatusBadge status={job.status} />
      </div>
      <div className="muted" style={{ marginTop: "0.25rem" }}>
        Created {formatDate(job.created_at)} · {job.config.num_ideas} ideas ·
        top {job.config.top_k}
      </div>
    </Link>
  );
}
