import { useState, type FormEvent } from "react";
import type { JobConfig } from "../api/jobs";

interface JobFormProps {
  onSubmit: (config: JobConfig) => Promise<void> | void;
  submitting?: boolean;
}

const DEFAULT_CONFIG: JobConfig = {
  research_prompt: "",
  num_ideas: 8,
  top_k: 3,
  score_threshold: 0.55,
  output_format: "markdown",
};

export default function JobForm({ onSubmit, submitting }: JobFormProps) {
  const [config, setConfig] = useState<JobConfig>(DEFAULT_CONFIG);

  function update<K extends keyof JobConfig>(key: K, value: JobConfig[K]) {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!config.research_prompt.trim()) return;
    await onSubmit(config);
  }

  return (
    <form onSubmit={handleSubmit} className="card">
      <div className="field">
        <label className="label" htmlFor="research_prompt">
          Research prompt
        </label>
        <textarea
          id="research_prompt"
          className="input"
          rows={3}
          required
          value={config.research_prompt}
          onChange={(e) => update("research_prompt", e.target.value)}
          placeholder="e.g. AI tools for indie podcasters"
        />
      </div>
      <div className="row">
        <div className="field" style={{ flex: 1 }}>
          <label className="label" htmlFor="num_ideas">
            Number of ideas
          </label>
          <input
            id="num_ideas"
            className="input"
            type="number"
            min={1}
            max={50}
            value={config.num_ideas}
            onChange={(e) => update("num_ideas", Number(e.target.value))}
          />
        </div>
        <div className="field" style={{ flex: 1 }}>
          <label className="label" htmlFor="top_k">
            Top K
          </label>
          <input
            id="top_k"
            className="input"
            type="number"
            min={1}
            max={20}
            value={config.top_k}
            onChange={(e) => update("top_k", Number(e.target.value))}
          />
        </div>
        <div className="field" style={{ flex: 1 }}>
          <label className="label" htmlFor="score_threshold">
            Score threshold
          </label>
          <input
            id="score_threshold"
            className="input"
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={config.score_threshold}
            onChange={(e) =>
              update("score_threshold", Number(e.target.value))
            }
          />
        </div>
        <div className="field" style={{ flex: 1 }}>
          <label className="label" htmlFor="output_format">
            Output format
          </label>
          <select
            id="output_format"
            className="input"
            value={config.output_format}
            onChange={(e) => update("output_format", e.target.value)}
          >
            <option value="markdown">Markdown</option>
            <option value="json">JSON</option>
          </select>
        </div>
      </div>
      <button
        type="submit"
        className="btn btn-primary"
        disabled={submitting || !config.research_prompt.trim()}
      >
        {submitting ? "Submitting…" : "Run pipeline"}
      </button>
    </form>
  );
}
