# Nexis — Claude Code Instructions

## Project overview

Nexis is an autonomous multi-agent business idea pipeline built on LangGraph. It runs end-to-end without human intervention, producing a structured report of evaluated and planned business ideas. The full technical specification is in [`docs/specification.md`](docs/specification.md).

## Tech stack

- **Python 3.11+** with `asyncio` for parallel execution
- **LangGraph 0.3+** — StateGraph, Send API, subgraphs, checkpointing
- **LangChain** — `with_structured_output()` for structured LLM responses
- **Pydantic v2** — all agent inputs/outputs and configuration are typed models
- **LLM** — configurable via `model_name`; model TBD
- **Tavily** (primary) / **Serper** (fallback) for web search
- **PostgresSaver** (production) / **SqliteSaver** (development) for checkpointing
- **LangSmith** for tracing and cost attribution
- **Jinja2** + **WeasyPrint** for report generation

## Architecture

Four sequential LangGraph subgraphs composed into a parent graph:

1. `layers/research.py` — Layer 1: idea generation with web research
2. `layers/review.py` — Layer 2: parallel critic panel via `Send()` API (N ideas × 5 critics)
3. `layers/planning.py` — Layer 3: MVP + GTM planning in parallel branches
4. `layers/output.py` — Layer 4: adversarial validation and report generation

The parent graph in `graph.py` owns `PipelineState` and handles the conditional retry edge after Layer 2.

## Key conventions

- All inter-agent data uses Pydantic models defined in `src/state.py` — never use plain dicts for agent I/O
- Use `with_structured_output()` for every LLM call that returns structured data
- Agents must handle `failure_reason` fields gracefully — don't crash on partial results
- Each layer subgraph must be independently testable without running the full pipeline
- Async-first: all agent methods should be `async def` and use `asyncio.gather()` for concurrency

## Development checkpointer

Use `SqliteSaver` locally (set `DATABASE_URL=sqlite:///./nexis_dev.db` in `.env`). Never hardcode connection strings.

## Testing

- Unit tests live in `tests/test_agents/` — test each agent in isolation with mocked LLM calls
- Layer tests live in `tests/test_layers/` — test subgraph routing and state transitions
- `tests/test_integration.py` runs the full pipeline; only run against real APIs, not in CI
