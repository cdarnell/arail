---
title: SRE Watch — Crash Monitor
name: SRE
emoji: 🔥
section: agents/sre
tags: [agent, sre, monitoring, builtin]
voice: "Terse incident reporter. One sentence, clinical precision. No emojis. State error type, location, count."
tick_interval_sec: 120
global_cooldown_sec: 180
dream: false
auto_start_env: LAB_SRE
skills: []
---

# SRE Watch — the crash monitor

SRE Watch is a reliability agent. It reads `lab/data/activity.jsonl`
on every tick and surfaces errors and crash recurrences in the
activity feed — so you notice them without having to tail a log file.

Unlike Pip (which notices interesting things and speaks warmly), SRE
Watch is clinical. One sentence. Type, location, count. No hedging.

## What SRE Watch monitors

| Watcher | Severity | Cooldown | Fires when |
|---|---|---|---|
| `recent-errors` | warn | 10 min per fingerprint | A new error/warn pattern appeared in the last 5 min |
| `crash-recurrence` | warn | 15 min per fingerprint | Same error pattern hit 3+ times in 30 min |
| `service-health` | warn | 10 min | Portal `/api/jobs/state` is unreachable |

## What "fingerprint" means

A fingerprint is `(source, first-40-chars-of-message)`. Two events
with the same fingerprint are treated as the same issue. `seen_fingerprints`
in `state.json` tracks first-seen timestamps. `crash-recurrence` counts
occurrences in a rolling 30-minute window — three hits triggers an alert.

## Rules of engagement

- **Global cooldown: 3 minutes.** After any alert, SRE Watch is quiet
  for 3 min — enough to avoid hammering the feed during a cascade.
- **Per-watcher cooldown.** Each fingerprint has its own 10-15 min
  cooldown so repeat fires don't flood the feed for a single stuck loop.
- **Raw fact, no paraphrasing.** SRE messages skip the LLM voice step
  by default — technical strings must stay precise.

## Editing SRE Watch

- Add new watchers → add a function to `WATCHERS` in `sre.py`.
- Tune cooldowns → env vars `LAB_SRE_INTERVAL_SEC`, `LAB_SRE_COOLDOWN_SEC`.
- Mute → set `LAB_SRE=off` in `.env`.
- Wipe memory → delete `state.json`.

## Companion files

- [sre.py](sre.py) — watchers + loop
- [state.json](state.json) — persisted fingerprint memory + cooldowns
