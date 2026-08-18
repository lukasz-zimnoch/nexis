import type { CallMetrics, RunMetrics } from "../api/jobs";
import { formatSeconds, formatTokens, formatUsd } from "../lib/format";

interface MetricsPanelProps {
  metrics: RunMetrics | null;
}

function totalTokens(bucket: CallMetrics): number {
  return bucket.input_tokens + bucket.output_tokens;
}

export default function MetricsPanel({ metrics }: MetricsPanelProps) {
  if (!metrics) {
    return <p className="muted">No run metrics recorded for this job.</p>;
  }

  const { totals } = metrics;
  const layers = Object.entries(metrics.by_layer);
  const prompts = Object.entries(metrics.prompt_versions);

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Run cost</h3>

      <div className="row">
        <div>
          <div className="metric-value">{formatUsd(totals.cost_usd)}</div>
          <div className="muted">estimated cost</div>
        </div>
        <div>
          <div className="metric-value">{totals.calls}</div>
          <div className="muted">LLM calls</div>
        </div>
        <div>
          <div className="metric-value">{formatTokens(totalTokens(totals))}</div>
          <div className="muted">tokens</div>
        </div>
        <div>
          <div className="metric-value">{formatSeconds(metrics.wall_seconds)}</div>
          <div className="muted">wall time</div>
        </div>
        <div>
          <div className="metric-value">{formatSeconds(totals.llm_seconds)}</div>
          <div className="muted">summed LLM time</div>
        </div>
      </div>

      {metrics.unpriced_models.length > 0 ? (
        <p className="muted">
          Cost excludes {metrics.unpriced_models.length} model(s) with no price in the
          table: {metrics.unpriced_models.join(", ")}.
        </p>
      ) : null}

      {layers.length > 0 ? (
        <table className="metrics-table">
          <thead>
            <tr>
              <th>Layer</th>
              <th>Calls</th>
              <th>Input</th>
              <th>Output</th>
              <th>LLM time</th>
              <th>Cost</th>
            </tr>
          </thead>
          <tbody>
            {layers.map(([layer, bucket]) => (
              <tr key={layer}>
                <td>{layer}</td>
                <td>{bucket.calls}</td>
                <td>{formatTokens(bucket.input_tokens)}</td>
                <td>{formatTokens(bucket.output_tokens)}</td>
                <td>{formatSeconds(bucket.llm_seconds)}</td>
                <td>{formatUsd(bucket.cost_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      {prompts.length > 0 ? (
        <details>
          <summary className="muted">Prompt versions</summary>
          <table className="metrics-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Prompt</th>
              </tr>
            </thead>
            <tbody>
              {prompts.map(([agent, version]) => (
                <tr key={agent}>
                  <td>{agent}</td>
                  <td>
                    <code>{version}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ) : null}

      <div className="muted">Run {metrics.run_id}</div>
    </div>
  );
}
