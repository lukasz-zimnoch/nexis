import ReactMarkdown from "react-markdown";
import type { JobResultItem } from "../api/jobs";

interface ReportViewProps {
  result: JobResultItem[] | null;
}

function extractMarkdown(item: JobResultItem): string {
  if (typeof item.markdown === "string") return item.markdown;
  // Fallback: dump JSON inside a fenced block so the user can still see what
  // came back even if the schema changes.
  return "```json\n" + JSON.stringify(item, null, 2) + "\n```";
}

export default function ReportView({ result }: ReportViewProps) {
  if (!result || result.length === 0) {
    return <p className="muted">No reports yet.</p>;
  }
  return (
    <div className="report">
      {result.map((item, index) => (
        <div key={index}>
          {item.title ? <h2>{String(item.title)}</h2> : null}
          <ReactMarkdown>{extractMarkdown(item)}</ReactMarkdown>
          {index < result.length - 1 ? <hr /> : null}
        </div>
      ))}
    </div>
  );
}
