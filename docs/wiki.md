# Wiki — documentation as code

OGLab ships with a **self-curating wiki** that lives at
<http://127.0.0.1:8080/wiki> once the portal is running. Dump a file,
drop a note, let an agent run — the wiki compiles the PKB tree into
a navigable knowledge base with wikilinks, backlinks, tags, and a
knowledge graph.

The wiki is also **self-documenting**: when you rebuild it, OGLab
scans its own source (Python modules, shell scripts, compose overlays,
hand-written guides, `.env.example`) and generates a wiki page for
each one. The first time you open `/wiki`, you're reading docs about
the lab that the lab wrote about itself.

## Two kinds of pages

| Kind | Where | How it got there |
| --- | --- | --- |
| **User content** | `lab/pkb/{notes,sources,agents,compiled,inference}/` | You wrote it, ingested it, or an agent produced it |
| **Auto-generated docs** | `lab/pkb/compiled/docs/` | Rebuilt from the repo source by `oglab.docgen` |

Auto-generated pages are **always** confined to `compiled/docs/`. The
docgen step will never overwrite files in `notes/`, `sources/`, or
`agents/` — those are yours.

## Writing a page

Pages are plain markdown with optional YAML frontmatter:

```markdown
---
title: Raising peanuts in zone 7
section: notes
tags: [farming, peanuts, zone7]
aliases: [peanut-farming, peanuts]
---

# Raising peanuts in zone 7

I checked [[scheduler]] to figure out when to run the soil simulation —
active hours for quick observations, heavy hours for the full run.

## Soil pH

Target 6.0-6.5. See [[researcher]] for how the agent tracks this.

#soil #regional
```

Every square-bracketed `[[target]]` becomes a hyperlink in the rendered
page. Targets resolve to page slugs by matching:

1. Exact slug (`agents/research/2026-04-14-report`)
2. Slugified title (`raising-peanuts-in-zone-7`)
3. Slugified alias (from frontmatter `aliases:`)

If the target doesn't resolve, you get a red **missing** link — the
page still renders fine, but you know a link is waiting to be filled.

### Wikilink syntax

- `[[target]]` — plain link
- `[[target|display text]]` — custom label
- `[[target#heading]]` — anchor link to a heading
- `[[target#heading|display text]]` — combined

### Tags

Tags come from two places:

1. Frontmatter `tags: [a, b, c]` — the source of truth.
2. Inline `#hashtags` in the body — parsed and merged into the tag
   list so your notes stay readable in any markdown editor.

Click any tag on the wiki landing page to see every page carrying
that tag.

## The knowledge graph

Every page is a node; every resolved wikilink is an edge. Visit
<http://127.0.0.1:8080/wiki/graph> for a full-screen force-directed
view (same Canvas renderer the system graph uses — zero JS deps,
pan/zoom/drag). Click a node to see its backlinks, tags, and a
"Open page" button.

Page colors on the graph map to sections:

| Section | What's in it |
| --- | --- |
| `sources` | Papers, articles, datasets, bookmarks the user ingested |
| `agents` | Research reports, experiments, synthesis, recommendations written by agents |
| `notes` | Your own journal, ideas, scratch |
| `compiled` | Polished reports, summaries, exports |
| `docs` | Auto-generated from the repo source (modules, scripts, guides) |
| `inference` | Saved prompts, completions, chains |

## Building and rebuilding

The compiler runs automatically in three situations:

1. **First request to `/wiki`** when no manifest exists — the portal
   builds on demand.
2. **Click "Rebuild" on the landing page** — POSTs to
   `/api/wiki/rebuild`, emits a success event to the activity log.
3. **CLI** — `python -m oglab.wiki build` (the Phase 4 commit adds
   `./oglab wiki build` as a dispatcher shortcut).

The Python CLI directly:

```bash
python -m oglab.wiki build --repo-root .
python -m oglab.wiki info
```

The `--repo-root .` flag enables the docgen pass. Leave it off and
only user content is compiled — useful if you just want to pick up
a new note without re-scanning the repo.

## How fast is it?

A fresh build over the stock blueprint (5 seed pages + 23 Python
modules + 8 shell scripts + 2 compose overlays + 8 guides + env
reference) runs in ~36 ms on an M3 Mac. The manifest cache means
subsequent page loads never recompile unless you ask them to.

## Adding documentation just by writing good docstrings

Because docgen reads Python module docstrings via `ast` (no imports,
no runtime coupling), the fastest way to improve the wiki is to
write better module-level and function-level docstrings in
`src/oglab/`. Anything you write there will turn into a wiki page
the next time you rebuild. Same for the header comment blocks in
`scripts/*.sh` — they become the Overview section of each script's
wiki page.

## Obsidian compatibility

The wiki markdown is fully Obsidian-compatible (frontmatter +
`[[wikilinks]]` + `#tags`), so power-users can open the `lab/pkb/`
folder directly in Obsidian and get the same graph, same links,
same tags. OGLab writes to `lab/pkb/` and Obsidian reads it — no
import step.

## Where files live

```text
lab/pkb/
├── inbox/                     # drop zone — pkb-ingest sorts from here
├── sources/                   # sorted user-ingested material
│   ├── papers/ articles/ datasets/
│   └── bookmarks.md
├── agents/                    # written by the researcher agent
│   ├── research/ experiments/
│   └── synthesis/ recommendations/
├── notes/                     # your own markdown
│   ├── journal.md ideas.md scratch/
├── compiled/
│   ├── reports/ summaries/ exports/
│   └── docs/                  # ← auto-generated from repo source
│       ├── modules/           # Python module pages
│       ├── scripts/           # shell script pages
│       ├── compose/           # compose overlay pages
│       ├── guides/            # hand-written docs (README, CONTRIBUTING, docs/*.md)
│       └── configuration/     # .env.example reference
├── inference/                 # saved prompts, completions, chains
├── index.md                   # legacy flat index from oglab.pkb.compile_index
└── .wiki-cache/
    └── manifest.json          # compiled wiki state, not committed
```

## Out of scope

- **Video/audio ingest.** That's [Open Notebook](../compose/open-notebook.yml)'s
  job — run the compose overlay, let it transcribe, and drop the
  markdown exports into `lab/pkb/inbox/`. The wiki picks them up
  from there.
- **In-browser editing.** Edit pages in your IDE (code-server is
  right there in the lab) and click Rebuild. The wiki is a reader,
  not a WYSIWYG editor.
- **Semantic search.** The current search is hybrid title/tag/body
  substring. Embedding-based search is a stretch goal.
- **Transclusion** (`![[file.png]]`). Not wired up in v1.
