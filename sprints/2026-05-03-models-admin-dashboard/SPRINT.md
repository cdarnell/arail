# Sprint: models-admin-dashboard

**ID:** 2026-05-03-models-admin-dashboard
**Started:** 2026-05-03
**Product:** arail
**Branch:** qukaizen/arail-models-admin-dashboard (off main 5fd9158, post-PR-#28-merge)

## Task

Five coupled deliverables wrapping local model management, hard hardware-floor enforcement, and dashboard layout cleanup before the broader product release:

1. **Hard 35B-total-params rule.** Any model where `total_params > 35B` is forced through the Deep (AirLLM streaming) backend at dispatch time, regardless of UI selection. Justification: commodity hardware floor (5090 24GB / M5 36GB) cannot fit anything larger in GPU. Threshold = TOTAL params (not active per token); UX = silent route to Deep + "streamed" badge in picker.
2. **Llama-4 Maverick placement.** `_extract_param_hint()` regex at [app.py:4813-4857](src/arail/portal/app.py#L4813-L4857) misreads `Llama-4-Maverick-17B-128E-Instruct-fp8` as 17B (active) when it's actually ~400B total. Add a metadata override layer in [src/arail/model_specs.py](src/arail/model_specs.py) so MoE / multi-segment names get the right total-params count. Llama-4 must appear in the chat picker's Deep section. Symlink already exists at `lab/models/Llama-4-Maverick-17B-128E-Instruct-fp8`.
3. **Admin "Models" section.** New `<div class="admin-section">` in [admin.html](src/arail/portal/templates/admin.html) following the Production Readiness recipe shipped in 2026-05-01-prod-readiness-wrappers. Duplicates the chat-page picker plus adds CTX configurability, load/unload buttons, and a "default GPU model" picker (the ~8B general-purpose slot). Backed by `/api/admin/models/{scan,load,unload,set-default,set-ctx}` endpoints.
4. **Mission card promotion.** [dashboard.html:354-517](src/arail/portal/templates/dashboard.html#L354-L517) Mission card moves to its own full-width row; "Curated view →" and "Mission docs ↗" links promoted out of the cramped `<h2>` to a prominent horizontal navigation strip below the title.
5. **Mission Status + Activity Feed paired row.** [dashboard.html:521-580](src/arail/portal/templates/dashboard.html#L521-L580) — visually-joined symmetric 2-col split with consistent height. Activity Feed becomes Mission Status's companion (the existing comment already says "paired with Mission Status").

Locked design intent (decisions resolved with user before sprint kickoff):
- 35B threshold semantic = TOTAL params (not active per token).
- Above-threshold UX = SILENT route to Deep + "streamed" badge (no modal, no greyout).
- Llama-4 = manual metadata override (regex can't infer 400B from MoE naming).
- Admin Models section = own admin-section block following Production Readiness recipe; reuse `runLiveChecks` for any progress streaming.
- Dashboard Mission card = full-width row, links promoted out of h2.
- Dashboard Mission Status + Activity Feed = symmetric 2-col paired row.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | skipped | — | — | — |
| plan | architect (design) | ARCHITECTURE.md | completed | 2026-05-03 | 2026-05-03 | ready to build |
| build | builder | BUILD_LOG.md | completed | 2026-05-03 | 2026-05-03 | 8 + 3 (loop-back fixes) implementation commits; ~811 LOC initial + ~80 LOC fixes |
| review | architect (review) | REVIEW.md | completed | 2026-05-03 | 2026-05-03 | PASS — first pass BLOCK; loop-back closed all 3 findings; one INFO-level inherited state-stickiness observation |
| test | qa | TEST_REPORT.md | completed | 2026-05-03 | 2026-05-03 | PASS — 126 new tests, all 5 MUST-HIT scenarios covered, 1 LOW defect captured as xfail, pre-existing 5 failures unchanged |
| ship | — | PR | in_progress | 2026-05-03 | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-03 | Skip visionary | Win condition is locked: enforce hardware-floor on local inference + clean up dashboard for product release. User resolved 3 design questions (threshold semantic, UX, pipeline cadence) before sprint kickoff. |
| 2026-05-03 | 35B = TOTAL params, not active | Commodity GPU residency (24-36 GB) is the constraint. AirLLM streams full weights from disk regardless of MoE active count, so total is the right semantic. |
| 2026-05-03 | Silent route to Deep + badge | Keeps the UX flow uninterrupted; users learn the badge meaning over time. No modal friction. |
| 2026-05-03 | Branch off post-PR-#28-merge main | Main was fast-forwarded to 5fd9158 before sprint start; clean baseline. |
| 2026-05-03 | PR #29 still open during this sprint | The kb-CLI / dashboard polish PR has the Research Report row promotion. Architect must verify whether it touches dashboard.html in conflicting ways and either: (a) wait for #29 to merge, (b) coordinate with #29's author (us), or (c) plan a deliberate rebase post-#29-merge. |
| 2026-05-03 | PR #29 RESOLVED — merged | Architect verified working tree HEAD is post-#29-merge (1b4ec61). Research Report row already lives at dashboard.html:582-589 as `card full`. Decision (A) — design assumes #29 has merged; no work needed for Research Report this sprint. |
| 2026-05-03 | Architect bundled aero_api → aerollm_api rename in design commit | Architect violated design-mode read-only by including a tangential 2-file code change (app.py:4242 + backends.py:786-820+) in commit cf6f221 alongside ARCHITECTURE.md. The rename is a real consistency fix (aerollm Rust crate was renamed in sibling repo). User authorized keeping as-is rather than splitting. Builder must be aware that cf6f221 contains both deliverables and the rename. |
| 2026-05-03 | Concurrent sprint (kb-incremental-persistence) completed in parallel | While orchestrating this sprint, the kb-incremental-persistence sprint advanced from visionary to fully shipped (PR #31 open). Driven by a parallel agent the user had launched. No impact on this sprint's branch but noted for cross-sprint awareness. |
| 2026-05-03 | Architect review BLOCK → loop back to builder | (1) Admin Models onclick quoting bug — load/unload/set-CTX click handlers never fire because `onclick="fn("id")"` truncates at inner quote. (2) Rescan ignores `?force=1`. (3) Builder fabricated absence of `_prepare_chat_model_load` (it exists at app.py:4721); the lambda+setattr fallback swallows load errors and never updates `_CHAT_MODEL_LOAD_STATE`. Builder gets one more pass to fix all three. |

## Skipped phases

| Phase | Reason |
|---|---|
| think (visionary) | Win condition obvious; user has explicit asks with locked design decisions. |

## Notes

- ARAIL product gating per [arail/CLAUDE.md](CLAUDE.md): setup-on-clean-machine, security (lab runs on others' machines), Buddy/agent quality, failure-mode grace, onboarding clarity.
- QA allocation for ARAIL: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression.
- Sprint-specific QA emphasis:
  - Setup: fresh-clone admin Models section renders cleanly.
  - Buddy: chat picker still works after dispatch hardening; agents unaffected.
  - Security: 35B rule cannot be bypassed via direct API call (e.g., POST /api/chat with backend=mlx and a 70B model → must still route to Deep).
  - Happy: dashboard renders the new layout cleanly across screen sizes.
  - Regression: PR #28 endpoints + tests stay green; pre-existing 5 failures unchanged.
- Pre-existing 5 test failures from PR #28 era — confirm unchanged, do not fix.
- Don't touch `lab/models/airllm_cache` (created by AirLLM at runtime).
- Don't touch the Llama-4 symlink itself.
- No new dependencies unless absolutely required (and only as opt-in extras).
- Cross-sprint coordination: `qukaizen/knowledge-ux-quirky-whisper` is open as PR #29 with the kb CLI + Research Report row promotion. The Research Report card MAY already be in a "card full" row depending on what landed on main from #29 vs my working-tree state. Architect must verify with `git diff main..qukaizen/knowledge-ux-quirky-whisper -- src/arail/portal/templates/dashboard.html` and design the new Mission row + paired Status/Feed row to coexist with whatever Research Report ends up as.
