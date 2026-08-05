# Build log: Bundled AeroLLM (Option B) — third install channel

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at c83db2f
**Started:** 2026-08-05

A2 (publishing a compiled aeroLLM binary on a public ARAIL release) was
confirmed by the maintainer before this build started — public binary
distribution is acceptable; aeroLLM's source repo and a public-PyPI package
listing stay off the table. This build follows §13's recommended order.

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `THIRD-PARTY-LICENSES/aerollm/{LICENSE,NOTICE,README.md,BUNDLE.json}`, root `NOTICE` | Compliance material first (§7, §13 step 2) | compliance tests (F10) | TBD |
| 2 | `scripts/package-aerollm-bundle.sh` | Producer script: cargo build → tarball + sha256 + MANIFEST.json, dirty-worktree refusal | manual local run against sibling | TBD |
| 3 | `scripts/build-aerollm.sh` | `bundle_install()` driven by `AEROLLM_BUNDLE_FILE`, no network yet (F1/F2/F4/F7) | unit tests | TBD |
| 4 | `scripts/build-aerollm.sh` | URL resolution + curl download + sha256 sidecar + https-only guard (F3/F5) | unit tests | TBD |
| 5 | `scripts/build-aerollm.sh` | `auto` third branch + `AEROLLM_CHANNEL` escape hatch | regression tests | TBD |
| 6 | `scripts/build-aerollm.sh` (`status`), `arailctl`, `scripts/setup.sh` | channel-aware status, `deep install`, setup messaging | tests | TBD |
| 7 | `src/arail/router/backends.py` | ImportError message — 3 ordered routes | contract test | TBD |
| 8 | `pyproject.toml`, `docs/cli.md`, `docs/releasing.md`, `CHANGELOG.md` | env knobs, release checklist, behavior-shift note | n/a (docs) | TBD |
| 9 | tarball build + local `AEROLLM_BUNDLE_FILE` acceptance run | §9.1 acceptance simulation (network-asset step not published — see Architect feedback) | manual | TBD |

## Execution

### Step 1 — compliance material
`THIRD-PARTY-LICENSES/aerollm/{LICENSE,NOTICE,README.md,BUNDLE.json}` +
root `NOTICE` paragraph. `LICENSE`/`NOTICE` are byte-identical copies read
from `~/ProJects/qukaizen-aerollm/{LICENSE,NOTICE}` (verified with `diff`).
`BUNDLE.json` was written with placeholder values, then overwritten with
the real manifest produced by step 2 so nothing in it is fabricated.
Commit: `c631bdc`.

### Step 2 — `scripts/package-aerollm-bundle.sh`
Producer script, run for real against `~/ProJects/qukaizen-aerollm` (a
READ-ONLY `cargo build --release -p aerollm-api --features extension-module`
— confirmed via `git status` in the sibling repo before/after: only the
pre-existing, pre-task-start dirty state (`M CLAUDE.md`, `?? Untitled.md`)
remained; nothing under `~/ProJects/qukaizen-aerollm` was created,
modified, or committed by this build). The sibling worktree was already
dirty from unrelated prior work, so `ALLOW_DIRTY=1` was used and
`MANIFEST.json.aerollm_dirty` honestly records `true` — the "verbatim"
claim in `THIRD-PARTY-LICENSES/aerollm/BUNDLE.json.modifications` reflects
that (see the note there). Produced
`dist/aerollm-bundle/aerollm-api-0.1.0-9e08230-macos-arm64.tar.gz` (22 MB
range; `dist/` is gitignored) at commit `9e08230f0bebfe5eeca5a2da3191fa4a96f24d2d`.
Commit: `b8e1e97`.

### Step 3-6 — `bundle_install()`, dispatch, status
Landed together (§13 steps 4-7 combined into one script commit for
reviewability — the failure-mode tests exercise each piece independently).
`AEROLLM_CHANNEL=dev|release|bundle` escape hatch; `auto`'s new third
branch; `status` channel-awareness. Verified live against the real
tarball from step 2, in a fresh throwaway venv acting as an "outside
user" interpreter (see §Acceptance below) — not just via the automated
test suite. Commit: `da4153a`.

### Step 6 (cont.) — `arailctl deep install`, `AeroLLMBackend` message, `setup.sh`
Three small, separately-reviewable commits: `arailctl` verb (`e634d7d`),
`AeroLLMBackend.__new__` ImportError three-route message (`92b4971`,
with its own contract test), `setup.sh` AeroLLM block comment/messaging
update — no dispatch-logic change there, `build-aerollm.sh auto` already
carries the real logic (`c18855a`).

