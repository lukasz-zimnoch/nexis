# ADR-0003: Hybrid Parallelism with Send() and asyncio.gather()

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-03-29 |
| **Deciders** | Łukasz Zimnoch |

## Context

Two layers require significant parallelism:

- **Layer 2 (review)**: Every idea must be evaluated by all six critic roles.
  With N ideas, this produces N×6 independent LLM calls. The number of ideas N
  is not known at graph-compile time; it depends on how many ideas Layer 1
  generates.
- **Layer 3 (planning)**: For each top idea, MVP and GTM plans must be produced
  concurrently (they are independent), followed by a sequential business plan
  composition step that depends on both.

The parallelism strategy determines how results are collected, how failures are
isolated, and whether intermediate results are checkpointed.

## Decision

We use a hybrid approach:

- **`Send()` for cross-idea fan-out** (Layers 2 and 3): LangGraph's `Send()`
  API dispatches one graph node invocation per (idea, role) pair in Layer 2, and
  one per top idea in Layer 3. Each invocation writes its result back to the
  shared `PipelineState` via reducer functions (`operator.add` for lists,
  `merge_dicts` for dicts).
- **`asyncio.gather()` for intra-node concurrency** (Layer 3 MVP + GTM): Within
  each `plan_idea_node`, MVP and GTM planning run concurrently using
  `asyncio.gather()` because they are independent and both results are needed
  before the business plan composer can proceed.

## Considered Alternatives

### Option A: Pure asyncio.gather() for All Parallelism

Run all N×6 review LLM calls inside a single node using `asyncio.gather()`,
returning all reviews at once.

**Pros**
- Simpler graph topology (no `Send()` routing function needed)
- All results available in one place; no reducer merging

**Cons**
- LangGraph does not checkpoint intermediate results within a single node; if
  the node crashes after 20 of 30 LLM calls complete, all 20 must be re-run
- Memory pressure: all N×6 in-flight coroutines exist simultaneously within one
  node execution context

### Option B: Pure Send() for All Parallelism (Including MVP + GTM)

Express MVP and GTM planning as two separate `Send()` targets, merging results
in a subsequent synthesis node.

**Pros**
- Uniform parallelism model throughout the graph
- Each MVP and GTM call is independently checkpointed

**Cons**
- Requires a synthesis node after planning that must wait for both plans before
  invoking the business plan composer; adds graph complexity and an extra node
- The business plan composer needs both MVP and GTM results together, which
  would require passing them through state in a way that creates implicit
  sequencing

### Option C: Sequential Execution (No Parallelism)

Run each LLM call one at a time.

**Pros**
- Simplest code; no concurrency bugs

**Cons**
- Layer 2 with 8 ideas × 6 reviewers = 48 sequential LLM calls at ~5s each
  means ~4 minutes for Layer 2 alone
- Total pipeline time would be ~15–20 minutes instead of ~5–8 minutes

## Consequences

### Positive
- `Send()` fan-out in Layer 2 reduces wall-clock time from ~4 minutes to ~20–30
  seconds for the review phase (48 parallel calls vs. sequential)
- `asyncio.gather()` within `plan_idea_node` eliminates the sequential wait
  between MVP and GTM planning (saves ~30s per idea)
- `Send()` results are individually checkpointed by LangGraph; a crash mid-fan-out
  only loses the incomplete calls

### Negative
- `Send()` writes to shared `PipelineState`; reducer functions (`operator.add`,
  `merge_dicts`) must be carefully designed to be commutative and associative
- `asyncio.gather()` results are not checkpointed; if `plan_idea_node` crashes
  after both MVP and GTM succeed but before the business plan composer returns,
  both calls must be re-run on resume

### Trade-offs
- The hybrid model means developers must understand two different parallelism
  primitives. This is acceptable because each is used in a clearly bounded
  context and documented in the layer files.
