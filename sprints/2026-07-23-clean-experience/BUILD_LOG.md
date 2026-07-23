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

## WP3 — Security quick wins

**Goal:** make tier a real access boundary, stop the plugin installer from
running unconfirmed, keep the passphrase off disk-world-readable + out of the
Marimo URL, and warn on the hand-off / non-loopback-bind cases. (Full dashboard
auth deferred, per owner.)

**Changes** (all `src/arail/portal/app.py` unless noted)

- **Server-side tier guards.** New `_require_surface(name)` (generalizes the
  old `_require_workbench`, now a thin alias) 404s when the surface isn't in the
  current tier. Applied to `/terminal`, `/notebook`, `/notebooks`, `/marimo`,
  `/plugins`, `/admin`, `/build`, `/tuning` (GET) and `/api/notebook/start`,
  `/api/marimo/start`, `/api/plugins/install` (POST). Routes/URLs unchanged;
  minimalist users get 404 (existence not disclosed) instead of the full page.
- **Plugin install confirmation.** `/api/plugins/install` now requires
  `confirm_code_execution=true` in the body (server-side) and the plugins.html
  form both shows a persistent warning and raises a `confirm()` dialog that
  spells out "git clone + pip install runs arbitrary code as you".
- **Passphrase file perms.** New `_chmod_600` helper; `.env`, `lab.conf`, and
  `~/.config/code-server/config.yaml` writes are now owner-only (were
  world-readable), matching secrets.env.
- **Marimo URL.** Removed `?access_token=<ARAIL_PASSWORD>` from the iframe /
  pop-out URL (it leaked the passphrase into browser history). The token is now
  a click-to-reveal "Access token" button (copies to clipboard); Marimo prompts
  for it once. (`templates/marimo.html`)
- **Hand-off warning.** welcome.html gains a warning card: the dashboard has no
  login — anyone at this browser is treated as you (can run code, flip egress,
  read tokens). A loud startup log + activity-log `security` warning now fires
  when `BIND_ADDR` is non-loopback.
- **Design tokens.** All new banner/button styling uses CSS classes, not inline
  `style=` (keeps the token-compliance ratchet green).

**Tests**

- New `tests/test_tier_route_guards.py` (3): minimalist 404s on all 11 maximus
  routes; maximus serves them; plugin install without confirmation is refused.
- Adapted `test_world_recolor.py` (autouse maximus fixture) and
  `test_admin_models_html_safety.py` (maximus env) — they render maximus-only
  pages that now correctly 404 on minimalist.
- Fixed a pre-existing token-compliance false positive (the hex regex counted
  `href="#dac-proposals-panel"` as a color); it now requires a real color
  boundary. Verified this hid no genuine literal (no file dropped below
  baseline).
- Full portal sweep: 379 pass. The only 2 reds
  (`test_opencode_*` log-rotation / config-env) are **pre-existing** — they fail
  identically on the untouched parent checkout.

**Environment note:** the worktree was missing the vendored
`lab/worlds/{photography,physics}` bundles the parent has (git-ignored runtime
state); restored them for test parity (not committed). The 4 `test_build_tab`
failures seen mid-work were this, not the tier guard.

**Verification (WP3 gate)**

- `LAB_TIER=minimalist` → 404 on `/plugins`, `/admin`, `/build`, `/tuning`,
  `/terminal`, notebooks/marimo, and the POST endpoints. ✓
- Plugin install without `confirm_code_execution` → refused, no clone/pip. ✓
- Marimo template contains no `access_token=` in any URL. ✓
- Non-loopback `BIND_ADDR` emits a security warning at boot. ✓
- `stat` 0600 on secret files: left for QA on a real setup (unit paths use
  tmp dirs).