### Step 6 (cont.) — tests
`tests/test_aerollm_bundle_install.py` (bash-level: F2/F3/F4/F7/F11 +
https-only guard + status channel line) and
`tests/test_aerollm_bundle_compliance.py` (F10 drift + compliance-file
existence). Commit: `1450a57`.

One test-authoring bug surfaced and was fixed before commit: the first
draft of `test_aerollm_backend_install_message.py` used
`importlib.reload(backends)` to force a clean `ImportError`, which
polluted other test files holding references to the pre-reload module
object (`test_aerollm_model_ready.py`,
`test_model_ux_phase0_warmth_probe.py` started failing when run in the
same session, despite passing standalone). Fixed by using
`monkeypatch.setitem(sys.modules, "aerollm_api", None)` instead — no
reload needed. Verified the fix against the *baseline* (pre-sprint) test
suite too, via `git stash`, to confirm a separate, pre-existing 9-test
ordering-pollution issue (kv_budget tests + `test_aerollm_model_ready.py`
sharing a singleton cache across test files) is unrelated to this sprint
— it reproduces identically with or without these changes.

### Step 9 — docs + CHANGELOG
`docs/cli.md` (`deep <op>` section rewritten with the channel table + env
knobs), `docs/releasing.md` (new — didn't exist; architecture allowed
either a new file or a new section), `CHANGELOG.md` (names the `auto`
behavior shift per F9, per the explicit instruction in ARCHITECTURE.md
§6.2). Commit: `aa77d6a`.

### Acceptance simulation (§9.1)

Ran the full "outside user" path for real, end to end, in this session:

1. Fresh venv (`python3 -m venv`), `import aerollm_api` confirmed absent.
2. `ARAIL_AEROLLM_REPO=/nonexistent` (no sibling source).
3. `AEROLLM_INDEX_URL=https://unreachable-index.invalid/simple/` (no
   silent RELEASE fallback possible).
4. `AEROLLM_BUNDLE_FILE=<the real tarball from step 2>` — standing in for
   the GitHub Release download, since the asset is **not yet published**
   (§9.1's network-asset step is therefore validated at the
   `bundle_install()` mechanism level, not the live-URL level — see
   "Not done" below).
5. `./arailctl deep install` → exit 0.
6. **Assert:** `python3 -c "import aerollm_api"` succeeds (confirmed);
   `./arailctl deep status` reports `channel: bundled` with version
   `0.1.0`, commit `9e08230`, build date (confirmed, output captured
   above in the session transcript).

**Not done, and explicitly flagged rather than silently downgraded per
§9.1's own instruction:**
- **The real curl-from-`github.com` download path is untested** — the
  release asset was never uploaded (task instruction: do not run
  `gh release upload`). `resolve_bundle_url()`'s URL construction and the
  404/offline failure path (F3) were tested against a real, deliberately
  nonexistent GitHub repo/tag (`tests/test_aerollm_bundle_install.py::
  test_curl_failure_names_resolved_url_and_exits_nonzero`), which
  exercises the same `curl` call — the only untested leg is "does a real
  asset at a real URL download successfully," which requires the asset
  to exist.
- **"a real chat turn routed through `AeroLLMBackend` returns non-empty
  text" (§9.1 step 6, last clause) is hardware-pending** — no model
  checkpoint was downloaded in this environment. Recorded here as a
  hardware-pending sub-gate, matching how the same caveat is handled
  elsewhere in this repo's aeroLLM correctness gates, rather than
  silently treating "imports" as "works."

### Publish step — intentionally not run

Per the task's explicit instruction, no GitHub Release was created or
modified. The maintainer runs, when ready:

```sh
gh release upload <arail-tag> \
    dist/aerollm-bundle/aerollm-api-0.1.0-9e08230-macos-arm64.tar.gz \
    dist/aerollm-bundle/aerollm-api-0.1.0-9e08230-macos-arm64.tar.gz.sha256
```

