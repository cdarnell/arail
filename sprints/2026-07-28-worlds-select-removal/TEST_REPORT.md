# Test report: remove in-place World switching

**Date:** 2026-07-29
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `ce4d8b3` (review PASS after one fix loop)
**Tests added:** `tests/test_worlds_select_removal_qa.py` (commit `31cd90d`)
**Verdict:** FAIL

The removal is correct at every door the sprint enumerated. It is incomplete at
the doors nobody enumerated. Three HTTP-reachable paths still perform the exact
in-place World switch this sprint exists to remove, and one of them is a single
click on a lab that has a World bound. Two of the three are the *same* root
cause the re-review filed as an open INFO and rated non-destructive; it is
destructive, and I have the failing test.

---

## Test inventory

`tests/test_worlds_select_removal_qa.py` — 22 cases, 19 pass, 3 strict-xfail
(each pins a live bug and flips to a failure the moment it is fixed).

| # | Test | Category | Covers | Status |
|---|---|---|---|---|
| 1 | `test_forge_confirm_over_a_mounted_world_is_refused` | edge/security | QA-1 — the fourth door | **XFAIL (bug)** |
| 2 | `test_forge_confirm_into_an_empty_root_still_mounts` | happy | forge on an unbound lab still binds | pass |
| 3 | `test_impostor_bundle_in_a_nested_dir_cannot_take_the_mounted_slug` | edge/security | QA-2 — basename-keyed exemption, `select` | **XFAIL (bug)** |
| 4 | `test_import_of_a_foreign_bundle_in_a_same_named_folder_is_refused` | edge/security | QA-3 — same exemption, `import`, unjailed path | **XFAIL (bug)** |
| 5 | `test_trailing_slash_and_dotdot_paths_do_not_bypass_the_guard` | edge | `b/`, `b/.`, `a/../b` all still 409 | pass |
| 6 | `test_slug_and_path_together_still_refused` | edge | both keys set; slug wins, neither bypasses | pass |
| 7–14 | `test_malformed_slugs_never_reach_mount_on_a_bound_lab` (8 params) | security/edge | empty, blank, `../physics`, `phys/../../etc`, NUL byte, Cyrillic `физика`, uppercase, 300 chars | pass |
| 15 | `test_non_dict_and_oversized_bodies_are_tolerated` | edge | array body, `null`, 5 KB path, `slug: null` — no 500, no mount | pass |
| 16 | `test_first_bind_into_an_empty_root` | regression | survivor #1 | pass |
| 17 | `test_unbind_is_allowed_from_any_state_and_is_idempotent` | regression | survivor #2, F1, 3× idempotent | pass |
| 18 | `test_unbind_still_works_after_the_bundle_dir_is_deleted` | regression | F3 un-brick, re-pinned independently | pass |
| 19 | `test_two_step_swap_is_the_permitted_path` | regression | the explicitly-permitted unmount→mount | pass |
| 20 | `test_cross_site_is_refused_before_the_new_guard` | security | F2 — envelope precedence, both `cross_site` and `cross_origin` | pass |
| 21 | `test_refusal_message_names_the_instance_command` | regression | the 409 is the only place the user learns the replacement | pass |
| 22 | `test_refused_select_leaves_the_mount_record_byte_identical` | regression | anti-`rmtree`: record bytes + staged dirs unchanged | pass |

Also exercised, unmodified: `tests/js/world_step_harness.mjs` **7/7** (welcome
first-bind and the mounted read-only variant), `tests/js/cloud_render_harness.mjs`
**3/3**, `test_world_switcher.py` / `test_world_import.py` /
`test_world_import_zip.py` / `test_instance_api.py` / `test_worlds_ui.py` /
`test_world_mount.py` / `test_worlds_docs_consistency.py` /
`test_instance_isolation.py` — all green.

---

## Failures

| # | Test | Symptom | Minimal repro | Severity |
|---|---|---|---|---|
| QA-1 | `test_forge_confirm_over_a_mounted_world_is_refused` | `POST /api/worlds/forge/confirm` mounts the freshly forged World over the bound one and sweeps its staged KB layer | mount `physics`; forge any subject; confirm → 200, `current_mount().world == "botany"`, `pkb/sources/world-physics` gone | **HIGH** |
| QA-2 | `test_impostor_bundle_in_a_nested_dir_cannot_take_the_mounted_slug` | a validly-sealed bundle declaring slug `impostor`, in a dir named `physics`, mounts over the bound `physics` | mount `worlds/physics`; `POST /api/worlds/select {"path": ".../worlds/backup/physics"}` → 200, `current=impostor`, staged set becomes `{world-impostor}` | **MEDIUM** |
| QA-3 | `test_import_of_a_foreign_bundle_in_a_same_named_folder_is_refused` | same exemption on `/api/worlds/import`, where the path is **not** jailed and is typed by the user in the nav dialog | mount `physics`; import `~/Downloads/physics/` containing a `chemistry` bundle → 200, `world-physics` swept | **MEDIUM** |

