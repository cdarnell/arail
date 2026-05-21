# Review: aerollm-72b-lift

**Date:** 2026-05-20
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `bf189dc`
**Design basis:** [SPRINT.md](./SPRINT.md) (no standalone ARCHITECTURE.md — deferred commit 3b from sprint `2026-05-18-ai-eng-v2.1`; design lives in SPRINT.md §"Two bugs" + `pure-forging-pizza.md` § Phase 3)

## Verdict: WEAK_PASS

Both target bugs are genuinely fixed and proven against the real `pyproject.toml`.
The OOM trap (minimalist resolving to 72B) is closed and cannot recur without a
test going red. One carryover prevents a clean PASS: this sprint deepens an
already-failing stale scope-guard from a prior sprint, which should be retired as
a follow-up. No BLOCKs.

**Tier resolution confirmed (the load-bearing claim):**
- **minimalist → 7B** (`mlx-community/Qwen2.5-7B-Instruct-4bit`) — confirmed
- **maximus → 72B** (`mlx-community/Qwen2.5-72B-Instruct-4bit`) — confirmed

Proven end-to-end against the actual `pyproject.toml`, not just the test mirror:
fixed loader → MIN 7B / MAX 72B; the *old* (reverted) loader order would have
produced MIN=72B (stomp confirmed real, and confirmed fixed).

## Spec adherence

Strong. Every in-scope item in SPRINT.md was delivered, nothing out-of-scope:

| Spec item | Status |
|---|---|
| `aerollm_maximus` → 72B | Done (`pyproject.toml:140`) |
| `aerollm_minimalist` = 7B added | Done (`pyproject.toml:141`) |
| `aerollm` legacy alias stays 7B | Done (`pyproject.toml:145`) |
| Bug 1: MIN_ID loader stomp fixed | Done (`setup.sh:115` now leads with `aerollm_minimalist`) |
| Bug 2: per-tier `case` in `capture_tier` | Done (`setup.sh:987-990`, mirrors AirLLM `976-979`) |
| `AEROLLM_MODEL_MAX_ID` shell default → 72B | Done (`setup.sh:82`) |
| Comments updated | Done in setup.sh + pyproject; **stale comments remain in `src/`** (see findings) |
| RAM-headroom warning | Done (`setup.sh:993-1012`), portable + non-fatal |
| Tier-resolution tests | Done (12, all green) |

`.env` override path verified intact: `setup_env` only writes `AEROLLM_MODEL` into
`.env` on first creation (`setup.sh:1122` guards with `if [[ ! -f .env ]]`); a
re-run with an existing `.env` skips the whole block ("preserving model settings",
`:1157`). Line `:1140` itself is unmodified by this diff. A hand-edited override
survives, and is consumed at runtime by `backends.py:1135` / `app.py:6281`.
Override semantics correct.

## Code quality findings

- **[INFO]** Bug 1 fix is a one-token reorder (`aerollm_maximus` → `aerollm_minimalist`
  as first key in the `.get` chain at `setup.sh:115`). Now exactly parallel to the
  AirLLM line above it (`:111`). Clean and symmetric.
- **[INFO]** Bug 2 `case` block (`setup.sh:987-990`) is a faithful mirror of the
  AirLLM block (`:976-979`) — same structure, same `*` wildcard arm → minimalist.
  Good consistency; a future reader will recognise the pattern.
- **[INFO]** The RAM warning is well-scoped: gated to `maximus` only, `local`-scoped
  vars, both detection paths have `|| echo 0` fallbacks. Threshold (51539607552 =
  48 GiB) documented inline with the byte math. Reasonable for a ~40 GB-resident
  72B-4bit.
- **[ASK / carryover, not in this diff]** Stale `src/` comments now describe the
  wrong max model:
  - `src/arail/portal/app.py:6306` — "max tier ships Llama-3.1-70B-4bit"
  - `src/arail/router/backends.py:1132` — "max tier ships with [70B]"
  These were correct before the lift; they are now factually wrong (it is
  Qwen2.5-72B). Out of this sprint's file scope, so not fixed here, but they should
  be corrected in a follow-up to avoid operator confusion. Filed as carryover CO-2.

