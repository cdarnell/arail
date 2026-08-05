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

(filled in as steps land)

## Architect feedback required

(empty unless the architect's plan needs revision mid-build)

## Final state

(numbers: tests passing, coverage delta, lines changed — filled in at the end)
