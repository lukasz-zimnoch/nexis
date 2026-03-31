# ADR-0010: Deterministic Weighted Scoring Without LLM

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-03-29 |
| **Deciders** | Łukasz Zimnoch |

## Context

After six reviewer agents each assign a score (1–10) and a confidence (0–1) to
every idea, the pipeline must rank ideas and select the top K to proceed to
planning. The ranking mechanism must be:

- **Auditable**: it must be possible to explain exactly why idea A ranked above
  idea B
- **Reproducible**: the same reviews must always produce the same ranking
- **Configurable**: different use cases may weigh certain reviewer roles more
  heavily (e.g., a technical co-founder might weight technical feasibility
  higher than market size)

## Decision

`ReviewSynthesizer` in `agents/reviewers.py` ranks ideas using a pure Python
weighted average formula (no LLM call):

```
score(idea) = sum(weight_i × score_i × confidence_i) / 10
```

where `weight_i` is the configurable weight for reviewer role `i`
(`config.reviewer_weights`), `score_i` is the raw score (1–10), and
`confidence_i` is the reviewer's self-reported confidence (0–1).

Default weights are defined in `config.py`:

| Role | Weight |
|------|--------|
| market | 0.25 |
| technical | 0.20 |
| financial | 0.20 |
| moat | 0.15 |
| risk | 0.10 |
| ai_resilience | 0.10 |

Ideas are ranked by descending score; those above `config.score_threshold`
(default 0.55) and within the top `config.top_k` (default 3) become `top_ideas`.
Failed reviews (`failure_reason is not None`) are excluded from the weighted sum.

## Considered Alternatives

### Option A: LLM-Based Meta-Reviewer

Add a 14th agent (a "meta-reviewer") that reads all six reviews and decides the
ranking.

**Pros**
- Can incorporate qualitative nuance that a numeric formula cannot capture
- Can reason about review inconsistencies (e.g., when reviewers directly
  contradict each other)

**Cons**
- Non-deterministic: two identical sets of reviews can produce different
  rankings across runs due to LLM sampling
- Adds latency and cost for an extra LLM call at a critical decision point
- Hard to audit: "the LLM decided" is not a satisfying explanation for why one
  idea was selected over another

### Option B: Simple Average (Unweighted)

Compute `mean(score_i × confidence_i)` across all reviewers, ignoring weights.

**Pros**
- Even simpler formula; fewer configuration parameters

**Cons**
- Treats a market analyst's score identically to a risk assessor's; not
  appropriate when different dimensions have different importance for the use case
- Eliminates the ability to tune ranking behavior without code changes

### Option C: Elo / Pairwise Ranking System

Compute a ranking by having each idea "compete" against others in pairwise
comparisons, either via a formula or via an LLM judge.

**Pros**
- Better at distinguishing ideas with similar absolute scores
- Pairwise comparison is a well-studied ranking technique

**Cons**
- Requires O(N²) comparisons (or LLM calls) for N ideas; N=8 means 28 pairs
- Formula-based Elo is hard to interpret; LLM-based introduces non-determinism
- Overkill for N=8 ideas where a simple ranking suffices

## Consequences

### Positive
- The formula is one line of code; any engineer can verify the ranking by hand
- `config.reviewer_weights` makes the weighting scheme explicit and
  configurable per deployment without code changes
- No extra LLM calls at the ranking step; `ReviewSynthesizer.synthesize()` runs
  in microseconds

### Negative
- Confidence is self-reported by the reviewer LLM; a model that always returns
  `confidence=0.9` will have its scores inflated relative to a more calibrated
  model
- The formula treats a score×confidence product linearly; it cannot capture
  veto scenarios (e.g., "if risk score < 3, reject regardless of other scores")

### Trade-offs
- Configurable weights are powerful but require calibration. The default weights
  (market 25%, technical 20%, financial 20%) reflect a balanced view suitable
  for most idea types but may need tuning for niche domains (e.g., deep-tech
  ideas where technical feasibility should dominate).
