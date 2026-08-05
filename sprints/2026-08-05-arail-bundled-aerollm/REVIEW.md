# Review: Bundled AeroLLM — a third install channel

**Date:** 2026-08-05
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `26228b5`
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at `c83db2f`
**Reviewed range:** `c83db2f^..26228b5` (10 commits)

## Verdict: BLOCK

Two defects break the headline user journey this sprint exists to deliver:
an outside user with no sibling repo and no index credentials getting the
2nd inference. Both are cheap to fix. Everything else in the sprint is
genuinely good work — the security posture of `bundle_install()` is sound
and I verified it by execution, not by reading.

---

## What I verified by running it, not by reading

| Check | Result |
|---|---|
| `THIRD-PARTY-LICENSES/aerollm/{LICENSE,NOTICE}` byte-identical to sibling repo | ✅ sha256 match (`608a1e3a…`, both 770 B / 384 B) |
| LICENSE/NOTICE embedded *inside* the tarball too | ✅ identical shas to repo copies |
| Tarball ↔ sidecar ↔ manifest internal consistency | ✅ sidecar = real tarball sha `0d602a69…`; manifest `sha256` = real `.so` sha `5e7c8e0c…` |
| sha256 verified **before** any copy | ✅ verify at L224–242, first `cp` at L261 |
| Fail-closed on tampered tarball | ✅ refused, exit 1, nothing installed |
| Fail-closed when **no** digest is obtainable | ✅ refused ("Refusing to install an unverified artifact") |
| F7 guard: existing `.so` with no provenance marker | ✅ refused without `--force` |
| Acceptance §9.1 (offline, no sibling, unreachable index) | ✅ **reproduced in a fresh venv** — `channel: bundled`, importable, exit 0 |
| Producer refuses a dirty aeroLLM worktree | ✅ code path correct (builder used `ALLOW_DIRTY=1`; see A2) |
| No new commits/pushes in sibling aeroLLM repo | ✅ HEAD still `9e08230`; dirt is pre-existing grammar work only |
| No `gh release` executed | ✅ appears only in doc text / an `info` echo |
| `shellcheck` both scripts | ✅ clean; `bash -n` clean |
| `AEROLLM_CHANNEL` leakage | ✅ confined to `build-aerollm.sh` + docs |
| New tests | ✅ 12/12 pass |
| Pre-existing-failure claim | ✅ **independently reproduced**: identical 9 failures at `c83db2f^`; 129→141 passed. Zero regressions. |

---

## Code quality findings

- **[BLOCK] B1 — the producer and the consumer disagree on the asset
  filename, so the default bundled channel 404s by construction.**
  `package-aerollm-bundle.sh:128-129` names the artifact
  `aerollm-api-${AEROLLM_VERSION}-${SHORT_COMMIT}-macos-arm64.tar.gz`
  → the real file on disk is `aerollm-api-0.1.0-9e08230-macos-arm64.tar.gz`.
  `resolve_bundle_url()` (`build-aerollm.sh:142-143`) requests
  `aerollm-api-${TAG}-macos-arm64.tar.gz`
  → `…/releases/download/v1.1.0/aerollm-api-v1.1.0-macos-arm64.tar.gz`.
  `docs/releasing.md:33` uploads the producer's name verbatim (`*.tar.gz`)
  and never instructs a rename. So the very first outside user to run
  `./arailctl deep install` gets a 404.
  This reclassifies the builder's disclosed gap: the GitHub path is not
  merely *untested*, it is *provably broken*. Fix by deriving one name from
  one source (simplest: have the producer emit the tag-named asset).

- **[BLOCK] B2 — `aerollm_bundle_tag` is never plumbed into
  `AEROLLM_BUNDLE_TAG`; three docs claim it is.**
  `pyproject.toml:258` pins `aerollm_bundle_tag = "v1.1.0"`, and
  `build-aerollm.sh:53-54`, `docs/cli.md:338` and
  `THIRD-PARTY-LICENSES/aerollm/README.md:21,39` all state that `setup.sh`
  overrides the env var from it. It does not — `setup.sh:659` forwards only
  `AEROLLM_INDEX_URL` and `AEROLLM_PIP_SPEC`. The only reader of the pin is
  the compliance *test*. Consequence: the hardcoded default at
  `build-aerollm.sh:57` is the true source of truth, and a maintainer
  following `docs/releasing.md` step 4 (bump the pin) will see the drift
  test go green while the download URL silently does not move. Either wire
  it through `setup.sh` or delete the claim and document the constant as
  authoritative.

- **[ASK] A5 — `_release_creds_configured()` under-detects, diverting
  maintainers to the bundled channel.** It checks `PIP_INDEX_URL`,
  `PIP_EXTRA_INDEX_URL`, a non-default `AEROLLM_INDEX_URL`, and `~/.netrc`.
  It misses `pip.conf` / `PIP_CONFIG_FILE` / keyring — the most common way
  to configure a private index. Such a machine now silently gets BUNDLED
  where it used to get RELEASE. The CHANGELOG discloses the fallthrough
  change honestly, but names `AEROLLM_CHANNEL=release` as the remedy
  without noting pip.conf users are affected.

