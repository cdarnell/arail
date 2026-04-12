# Lab PKM — Personal Knowledge Management

Your lab's brain. Everything the AI discovers, everything you capture, everything
you learn — organized and searchable from one place.

## Folder Structure

```
lab_pkm/
├── inbox/              ← Drop anything here. PDFs, URLs, notes, images.
│                         The ingest script picks it up and files it.
│
├── sources/            ← Raw material. Fetched papers, articles, datasets.
│   ├── papers/         ← Research papers (PDF, text extracts)
│   ├── articles/       ← Web articles, blog posts, reference material
│   ├── datasets/       ← CSV, JSON, raw data files
│   └── bookmarks.md    ← Quick-save URLs with one-line descriptions
│
├── agents/             ← What the AI built. Hands off — agents write here.
│   ├── research/       ← Researcher agent findings, reports, hypotheses
│   ├── experiments/    ← Experiment logs, observations, analysis
│   ├── synthesis/      ← Cross-experiment insights, patterns the AI found
│   └── recommendations/← Actionable suggestions from the AI
│
├── notes/              ← Your notes. Write freely.
│   ├── journal.md      ← Running lab journal — date-stamped entries
│   ├── ideas.md        ← Quick ideas, hunches, what-ifs
│   └── scratch/        ← Throwaway working notes
│
├── compiled/           ← Polished outputs. The good stuff.
│   ├── reports/        ← Final research reports (Markdown)
│   ├── summaries/      ← Topic summaries compiled from sources + agent work
│   └── exports/        ← Ready-to-share artifacts (HTML, PDF)
│
├── inference/          ← Karpathy-style model workspace.
│   ├── prompts/        ← Your saved prompts — what worked, what didn't
│   ├── completions/    ← Raw model outputs worth keeping
│   └── chains/         ← Multi-step reasoning traces
│
└── index.md            ← Auto-generated knowledge map (updated by compile)
```

## Quick Start

### Drop something in the inbox
```bash
# Copy a file
cp ~/Downloads/interesting-paper.pdf ~/lab_pkm/inbox/

# Save a URL
echo "https://example.com/great-article — crop rotation study" >> ~/lab_pkm/inbox/links.txt

# Quick note
echo "$(date +%Y-%m-%d) Thought: try lower nitrogen ratio" >> ~/lab_pkm/inbox/quick.txt
```

### Ingest (process inbox → sources)
```bash
./scripts/pkm-ingest
```
Moves files from `inbox/` into the right subfolder in `sources/`, extracts
text from PDFs, fetches URLs and saves readable content, timestamps everything.

### Compile (sources + agents → compiled)
```bash
./scripts/pkm-compile
```
Scans `sources/`, `agents/`, and `notes/` to build:
- An updated `index.md` (full knowledge map with links)
- Topic summaries in `compiled/summaries/`
- Merges agent research with your notes into coherent reports

### Browse (see what you have)
```bash
./scripts/pkm-browse
```
Interactive terminal viewer. Shows your knowledge tree, recent additions,
agent activity, and lets you search across everything.

## How Agents Use This

The researcher agent writes to `agents/` automatically:
- After each research cycle → `agents/research/{goal_id}_report.md`
- Experiment logs → `agents/experiments/{exp_id}.md`
- Cross-cutting insights → `agents/synthesis/`
- "You should try this" → `agents/recommendations/`

**You own the PKM.** Agents can write to `agents/` but never touch your
`notes/`, `sources/`, or `compiled/` folders. The compile step merges
everything together.

## Tips

- **Journal daily.** Even one line. `echo "$(date +%Y-%m-%d) ..." >> notes/journal.md`
- **Tag with hashtags.** Use `#topic` anywhere — the compile script indexes them.
- **Star important items.** Prefix lines with `⭐` to mark key findings.
- **Review `agents/recommendations/`** — that's where the AI tells you what to do next.
- **The inbox is forgiving.** Throw anything in. The ingest script figures out where it goes.
