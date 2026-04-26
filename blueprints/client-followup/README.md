# Client Follow-up blueprint

Consultant relationship assistant. After every client meeting,
reads the notes you dropped in, pulls relevant context on the
client, drafts a follow-up, and recommends the next-touch cadence.
**Drafts only** — sending is always your call.

## Quick start

```bash
./arail blueprint create my-clients --from client-followup
./arail blueprint apply my-clients
# Edit instances/my-clients/.env to set your client list + voice profile.
```

## Agents this blueprint expects

| Agent          | Status        | Where to implement                       |
|----------------|---------------|------------------------------------------|
| `researcher`   | ✅ exists     | `src/arail/agents/researcher.py`         |
| `drafter`      | ⏳ aspirational | `src/arail/agents/drafter.py` (TBD)     |
| `scheduler`    | ⏳ aspirational | `src/arail/agents/scheduler.py` (TBD)   |
| `consent`      | ✅ exists     | `src/arail/agents/consent.py`            |
| `curator`      | ✅ exists     | `src/arail/agents/curator.py`            |

`drafter` and `scheduler` are shared with `inbox-triager` and
`status-digest` respectively — implementing one unlocks multiple
blueprints.

## External integrations needed

- **Meeting notes source** — Markdown vault, Notion, or post-meeting
  voice-to-text export
- **Client database** — anything queryable by client name; vCard,
  CRM export, or a simple TOML file under `instances/<name>/clients/`
- **Calendar** — to read the meeting context and propose the
  next-touch date
- **Email send** (gated by `consent`) — for the actual follow-up

## Default model rationale

Tier `max` because client work uses the full surface:

- **Notebooks** for ad-hoc per-client analysis
- **Terminal** for quick lookups (last invoice, contract end date)
- **Tuning** to calibrate per-client voice profiles

Default `mlx` model is `qwen2_5_7b_bf16` — same as
`inbox-triager`, since the writing quality requirements are
similar. The `airllm` fallback bumps to `llama_3_1_70b_bf16`
because if you're streaming from disk you might as well get the
sharper output for client communication.

## Voice calibration (where this blueprint earns its keep)

`drafter` should learn your per-client tone over time:

- Some clients want bullets, some want paragraphs
- Some appreciate humor, some need pure information
- Some need the meeting summary recapped, some are insulted by it

The blueprint reserves a `voice_profile` slot in
`instances/<name>/clients/<client-id>.toml` — this is the
per-client config the `drafter` agent consumes. Schema TBD when
the agent lands.

## Cadence recommendations (the `scheduler`'s job)

- **Active engagement** (current project): every 3-5 business days
- **Warm relationship** (no active project): every 4-6 weeks
- **Cold relationship** (last touch > 3 months): every 8-12 weeks,
  with a value-add hook (article, intro, useful link)

These are starting heuristics; the `scheduler` agent should adjust
based on response cadence — clients who reply quickly get touched
more often; clients who let messages age get longer cycles.

## Safety model

Same three-layer gate as `inbox-triager` — `drafter` writes to a
draft folder, `consent` blocks any send-action transition. Tier
`max` does not relax this.

## When this blueprint is "done"

- `drafter` agent implemented (shared with `inbox-triager`)
- `scheduler` agent implemented (shared with `status-digest`)
- Per-client voice-profile schema settled
- End-to-end run on three real clients produces follow-ups the
  consultant actually sends with minimal editing
- Add `blueprints/client-followup/example-followup.md` with a
  sanitized run
