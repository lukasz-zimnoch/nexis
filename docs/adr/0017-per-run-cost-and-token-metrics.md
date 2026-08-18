# ADR-0017: Per-Run Cost and Token Metrics

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-18 |
| **Deciders** | Łukasz Zimnoch |

## Context

One run makes about 65 LLM calls across 13 agents and 6 models. ADR-0009 gave
each call a structured `llm_call` event with its token counts. Three questions
still had no answer:

1. What did this run cost?
2. Which layer spent it?
3. Which prompt produced this report?

The token counts existed but nothing added them up. They lived only in the log,
so the answer expired with the log retention of Cloud Run, and a user of the web
UI saw a finished report with no price on it. The `llm_call` event also named the
model but not the layer, because the agent that emits the event sits several
frames below the node that knows the layer.

OpenRouter returns token usage on the response itself. It does not return a
price there. Its `/generation` endpoint reports the amount actually charged for
one call, but only after the call, through a separate request.

Two constraints shaped the decision. The pipeline must not depend on a live
price lookup while it runs, and a test must produce the same numbers with no
network and no API key.

## Decision

We measure every run in the process that runs it, and we store the result with
the job. Four parts:

1. **A dated price table** (`nexis/pricing.py`). USD per million tokens, input
   and output, read from OpenRouter on 2026-08-14. The rates repeat the ones
   already quoted per assignment in `nexis/models.py`.
   `estimate_cost_usd()` returns `None` for a model that is not in the table.
2. **An accumulator** (`nexis/metrics.py`). `RunMetrics` holds one run in three
   views: totals, per layer, and per agent. Each view counts calls, input and
   output tokens, cost and LLM seconds. A model with no price goes into
   `unpriced_models`, so a gap in the table reads as a gap and never as a free
   call.
3. **A run scope** (`nexis/telemetry.py`). `run_context(run_id)` holds the
   accumulator in a context variable, and `instrument_node()` holds the layer in
   a second one. asyncio copies the context into every task, so a fan-out
   inherits both and a concurrent layer cannot claim another layer's calls. Every
   `llm_call` event now carries `run_id`, `layer`, `prompt_version` and
   `cost_usd`.
4. **A prompt version**. The first 12 hex characters of the SHA-256 digest of an
   agent's system prompt. It rides on every `llm_call` event and is stored per
   agent on `RunMetrics`.

The Cloud Run Job writes `RunMetrics` to `JobRecord.metrics` when the run ends,
for a failed run as well as a completed one, and the SPA renders it beside the
report.

ADR-0009 stays in force. This decision adds fields to its two events and a total
on top of them.

## Considered Alternatives

### Option A: Ask OpenRouter for the amount charged

Call `/generation` after each LLM call and record the price OpenRouter reports.

**Pros**
- The real charged amount, not an estimate
- No price table to maintain, and no drift when a vendor changes a rate
- Covers the higher rate that two models charge for a very long prompt

**Cons**
- One extra HTTP request per LLM call, on the hot path of every run
- A second failure mode for a number that is only a report, not a result
- The value is not ready the moment the call returns
- Every test would need a key and a network, or a mock of the endpoint

### Option B: Carry the accumulator in the graph state

Add a metrics field to `PipelineState` with a merge reducer.

**Pros**
- Explicit. No context variables, and the value is visible in a checkpoint
- Fits the existing state contract

**Cons**
- `PipelineState` is the data contract between agents. Cost is not agent data
- Every node would have to return the field for the reducer to merge it
- An agent sits below the node, so `BaseAgent` would need the object threaded
  through every call signature

### Option C: Read the numbers out of the logs

Build a log-based metric in Cloud Logging over the `llm_call` events.

**Pros**
- No code in the pipeline at all
- Aggregates across runs for free

**Cons**
- The number lives outside the product. The SPA cannot show it without a second
  data path
- Log retention decides how long a run's cost exists
- Ties a portfolio project to one cloud vendor's log query language

### Option D: A module-level accumulator

One global object, reset at the start of each run.

**Pros**
- The least code

**Cons**
- Two runs in one process mix their numbers
- One test leaks its calls into the next test

## Consequences

### Positive
- A finished job carries its own price, per layer and per agent, with no log
  search
- A failed run reports what it spent before it broke
- A stored report names the prompt version behind each agent, so a change in
  output quality can be tied to a change of prompt
- The price table is one file with a date on it, and a test asserts that every
  model in `DEFAULT_AGENT_MODELS` and the fallback model has a price

### Negative
- The table rots on its own schedule. The test catches a new model assignment
  with no price. It cannot catch a vendor that changes a rate, which needs a
  human to refresh the table and the date together
- Two more context variables to reason about when a future code path calls an
  agent outside a node. Such a call lands in the `unattributed` layer bucket

### Trade-offs
- **The cost is an estimate, not a bill.** The table holds base rates only. The
  two OpenAI models charge more above 272k prompt tokens, a limit these prompts
  do not approach. Provider discounts, cache hits and gateway fees are not
  modelled
- **A failed call counts.** A retry pays for both attempts, so both are in the
  total. The number answers "what did this run cost", not "how much useful work
  did it buy"
- **`llm_seconds` exceeds `wall_seconds` whenever a layer fans out.** The two are
  reported separately on purpose: the ratio between them shows what concurrency
  saved
- **A CLI run keeps its metrics in the `run_complete` log event only.** Only the
  Cloud Run Job persists them, because only it has a job record to write to

<!--
Reminder: once this ADR is accepted, its content becomes append-only.
Do not rewrite Context/Decision/Consequences to reflect later changes —
write a new ADR that supersedes this one and flip the Status field here.
See docs/adr/README.md → "ADRs are append-only".
-->
