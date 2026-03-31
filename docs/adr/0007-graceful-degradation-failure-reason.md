# ADR-0007: Graceful Degradation via failure_reason Fields

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-03-29 |
| **Deciders** | Łukasz Zimnoch |

## Context

LLM calls can fail in several ways: API timeouts (network or provider-side),
structured output parsing errors (model returns malformed JSON), rate limit
errors (429 from provider), or model refusals (content policy). With 13 agents
and N×6 parallel review calls per run, some subset of calls failing in any
given run is expected, not exceptional.

The pipeline should produce the best possible output given whatever agents
succeeded, rather than crashing on the first failure. At the same time, failures
should be visible and inspectable — silent data loss is worse than a partial
result.

## Decision

Every Pydantic output model that can be produced by an LLM agent carries a
`failure_reason: str | None = None` field. When `BaseAgent.invoke()` exhausts
all retries, it calls `_failure_result(reason)` which constructs a minimal valid
instance of the output schema with:

- `failure_reason` set to the last error message
- All required fields set to their minimal valid values (`""`, `0`, `[]`, `0.0`)
- All optional fields left at their defaults

Downstream agents and synthesis nodes check `failure_reason is None` before
using a result. For example, `ReviewSynthesizer` skips reviews where
`review.failure_reason is not None` when computing weighted scores.

## Considered Alternatives

### Option A: Raise Exceptions (Fail-Fast)

Propagate exceptions from `BaseAgent.invoke()` to the calling node, which
raises them to LangGraph, which halts the graph.

**Pros**
- Simple: no special result types needed
- Failures are immediately visible and unambiguous

**Cons**
- A single reviewer failure (1 of 48 parallel LLM calls) aborts the entire
  pipeline run, discarding all completed work
- With LangGraph checkpointing, the run can be resumed, but resuming still
  re-runs the failed node — and if the failure is transient (rate limit),
  re-running may succeed, but if it's systematic (model retired), it will loop

### Option B: Circuit Breaker Pattern

Track failure rates per agent; once a threshold is exceeded, short-circuit that
agent and skip its output entirely.

**Pros**
- Prevents cascading failures more elegantly than per-call retry
- Can distinguish between transient and systematic failures

**Cons**
- Adds significant complexity: a circuit breaker requires shared mutable state
  across parallel node invocations, which conflicts with LangGraph's immutable
  state model
- For a pipeline with at most 48 concurrent calls, the overhead of a circuit
  breaker is not justified

### Option C: Human-in-the-Loop Escalation

When an agent fails, emit a LangGraph `interrupt()` to pause the graph and
notify the operator.

**Pros**
- Human can decide whether to retry, skip, or abort

**Cons**
- Incompatible with the unattended batch execution model; Nexis is designed to
  run autonomously without human intervention
- A single reviewer failure is not worth operator attention

## Consequences

### Positive
- The pipeline always produces output, even if some agents fail; partial results
  are better than no results for a batch pipeline
- Failures are fully inspectable: every Pydantic object in state carries the
  exact error message that caused the failure
- Downstream agents can make explicit decisions about how to handle partial
  data (e.g., skip, weight lower, or flag in the report)

### Negative
- Every output model must declare `failure_reason: str | None = None`; forgetting
  this field on a new model means `_failure_result()` cannot construct a valid
  failure instance and will raise `RuntimeError`
- The "minimal valid instance" returned on failure may contain misleading
  default values (e.g., `score=0`, `confidence=0.0`) if downstream code does
  not check `failure_reason` before using the fields

### Trade-offs
- Graceful degradation can mask systematic failures: if all 6 reviewers for an
  idea fail, that idea gets a score of 0.0 and is ranked last, which looks like
  a low-quality idea rather than a failed evaluation. The `failure_reason` field
  in each `Review` makes this diagnosable but requires active inspection of
  results.
