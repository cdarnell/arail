# Vision: KB incremental persistence — close the agent → KB → chat retrieval loop

**Date:** 2026-05-01
**Product:** arail
**Wedge size:** one sprint

## User

A solo ARAIL operator running the `min` tier on their own laptop in
`airgapped` mode. They've kicked off an Autoresearch run, walked away,
come back an hour later, and opened the Chat tab to ask the lab "what
did the Researcher find about X?" Today the answer is "nothing useful"
— the Researcher's notes are on disk under `lab/pkb/`, but `pkb.search()`
doesn't see them until the operator manually triggers a full rebuild.
The operator is the same person whose mental model is "the agents are
my coworkers and the KB is our shared memory"; right now that memory
is write-only from the agent side.

## Problem

The Chat ↔ KB retrieval loop is broken at the write step. Agent write
helpers (`write_agent_research`, `write_agent_experiment`,
`write_agent_experiment_rollup`) persist markdown to the filesystem
but do not update the LanceDB index that chat retrieval queries. The
result: the lab looks like it's working (agents are running, files
appear under `lab/pkb/`) but the value the operator expected — asking
the lab what its agents have learned — silently fails. This violates
the local-first promise: the data is right there, just not findable.
Manual full rebuilds work but are expensive and require the operator
to know to run them, which defeats the "walk away and come back"
mode the Autoresearch surface is built around.

## Win condition

Pre-committed, measurable thresholds:

1. **Latency:** an agent write becomes findable via `pkb.search()` in
   under 10 seconds, with no human intervention. Measured by a test
   that calls a write helper, polls `pkb.search()` for the new
   content, and asserts retrieval within the budget.
2. **Durability:** after a write + process kill + cold restart, the
   same query still returns the new content. No re-derivation of the
   full corpus on cold start; the existing index is reused when
   schema-compatible.
3. **End-to-end witness:** a scripted scenario — start lab, ask
   Researcher to investigate a topic, wait for one experiment write,
   open Chat, ask "what did you find about $TOPIC" — returns a
   response grounded in the agent's actual write within one session.
   No manual rebuild step in the script.
4. **No new long-lived service** introduced; the LanceDB cache
   directory and on-disk layout remain at `lab/pkb/.cache/lancedb/`.

If thresholds 1, 2, and 3 hold and constraint 4 is preserved, we
shipped the right thing.

## Wedge

The sprint task already names it: incremental upsert into LanceDB at
the `write_agent_*` boundary, with an in-process debounce/coalescer to
batch bursts. No new service, no UI changes, no schema migration tool.
The wedge is the smallest change that proves "the loop closes": one
agent writes, chat finds it. Everything beyond that — KB → fine-tune,
KB → system-prompt preamble, wiki-rebuild rewrite, /knowledge UI work —
is explicitly out of scope and deferred.

## Disconfirming evidence

The hypothesis behind this sprint is that **agents produce notes the
operator would actually want to retrieve**. If the agents almost never
write content useful to a chat query — because Researcher rollups are
too generic, or because Pip and SRE have nothing chat-shaped to say —
then closing the loop closes nothing; we'd have built a fast pipe
between two empty rooms. The disconfirming signal: after this ships,
run the lab for one week of normal use; if the operator never gets a
chat response that visibly cites an agent-written page (no
provenance-linked answer, no "the Researcher noted that..." retrieval
hit), the wedge proved the wrong thing and the next sprint is about
agent write quality, not write plumbing. Pre-commit: at end of week
one, count chat sessions with agent-page-grounded answers; if zero,
we revisit.

## Displacement

The user-visible behavior change is that `pkb.search()` results will
include agent-written pages without a manual rebuild. There are two
risks of disruption: (a) chat retrieval starts surfacing
half-baked agent drafts that previously were invisible until the
operator chose to rebuild — operators who used "no rebuild yet" as an
implicit quality gate lose that gate; (b) the in-process coalescer
adds work to the write path, so an agent doing a tight write loop
might see slightly higher latency on each helper call. Neither is a
regression of a documented contract — manual rebuild stays available;
write helpers were never speed-contracted — but both should be called
out in the BUILD_LOG so the architect can decide whether to gate
agent-page surfacing behind a "draft / published" flag in a follow-up.
Within the QuKaiZen portfolio, this sprint displaces attention from
aerollm and qukaizen for one sprint; that's acceptable because the
arail Chat surface is the product wedge that aerollm will eventually
plug into, and a broken retrieval loop undermines every future demo.

## Recommended next step

**Proceed to `/architect` design with this VISION.md as the spec.**
The wedge is small, the win condition is measurable in a single test
script, and the disconfirming evidence is pre-committed. The architect
should pick the upsert / coalescer / cold-start design; the win
condition above is what they're designing against.
