# Frozen eval data

This directory holds data, not tests. The tests that read it are in
`tests/test_evals/` and `tests/test_scoring_regression.py`.

## `dataset.jsonl`

One labelled idea per line: a `BusinessIdea`, the score band each reviewer role
is expected to land in, and the reasoning behind those bands.

A label is a band and never a single number. Two people who agree that an idea
is commoditised still disagree on whether that is a 2 or a 3, so the band is the
strongest claim the label can honestly make. The gate reads the band.

A role carries a band only where the label writer holds a firm opinion. The
panel still reviews every idea with all six roles, because the variance report
needs the whole panel, but an unlabelled role does not gate.

The labels are one person's judgement about businesses that were never built.
They measure whether a reviewer agrees with that person, which is not the same
as measuring whether the reviewer is right. Read the numbers with that in mind,
and reread `label_rationale` before you trust a miss.

### What the moat labels ask for

The moat bands split on whether an idea's structure builds defensibility as the
business matures, not on whether it holds any today. None of these businesses
exists, so none of them holds a moat now, and a reviewer that scores the present
state puts every idea near the floor.

Five label rationales carry the distinctions the bands rely on, and a reviewer
that misses any one of them will disagree with the labels in a readable way:

- A regulatory barrier counts when this business must pay it to sell at all, and
  not when somebody else's compliance is the product being sold.
- A network effect that restarts in each new city or segment is weak, however
  real it is inside one.
- Where an established competitor already holds the position, the moat is theirs.
- Operational data that piles up from ordinary use is a moat even when it builds
  slowly and the software around it is dull.
- Public source material does not cancel that accumulation. The question is
  whether the assembled and maintained record can be bought off the shelf, not
  whether the raw input is secret.

The bands are deliberately not symmetric around the middle. Most of these ideas
are commodity software, so the low bands carry more of the set than the high
ones, and only one idea claims the top band.

To change a label, edit the line and run `pytest tests/test_evals/test_dataset.py`.
The guards there check that the file stays large enough, that every role keeps
enough bands to read a hit rate from, and that no band collapses to one point.

## `scoring_regression.json`

A frozen panel of reviews and the exact scores and ranking the weighted formula
must produce from them. The expected values were computed from the formula in
the specification, not by running `ReviewSynthesizer`, so the file checks the
code against the specification instead of against itself.

Changing the weights, the formula, the threshold or `top_k` will fail
`tests/test_scoring_regression.py`. That is the point. Update the frozen values
in the same commit as the change, and the diff shows what moved.
