# ADR-0009: Structured JSON Telemetry Alongside LangSmith

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-03-29 |
| **Deciders** | Łukasz Zimnoch |

## Context

A pipeline run involves 13+ LLM calls, 4 subgraph layers, and conditional
branching. Without observability, diagnosing a slow run, a high-cost run, or a
run that produced surprising output requires re-reading source code and guessing.
Two categories of observability are needed:

1. **Per-node timing and I/O**: which nodes ran, how long they took, what state
   keys they read and wrote
2. **Per-LLM-call metrics**: which model was called, how many tokens were used,
   whether parsing succeeded, what the latency was

LangSmith (Anthropic's managed tracing service) is already integrated into
LangGraph via environment variable (`LANGCHAIN_TRACING_V2=true`) and provides
rich UI for visualizing LLM call chains. However, it requires an API key and
sends trace data to an external service.

## Decision

We implement two complementary observability layers:

- **Custom JSON telemetry** (`telemetry.py`): always-on, zero-dependency
  structured logging. Two event types are emitted:
  - `node_complete`: emitted by `instrument_node()` wrapper for every
    LangGraph node, capturing `node`, `layer`, `latency_ms`, `input_keys`,
    `output_keys`, and `error`
  - `llm_call`: emitted by `BaseAgent.invoke()` after every LLM call,
    capturing `agent`, `model`, `latency_ms`, `input_tokens`, `output_tokens`,
    `total_tokens`, `attempt`, and `success`
- **LangSmith tracing**: opt-in via `LANGCHAIN_TRACING_V2=true` environment
  variable. When enabled, LangGraph automatically sends full trace data
  (including LLM prompts and responses) to LangSmith.

JSON events are emitted via the standard `logging` module at `INFO` level under
the `nexis.telemetry` logger, making them available in any log aggregator
(CloudWatch, Datadog, or plain `grep`/`jq`).

## Considered Alternatives

### Option A: LangSmith Only

Rely exclusively on LangSmith for all observability. Remove the custom
`telemetry.py` module.

**Pros**
- Rich UI with token-level diff views and latency breakdowns
- No custom code to maintain

**Cons**
- Requires `LANGCHAIN_TRACING_V2=true` and a valid `LANGCHAIN_API_KEY` in
  every environment; CI and local dev without the key have zero observability
- Sends full prompt and response content to an external service; may be
  unacceptable for sensitive business idea prompts
- LangSmith's free tier has data retention limits

### Option B: OpenTelemetry

Emit spans and metrics using OpenTelemetry, exporting to a local Jaeger
instance or a cloud collector.

**Pros**
- Vendor-neutral; works with any OTel-compatible backend
- Richer than `logging`-based telemetry (distributed trace context, span
  attributes)

**Cons**
- Requires adding `opentelemetry-sdk` and a collector as dependencies
- LangGraph's native OTel integration is limited; custom spans would need
  manual context propagation
- Significant overhead for a single-developer project with batch workloads

### Option C: Custom Metrics Database

Write telemetry events to SQLite or PostgreSQL for aggregation and querying.

**Pros**
- Queryable history across pipeline runs
- No external service dependency

**Cons**
- Requires schema management, migration handling, and connection management
- Read/write to a separate database from within async LangGraph nodes adds
  complexity and potential blocking

## Consequences

### Positive
- JSON telemetry works in every environment with zero configuration; CI logs
  include timing and token data automatically
- `jq '.latency_ms' nexis.log | sort -n` gives instant per-node latency
  ranking without any dashboard
- LangSmith is available for deep debugging sessions without being a
  hard dependency

### Negative
- Two observability systems to maintain; changes to `BaseAgent` must update
  both the `log_llm_call()` call and any LangSmith-relevant attributes
- `instrument_node()` wraps every node function; if LangGraph changes how it
  calls nodes, the wrapper may need updating

### Trade-offs
- JSON logging captures timings and token counts but not full prompt/response
  content (to avoid log bloat). Prompt content is only available via LangSmith.
  For debugging output quality issues, LangSmith must be enabled.
