# BUILD_LOG — 2026-07-23-clean-experience

## WP1 — Quiet boot (no auto-checks unless invoked)

**Goal:** nothing probes packages/versions/models or warms weights at boot or on
an interval unless the user opts in (`ARAIL_AUTOCHECKS`) or explicitly asks
(`./arailctl doctor`, an Admin button). First byte fast even with no model.

**Changes**

- **New `src/arail/autochecks.py`** — master switch `ARAIL_AUTOCHECKS` (default
  off). `enabled()` gates every background probe/warmer. Load-bearing boot work
  (egress guard, seeds, orphan sweep) is deliberately NOT gated.
- **`src/arail/portal/app.py` `_startup`:**
  - Registry health thread (`get_registry().start_background()`), aeroLLM
    preload, boot model-warm (`_warm_primary_router`), Claude cache prewarm, and
    the hybrid boot CVE scan all now behind `_autochecks_on`. When the warm is
    skipped, `_MODEL_WARM` is flipped True inline so the `/api/ready` overlay
    dismisses instantly.
  - Bootstrap goal now parses with `parser.parse_offline` (heuristic-only, no
    60s LLM subprocess) and **no longer auto-starts the researcher** — the goal
    is staged; the user presses Approve & Run.
  - `pkb_index.ensure_ready` and the Knowledge-Canvas Neo4j init moved into
    background tasks (first byte never waits on a LanceDB rebuild / Neo4j
    connect). New `ARAIL_SKIP_CANVAS=1`.
  - `/api/admin/components` does zero subprocess work by default — versions via
    `importlib.metadata`; shell-only components read "not checked" unless
    `?probe=1` (the new Admin "Check versions" button).
- **`src/arail/registry/health.py`** — `MODEL_HEALTH_INTERVAL_SEC=0` runs one
  preflight then exits the loop (one-shot, no recurring "MODEL TIER DOWN").
  Verified `resolve()`/`_gate_reason` treat `unknown` health as usable, so
  skipping the boot preflight is safe (probe-on-first-call).
- **`src/arail/doctor.py` (new)** + `arailctl doctor` — the explicit checkup:
  lab mode + egress guard (installs it in-process so its own probes obey airgap),
  a single model preflight + tier table, PKB index readiness, component versions,
  and `--updates` (hybrid only). `arailctl doctor` now runs `python -m
  arail.doctor "$@"` after the venv/import smoke-test.
- **`scripts/setup.sh`** — model pulls fail fast: skip the download when the
  ollama daemon is unreachable (`ollama list` 5s probe) or `ARAIL_SKIP_MODEL_
  DOWNLOAD=1`; every `ollama pull` timeout lowered 900s→180s. (An earlier
  non-interactive auto-skip was reverted — it broke automated/CI installs and
  the setup-ladder tests; the unreachable-check + timeout cover the hang.)
- **`start-portal.sh`** — `--reload` now behind `ARAIL_DEV=1`/`ARAIL_RELOAD=1`
  (off by default) so a stray file touch no longer re-runs the whole startup.
- **Templates** — `dashboard.html`: removed the auto-fire update check on load
  (button-only now). `admin.html`: "Check versions" button → `?probe=1`.
  `_model_switcher.html`: `unknown` health dot tooltip explains the quiet-boot
  "not checked yet — press Refresh" state.
- **Docs** — `.env.example` gains a "QUIET BOOT / AUTOCHECKS" section + fully-
  silent recipe; `docs/MACOS.md` corrected (goal is staged, not auto-started).

**Tests**

- New `tests/test_autochecks_boot.py` (5): autochecks default-off + toggle;
  `MODEL_HEALTH_INTERVAL_SEC=0` one-shot; unknown-health resolves usable;
  `/api/admin/components` no subprocess by default; `?probe=1` shells out.
- Regression: `test_boot_warm/grace/security_scan/aerollm_preload` (21) pass;
  `setup_ladder/` (30) pass; `test_r1_r3_chat_models` (29) pass with stable
  ordering (the 4 seen failing under pytest-randomly reproduce on the untouched
  parent — pre-existing order-flakiness, not WP1).

**Verification (per ARCHITECTURE.md Part C / WP1 gate)**

- `python -m arail.doctor` prints the full tier/components/egress table. ✓
- `/api/admin/components` spawns no subprocess by default; `?probe=1` does. ✓
- No registry health thread / no `parser.parse` subprocess at boot with
  `ARAIL_AUTOCHECKS` unset. ✓ (unit-level; portal is import-clean)
- Deferred: live "time ./arailctl start → first byte < 5s" needs a booted
  portal + venv on the target box (no venv in the worktree) — left for the QA
  pass on Charlie's machine.

## WP2 — Egress honesty (live privacy bug + browser consent)

**Goal:** the "agents only touch approved knowledge and don't phone home"
contract is true, enforced, and honestly documented — no undisclosed egress,
no private user text in third-party URLs.

**Changes**

- **`src/arail/agents/_builtin_buddy.py` `_suggest_internet_correlation`:**
  - Now consent-gated: in hybrid with no consent for `huggingface.co`, Buddy
    creates ONE pending consent request (idempotent — no duplicate spam) and
    returns a "approve web access" suggestion instead of fetching. Nothing
    reaches the network until the user approves.
  - **Goal text removed from the URL.** The fetch target is a fixed,
    un-parameterized `_HF_PAPERS_URL` (`…/api/daily_papers`); goal correlation
    is computed locally from returned titles/summaries by keyword overlap. No
    match → no suggestion (honest — no pretending an unrelated paper connects).
- **`src/arail/agents/browser.py`:** new `_consent_gate()` — `browse_url` and
  `chat` now check `ConsentStore.is_allowed(domain)` before any fetch; an
  un-approved domain creates one pending request and returns an
  `awaiting_consent` result. For `chat` the gate runs after Phase-1 URL
  resolution (a local model call) and before the network `open`. Module
  docstring corrected to "consent-gated per domain when hybrid" (was
  overclaiming).
- **`src/arail/agents/researcher.py`:** reworded the source messaging — it now
  says approval records *permission* (nothing is fetched/downloaded), removing
  the implication that approved sources are pulled.
- **`src/arail/agents/consent.py`:** `_save` now `chmod 0600` (allowlist /
  pending / history are owner-only, matching secrets.env).

**Tests**

- New `tests/test_buddy_internet_consent.py` (4): airgapped → no network;
  hybrid+no-consent → one pending request, no fetch, no duplicate on re-run;
  hybrid+consent → fetches the fixed URL (asserts no goal words / no `?` in
  URL) and correlates locally; no keyword match → None.
- Regression: buddy/browser/curator/egress suites (108 assertions across the
  touched files) pass.

**Verification (WP2 gate)**

- Buddy hybrid cycle without consent performs no HuggingFace request and
  leaves a single pending consent entry; the fetched URL never contains goal
  words. ✓ (unit-proven; live egress.jsonl check left for QA on a hybrid box)