(the exact tarball this sprint built and verified end-to-end is staged
locally at that path — `dist/` is gitignored, so it did not enter git
history). Before running it: confirm the target `<arail-tag>` matches
`pyproject.toml`'s `aerollm_bundle_tag` (currently pinned to `v1.1.0` as
a placeholder for the next real ARAIL release), and add the "Bundled
third-party components" section to the release body per
`docs/releasing.md` step 5. **Note:** the bundle used for this sprint's
verification was built from a dirty sibling worktree
(`aerollm_dirty: true`) because the sibling repo already had unrelated
uncommitted changes (`CLAUDE.md`, `Untitled.md`) at task start; before
actually publishing, the maintainer should re-run
`scripts/package-aerollm-bundle.sh` from a clean sibling worktree to get
a strictly verbatim-commit bundle, and refresh
`THIRD-PARTY-LICENSES/aerollm/BUNDLE.json` accordingly.

## Architect feedback required

None. No part of the architect's plan needed revision — every interface
contract in §4, failure mode in §8, and test in §9 was implementable as
specified. The one operational wrinkle (sibling repo dirty at build time)
was anticipated by the architecture itself (§4.3, F11) and handled exactly
as designed.

## Final state

- **Commits:** 10 atomic commits on `qukaizen/arail-bundled-aerollm`
  (`351d5bf` BUILD_LOG skeleton → `aa77d6a` docs), all pushed.
- **New tests:** 3 files, 12 test functions
  (`test_aerollm_backend_install_message.py`,
  `test_aerollm_bundle_compliance.py`, `test_aerollm_bundle_install.py`) —
  all passing.
- **Regression:** `tests/` filtered to `-k aerollm` (150 tests): 141
  passing, 9 pre-existing failures confirmed unrelated to this sprint
  (reproduce identically on the pre-sprint baseline via `git stash`;
  root cause is unrelated cross-file singleton-cache pollution in
  `AeroLLMBackend._shared`, tracked separately — not introduced or
  touched by this build).
  `tests/test_aerollm_local_sibling_build.py` (DEV/RELEASE regression
  suite) and `tests/test_aerollm_compute_source.py`: 15/15 passing,
  unmodified.
- **Lint:** `shellcheck -x scripts/build-aerollm.sh scripts/package-aerollm-bundle.sh`
  clean. `bash -n` clean on all three touched shell scripts.
- **Lines changed:** `scripts/build-aerollm.sh` +244/-17;
  `scripts/package-aerollm-bundle.sh` new (155 lines); 3 new test files
  (~230 lines); compliance material (4 new files); doc/changelog updates.
- **Sibling repo (`~/ProJects/qukaizen-aerollm`):** confirmed untouched by
  this build beyond its own gitignored `target/` build output — no
  commits, no working-tree changes attributable to this sprint.

## Round 2 fixes

Response to [REVIEW.md](./REVIEW.md)'s BLOCK verdict. Four commits,
`85aa946` → `cd50850`.

### B1 — producer/consumer filename mismatch (BLOCK)

Adopted the tag-only convention `aerollm-api-<ARAIL release tag>-macos-arm64.tar.gz`
on both sides — it was already what `resolve_bundle_url()` requested, so
the fix is entirely in `package-aerollm-bundle.sh`: `ARAIL_RELEASE_TAG` is
now a required input (was optional, silently defaulting to `unreleased`
and a version+commit-based filename), and the output filename derives
from it directly. `docs/releasing.md` now spells out the exact filename
convention rather than saying "attach the tarball." Removed the dead
`AEROLLM_BUNDLE_ASSET` variable REVIEW.md flagged as tech debt.

Regression test added: `test_producer_filename_matches_consumer_resolved_filename`
in `tests/test_aerollm_bundle_install.py` — runs the real producer script
against a fake clean sibling repo (stubbed `cargo` on `PATH`) and the real
consumer's `bundle_install()` against an unreachable host, and asserts the
producer's output filename appears in the URL the consumer actually
requested. This is the exact gap REVIEW.md named as missing.

### B2 — `aerollm_bundle_tag` never reached `AEROLLM_BUNDLE_TAG` (BLOCK)

`setup.sh`'s `load_pyproject_metadata()` now reads
`[tool.arail.package-sources] aerollm_bundle_tag` into `AEROLLM_BUNDLE_TAG`
(mirroring the existing `AEROLLM_INDEX_URL`/`AEROLLM_PIP_SPEC` pattern
exactly), and the AeroLLM install block in `main()` forwards it to
`build-aerollm.sh auto` alongside those two. Verified both link points
directly rather than trusting the wiring by inspection: (1) a bumped
`aerollm_bundle_tag` pin is read correctly by the same `tomllib`
extraction `load_pyproject_metadata()` uses; (2) `AEROLLM_BUNDLE_TAG`
changes the URL `resolve_bundle_url()` constructs, confirmed against a
deliberately nonexistent GitHub repo/tag.

