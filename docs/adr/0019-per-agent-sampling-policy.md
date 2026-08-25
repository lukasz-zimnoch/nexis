# ADR-0019: Sampling temperature is a per-agent policy, not a global setting

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-24 |
| **Deciders** | Lukasz Zimnoch |

## Context

Until now `build_llm()` created every client without a temperature, so all
thirteen agents ran at whatever the provider defaults to. Nothing in the code
said what that value was, and nothing stopped it from changing when a provider
changed its default.

Two facts make that unacceptable.

The review panel is a measuring instrument. Its six scores feed the weighted
formula in `ReviewSynthesizer`, and ADR-0018 compares those same scores against
human labels to decide whether the panel is calibrated. A score that moves on
its own is noise inside both uses. The first eval run measured this: the mean
standard deviation over five repeats of one idea was 0.26 points, worst role
0.38. That is small, but it was luck, not policy.

The research layer wants the opposite. `ResearchAgent` exists to return several
ideas that differ from each other, and the retry branch in `graph.py` runs it
again with the previous titles listed as exclusions, asking for ideas unlike
the ones already seen. Narrow sampling works against both.

A single global temperature cannot serve both, and neither can a layer-wide
one: the research layer holds `TrendScanner`, which lists the signals in pages
it is handed, and `NicheValidator`, which answers yes or no. Those two are
instruments sitting in the layer named after invention.

## Decision

We adopt a per-agent sampling temperature, held in `src/nexis/sampling.py`
next to the per-agent model table in `src/nexis/models.py`, and exposed as
`PipelineConfig.agent_temperatures` with `temperature_for(agent_key)`.

Agents fall into three bands:

| Band | Value | Agents |
|---|---|---|
| `MEASUREMENT` | 0.0 | six reviewers, `TrendScanner`, `NicheValidator` |
| `BALANCED` | 0.5 | `MVPArchitect`, `GTMStrategist`, `BusinessPlanComposer`, `DevilsAdvocate` |
| `DIVERGENCE` | 1.0 | `ResearchAgent` |

Four rules hold this in place.

**`temperature` is a required argument.** `build_llm()` and every agent
constructor take it with no default. An agent whose author never thought about
sampling fails to construct, rather than inheriting a value that happens to be
wrong for it.

**The fallback model keeps the temperature.** `_switch_to_fallback()` passes
`self.temperature` to the new client. A timeout must not re-sample a reviewer
at a different setting, which would change the instrument's calibration exactly
when the run is already degraded.

**The two agent tables must describe the same agents.** `PipelineConfig`
rejects a temperature table whose keys differ from the model table, so a
half-finished override fails at startup instead of part-way through a paid run.

**The eval manifest records the temperature per role.** ADR-0018 warns when a
report is built from answers whose prompt or model the code has outgrown. A
changed temperature invalidates a run the same way, so it joins that check. A
manifest written before this ADR records no temperature and makes no claim
about one, so the check skips it.

`None` is a legal temperature and means "send no setting at all". A model that
rejects the parameter can be handled in configuration rather than in code.

## Considered Alternatives

### Option A: One global `temperature` field on `PipelineConfig`

A single number applied to every agent.

**Pros**
- Smallest change: one field, one call site.
- Easy to explain and to override from the environment.

**Cons**
- Cannot express the decision at all. The one setting good for the review panel
  is the setting that makes the retry branch pointless.
- Invites a middling compromise value that suits no agent.

### Option B: Per-layer temperature

Low for review, high for research, medium for planning and output.

**Pros**
- Matches the subgraph boundary already in the code, so it is cheap to wire.
- Expresses most of the contrast.

**Cons**
- Wrong for the research layer, which holds two instruments and one generator.
  `TrendScanner` and `NicheValidator` would be pushed to sample widely for no
  reason.
- The layer boundary is about data flow, not about whether an agent judges or
  invents. Tying sampling to it would tie two unrelated concerns together.

### Option C: Put the temperature in `models.py` beside the model

One table holding both settings per agent.

**Pros**
- One file to open when changing anything about an agent.
- No risk of the two tables drifting apart.

**Cons**
- `models.py` documents each choice with vendor benchmark evidence. Temperature
  evidence is about the shape of the task, not about the model, so the two
  rationales would sit interleaved and read as one.
- The file is already long and is the most-read file in the repository.

The drift risk that made this option attractive is handled instead by the
startup check on the two key sets.

### Option D: Leave the provider default and document it

Write down that the pipeline does not set a temperature.

**Pros**
- No code change.

**Cons**
- The default is the provider's to change, so the document would be a claim the
  repository cannot keep true.
- Leaves the panel's variance outside the project's control while ADR-0018
  publishes numbers derived from it.

## Consequences

### Positive
- The review panel's sampling is now stated, held by a test, and recorded in
  every eval manifest, so the calibration numbers in ADR-0018 describe a known
  configuration.
- The contrast is explicit: the one agent whose job is variety sits at 1.0 and
  every agent that judges sits at 0.0. A reader can see the policy in one table.
- Adding an agent forces a sampling decision, because the config refuses to
  start until both tables agree.

### Negative
- Thirteen constructors and every test that builds an agent now pass an extra
  argument. The change is mechanical but wide.
- A model that rejects a temperature setting fails every call until somebody
  maps it to `None`. The failure is loud, but it is a new way to break a run.

### Trade-offs
- The numbers inside a band are a judgement call, not a measured optimum. What
  the evidence supports is the ordering. Picking 0.5 over 0.4 for the planning
  agents is taste, and the module says so rather than implying a measurement.
- Lower temperature narrows the spread; it does not remove it. A provider can
  still return two different answers at 0.0. Every claim about this change is
  phrased as reduced variance, never as a repeatable result.
- The variance already measured at 0.26 points before this ADR, so pinning the
  reviewers to 0.0 is unlikely to move that number much. The value here is
  control and disclosure, not an expected drop. Any before-and-after claim
  needs a second collected run to stand on.