- **[INFO] A4 — the extraction comment overclaims.** `build-aerollm.sh:246-248`
  says copying out four filenames means "a tarball with unexpected/`../`
  entries can't escape", but `tar xzf` has already extracted everything by
  then; the selective copy limits what is *installed*, not what is
  *written*. Real risk is low (post-checksum, maintainer-produced artifact),
  but the comment should say what the code does. `--no-same-owner
  --no-xattrs` and an explicit member list would make it true.

- **[INFO] Version-universe inconsistency (pre-existing, surfaced here):**
  `pyproject.toml` pins `aerollm = "aerollm-api>=1.0,<2.0"`, `setup.sh:133`
  uses `>=0.1,<0.2`, and the bundle ships `0.1.0`. Not introduced by this
  sprint, but the bundled channel now makes the disagreement user-visible.

## Security findings

- **[INFO] A3 — the digest is a corruption check, not an authenticity
  control.** When `AEROLLM_BUNDLE_SHA256` is unset, the expected digest is
  fetched from `${url}.sha256` — same origin, same transport, same trust
  boundary as the tarball (L216-219). Anyone who can serve the artifact can
  serve a matching digest. Combined with `AEROLLM_BUNDLE_URL` accepting any
  https origin, a malicious mirror is fully trusted. The real integrity
  guarantee here is GitHub's TLS, not the sha256. This is an acceptable
  posture for v1 — but `CHANGELOG.md` and `docs/releasing.md` should not
  let a reader infer supply-chain integrity. The committed
  `BUNDLE.json.sha256` is the trustworthy pin; recommend the installer
  prefer it over the sidecar.
- ✅ https-only scheme check before `curl` (L202-205). Good.
- ✅ Platform guard fires before any network call (L148-152). Good.
- ✅ F1 rollback removes a broken artifact rather than leaving it shadowing
  a future good install (L264-271). Verified by reading; matches design.
- ✅ No secrets, no credential handling, no new dependencies.

## Test coverage assessment

12 new tests, all passing; 141 passed / 9 failed under `-k aerollm`, with
the 9 failures independently reproduced on the pre-sprint tree. Coverage of
the design's failure table is good for F1/F2/F4/F5/F7/F10/F11.

**Gap:** no test asserts that the producer's output filename is the one the
consumer requests. That single assertion would have caught B1. It is the
required regression test for this fix.

## Tech debt delta

Roughly as ARCHITECTURE.md predicted (a manual, uncached release step), with
two unanticipated items: the dead `aerollm_bundle_tag` plumbing (B2) and the
unused `AEROLLM_BUNDLE_ASSET` variable declared at L58 but never read.

- **[ASK] A2 — the shipped pin has dirty provenance.**
  `THIRD-PARTY-LICENSES/aerollm/BUNDLE.json` is committed with
  `"aerollm_dirty": true` and a `modifications` string admitting it is not a
  verbatim build of `9e08230`. The mechanism worked exactly as designed —
  it told the truth — but a compliance manifest asserting an
  unattributable build should not be the committed pin for `v1.1.0`.
  Re-cut from a clean worktree before tagging.

- **[ASK] A1 — the bundled `LICENSE` is a stub, not the Apache-2.0 text.**
  This is the one my own design got wrong: I specified "byte-identical to
  upstream" as the acceptance criterion, and the builder met it exactly.
  But upstream's `LICENSE` is 17 lines — the Apache *header boilerplate*
  plus a copyright line — not the ~200-line license. Apache-2.0 §4(a)
  requires giving recipients "a copy of this License," and the adjacent
  `NOTICE` says "See the LICENSE file for the full license text," which is
  false as shipped. Since redistributing a compiled Object form is the
  entire premise of this sprint, byte-identity was the wrong test.
  Recommended: fix upstream in `qukaizen-aerollm` (full license text), then
  re-sync — that repairs both repos. My design defect, not the builder's.

## Required actions before merge

1. **B1** — make the producer emit, or `releasing.md` explicitly rename to,
   the exact filename `resolve_bundle_url()` requests. Derive both from one
   source.
2. **B1-test** — add a regression test asserting producer output name ==
   consumer requested name.
3. **B2** — either wire `aerollm_bundle_tag` → `AEROLLM_BUNDLE_TAG` through
   `setup.sh`, or delete the three claims that it already happens.
4. **A1** — replace the stub `LICENSE` with the full Apache-2.0 text
   (upstream first), or correct the NOTICE sentence.
5. **A2** — re-cut `BUNDLE.json` and the tarball from a clean aeroLLM
   worktree before tagging `v1.1.0`.
6. **A3/A5/A4** — acceptable as follow-ups if ticketed: prefer the committed
   `BUNDLE.json.sha256` over the same-origin sidecar; widen
   `_release_creds_configured()` to `pip.conf`/`PIP_CONFIG_FILE`; correct
   the extraction comment. Remove the unused `AEROLLM_BUNDLE_ASSET`.

Once 1–5 land, this is a PASS. The hardware-pending chat-turn gap is
acceptable to ship disclosed — the `.so` demonstrably loads and imports in a
clean interpreter, which is the part this sprint owns.
