# Nexis — Claude Code Instructions

## Project overview

Nexis is an autonomous multi-agent business idea pipeline built on LangGraph. It runs end-to-end without human intervention, producing a structured report of evaluated and planned business ideas. The full technical specification is in [`docs/specification.md`](docs/specification.md).

## Tech stack

- **Python 3.11+** with `asyncio` for parallel execution; **uv** for dependency management
- **LangGraph 1.1+** — StateGraph, Send API, subgraphs, checkpointing
- **LangChain** — `with_structured_output()` for structured LLM responses
- **Pydantic v2** — all agent inputs/outputs and configuration are typed models
- **LLM** — per-agent model assignments in `src/nexis/models.py`; all calls routed through OpenRouter (`OPENROUTER_API_KEY` required)
- **Tavily** for web search
- **SqliteSaver** via `langgraph-checkpoint-sqlite` for checkpointing
- **Structured logging** (`nexis.telemetry`) for per-node and per-LLM-call telemetry; **LangSmith** for detailed tracing (opt-in via `LANGCHAIN_TRACING_V2` env var)
- **Jinja2** for report generation (markdown + JSON output)

## Architecture

Four sequential LangGraph subgraphs composed into a parent graph:

1. `layers/research.py` — Layer 1: idea generation with web research
2. `layers/review.py` — Layer 2: parallel critic panel via `Send()` API (N ideas × 6 critics)
3. `layers/planning.py` — Layer 3: MVP + GTM planning via `asyncio.gather()` inside per-idea nodes
4. `layers/output.py` — Layer 4: adversarial validation and report generation

The parent graph in `graph.py` owns `PipelineState` and handles the conditional retry edge after Layer 2.

## Key conventions

- All inter-agent data uses Pydantic models defined in `src/nexis/state.py` — never use plain dicts for agent I/O
- Use `with_structured_output()` for every LLM call that returns structured data
- Agents must handle `failure_reason` fields gracefully — don't crash on partial results
- Each layer subgraph must be independently testable without running the full pipeline
- Async-first: all agent methods should be `async def` and use `asyncio.gather()` for concurrency

## Checkpointer

The pipeline uses `SqliteSaver` for checkpointing (set `CHECKPOINT_DB=./nexis_dev.db` in `.env`). `SqliteSaver.from_conn_string()` takes a file path, not a SQLAlchemy URL. Never hardcode connection strings.

## Testing

- Unit tests live in `tests/test_agents/` — test each agent in isolation with mocked LLM calls
- Layer tests live in `tests/test_layers/` — test subgraph routing and state transitions
- `tests/test_integration.py` runs the full pipeline; only run against real APIs, not in CI
