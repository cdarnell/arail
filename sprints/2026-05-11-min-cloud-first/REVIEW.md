# Review: min-cloud-first (architect, REVIEW mode)
**Verdict:** PASS
**Date:** 2026-05-11

## Failure-mode coverage
All seven rows in ARCHITECTURE.md's failure-mode table are addressed in code or in the new tests. Provider-uniqueness, signup-payload presence, HTTPS-URL invariants, idempotent setup, and upsert-when-missing upgrade semantics are pinned across `tests/test_provider_catalog.py` (7 cases), `tests/test_lab_mode_per_tier.py` (6 cases), and `tests/test_cloud_providers_doc.py` (5 cases). The two acknowledged out-of-scope risks (silent `_write_secrets()` OSError swallow, sign-up URL rot) remain pre-existing debt with explicit followup notes.

## LAB_MODE per tier
`scripts/setup.sh:1148–1160` writes `LAB_MODE=hybrid` for min and `airgapped` for max via the idempotent `_set_env_var` helper. `scripts/upgrade.sh:109–112` upserts only when the key is absent, preserving any explicit user value across tier switches — semantics match the ARCHITECTURE.md contract exactly.

## Provider catalogue
`_PROVIDER_KEY_ENVS` (app.py:888) holds 11 entries (10 curated + `custom`), each env-var value distinct. `_PROVIDER_META` (app.py:915) has matching entries for all 10 plus custom; every entry carries a `signup` field (custom's is empty string, intentional). `/api/providers/status` payload at app.py:1094 now includes `signup` in the per-provider dict.

## Modal UX + endpoint fix
The chat.html `PROVIDERS` array is 10 entries plus a custom row; each row renders a `signup` link (hidden once `has_token=true`) and a `docs` 🔑 affordance. The out-of-scope chat.html JS bug fix (was calling `/api/tokens/...` non-existent routes; now uses `/api/providers/save` and `/api/providers/status`) is justified — shipping 10 providers through a known-broken JS path would have made the entire sprint non-functional. Override flagged in BUILD_LOG, fix is minimal and correct. `grep -c "/api/tokens" chat.html` returns zero matches.

## docs/CLOUD_PROVIDERS.md
204 lines, 10 H2 provider sections (5 labs, 5 aggregators) plus Custom; every section has the canonical `Sign up:` / `Get your key:` / `Env var:` bullets, plus how-to-add-a-key intro and a troubleshooting table.

## Tier framing consistency
README §Pick a tier, `scripts/setup.sh` `capture_tier` prompt, `pyproject.toml` `[tool.arail.tiers]` descriptions, and `CLAUDE.md` all tell the same story: min = cloud-first lab (10 providers, hybrid, 8 GB+ RAM, VM-friendly); max = local-first / air-gapped capable (AeroLLM 70B / AirLLM 405B, airgapped, 12 GB GPU or 32 GB Apple Silicon). Grep audit `min.*airgapped|airgapped.*min` outside `sprints/` returns zero matches.

## Tech debt
Net neutral. Added: 10 hard-coded provider entries (refactor trigger at >12–15 → externalize to YAML), `signup`/`docs` field duplication. Repaid: min tier framing is now coherent across runtime + setup + docs; modal endpoint paths are no longer fictional.

## Must-fix before ship
(none)

## Nice-to-have followups
- Externalize provider catalogue to a YAML/TOML file when curated set crosses ~12 entries
- Quarterly review of sign-up URLs (provider rebranding risk)
- Log `_write_secrets()` OSError instead of silent `pass` (pre-existing; out of sprint scope)
- Smoke-test the new bulk `/api/providers/status` modal path on a clean VM (manual; outside QA's automated allocation)
