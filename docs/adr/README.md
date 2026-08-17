# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the Nexis
project. ADRs document significant architectural decisions: the context that
prompted them, the alternatives considered, and the trade-offs accepted.

## Template

[ADR-0000: Template](0000-template.md)

## Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [0001](0001-langgraph-orchestration-framework.md) | LangGraph as Orchestration Framework | Accepted | 2026-03-29 |
| [0002](0002-four-layer-sequential-pipeline.md) | Four-Layer Sequential Pipeline Architecture | Accepted | 2026-03-29 |
| [0003](0003-hybrid-parallelism-send-and-gather.md) | Hybrid Parallelism with Send() and asyncio.gather() | Accepted | 2026-03-29 |
| [0004](0004-openrouter-unified-llm-gateway.md) | OpenRouter as Unified LLM Gateway | Accepted | 2026-03-29 |
| [0005](0005-per-agent-model-specialization.md) | Per-Agent Model Specialization | Accepted | 2026-03-29 |
| [0006](0006-pydantic-v2-data-contracts-typeddict-state.md) | Pydantic v2 Data Contracts with TypedDict Graph State | Accepted | 2026-03-29 |
| [0007](0007-graceful-degradation-failure-reason.md) | Graceful Degradation via failure_reason Fields | Accepted | 2026-03-29 |
| [0008](0008-conditional-retry-force-pass-fallback.md) | Conditional Retry with Force-Pass Fallback | Accepted | 2026-03-29 |
| [0009](0009-structured-json-telemetry-and-langsmith.md) | Structured JSON Telemetry Alongside LangSmith | Accepted | 2026-03-29 |
| [0010](0010-deterministic-weighted-scoring.md) | Deterministic Weighted Scoring Without LLM | Accepted | 2026-03-29 |
| [0011](0011-cloud-run-scale-to-zero-iam-auth.md) | Cloud Run with Scale-to-Zero and IAM Auth | Superseded by ADR-0013, ADR-0014 | 2026-03-30 |
| [0012](0012-terraform-infrastructure-management.md) | Terraform for Infrastructure Management | Accepted | 2026-04-10 |
| [0013](0013-cloud-run-jobs-async-pipeline.md) | Cloud Run Jobs for Async Pipeline Execution | Accepted | 2026-04-10 |
| [0014](0014-firebase-auth-firestore-persistence.md) | Firebase Auth and Firestore for Auth and Job Persistence | Accepted | 2026-04-10 |
| [0015](0015-react-vite-monolith-spa.md) | React + Vite SPA Served from the FastAPI Container | Accepted | 2026-04-10 |

## How to Add a New ADR

1. Copy `0000-template.md` to `NNNN-kebab-case-title.md` (next sequential number)
2. Fill in all sections
3. Set status to `Proposed` until accepted by the team
4. Add a row to the index table above

## ADRs are append-only

Once an ADR is `Accepted`, its Context, Decision, Considered Alternatives, and Consequences sections **must not be edited**. They are a historical record of the reasoning at the time of the decision, and their value comes from preserving that snapshot — later edits obscure when and why direction changed.

The only permitted in-place edits on an accepted ADR are:

- Typo and formatting fixes that do not change meaning
- Flipping the **Status** field (e.g. `Accepted` → `Deprecated`, or `Accepted` → `Superseded by ADR-NNNN`)
- Adding a one-line cross-reference to a newer ADR that supersedes or deprecates this one
- Correcting a statement of fact that was wrong when written, such as a misnamed product or a wrong figure

The convention protects the **decision**, not a factual error. A wrong fact preserves nothing worth keeping and misleads every later reader, so fix it in place and add a dated line under a `## Corrections` heading at the end of the file saying what the text said before. A changed decision is the other case: leave it alone and write a new ADR. ADR-0009 is the canonical example of a correction.

If the decision itself needs to change — the context evolved, a trade-off no longer holds, a new constraint appeared — do **not** rewrite the existing ADR. Instead:

1. Write a new ADR that documents the new decision in its own Context/Decision/Consequences.
2. Reference the old ADR from the new one (e.g. "Supersedes ADR-NNNN").
3. Flip the old ADR's status to `Superseded by ADR-MMMM` and add a one-line pointer at the top.
4. Update the index table's Status column.

ADR-0011 is the canonical example in this repo.
