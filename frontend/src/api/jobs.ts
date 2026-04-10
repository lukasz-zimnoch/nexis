import { apiFetch } from "./client";

export type JobStatus = "pending" | "running" | "completed" | "failed";

export interface JobConfig {
  research_prompt: string;
  num_ideas: number;
  top_k: number;
  score_threshold: number;
  output_format: string;
}

export interface JobResultItem {
  // Each entry corresponds to a serialized Report. Free-form to remain
  // compatible with backend changes; the markdown body is the field of
  // interest for rendering.
  [key: string]: unknown;
  markdown?: string;
  title?: string;
}

export interface JobRecord {
  id: string;
  user_id: string;
  status: JobStatus;
  config: JobConfig;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  result: JobResultItem[] | null;
}

export function listJobs(): Promise<JobRecord[]> {
  return apiFetch<JobRecord[]>("/api/jobs");
}

export function getJob(jobId: string): Promise<JobRecord> {
  return apiFetch<JobRecord>(`/api/jobs/${encodeURIComponent(jobId)}`);
}

export function createJob(config: JobConfig): Promise<JobRecord> {
  return apiFetch<JobRecord>("/api/jobs", {
    method: "POST",
    body: JSON.stringify(config),
  });
}
