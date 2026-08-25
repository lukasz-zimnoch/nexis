# Nexis: instructions for AI agents

Nexis is an autonomous multi-agent business idea pipeline built on LangGraph.
Specialist LLM agents run in four layers and produce a report without human
input.

This file holds only what an agent needs to work on the repository. Everything
else lives in a document below. Read the one that matches the task instead of
guessing.

## Where to read what

| Document | Holds | Read it before you |
|---|---|---|
| [`docs/specification.md`](docs/specification.md) | Single source of truth. Architecture, the four layers, data contracts, scoring, evals, trust boundary, models and temperature, configuration, observability, the service and job surface, the project tree. | Change behaviour, add an agent, or answer "how does X work" |
| [`docs/deployment.md`](docs/deployment.md) | How to deploy on Cloud Run: prerequisites, the one-time setup steps, CI/CD, cost. | Touch deployment, secrets or GitHub Actions |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records. Context, alternatives, trade-off. | Change a decision, or need the reason behind one |
| [`docs/adr/README.md`](docs/adr/README.md) | The ADR index and the rules for writing one. | Add or edit an ADR |
| `infrastructure/terraform/*.tf` | Every GCP resource. The definition, not a copy of it. | Change any deployed configuration |
| `src/nexis/models.py` | The model per agent, with the evidence behind each choice. | Change which model an agent uses |
| `src/nexis/sampling.py` | The temperature per agent, and the bands. | Change how much spread an agent gets |
| `src/nexis/pricing.py` | The dated price table the cost estimate reads. | Add a model, or the run will not price it |
| `src/nexis/state.py` | Every Pydantic contract and the graph state. | Change what an agent sends or returns |
| [`README.md`](README.md) | The public introduction. Points outward, holds no detail of its own. | Change what the project claims to be |

Put a new fact in exactly one of these. If it belongs in two, it belongs in the
more specific one, and the other links to it.

## Rules for changing code

- Agent input and output is always a Pydantic model from `src/nexis/state.py`.
  Never a plain dict.
- Every LLM call that returns structured data uses `with_structured_output()`.
- Every consumer checks `failure_reason` before it uses a result. A partial
  result must never crash the caller (ADR-0007).
- Agent methods are `async def`. Use `asyncio.gather()` for concurrency, and
  make sure one failed branch cannot sink the others.
- Each layer subgraph stays testable on its own, without the full pipeline.
- Web text reaches a prompt only through `src/nexis/untrusted.py`. Sanitize the
  result, wrap it with `wrap_untrusted()`, and append `UNTRUSTED_DATA_RULE` to
  the agent's system prompt (ADR-0016).
- Every LLM call goes through `BaseAgent`, which is what puts it in the run
  totals. Open a run scope with `run_context()` at an entry point (ADR-0017).
- Nothing under `tests/` calls a real model. Work that needs real answers goes
  behind `python -m nexis.evals`, which is manual and spend-capped (ADR-0018).

## Changes that must land together

Each of these breaks something quietly when you do only half of it.

| If you change | Also change |
|---|---|
| The reviewer weights or the score formula | The frozen values in `tests/evals/scoring_regression.json`, in the same commit |
| The agent set | Both `models.py` and `sampling.py`. `PipelineConfig` refuses to build when the two tables disagree |
| The model an agent uses | `pricing.py`, or the run reports the model in `unpriced_models` and its cost as a floor |
| An agent's system prompt | Nothing in code, but the prompt digest moves, so every earlier eval run now reads as stale |
| Deployed Cloud Run configuration | The `.tf` file. Never `gcloud run services update`: the next apply reverts it |
| A specification section number | The `§` references inside the specification and in `.env.example` |

An accepted ADR is append-only. Do not rewrite one to record a new decision;
write a new ADR and flip the old status. A wrong fact is the one exception, and
`docs/adr/README.md` states how to correct it.

## Commands

```bash
uv run pytest tests/ -k "not live"    # the suite CI runs; no API key needed
uv run ruff check . && uv run ruff format --check .
cd frontend && npm test && npm run lint && npm run typecheck
```

Tests live next to what they cover: `tests/test_agents/` per agent with a
mocked LLM, `tests/test_layers/` per subgraph, `tests/test_evals/` for the eval
harness with a stand-in reviewer. `tests/test_integration.py` holds a mocked
smoke test plus one `@pytest.mark.live` test that CI deselects.

The reviewer evals are the exception: they call real models, cost money, and
run by hand. Read
[specification §5.1](docs/specification.md#51-how-to-run-them) before you run
one.
