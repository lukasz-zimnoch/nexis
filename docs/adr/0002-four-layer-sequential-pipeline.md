# ADR-0002: Four-Layer Sequential Pipeline Architecture

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-03-29 |
| **Deciders** | Łukasz Zimnoch |

## Context

The pipeline must take a research prompt and produce a structured report of
evaluated and planned business ideas. The full flow involves several logically
distinct phases:

1. Generating raw ideas from trend research
2. Evaluating ideas against multiple quality dimensions in parallel
3. Creating detailed implementation and go-to-market plans for the best ideas
4. Producing a report with adversarial validation

The question is how to decompose this work into nodes or subgraphs and how to
sequence them.

## Decision

We structure the pipeline as four sequential LangGraph subgraphs — Layers 1–4 —
each compiled independently and added as a node in the parent `StateGraph`
defined in `graph.py`:

- **Layer 1** (`layers/research.py`): trend scanning and idea generation
- **Layer 2** (`layers/review.py`): parallel critic panel via `Send()`
- **Layer 3** (`layers/planning.py`): MVP + GTM planning via `Send()`
- **Layer 4** (`layers/output.py`): adversarial validation and report generation

The parent graph owns `PipelineState` and handles cross-layer concerns:
supervisor initialization, conditional retry after Layer 2, and force-pass
fallback.

## Considered Alternatives

### Option A: Single Monolithic Graph

Express the entire pipeline as a flat `StateGraph` with one node per agent
(~13 nodes) and hand-coded edges between them.

**Pros**
- Simpler graph topology; easier to visualize end-to-end
- No subgraph compilation overhead

**Cons**
- All 13 agents share a single node namespace; naming conflicts become likely
  as the pipeline grows
- Cannot test a single phase (e.g., just the review layer) in isolation without
  running the entire graph
- Cross-layer retry logic (loop back from review to research) is harder to
  express cleanly in a flat graph

### Option B: Three Layers (Merge Review + Planning)

Combine Layers 2 and 3 into a single "evaluation" subgraph that reviews and
plans ideas in one pass.

**Pros**
- One fewer subgraph to wire and compile

**Cons**
- The review phase must complete before planning can start (planning needs
  scores to select top ideas); merging them would require awkward internal
  routing
- The two phases have very different parallelism patterns (N×6 fan-out vs. N×2
  gather), making a combined subgraph harder to reason about

### Option C: Micro-Agents (One Subgraph per Agent)

Treat each of the 13 agents as its own compiled subgraph.

**Pros**
- Maximum isolation; each agent is independently deployable

**Cons**
- 13 subgraph compilation steps add startup latency
- The parent graph would need to manage all inter-agent state passing
  explicitly, recreating the complexity that layer grouping is meant to hide

## Consequences

### Positive
- Each layer subgraph can be unit-tested independently without running the full
  pipeline (enforced by the test layout in `tests/test_layers/`)
- Layer boundaries map directly to information dependencies: Layer 3 cannot
  start until Layer 2 produces `top_ideas`; this is enforced structurally
- Adding a new agent to an existing layer requires changes only within that
  layer's file

### Negative
- Subgraph composition in LangGraph requires that each subgraph's state type is
  compatible with `PipelineState`; the `ReviewNodeState` and `PlanningNodeState`
  extension pattern adds boilerplate

### Trade-offs
- The parent graph must compile all four subgraphs at startup, which adds
  ~100–200 ms. This is acceptable for a batch pipeline that runs for ~10 minutes.