### A1 — LICENSE was the upstream stub, not the full text (ASK)

Read `~/ProJects/qukaizen-aerollm/LICENSE` directly, per instruction —
it turns out to be only the Apache-2.0 header boilerplate + copyright
line (17 lines), not the full ~200-line license. The task's assumption
that upstream had the full text was wrong; fixing upstream was
explicitly out of scope (no writes to the sibling repo beyond a
read-only `cargo build`). `THIRD-PARTY-LICENSES/aerollm/LICENSE` now
carries the full, standard Apache-2.0 text verbatim from
`apache.org/licenses/LICENSE-2.0.txt` with aeroLLM's copyright line —
this is the definitive, unambiguous published text, not a guess.
`NOTICE` is unchanged (byte-identical to upstream's, whose claim was
already accurate). `package-aerollm-bundle.sh` now copies the tarball's
`LICENSE` from ARAIL's own `THIRD-PARTY-LICENSES/aerollm/LICENSE`
instead of the sibling's stub, so what ships matches what's committed.
`tests/test_aerollm_bundle_compliance.py`'s byte-identity assertion is
split: `NOTICE` keeps the sibling-comparison test; `LICENSE` gets a
full-text-marker test (checks for section headers + line count) instead
of a byte-equality test that would have re-encoded the same bug.

### A2 — `BUNDLE.json` shipped `aerollm_dirty: true` (ASK)

The sibling worktree at `~/ProJects/qukaizen-aerollm` had unrelated
uncommitted changes (from a different, concurrent task) at build time —
genuinely dirty, not a bug in the dirty-check. Rather than hardcode
`false`, re-cut from an actually-clean tree: `git worktree add` against
the pinned commit `9e08230f0be...` (a separate, temporary checkout — no
writes to the sibling's real working tree), ran the real
`package-aerollm-bundle.sh` against it, confirmed `aerollm_dirty: false`
in the resulting `MANIFEST.json`, and copied that into
`THIRD-PARTY-LICENSES/aerollm/BUNDLE.json`. The worktree was removed
afterward (`git worktree remove --force`); `git -C
~/ProJects/qukaizen-aerollm status --porcelain` confirmed only the
original, pre-existing unrelated dirt remained.

### A3 — sha256 sidecar overclaimed as authenticity control (INFO)

Added an explicit "what this does and doesn't guarantee" paragraph to
`docs/cli.md` next to the `AEROLLM_BUNDLE_SHA256` knob: same-origin sidecar
catches corruption, not tampering; the real trust boundary is GitHub's TLS
+ repo access, not the checksum.

### Re-verification

- Regenerated the tarball from the clean worktree with
  `ARAIL_RELEASE_TAG=v1.1.0`: `dist/aerollm-bundle/aerollm-api-v1.1.0-macos-arm64.tar.gz`,
  `aerollm_dirty: false`, commit `9e08230f0bebfe5eeca5a2da3191fa4a96f24d2d`.
- §9.1 acceptance re-run: fresh venv, `ARAIL_AEROLLM_REPO=/nonexistent`, no
  PIP_INDEX_URL/PIP_EXTRA_INDEX_URL/netrc creds,
  `AEROLLM_BUNDLE_FILE=<the corrected-filename tarball>` → `auto` selects
  the bundled channel, checksum verifies, `import aerollm_api` succeeds,
  `deep status` reports `channel: bundled` with the right commit/version.
- Full suite: `pytest -k aerollm` → **144 passed, 9 failed** (same 9
  pre-existing failures as REVIEW.md's baseline — cross-file singleton-
  cache pollution in `AeroLLMBackend._shared`, unrelated to this sprint;
  zero regressions, 3 new tests added this round).
- `shellcheck -x scripts/build-aerollm.sh scripts/package-aerollm-bundle.sh`
  clean. `bash -n` clean on all three touched shell scripts.
- No `gh release` executed. Sibling repo confirmed untouched beyond the
  temporary worktree (removed) and its own gitignored `target/` output.

## Architect feedback required (round 2)

None. Both BLOCK findings and all ASK/INFO findings had clean, in-scope
fixes; nothing required a design change.
