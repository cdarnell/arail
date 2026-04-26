# Status Digest blueprint

Monday-morning brief generator. Reads the past 7 days of calendar
entries, doc edits, and message threads; produces a single
prioritized page covering what shipped, what's blocked, and what
needs attention.

## Quick start

```bash
./arail blueprint create my-digest --from status-digest
./arail blueprint apply my-digest
# Edit instances/my-digest/.env to point at your data sources.
```

## Agents this blueprint expects

| Agent          | Status        | Where to implement                       |
|----------------|---------------|------------------------------------------|
| `researcher`   | ✅ exists     | `src/arail/agents/researcher.py`         |
| `summarizer`   | ⏳ aspirational | `src/arail/agents/summarizer.py` (TBD)  |
| `scheduler`    | ⏳ aspirational | `src/arail/agents/scheduler.py` (TBD)   |

`./arail blueprint apply` validates the blueprint against
`catalog/models.toml` (model ids must resolve), but does **not**
validate agent class names — applying this blueprint succeeds today;
the missing agents would surface as runtime errors when the lab
actually tries to load them. That's intentional: the blueprint
documents the desired state and serves as a concrete spec for the
agent work.

## External integrations needed

- **Calendar:** Google Calendar / iCal feed read access
- **Docs:** GDocs / Notion / Markdown vault path
- **Threads:** Slack / Discord export, or imap mailbox

These are runtime concerns the lab consumes through its own config;
none belong in the blueprint TOML directly.

## Default model rationale

`Qwen2.5-3B-Instruct` is the sweet spot for weekly digest
summarization:

- Big enough to produce coherent multi-paragraph prose (the 0.5B
  output gets repetitive on long contexts)
- Small enough to run comfortably on a laptop without contending
  with whatever else the lab is doing
- bf16 fits in ~6 GB resident — no quantization quality loss

Bump to `qwen2_5_7b_bf16` if you have a Mac Studio and want
sharper prioritization; the 3B is the laptop default.

## When this blueprint is "done"

- `summarizer` agent lands under `src/arail/agents/summarizer.py`
- `scheduler` agent lands and supports cron-like Monday-morning trigger
- An end-to-end run produces a real Monday digest from a real source set
- Add `blueprints/status-digest/example-output.md` with a sanitized run
