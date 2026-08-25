# ADR-0001: LangGraph as Orchestration Framework

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-03-29 |
| **Deciders** | Łukasz Zimnoch |
| **Partly superseded by** | [ADR-0013](0013-cloud-run-jobs-async-pipeline.md) (checkpointing and the production runtime) |

## Context

Nexis must orchestrate 13 LLM agents across four sequential phases (research,
review, planning, output). The pipeline requires:

- Typed, inspectable state shared across all agents
- Fan-out parallelism: N ideas × 6 reviewers must run concurrently (Layer 2)
  and per-idea MVP + GTM must run concurrently (Layer 3)
- Persistent checkpointing so a crashed run can be resumed without re-running
  completed agents
- Conditional retry routing: if no ideas pass the quality threshold, loop back
  to research with a refined prompt

The choice of orchestration layer shapes every other architectural decision —
how state is typed, how parallelism is expressed, and how errors propagate.

## Decision

We use [LangGraph](https://github.com/langchain-ai/langgraph) as the
orchestration framework. The pipeline is expressed as a `StateGraph` whose
nodes are LangGraph subgraphs (one per layer). Parallelism uses the `Send()`
API for cross-idea fan-out and `asyncio.gather()` for intra-node concurrency.
Checkpointing uses `SqliteSaver` for local development and LangGraph Platform's
built-in checkpointer in production.

## Considered Alternatives

### Option A: Raw asyncio + Custom State Machine

Hand-roll a state machine using Python `asyncio`, `dataclasses` or `TypedDict`
for state, and explicit `asyncio.gather()` for parallelism.

**Pros**
- Zero framework dependency; full control over execution semantics
- No LangChain ecosystem coupling

**Cons**
- Checkpointing (resume on crash) must be implemented from scratch
- Conditional routing, fan-out reducers, and subgraph composition all require
  significant boilerplate
- No built-in LangSmith tracing integration

### Option B: Prefect / Temporal (Workflow Engines)

Use a production-grade workflow engine designed for durable execution and retry.

**Pros**
- Battle-tested durability guarantees; built-in retry and resume semantics
- Strong observability dashboards out of the box

**Cons**
- Requires a separate server (Prefect Cloud or Temporal cluster) even for local dev
- Not designed for LLM-native patterns (structured output binding, message history,
  Send()-style fan-out)
- Significant operational overhead for a single-developer project

### Option C: CrewAI / AutoGen (Multi-Agent Frameworks)

Use a framework specifically designed for multi-agent collaboration.

**Pros**
- Higher-level abstractions for agent roles, tools, and inter-agent communication
- Faster initial prototype

**Cons**
- Opinionated agent-to-agent communication model conflicts with Nexis's
  sequential, layer-based pipeline design
- Limited support for typed state that is shared across all agents
- Checkpointing and conditional routing are not first-class features

### Option D: Apache Airflow (DAG Scheduler)

Model the pipeline as an Airflow DAG.

**Pros**
- Mature, production-proven scheduler
- Strong UI for monitoring DAG runs

**Cons**
- Designed for data-pipeline DAGs (batch tasks), not interactive LLM agents
- No native support for LLM structured output, message history, or dynamic fan-out
- Heavyweight: requires a scheduler, webserver, and metadata DB

## Consequences

### Positive
- `StateGraph` with `TypedDict` state provides compile-time type safety and
  runtime validation across all nodes
- The `Send()` API expresses dynamic fan-out (N ideas × 6 roles) without
  boilerplate reducers
- `SqliteSaver` / LangGraph Platform checkpointing gives crash-recovery for free
- LangSmith tracing integrates automatically with zero code changes

### Negative
- Couples the codebase to the LangChain / LangGraph ecosystem; migrating to a
  different orchestrator would require rewriting all node functions and state types
- LangGraph's execution model (sync node functions called by the graph runner)
  requires `instrument_node` wrappers to add custom telemetry

### Trade-offs
- LangGraph's state reducer model (Annotated list/dict fields) is non-obvious
  for developers unfamiliar with the framework. This is acceptable because the
  complexity is localized to `state.py` and each layer's state class.
