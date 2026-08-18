import { apiFetch } from "./client";

export type JobStatus = "pending" | "running" | "completed" | "failed";

export type OutputFormat = "markdown" | "json";

export interface JobConfig {
  research_prompt: string;
  num_ideas: number;
  top_k: number;
  score_threshold: number;
  output_format: OutputFormat;
}

// Mirrors src/nexis/state.py::Report.
export interface Report {
  title: string;
  generated_at: string;
  ideas_evaluated: number;
  ideas_selected: number;
  content: string;
  format: OutputFormat;
}

// Mirrors src/nexis/metrics.py::CallMetrics.
export interface CallMetrics {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  llm_seconds: number;
}

// Mirrors src/nexis/metrics.py::RunMetrics.
export interface RunMetrics {
  run_id: string;
  wall_seconds: number;
  totals: CallMetrics;
  by_layer: Record<string, CallMetrics>;
  by_agent: Record<string, CallMetrics>;
  prompt_versions: Record<string, string>;
  unpriced_models: string[];
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
  result: Report[] | null;
  // Absent on a job that ran before the backend measured its runs.
  metrics: RunMetrics | null;
}

export function isActiveStatus(status: JobStatus): boolean {
  return status === "pending" || status === "running";
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
