# ADR-0006: Pydantic v2 Data Contracts with TypedDict Graph State

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-03-29 |
| **Deciders** | Łukasz Zimnoch |

## Context

Data flows between 13 LLM agents across four pipeline layers. Two concerns must
be addressed simultaneously:

1. **Agent I/O validation**: LLM responses must be validated against a schema
   before being stored in state. Invalid responses (missing fields, wrong types)
   must be caught early and produce structured failure signals, not runtime
   crashes.
2. **Safe parallel state merging**: When `Send()` dispatches N×6 concurrent
   review nodes, each node must write its result back to `PipelineState` without
   overwriting results from sibling nodes. LangGraph uses `Annotated` type
   metadata on `TypedDict` fields to declare reducer functions for this purpose.

These two concerns push in different directions: Pydantic `BaseModel` excels at
validation and structured LLM output binding, while LangGraph's state merging
requires `TypedDict` with `Annotated` reducers.

## Decision

We use a split approach:

- **All agent input and output types are Pydantic `BaseModel` subclasses**
  (`BusinessIdea`, `Review`, `MVPPlan`, `GTMPlan`, etc., defined in `state.py`).
  LangChain's `with_structured_output()` binds directly to these models.
- **`PipelineState` and layer-specific state extensions are `TypedDict` with
  `Annotated` reducer fields** for fields that accumulate across parallel nodes
  (e.g., `ideas`, `reviews`, `scores`, `mvp_plans`).

```python
class PipelineState(TypedDict):
    ideas:   Annotated[list[BusinessIdea],  operator.add]
    reviews: Annotated[list[Review],        operator.add]
    scores:  Annotated[dict[str, float],    merge_dicts]
    ...
```

## Considered Alternatives

### Option A: Plain Dicts for Everything

Use plain `dict` for all agent I/O and graph state.

**Pros**
- No schema definition overhead; fastest to write initially

**Cons**
- No validation at agent boundaries; LLM hallucinations silently propagate
- `with_structured_output()` requires a schema; plain dicts are not supported
- No IDE autocompletion or static analysis

### Option B: Dataclasses for Agent I/O

Use Python `dataclasses` instead of Pydantic `BaseModel`.

**Pros**
- Standard library; no Pydantic dependency for validation

**Cons**
- `with_structured_output()` has first-class support for Pydantic models but
  not dataclasses; using dataclasses would require manual conversion
- No built-in JSON schema generation; structured LLM output requires a JSON
  schema, which Pydantic generates automatically via `model_json_schema()`

### Option C: All-Pydantic (Including State)

Use Pydantic `BaseModel` for `PipelineState` as well as agent I/O.

**Pros**
- Uniform model type throughout; one mental model

**Cons**
- LangGraph's reducer annotation system (`Annotated[list, operator.add]`) is
  designed for `TypedDict`; Pydantic models do not support the same annotation
  semantics
- LangGraph internally uses `TypedDict` for state schema introspection; using
  a Pydantic model as state type would require additional compatibility shims

### Option D: All-TypedDict (Including Agent I/O)

Use `TypedDict` for agent I/O as well as state.

**Pros**
- Uniform approach; one model type throughout

**Cons**
- `TypedDict` provides no runtime validation; an LLM returning a wrong type
  would silently corrupt state
- `with_structured_output()` works best with Pydantic models; `TypedDict`
  support is less reliable across LangChain versions

## Consequences

### Positive
- Pydantic validation catches LLM output errors at the agent boundary, before
  they corrupt pipeline state
- `with_structured_output(schema, include_raw=True)` returns both the parsed
  object and raw LLM message, enabling telemetry token counting without
  additional parsing
- `TypedDict` reducers ensure parallel `Send()` nodes write safely to shared
  state without overwriting each other

### Negative
- Developers must understand why two different model systems are used; without
  context, the split can seem inconsistent
- `failure_reason` fields must be added manually to every Pydantic model that
  can fail (see ADR-0007)

### Trade-offs
- The `PipelineState` field types reference Pydantic models (e.g.,
  `list[BusinessIdea]`) but the state itself is a `TypedDict`. This mixing is
  intentional and supported by LangGraph, but requires knowing the distinction.
