# ADR-0016: Trust Boundary for Web Content in Prompts

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-17 |
| **Deciders** | Łukasz Zimnoch |

## Context

Layer 1 puts text from the public web into prompts. Two paths exist:

- `ResearchAgent` searches with Tavily and builds `web_search_context` from the
  title and the body of each result (`agents/research.py`).
- `TrendScanner` reads HackerNews, ProductHunt and Reddit through site-scoped
  Tavily queries, then passes the raw hits to the LLM (`tools/trends.py`).

Every one of these sources carries text that a stranger wrote. Anyone who
publishes a page, a comment or a post can therefore write into a Nexis prompt.
That is a prompt injection: hostile text placed in a prompt so the model reads
it as an instruction instead of as data.

Before this decision the text arrived with no boundary of any kind. It was
concatenated straight into the human message, next to our own instructions, in
the same voice. Nothing told the model which part it must obey and which part it
must only analyze. The size was also open. `max_results=5` caps the number of
results, not their length, so one long page could fill the context window.

The pipeline runs unattended, which raises the value of a takeover: nobody reads
the intermediate state, so a poisoned idea travels through review, planning and
into the final report. Two facts limit the damage. These agents bind no tools,
so the model cannot act on an instruction, and the prompt holds no credentials.
The realistic loss is a report that serves the attacker, not stolen data or
remote code execution.

## Decision

We treat text that a tool fetched from the web as untrusted data, and we mark it
as such at the point where it enters a prompt.

`src/nexis/untrusted.py` owns the boundary:

- `sanitize_untrusted(text)` removes both block markers and control characters,
  then cuts the text to `MAX_UNTRUSTED_CHARS` (500) and notes the cut. It runs
  per result, so one page cannot crowd out the others.
- `wrap_untrusted(text)` puts the text between `<<<UNTRUSTED_WEB_CONTENT>>>` and
  `<<<END_UNTRUSTED_WEB_CONTENT>>>`. It removes markers again, so the block ends
  where the code says it ends even if a caller forgets to sanitize.
- `UNTRUSTED_DATA_RULE` is one paragraph appended to the system prompt of every
  agent that receives such a block. It names both markers and states that the
  text between them is data to analyze, never instructions to follow.

The line runs as follows: **what a tool fetched is untrusted, what an agent
produced is pipeline data.** So the raw Tavily hits are marked, while the
`list[TrendSignal]` that `TrendScanner` returns is not, because a Pydantic schema
already constrains its shape.

`TrendScraperTool` also caps `TrendSignal.signal`, because that string is web
text that Firestore stores and the report renders.

## Considered Alternatives

### Option A: A sentence in the system prompt, with no markers

Tell each agent that web content may be hostile and leave the text as it is.

**Pros**
- No new module, no change to prompt construction

**Cons**
- The model cannot tell where the web content starts and stops, so the
  instruction has nothing to point at
- Leaves the size open, so one long page still fills the context window

### Option B: Sanitize inside the tools

Clean the text in `tools/search.py` and `tools/trends.py`, so every caller gets
safe values.

**Pros**
- One place to change, and it covers future callers by default
- Keeps the agents free of security code

**Cons**
- Mutates data used for other purposes. A cut URL becomes a wrong link in the
  report
- Does not mark anything. The prompt still merges web text with our
  instructions, which is the actual defect

### Option C: A fresh random marker for each call

Generate a nonce (a value used once) per call and build the markers from it, so
the text cannot name a marker it has never seen.

**Pros**
- Strongest defence against a forged marker, because the attacker cannot guess
  the value

**Cons**
- The prompt text changes on every call. That breaks a stable prompt hash, which
  the planned cost and version telemetry needs
- Harder to read a log or a saved prompt when the markers differ every time
- Marker removal already denies the forgery, at no cost

### Option D: A classifier agent in front of the research agent

Add an LLM call that reads each search result and rejects hostile ones.

**Pros**
- Catches text that carries no marker and no obvious command

**Cons**
- One extra LLM call per result, so cost and latency grow with search volume
- The classifier reads the same hostile text, so it inherits the same weakness
- A judgment on "is this hostile" is not reproducible between runs

## Consequences

### Positive
- Web text now arrives inside a named block, and every prompt that carries such
  a block also carries the rule that governs it
- A hostile page cannot close the block early, so it cannot make its text look
  like our instructions
- One number, `MAX_UNTRUSTED_CHARS`, bounds what a single result costs in the
  context window
- The boundary is testable without an API key. `tests/test_untrusted.py` covers
  the primitives, and `tests/test_agents/test_research.py` sends a payload that
  tries to close the block and take over the task

### Negative
- The rule is a convention, not a control. A model can still obey text inside
  the block, and no test can prove it will not. This lowers the chance of a
  takeover; it does not remove it
- The cap drops detail from long pages, so an idea may rest on less evidence
- Both markers cost tokens on every research call

### Trade-offs
- The boundary stops at the first agent. If the research LLM copies hostile text
  into a `BusinessIdea` field, that text travels to the review and planning
  layers as pipeline data, with no marker. The schema constrains its shape and
  each agent's system prompt states its own task, but nothing marks the origin.
  To mark every field that came from the web, the state models need a per-field
  source, which is a larger change than this one. It stays open on purpose.
- 500 characters per result is a judgment, not a measurement. It holds a
  headline and a snippet, which is what the current prompts use. A layer that
  needs full page text must raise the limit for itself and say why.

<!--
Reminder: once this ADR is accepted, its content becomes append-only.
Do not rewrite Context/Decision/Consequences to reflect later changes —
write a new ADR that supersedes this one and flip the Status field here.
See docs/adr/README.md → "ADRs are append-only".
-->
