---
title: Vetting a Source
id: vet-source
name: vet-source
domain: curation
version: 1.0.0
tags: [skill, curation, sources, evidence]
when_to_use:
  - Before adding a new URL or paper to the knowledge base
  - When a finding hinges on a single citation
  - When a claim feels too clean or too convenient
when_not_to_use:
  - For obvious primary sources (ArXiv abstracts of well-known papers,
    GitHub repos of named projects you've already reviewed)
  - For internal lab notes (those are observations, not sources)
---

# Vetting a Source

Five questions to ask before a source enters the lab. The order
matters — answer them in sequence and stop early if any fails.

## 1. Who is the publisher?

Look for: a named author with a track record in the field, an
institutional homepage, an ArXiv affiliation, an editor with peer
review responsibilities. Anonymous SEO blogs and content farms get
declined here.

If you can't identify the publisher in 60 seconds, the source isn't
ready for the KB. Drop it in `lab/pkb/inbox/` for later review
instead.

## 2. When was it published?

Recency depends on the topic:

- **Inference engine performance** — months matter (the stack moves
  fast). Anything older than ~12 months should be treated as
  historical context, not current advice.
- **Architectural concepts** — years are fine. The original
  Transformer paper from 2017 is still load-bearing.
- **Tooling versions** — check that the version they reference is
  one you actually use; "fast in v0.4" doesn't help if you're on v2.x.

## 3. What is the conflict of interest?

Vendor blogs about their own product, framework maintainers
benchmarking against rivals, recruiters writing "best of" lists —
each has a thumb on the scale. Note the bias in the SOURCE.md
metadata so future readers can weigh it.

A source with a known bias is fine to keep — just label it.
A source pretending to be neutral while obviously biased gets
declined.

## 4. Does it cite primary evidence?

Best: links to the dataset, the runnable code, or the original
measurement. Good: links to a paper that links to those. Bad:
"recent studies have shown" with no citation.

If a finding only exists at second-hand, get the primary source or
note "not yet verified" in the KB entry.

## 5. Has someone independent reproduced it?

For benchmarks especially. A single team's tokens/sec number is a
data point, not a fact. Two independent reproductions on different
hardware = signal. None = anecdote.

When you can't find independent reproduction, ship the source but
mark its claim as "single-source — needs reproduction."

## What "decline" means

Decline doesn't mean delete. Move the source to
`lab/pkb/inbox/declined/` with a one-line reason in the filename
(`<original>.declined-no-author.md`). That preserves the trail in
case someone else wants to argue the call.
