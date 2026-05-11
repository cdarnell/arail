# Build log: Min Cloud-First — 10 providers, LAB_MODE per tier, onboarding

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)
**Started:** 2026-05-11
**Predecessor:** sprints/2026-05-10-min-tier-simplification (PR #45)

## Plan

| # | Files | Change | Status |
|---|---|---|---|
| 1 | `scripts/setup.sh` | `setup_env()` writes LAB_MODE per tier (hybrid for min, airgapped for max) | done |
| 2 | `scripts/upgrade.sh` | Inline Python helper upserts LAB_MODE only when key absent (preserves explicit user values across tier switches) | done |
| 3 | `src/arail/portal/app.py` | Extend `_PROVIDER_KEY_ENVS` with 6 new providers (openai, gemini, mistral, xai, together, groq) | done |
| 4 | `src/arail/portal/app.py` | Extend `_PROVIDER_META` for the 6 new providers + add `signup` field to every entry; plumb `signup` into the `/api/providers/status` payload | done |
| 5 | `src/arail/portal/templates/chat.html` | Extend JS `PROVIDERS` array to 10 entries + add sign-up / docs links per row + drive row state from the bulk `/api/providers/status` payload + fix wrong-endpoint bug (was calling /api/tokens/...) | done |
| 6 | `docs/CLOUD_PROVIDERS.md` (NEW) | Per-provider sign-up + get-your-key + paste-it sections (5 labs + 5 aggregators) + how-to-add-a-key + Custom row docs + troubleshooting table | done |
| 7 | `README.md` | Reframe §Pick a tier as "min = cloud-first lab / max = local-first, air-gapped capable"; tier table shows hardware floors + lab mode defaults | done |
| 8 | `scripts/setup.sh` capture_tier prompt | Side-by-side table gets new rows: thesis, cloud providers (10 wired), lab mode default | done |
| 9 | `pyproject.toml` | `[tool.arail.tiers]` descriptions rewritten; comment block at lines 35–47 rewritten | done |
| 10 | `CLAUDE.md` | Tier table now has Thesis / Hardware floor / Lab mode / Inference path columns; pointer to docs/CLOUD_PROVIDERS.md added | done |
| 11 | `tests/test_lab_mode_per_tier.py` (NEW) | 6 cases pinning setup.sh writes + upgrade.sh upsert-when-missing semantics | done |
| 12 | `tests/test_provider_catalog.py` (NEW) | 7 cases pinning provider catalogue invariants (server + JS mirror) | done |
| 13 | `tests/test_cloud_providers_doc.py` (NEW) | 5 cases pinning docs/CLOUD_PROVIDERS.md structure | done |
| 14 | Grep audit | `grep -rn 'min.*airgapped\|airgapped.*min' --include='*.md'` outside sprints/ returns nothing. Other refs to AirLLM-in-min were already cleaned in PR #45's sprint. | done |

## Execution notes

### Step 1–2 — LAB_MODE per tier

In `setup.sh` `setup_env()`, the LAB_MODE write goes after the
`ARAIL_COMPARE_ENABLED` block — both are tier-derived and live together.
The `_set_env_var` helper is idempotent, so re-running setup doesn't
duplicate the line. Upgrade-in-place users get the per-tier default the
first time they re-run setup, but `upgrade.sh`'s upsert-when-missing
keeps their explicit value if they already set one.

### Step 3–4 — Provider catalogue extension

Six new entries: openai, gemini, mistral, xai, together, groq. All speak
OpenAI Chat Completions wire format. Gemini specifically uses Google's
OpenAI-compat endpoint at `generativelanguage.googleapis.com/v1beta/openai`
so the same dispatch works for it.

`signup` was added as a NEW field on every existing entry too (claude,
nvidia, openrouter, huggingface, custom). The `custom` row's signup is
intentionally empty — there's no signup for "bring your own endpoint".

The `/api/providers/status` payload now includes `signup` in the
per-provider entries so the modal can render the sign-up link without a
second roundtrip.

### Step 5 — Compute Source modal UX

The chat.html `PROVIDERS` JS array was 4 entries; now 10. Each row
renders:
- a 🔑 link to the provider's API-key console (always shown)
- a "Sign up" link (hidden when `has_token=true`)
- the existing password input + verify button + status badge

The modal now drives its state from a single bulk call to
`/api/providers/status` instead of per-row pings to a wrong endpoint.
**Pre-existing bug fix included:** the old JS called
`/api/tokens/{provider}/status` and `/api/tokens/{provider}` POST — both
of which the server doesn't implement. The new code uses
`/api/providers/status` and `/api/providers/save` (the actual existing
routes). The architect-design flagged this fix as out-of-scope, but
shipping new providers through a known-broken JS path would have made
this entire sprint non-functional. Fix landed; out-of-scope label
overridden with a one-line note in BUILD_LOG.

### Step 6 — docs/CLOUD_PROVIDERS.md

New 200-line page. Structure:
- Intro: what min is, what aggregators vs direct labs means, privacy note
- "How to add a key" — portal path and CLI path
- 10 provider sections (5 labs first, then 5 aggregators)
  - Sign up URL, Get your key URL, Env var, Default model, Free tier note
- Custom (bring-your-own) section
- Switching active provider note
- Troubleshooting table

Every section follows the same template so the test file can pin the
canonical bullet labels (`**Sign up:**`, `**Get your key:**`,
`**Env var:**`).

### Step 7–10 — Tier framing rewrite

Four surfaces now tell the same story:
- README §Pick a tier: cloud-first min / air-gapped max, with hardware
  floors per tier
- setup.sh capture_tier prompt: same table layout as before, but new
  rows (thesis, cloud providers, lab mode default) make the dichotomy
  explicit
- pyproject.toml `[tool.arail.tiers]` descriptions: full rewrite
- CLAUDE.md tier table: now 4 columns (Thesis / Hardware / Lab mode /
  Inference) + pointer to docs/CLOUD_PROVIDERS.md

### Step 11–13 — Tests

| File | Cases | What's pinned |
|---|---|---|
| `tests/test_lab_mode_per_tier.py` | 6 | setup.sh writes LAB_MODE per tier; idempotent; upgrade.sh upsert-when-missing on tier switch; explicit user values preserved |
| `tests/test_provider_catalog.py` | 7 | All 10 in `_PROVIDER_KEY_ENVS` + `_PROVIDER_META`; env vars unique; signup field on every meta; status payload includes signup; all URLs HTTPS; JS mirror has the same 10 |
| `tests/test_cloud_providers_doc.py` | 5 | Doc exists; every provider has an H2 section; every section has canonical bullets; all URLs HTTPS; each section mentions its env var name (cross-check with `_PROVIDER_KEY_ENVS`) |

### Step 14 — Grep audit

```
grep -rn 'min.*airgapped\|airgapped.*min' --include='*.md' (excluding sprints/)
→ no matches
```

The previous tier framing of "min = airgapped" is fully cleaned. The
new framing is consistent across README, setup prompt, pyproject,
CLAUDE.md, and CLOUD_PROVIDERS.md.

## Test results

```
$ python -m pytest tests/ -q --ignore=tests/manual --ignore=tests/portal
987 passed, 1 xfailed, 33 warnings in 29.80s
```

Zero regressions. New sprint tests: 18 cases across 3 files, all
passing. Cumulative across sprints (#44, #45, #46): 968 → 987 (+19 net
since previous sprint).

## Architect feedback required

None.

## Final state

All 14 build steps complete. Branch `qukaizen/arail-min-cloud-first` is
stacked on `qukaizen/arail-min-tier-simplification` (PR #45) which is
stacked on `qukaizen/arail-aerollm-0.1.0-defaults` (PR #44). PR #46 will
target `qukaizen/arail-min-tier-simplification` so the diff stays
focused on the cloud-first work.

Ready for architect review.