## Security findings

- **[INFO]** No security surface. No user input, no auth/session, no network I/O, no
  secrets handling, no deserialization. `AEROLLM_MODEL` continues to flow through
  `.env` (the existing, unchanged path). The arail paranoid checklist items
  (API-key leakage, code-execution sandboxing, tracebacks to non-experts, Buddy
  over-confidence) are not triggered by a config/resolution change.
- **[INFO]** Shell expansions in the new code are safe: model ids are written via
  `info`/`warn` with `${VAR}` inside double quotes; the `case` arms use `:-`
  defaults; no `eval` of model ids; the RAM block does integer arithmetic only.
  Verified survival under `set -euo pipefail` (active at `setup.sh:6`) including the
  empty-awk-match edge (`ram_kb=""` → `$(( * 1024 ))` → 0, no unbound error) and the
  sysctl-failure path (`|| echo 0`).

## Test coverage assessment

12 new tests, all passing (`pytest tests/test_aerollm_tier_resolution.py -v` → 12
passed in 0.01s). Three groups: pyproject key assertions (4), loader resolution
chain (3), tier `case` simulation (5).

**Quality of the tests — spot-checked:**
- `test_loader_min_id_resolves_to_7b` and `test_loader_min_id_is_not_72b` are *real*
  resolution assertions, not existence-only. They run the exact `.get(...)` fallback
  chain against the loaded pyproject dict and assert MIN == 7B / MIN != 72B.
- **Regression-sentinel property (the key question): YES.** Because this sprint makes
  `aerollm_minimalist` (7B) and `aerollm_maximus` (72B) *distinct* values, the
  lookup *order* is now observable. Reverting the mirror to lead with
  `aerollm_maximus` makes `test_loader_min_id_resolves_to_7b` /
  `test_loader_min_id_is_not_72b` go red. (Pre-sprint, `aerollm_maximus == aerollm
  == 7B`, so the order was unobservable and untestable — this sprint is what makes
  the guard meaningful.) Verified empirically: the buggy order against the real
  pyproject yields 72B; the fixed order yields 7B.

**Coverage gap (bounded, INFO):** The tests *mirror* the shell logic in Python; they
read `pyproject.toml` (`:40`) but do **not** execute or parse `scripts/setup.sh`.
Consequence: a revert of *only* the shell loader (`setup.sh:115`) while leaving the
Python mirror fixed would NOT be caught. This is the standard "test mirrors source"
tradeoff and matches the existing `test_setup_extras.py` pattern, so it is
acceptable for this change — but it is a real limitation worth recording. A stronger
(future) guard would `grep` the actual line out of `setup.sh` or run the loader
heredoc. Filed as carryover CO-1 (nice-to-have, not blocking).

Changed-line coverage on the two fixed shell lines is effectively 100% via the
mirrored simulations; the RAM-warning block is not unit-tested (shell-only, hard to
unit-test without a bash harness) but was manually stress-tested under
`set -euo pipefail` across both OS paths and the failure fallbacks.

## Performance assessment

N/A — not a hot path. Setup-time, run-once resolution. No data-structure or
allocation concerns.

## Regression assessment

Full suite: **14 failed, 1922 passed, 1 xfailed** (78s). Baseline on `origin/main`
is 14 failed / 1910 passed / 1 xfailed. The +12 passes are exactly the new tests.
**Failure count unchanged — claim verified.**

Investigated whether any of the 14 is *attributable to this change*:
- One failure looked suspicious by name —
  `test_build_ai_eng_dry_run_works_on_lowram.py::test_sprint_did_not_touch_setup_or_catalog_files`
  — because it asserts setup.sh/pyproject/catalog are *untouched*, and this sprint
  touches setup.sh + pyproject. **Confirmed pre-existing, NOT introduced here:** that
  test belongs to the prior sprint `2026-05-18-ai-eng-v2.1`, comparing
  `ad25c88^..HEAD`. It is **already RED on `origin/main`** because PR #67
  (`534be29`) touched `models_catalog.yaml` after `ad25c88`. So it fails on main
  independently of this branch; the count does not change.
  - **BUT** this branch *deepens* the failure: on main its `leaked` set is
    `{models_catalog.yaml}`; on this branch it becomes
    `{models_catalog.yaml, pyproject.toml, scripts/setup.sh}`. The test's own
    docstring anticipates this — "If the sprint range ever expands to include 3a/3b,
    update SPRINT_HEAD accordingly" — and **this sprint IS commit 3b**. The stale
    guard should be retired/rescoped. This is the reason for WEAK_PASS rather than
    PASS. Filed as carryover CO-3.
