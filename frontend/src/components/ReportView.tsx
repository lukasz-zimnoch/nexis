import ReactMarkdown from "react-markdown";
import type { Report } from "../api/jobs";

interface ReportViewProps {
  result: Report[] | null;
}

function renderBody(report: Report) {
  if (report.format === "json") {
    return <pre>{report.content}</pre>;
  }
  return <ReactMarkdown>{report.content}</ReactMarkdown>;
}

export default function ReportView({ result }: ReportViewProps) {
  if (!result || result.length === 0) {
    return <p className="muted">No reports yet.</p>;
  }
  return (
    <div className="report">
      {result.map((report, index) => (
        <div key={index}>
          <h2>{report.title}</h2>
          {renderBody(report)}
          {index < result.length - 1 ? <hr /> : null}
        </div>
      ))}
    </div>
  );
}
