# Horizon watch — the lab's agents on the lookout

> Shipped. The world-generic scouting loop: the mounted World declares what
> matters, the Librarian watches it, changes come to YOU as reviewable
> findings. No World-specific code anywhere in the loop.

## What it is

Every sealed World carries an `agenda.json` (`dac.world-agenda/v1`) — watches
derived from its `spec.knowledge_sources`. The AI World declares arxiv.org;
the Video Games World declares Wikipedia and PC Gaming Wiki. Until now no
code read that file.

Now the Librarian does. On its tick (every ~30 minutes, quiet-hours- and
job-halt-aware), `arail.research.agenda_watch` checks each URL-shaped feed
the mounted World declares — at most once per `ARAIL_SCOUT_WATCH_HOURS`
(default 24) per feed — and when a source's content has changed since the
last look, it stages a **finding**: a markdown file under
`lab/pkb/sources/scout/` that appears in the `/dac` Compiled-KB review queue,
labeled `scout_finding`, with the watched URL as its provenance.

The point: mount a World and your lab naturally keeps watch over that
World's horizon. A new development your domain cares about — the next MCP,
a new driver release — surfaces as "the agents noticed this; want it in
your knowledge base?" You approve or reject. Nothing is adopted for you.

## The honesty rails, in enforcement order

1. **Airgapped labs never fetch.** `is_airgapped()` short-circuits the whole
   pass before consent or network machinery is touched. `LAB_MODE=airgapped`
   is the default and stays sacred.
2. **Consent per feed, durable, never nagged.** Each feed URL needs an
   approved `ConsentStore` record. The first hybrid-mode pass files the
   request; the operator approves or denies it in the portal. Pending waits;
   denied disables the feed. A scheduled agent never self-approves.
3. **URLs are verbatim from the sealed agenda.** `agenda_watch` never
   composes a URL — feeds that aren't URL-shaped (e.g. "vendor documentation
   (NVIDIA, AMD, …)") are skipped, not guessed. No user, hardware, or game
   data can leak into an outbound request because no request is ever built
   from runtime data. Every fetch is audited to `lab/data/egress.jsonl`.
4. **Findings are pending, never approved.** A change writes a
   hash-suffixed file into the review queue. Approving one snapshot never
   auto-approves the next; superseded unreviewed findings are pruned so the
   queue holds one live finding per feed.
5. **First look is a baseline.** The initial fetch of a feed records a
   content hash and stages nothing — findings only ever mean "this changed
   since your lab last looked."

## Where things land

| Artifact | Path |
|---|---|
| Watch state (per-feed hash, cadence, consent id) | `lab/data/agenda-watch.json` |
| Findings awaiting review | `lab/pkb/sources/scout/<world>-<node>-<feed>-<hash8>.md` |
| Egress audit line per fetch | `lab/data/egress.jsonl` |
| Consent records | `lab/data/consent/` |

## Tuning

- `ARAIL_SCOUT_WATCH_HOURS` — per-feed check interval (default 24).
- Feeds come from the mounted World's sealed `agenda.json`; to watch more or
  different sources, forge the World with different `knowledge_sources`.
- The loop is hosted by the Librarian agent; pausing the Librarian (or
  halting jobs, or quiet hours) pauses the watch.