### QA-1 — the fourth door (`src/arail/portal/world_routes.py:433`)

```python
rec = wm.swap(catalog) if wm.current_mount() is not None else wm.mount(catalog)
```

`wm.swap()` runs `_sweep_other_worlds(pkb, bundle.slug)` (`world_mount.py:1579`)
— the identical destructive primitive that `mount()` runs at `:1469` and that
this sprint spent three guards closing off. There is no `current_mount()`
refusal, no `instance_live` check, and no user confirmation between the Forge
UI's confirm button (`worlds.js:552`) and the sweep.

Why the review pass missed it: the enumeration was done over `mount(` call
sites in `app.py`. This door calls `wm.swap()` from `world_routes.py`, and the
grep that found the three import/select doors would not have surfaced it. The
reviewer's own instruction to "read the ruling by its rationale, not its
enumeration" (REVIEW.md, BLOCK-1) applies here verbatim.

It also makes `docs/concurrent-worlds.md:139-142` false as written — it claims
`world swap` is "reachable from no UI surface (the browser, the nav dropdown,
and the welcome flow all only ever call `/api/worlds/select`)". The browser
reaches `wm.swap()` through forge confirm.

I did **not** guess at the fix. Two defensible shapes: (a) refuse with
`in_place_switch_removed` when a *different* World is bound, which is
consistent with the other three doors but changes forge UX (you must unmount
before confirming a forge); or (b) treat forge-confirm as a deliberate
operator action like the CLI's `world swap` and make it explicit in the UI plus
in the docs paragraph that currently denies it exists. (a) is the sprint's
stated invariant; (b) is a product call. That is the builder's and architect's
decision, not QA's — but shipping neither is not an option, because the docs
and the UI now both promise the user something the code does not do.

### QA-2 / QA-3 — the open INFO is reachable and it is destructive

REVIEW.md's re-review filed the basename-keyed exemption (`app.py:3487`,
`cur.world != target_slug`) as an INFO with the rationale: *"it destroys
nothing belonging to a different World (the sweep keeps that slug) … it is not
a reachable data-loss path."* Both halves are wrong.

