# Inbox Triager blueprint

Inbox classification + reply-drafting assistant. Classifies new
email and drafts approval-gated replies in your voice. **Never
auto-sends** — the `consent` agent gates every outgoing send
behind explicit approval.

## Quick start

```bash
./arailctl blueprint create my-inbox --from inbox-triager
./arailctl blueprint apply my-inbox
# Edit instances/my-inbox/.env to set IMAP/SMTP credentials.
```

## Agents this blueprint expects

| Agent       | Status        | Where to implement                  |
|-------------|---------------|-------------------------------------|
| `triager`   | ⏳ aspirational | `src/arail/agents/triager.py` (TBD) |
| `drafter`   | ⏳ aspirational | `src/arail/agents/drafter.py` (TBD) |
| `consent`   | ✅ exists     | `src/arail/agents/consent.py`       |

The `consent` agent already exists and is the load-bearing safety
mechanism — it owns the "ask before sending" gate. The `triager`
and `drafter` are the per-blueprint specializations to implement.

## External integrations needed

- **IMAP read** for the source mailbox
- **SMTP send** (gated by `consent`) for outbound replies
- **Address book** (vCard / CardDAV) for sender context — informs the
  voice / tone the drafter targets

## Default model rationale

Email composition is more sensitive to model size than weekly
summarization — bad word choice in a draft is worse than bad word
choice in a digest you're going to re-read anyway. Qwen2.5-7B is
the sweet spot:

- Big enough for natural-sounding professional prose
- Small enough that draft latency stays reasonable
- Same model AeroLLM benchmarks against — re-uses your existing
  fixture if you've run the v0.1-alpha benchmark

If you have a Mac Studio with headroom, bump the `mlx` slot to
`qwen2_5_72b_bf16` for sharper voice matching.

## Safety model

Three layers, all enforced before any SMTP send:

1. **Classification gate** — `triager` flags `needs-reply` items
   only; informational / unsubscribe / calendar-conflict stay
   untouched.
2. **Draft-only output** — `drafter` writes the reply into a draft
   folder, never to the outbox.
3. **Consent gate** — `consent` requires explicit user
   acknowledgement (UI click or terminal prompt) before any
   transition from draft → outbox → send.

The blueprint is tier=min so the safety model is auditable in one
sitting. Don't promote to a higher tier without re-reading the
consent gate.

## When this blueprint is "done"

- `triager` + `drafter` agents implemented
- End-to-end run on a real inbox classifies + drafts without
  bypassing `consent`
- Add `blueprints/inbox-triager/example-classification.md` with
  a sanitized run showing the four categories
