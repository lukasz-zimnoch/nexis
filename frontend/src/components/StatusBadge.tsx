import type { JobStatus } from "../api/jobs";

interface StatusBadgeProps {
  status: JobStatus;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  return <span className={`badge badge-${status}`}>{status}</span>;
}
