# Nexis — Claude Code Instructions

## Project overview

Nexis is an autonomous multi-agent business idea pipeline built on LangGraph. It runs end-to-end without human intervention, producing a structured report of evaluated and planned business ideas. The full technical specification is in [`docs/specification.md`](docs/specification.md).

## Architecture

See the [specification](docs/specification.md) for full architecture, data contracts, configuration reference, project structure, and technology stack. Key source files:

- `graph.py` — parent graph (retry logic, supervisor, force-pass)
- `layers/` — four subgraphs: `research.py`, `review.py`, `planning.py`, `output.py`
- `server.py` + `langgraph.json` — LangGraph Platform deployment entry point

## Key conventions

- All inter-agent data uses Pydantic models defined in `src/nexis/state.py` — never use plain dicts for agent I/O
- Use `with_structured_output()` for every LLM call that returns structured data
- Agents must handle `failure_reason` fields gracefully — don't crash on partial results
- Each layer subgraph must be independently testable without running the full pipeline
- Async-first: all agent methods should be `async def` and use `asyncio.gather()` for concurrency

## Checkpointer

The pipeline uses `SqliteSaver` for checkpointing (set `CHECKPOINT_DB_PATH=./nexis_dev.db` in `.env`). `SqliteSaver.from_conn_string()` takes a file path, not a SQLAlchemy URL. Never hardcode connection strings.

## Deployment

See [`docs/deployment.md`](docs/deployment.md).

## Architecture Decision Records

Design decisions are documented as ADRs in `docs/adr/`. Use the template at `docs/adr/0000-template.md` when adding new ones.

## Testing

- Unit tests live in `tests/test_agents/` — test each agent in isolation with mocked LLM calls
- Layer tests live in `tests/test_layers/` — test subgraph routing and state transitions
- `tests/test_integration.py` has a mocked smoke test (runs in CI) and a `@pytest.mark.live` test (real APIs, skipped in CI)
