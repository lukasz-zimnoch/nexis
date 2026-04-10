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