- The other 13 failures: none reference `aerollm`/`AEROLLM`/tier resolution (grep
  clean). Spot-checked two in isolation: `test_lab_mode_empty_string_is_airgapped`
  *passes* alone (confirms the builder's "order-sensitive" pollution
  characterisation); `test_metrics_hybrid_mode` fails alone (pre-existing,
  unrelated assertion). No NEW failure attributable to this change.

`bash -n scripts/setup.sh` → clean (SYNTAX_OK).

## Tech debt delta

vs SPRINT.md prediction: net **negative** (debt repaid).

**Repaid:** Two latent bugs removed — the MIN_ID stomp (a live OOM trap the moment
72B landed) and the missing per-tier AeroLLM resolution (maximus silently getting
7B). Added a regression sentinel that only became expressible because of this change.

**Added:** (1) the Python-mirror test gap (CO-1) — small, matches existing pattern;
(2) stale `src/` comments referencing the old 70B (CO-2) — cosmetic but
operator-facing; (3) a prior-sprint scope guard now over-firing (CO-3) — not this
sprint's bug, but this sprint is the trigger to clean it up.

## Required actions before merge

None blocking. WEAK_PASS ships with the carryover notes below filed.

## Carryover (file as follow-up tickets — 3 items)

1. **CO-1 (test, nice-to-have):** Strengthen the tier-resolution guard so it catches
   a shell-only revert — `grep` the `aerollm_minimalist`-first ordering out of
   `scripts/setup.sh:115`, or execute the loader heredoc, instead of mirroring the
   logic in Python. Bounded gap; acceptable for now.
2. **CO-2 (docs/comments):** Update stale max-tier model references in `src/`:
   `src/arail/portal/app.py:6306` and `src/arail/router/backends.py:1132` still say
   "Llama-3.1-70B-4bit"; the max tier now ships Qwen2.5-72B-4bit. Also worth a pass
   on `app.py:5695`/`:6281` default-model docstrings for consistency.
3. **CO-3 (test scope, prior sprint):** Retire or rescope
   `tests/test_build_ai_eng_dry_run_works_on_lowram.py::test_sprint_did_not_touch_setup_or_catalog_files`.
   It was guarding deferral of commit 3b; commit 3b has now landed (this sprint), so
   the guard is satisfied-by-completion. Its docstring already says to update
   `SPRINT_HEAD` when 3a/3b land. Already failing on main (via #67), so this is
   cleanup, not a regression introduced here.

## QA recommendation

**No separate QA pass required — this architect review is sufficient.**

Rationale: this is a deterministic config/resolution change with (a) no network,
auth, secrets, or code-execution surface; (b) the OOM-sensitive direction is
*safe-by-default* in every consumer (the Python fallback at `backends.py:1135` /
`app.py:6281` is the 7B, never the 72B — a misconfiguration under-provisions, it
does not OOM); (c) the resolution is proven end-to-end against the real pyproject,
including the negative case (buggy order → 72B); (d) full-suite regression count is
unchanged and every delta is accounted for. The one thing QA would normally
validate here — "does a clean minimalist install ever get the 72B?" — is answered No
by both the test sentinel and the runtime fallback analysis. Running an actual 72B is
out of scope (no ≥96 GB machine), which is the only thing a live QA pass could add,
and it is explicitly deferred in SPRINT.md.

SPRINT.md marks qa "conditional — architect decides": decision is **skip qa**,
proceed to ship with the 3 carryover tickets filed. Recommend the orchestrator
record the qa-skip as the documented override in the sprint ledger (per workspace
rule: bypassing /qa requires a documented override).