- **It destroys.** The sweep keeps the *incoming bundle's declared slug*, not
  the directory basename that satisfied the exemption. A bundle in a dir named
  `physics` but declaring slug `impostor` sweeps `world-physics`. Verified
  end to end: `STATUS 200 · CUR impostor · STAGED {'world-impostor'}` (probe
  reproduced in test #3).
- **It is reachable without hand-crafting a nested path**, because the
  exemption is also on `/api/worlds/import` (`app.py:3589`), whose path is
  deliberately *not* jailed and comes straight from the "Add a World…" input
  in the nav dropdown, which renders on **every page**. The user only has to
  import a friend's bundle out of a folder whose name happens to match the
  World they have bound. That is a plausible accident, not an attack.

The comment at `nav.js:639-643` — "both `/api/worlds/import` and
`/api/worlds/import-zip` carry their own `in_place_switch_removed` guard,
refusing server-side when this root is already mounted" — is therefore still
not true of `/import`, in the same way it was not true of `/import-zip` before
BLOCK-1.

**Ruling on the open INFO: promote from INFO to MEDIUM, and it blocks.** The
BACKLOG's canonical-mount-record fix (option b) dissolves it, so the right
answer is probably to do option (b) now rather than to bolt a slug comparison
onto the exemption. Note that any fix must keep
`test_reselect_by_slug_after_external_import_allowed` (ASK-1's regression) and
`test_swap_by_path_while_mounted_refused` (F7) both green — that pair is the
narrow corridor the exemption has to fit through.

---

## Security review

| Surface | What I actually checked | Findings |
|---|---|---|
| CSRF envelope | Both refusals fire *before* the new guard on a bound lab: `sec-fetch-site: cross-site` → 403 `cross_site`; `origin: http://evil.example` with a matching same-origin fetch-site → 403 `cross_origin`. Mount record unchanged after both (test #20). F2 holds. | clean |
| Path traversal / jail | `_resolve_world_dir` (`app.py:3220-3247`) `.resolve()`s then prefix-checks with `root + os.sep`, so `..`, symlink-out and absolute escapes all fail closed; probed with `../physics`, `phys/../../etc`, `a/../b`, trailing slash, `b/.` (tests #5, #7-14). | clean |
| Input validation | `_SLUG_RE` rejects uppercase, NUL, Cyrillic, 300-char and blank slugs with 400/409 — never a 500, never a mount (test #7-14). Non-dict/`null`/5 KB bodies are coerced to `{}` and refused (test #15). | clean |
| Unjailed import path | `/api/worlds/import` accepts an arbitrary absolute dir by design (documented). It distinguishes "not a directory" (400) from "not a bundle" (409), which is a filesystem-existence oracle for a same-origin caller. Pre-existing, same trust boundary as a local-first lab's own file picker. | LOW, no action |
| Archive handling (import-zip) | `_safe_extract_bundle` zip-slip test present and green; `_ZIP_MAX_UPLOAD` cap is applied *after* `await upload.read()`, so a huge upload is spooled before rejection. Pre-existing; the new guard now short-circuits mounted labs before the body is read at all, which strictly improves it. | LOW, no action |
| Destructive-primitive reachability | Enumerated every caller of `mount()`/`swap()`/`_sweep_other_worlds` across `src/`: `app.py` ×3 (all guarded), `world_routes.py:433` (**unguarded — QA-1**), `world_routes.py:541` and `:890` (reseal/grow — both derive `bundle_dir` from `_mounted_catalog_dir()`, i.e. the World already bound, so the sweep keeps its own slug: **benign, confirmed by reading, not assumed**), `world_mount.py:1795` (CLI `world mount`). | 1 HIGH |
| Secrets / crypto / deps | No secrets path touched; no crypto; no new dependency in the diff. Bundle sealing (`verify_seal`) is unchanged by this sprint and still gates every mount that is reached. | clean |

---

## Regression sweep

Full suite: **3611 passed, 53 failed, 7 errors, 8 skipped, 5 xfailed** (12m49s).

The 7 errors and 5 of the failures are `tests/test_world_forge_api.py`, all one
environmental cause: `Egress blocked: host='huggingface.co'
caller='huggingface_hub.hf_api.HfApi.model_info' reason='airgapped'` — the
forge's `_curation_router()` reaches for a model hint before `forge_world` (the
seam these tests monkeypatch), so the fake never runs. Pre-existing, unrelated
to this sprint, consistent with the ~46-47F + 7E baseline on this lineage.

The remaining 48 failures span 24 files, none of them in the sprint's diff.
Spot-checked against the merge base `022a711` in a throwaway worktree —
`tests/portal/test_build_tab.py` (4F), `test_dashboard_layout_v2.py`,
`test_swarm_goal_surfaces.py` (2F), `test_reset_stop_scope.py` (2F),
`test_dac_rename.py` — all fail identically on the parent commit. **No
regression attributable to this sprint.**

**This is worth a follow-up on its own:** the forge-confirm suite is dark in
this environment, which is precisely why the fourth door survived three passes.
`tests/test_worlds_select_removal_qa.py` stubs `wr._curation_router`; doing the
same in `test_world_forge_api.py` would recover 12 tests and light up the path.

Everything in the sprint's blast radius is green: `test_world_switcher.py`,
`test_world_import.py`, `test_world_import_zip.py`, `test_worlds_ui.py`,
`test_world_mount.py`, `test_worlds_docs_consistency.py`,
`test_instance_api.py`, `test_instance_isolation.py`, `test_onboarding.py`,
`test_world_step_dom.py`, `test_world_first_impression.py`, plus both JS
harnesses (10/10). No test I added changes any existing test's meaning.

CLI: `./arailctl world … swap <dir>` (`arailctl:182`) does still exist and does
still switch in place; `docs/concurrent-worlds.md:139-146` documents it as a
deliberate CLI-only escape hatch and `test_worlds_docs_consistency.py` pins the
reconciliation. That part is honest and correct — except for the parenthetical
claiming no UI reaches `swap()`, which QA-1 falsifies.

## Performance

N/A. The guards add one `current_mount()` JSON read on user-initiated POSTs.
Nothing on a hot path; no benchmark warranted.

## Coverage delta

+22 cases on the select/import/forge mount seam, +8 previously untested input
classes on `POST /api/worlds/select`, and first-ever coverage of
`POST /api/worlds/forge/confirm` against a non-empty root.

## Notes for the next QA pass

1. **Enumerate by primitive, not by endpoint.** Three passes enumerated doors
   by grepping `mount(` in `app.py`. The bug lives in a different file behind a
   different verb. Grep `_sweep_other_worlds` and every transitive caller.
2. **A guard whose comparison mixes two namespaces will be wrong eventually.**
   `cur.world` (a name) vs `bundle_dir.name` (a basename) held only by the
   convention that `_adopt_into_catalog` names dirs after the World. Any
   re-fix should compare canonical identity, not strings that usually agree.
3. **A suite that is red for environmental reasons is a suite nobody reads.**
   `test_world_forge_api.py` has been dark long enough that a whole endpoint
   family stopped being regression-covered.
