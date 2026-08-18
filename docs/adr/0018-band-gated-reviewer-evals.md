# ADR-0018: Band-Gated Reviewer Evals

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-18 |
| **Deciders** | Łukasz Zimnoch |

## Context

Six reviewers score every idea from 1 to 10, and ADR-0010 turns those scores
into the weighted number that decides which ideas reach Layer 3. The weights and
the formula were tested. The scores feeding them were not. Nothing in the
project could answer either of the two questions that matter about a judge:

1. Does a reviewer agree with a human about an idea it has never seen?
2. Does a reviewer agree with itself when asked the same question twice?

The second question is not a detail. The pipeline treats a score as a
measurement, and a measurement that moves three points between runs cannot
support a threshold set at two decimal places.

Three properties of the problem shaped the answer.

A reviewer score has no ground truth. Nobody knows what the market analyst
"should" say about a business that was never built. A human can say an obviously
commoditised idea must not score 8 on moat, and cannot say whether it is a 2 or
a 3.

The reviewers are the thing under test, so they must run on their real models. A
cheaper stand-in calibrates a configuration that nobody ships.

The calls cost money and the analysis does not. Every change to a metric, a
threshold or a label is free if the raw answers are on disk, and costs the whole
run again if they are not.

## Decision

Evals live in `nexis/evals`, gate on bands, and split paid collection from free
analysis. Five parts:

1. **A frozen, hand-labelled dataset** (`tests/evals/dataset.jsonl`). Fifteen
   ideas, 67 labels. Each label is a `ScoreBand` for one (idea, role) pair, plus
   written reasoning for the whole idea. Layer 1 never runs during an eval, so
   the reviewer is the only variable, and no search API is called.

2. **The gate reads the band, never an exact value.** A score inside the band
   is correct. The error measure is the distance to the nearest edge of the
   band, which is zero inside it. Each role must land inside its bands at a
   minimum rate, which defaults to 70%.

3. **Partial labels.** A role carries a band only where the label writer holds
   a firm opinion. The panel still reviews every idea with all six roles,
   because the variance report needs the whole panel, but an unlabelled pair
   does not gate. Forcing a band onto all ninety pairs would invent opinions and
   then measure agreement with them.

4. **Collection and analysis are separate commands.**
   `python -m nexis.evals collect` calls the models and appends every answer to
   `reviews.jsonl` as it arrives. `python -m nexis.evals report` reads that
   directory, calls nothing, and exits non-zero when a role misses the gate. A
   manifest is written before the first call, so a run that dies halfway still
   leaves an analysable directory.

5. **A spend guard in code.** The collector projects the cost from the price
   table in ADR-0017 and refuses to start above a limit passed on the command
   line. A model with no price stops the projection rather than counting as
   free. The manifest records the projected and the measured cost side by side.

The workflow that runs the evals in CI is manual only. It never fires on a push
or a pull request.

Two things do not need an LLM and are tested without one. The weighted formula
of ADR-0010 gets a frozen panel and exact expected scores in
`tests/evals/scoring_regression.json`. The eval machinery itself gets unit tests
with a stand-in reviewer. Both run in the ordinary CI job.

## Considered Alternatives

**Gate on an exact expected score.** Rejected. It measures agreement with one
person's arbitrary choice between a 2 and a 3, so it fails on correct answers
and gets silenced within a week.

**Gate on the mean score per role instead of per idea.** A role could hit its
target mean while scoring every single idea wrongly, in opposite directions.
Rejected: the mean hides the errors that matter.

**Use an LLM as the judge instead of human labels.** Cheaper to scale and it
removes the labelling work. Rejected here because the judge would come from the
same model family as the reviewer under test, so the two share their blind
spots, and because the failure this eval exists to catch is exactly a model
being confidently wrong.

**Run the whole pipeline and score the final report.** More realistic, and
useless as a measurement: Layer 1 generates different ideas every run, so
nothing is held constant and no difference can be attributed to the reviewer.

**Store the collected answers in the repository as golden files.** Rejected.
The answers are not deterministic, so a committed set would change on every run
and turn the eval into a diff nobody reads.

## Consequences

The labels are one person's judgement, so the calibration number measures
agreement with that person and not correctness. The dataset keeps the written
reasoning for every idea so a disputed miss can be argued about, and a label
that loses the argument should be changed.

The dataset ages. It names real competitors and real market conditions, and an
idea that is commoditised today was not two years ago. A stale label reads as a
reviewer regression.

A hit rate on 9 to 14 labelled ideas per role is a small sample. One miss moves
a role by about ten points, so the gate catches a reviewer that is badly wrong
and not one that drifted slightly.

Variance needs repeats, and repeats multiply the cost. A five-repeat run over
the panel is five times the price of a calibration run, which is why the spend
guard exists and why the workflow is manual.

The eval measures the reviewer alone. A pass says nothing about the ideas Layer
1 produces or about the plans Layer 3 writes.

The gate threshold is a judgement call with no principled value behind it. It
starts at 70% and should move once real runs show what a healthy panel scores.
