# ADR-0008: Conditional Retry with Force-Pass Fallback

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-03-29 |
| **Deciders** | Łukasz Zimnoch |

## Context

After Layer 2 (review), ideas are filtered by a score threshold
(`config.score_threshold`, default 0.55) and the top K are selected
(`config.top_k`, default 3). If no ideas meet the threshold — for example,
because the research prompt generated generic ideas that scored poorly — the
pipeline would proceed to planning with an empty `top_ideas` list, producing an
empty report.

This "no ideas passed" outcome is undesirable for a pipeline designed to always
produce a useful report. A recovery strategy is needed that preserves quality
when possible while guaranteeing some output regardless.

## Decision

The `should_retry` function in `graph.py` implements three-way conditional
routing after the review subgraph:

1. **`planning`** (happy path): `top_ideas` is non-empty → proceed to Layer 3
2. **`retry`**: `top_ideas` is empty and `iteration < max_retries` → route to
   `increment_iteration_node` → `supervisor_node` (which appends a refinement
   suffix to the research prompt) → Layer 1 research again
3. **`force_pass`**: `top_ideas` is empty and `iteration >= max_retries` →
   `force_pass_node` selects the top-K ideas by raw score regardless of
   threshold → proceed to Layer 3

The supervisor node appends `" (previous ideas were too generic, focus on
underserved niches)"` to the research prompt on retry iterations.

`max_retries` defaults to 2, meaning the pipeline can loop through research
at most twice before force-passing.

## Considered Alternatives

### Option A: No Retry (Accept Empty Output)

If no ideas pass the threshold, proceed to Layer 4 with an empty `top_ideas`.
The output layer would generate a report stating no viable ideas were found.

**Pros**
- Simplest control flow; no looping in the graph
- Honest: if no ideas are good enough, say so

**Cons**
- For a pipeline run costing ~$1–2 in LLM tokens, producing an empty report
  is a total waste; the user gets nothing actionable
- The most likely cause of "no ideas passing" is a poorly specified prompt or
  a research layer that generated generic ideas — both are fixable with retry

### Option B: Unlimited Retries Until Ideas Pass

Keep retrying until at least one idea passes the threshold, with no maximum
iteration count.

**Pros**
- Guarantees non-empty `top_ideas` before proceeding

**Cons**
- Could loop indefinitely if the threshold is misconfigured or the research
  prompt is fundamentally not idea-generating
- No cost ceiling: each retry costs ~$0.30–0.50 in LLM tokens

### Option C: Lower Threshold Dynamically on Each Retry

On each retry, reduce `score_threshold` by a fixed amount (e.g., 0.1) until
ideas pass.

**Pros**
- No prompt refinement needed; pure numerical fallback

**Cons**
- A threshold that decays to 0 has the same effect as force-pass but is less
  transparent about what is happening
- The threshold carries semantic meaning (minimum acceptable quality bar);
  silently lowering it obscures quality expectations

### Option D: Human Approval Gate

After max retries, pause the graph (`interrupt()`) and ask the operator to
approve force-passing or abort.

**Pros**
- Human in the loop for a critical quality decision

**Cons**
- Incompatible with unattended batch execution; Nexis is designed to run
  autonomously

## Consequences

### Positive
- The pipeline always produces a report with at least `top_k` planned ideas,
  even when the research layer underperforms
- Prompt refinement on retry ("focus on underserved niches") gives Layer 1 a
  concrete directive to improve, not just a blind re-run
- `max_retries` is a configurable guardrail against infinite loops and
  runaway costs

### Negative
- Force-passed ideas have scores below the quality threshold; the final report
  may contain weaker ideas than the threshold was designed to filter
- The retry loop resets `ideas` and `reviews` on each iteration (LangGraph's
  `operator.add` reducer accumulates across retries); `synthesize_node` must
  filter by the current iteration's ideas to avoid mixing scores across runs

### Trade-offs
- The fixed prompt suffix ("focus on underserved niches") is a heuristic
  improvement, not a dynamic one. A more sophisticated approach (e.g., having
  an LLM analyze why the previous ideas scored low) would produce better
  refinements but adds cost and complexity for a marginal gain.
