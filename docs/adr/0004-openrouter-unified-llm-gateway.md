# ADR-0004: OpenRouter as Unified LLM Gateway

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-03-29 |
| **Deciders** | Łukasz Zimnoch |

## Context

Nexis uses models from three providers: Anthropic (Claude Opus/Sonnet/Haiku),
OpenAI (GPT series), and Google (Gemini Flash). Each provider has a separate
API, authentication mechanism, and Python SDK. Managing three sets of API keys,
three SDK versions, and three rate-limit budgets would add significant
operational overhead.

Additionally, `langchain-openai`'s `ChatOpenAI` supports custom `base_url` and
`default_headers`, making it straightforward to point all LLM calls at a single
proxy endpoint.

## Decision

All LLM calls are routed through [OpenRouter](https://openrouter.ai) using a
single `OPENROUTER_API_KEY`. The `build_llm()` function in `agents/base.py`
creates a `ChatOpenAI` client with:

```python
base_url="https://openrouter.ai/api/v1"
api_key=os.environ["OPENROUTER_API_KEY"]
```

Model names use OpenRouter's provider-prefixed format (e.g.,
`anthropic/claude-opus-4.6`, `openai/gpt-5.4`, `google/gemini-3-flash-preview`).
Switching to a different model for any agent requires changing one line in
`models.py`.

## Considered Alternatives

### Option A: Direct Provider SDKs

Use `langchain-anthropic`, `langchain-openai`, and `langchain-google` directly,
each configured with its own API key.

**Pros**
- No third-party intermediary in the critical path; slightly lower latency
- Provider-specific features (extended thinking, grounding) are accessible
  without compatibility workarounds

**Cons**
- Three API keys to rotate and store in secrets
- Three SDK dependencies to keep in sync; version conflicts are common
- Switching a model from one provider to another requires code changes in the
  agent factory, not just a config value

### Option B: LiteLLM Proxy (Self-Hosted)

Run a [LiteLLM](https://github.com/BerriAI/litellm) proxy locally or on a
small VM, routing all calls through it.

**Pros**
- Self-controlled; no data sent to a third-party aggregator
- Supports virtually every model via a single OpenAI-compatible API

**Cons**
- Requires running and maintaining an additional service
- Local proxy adds a network hop; remote proxy is another service to deploy and
  monitor
- No cost benefit over OpenRouter for a single-developer project

### Option C: Per-Provider SDK with a Factory Function

Keep direct provider SDKs but hide them behind a `build_llm(model_name: str)`
factory that inspects the model prefix and instantiates the right SDK client.

**Pros**
- No third-party aggregator in the critical path
- Full provider-specific feature access

**Cons**
- The factory function grows as new providers are added
- Still requires multiple API keys and dependency management

## Consequences

### Positive
- Single `OPENROUTER_API_KEY` secret; one billing dashboard for all providers
- Model swaps are configuration changes (one line in `models.py`), not code
  changes
- The `ChatOpenAI` client works for all three providers; no extra SDK
  dependencies

### Negative
- OpenRouter is a third-party dependency in the hot path of every LLM call; an
  OpenRouter outage prevents all LLM calls even if the underlying providers are
  healthy
- Latency may be slightly higher due to the additional network hop through
  OpenRouter's infrastructure

### Trade-offs
- OpenRouter's free tier and pay-as-you-go pricing are appropriate for a
  personal project with ~10 pipeline runs per month. For higher-volume
  production use, direct provider SDKs would reduce per-token cost.
