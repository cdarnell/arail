# Test report: Bundled AeroLLM — a third install channel

**Date:** 2026-08-05
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `d29e53b` · [REVIEW.md](./REVIEW.md) round 3 (`000c251`)
**Branch:** `qukaizen/arail-bundled-aerollm`
**Verdict:** **FAIL** — 1 new failing test, 2 medium security findings, 1 medium
onboarding finding. Nothing requires a design change; all four required fixes
are small and local. **Do not run `gh release upload` until Q1 and Q7 close.**

Allocation per this repo's `CLAUDE.md`, adapted for a distribution/install
feature rather than a Buddy-quality one: 30% setup-on-clean-machine ·
30% security · 20% onboarding clarity · 10% happy path · 10% regression.

---

## Summary

The **mechanics** are genuinely sound, and I confirmed that by execution
rather than by reading: checksum-before-copy ordering, F1 rollback, the
https-only scheme guard, the platform guard, fail-closed-on-no-digest, `auto`
dispatch, the licence material, and the artifact/sidecar/manifest sha chain
all behave exactly as ARCHITECTURE.md §4/§8 specifies. Three review rounds got
the mechanics right.

What the three rounds did not exercise is the layer *around* the mechanics:

1. The **only documented independent-verification path** for a channel that
   downloads and executes native code is **non-functional**. `docs/cli.md`
   tells the user to pass `THIRD-PARTY-LICENSES/aerollm/BUNDLE.json`'s
   `sha256` as `AEROLLM_BUNDLE_SHA256`, but that field is the digest of the
   `.so` while `AEROLLM_BUNDLE_SHA256` is compared against the *tarball*.
   Following the docs yields "Checksum mismatch — refusing to install." (**Q1**)
2. **ARCHITECTURE.md §9.1 step 3's acceptance recipe is self-defeating.** It
   instructs setting `AEROLLM_INDEX_URL` to an unreachable host "so a silent
   RELEASE fallback cannot rescue the run", but `_release_creds_configured()`
   reads any non-default `AEROLLM_INDEX_URL` as configured credentials, so
   that instruction **selects RELEASE and never reaches BUNDLED**. Reproduced.
   (**Q2**)
3. `setup.sh`'s AeroLLM failure message still names only `deep rebuild` and
   `deep update` — the two **maintainer-only** routes — and never `deep
   install`, the outside-user route this sprint exists to add. (**Q7**, the
   one red test)
4. The "integrity, not authenticity" caveat lives **only** in `docs/cli.md`'s
   CLI reference. Not in README, not in SECURITY.md, not in docs/INSTALL.md,
   not in `THIRD-PARTY-LICENSES/aerollm/README.md`, and not printed by the
   installer. `./arailctl setup` on maximus downloads and *executes* a
   prebuilt native binary with no prompt and no disclosure. (**Q5**)

Q5 is sharpened by the fact that **this repo already has the right pattern**:
the `ai-eng` GGUF download pins `ai_eng_sha256` in `pyproject.toml` and
fail-closes until a real digest is committed (CHANGELOG:512). The bundled
AeroLLM channel — higher risk, because it is executable code — does not follow
its own repo's precedent.

---

## Test inventory

`tests/test_aerollm_bundle_qa_hardening.py` — 30 new tests (29 pass, 1 fails
on a real defect). Every row was run.

| # | Test | Category | Covers | Status |
|---|---|---|---|---|
| 1 | `test_truncated_archive_with_matching_digest_installs_nothing` | edge | truncated download whose sidecar was regenerated over the truncated bytes (also: partial write to a full disk) | pass — fails closed |
| 2 | `test_non_archive_bytes_install_nothing` | edge | `AEROLLM_BUNDLE_FILE` at an HTML error page / random file | pass — fails closed |
| 3 | `test_traversal_member_cannot_escape_the_extraction_dir` | security | tar member `../../../ESCAPED.txt` | pass — bsdtar refuses, nothing escapes, install aborts |
| 4-7 | `test_bundle_missing_any_expected_member_is_refused[x4]` | edge | each of the four required members absent | pass — named in the error, nothing installed |
| 8 | `test_unloadable_so_is_rolled_back_leaving_no_shadowing_artifact` | edge/F1 | `.so` with Mach-O magic but a garbage body | pass — rollback complete |
| 9-12 | `test_status_survives_a_corrupt_provenance_marker[x4]` | edge | empty / malformed JSON / `null` schema / NUL-byte marker | pass — exit 0, no traceback |
| 13 | `test_corrupt_marker_does_not_block_reinstall` | edge | idempotence short-circuit on a corrupt marker | pass — self-heals |
| 14 | `test_auto_selects_release_when_aerollm_index_url_is_overridden` | regression | pins the §9.1 trap (Q2) | pass (documents defect) |
| 15 | `test_auto_selects_bundled_with_no_sibling_and_no_index_override` | happy | the headline outside-user journey | pass |
| 16-18 | `test_aerollm_channel_accepts_exactly_the_three_documented_values[x3]` | regression | `dev`/`release`/`bundle` honoured | pass |
| 19 | `test_unknown_aerollm_channel_exits_2_and_enumerates` | edge | `bundled`, `BUNDLE`, ` bundle` → exit 2 | pass |
| 20 | `test_committed_bundle_json_sha256_is_the_so_digest_not_the_tarball_digest` | security | pins the digest semantics behind Q1 | pass (documents defect) |
| 21 | `test_no_digest_available_refuses_rather_than_installing` | security | fail-closed with no sidecar and no pin | pass |
| 22-26 | `test_non_https_bundle_url_is_refused_before_any_fetch[x5]` | security | `http://`, `file://`, `ftp://`, bare path, `javascript:` | pass — all refused pre-`curl` |
| 27 | `test_f7_guard_message_on_an_interrupted_bundle_install` | edge | F7 misdiagnosis after an interrupted install (Q6) | pass (pins current behaviour) |
| 28 | `test_platform_guard_refuses_before_any_network_or_disk_write` | setup | F4 ordering vs the scheme guard | pass |
| 29 | `test_cli_docs_disclose_the_sha256_trust_boundary` | security/docs | the A3 caveat stays in `docs/cli.md` | pass |
| 30 | `test_setup_failure_message_names_the_outside_user_route` | onboarding | Q7 | **FAIL** |

Manual scenarios run outside pytest (transcripts below): live 404 against the
real not-yet-uploaded release URL; total-offline DNS failure;
maintainer-machine `auto` → DEV; `AEROLLM_CHANNEL=release` → pip; a fresh
`/usr/bin/python3 -m venv` outside-user install from the real v1.1.0 tarball;
`--force` override; and a benign arbitrary-code-execution proof of concept.

---

## Failures

| # | ID | Symptom | Repro | Severity |
|---|---|---|---|---|
| 1 | **Q1** | The one documented out-of-band digest override is unusable, and fails with a message that looks like artifact corruption | below | **Medium (security)** |
| 2 | **Q7** | `setup.sh`'s failure message sends outside users to two maintainer-only routes | `pytest tests/test_aerollm_bundle_qa_hardening.py -k outside_user_route` | **Medium (onboarding)** |
| 3 | **Q2** | ARCHITECTURE.md §9.1 step 3's acceptance recipe selects RELEASE, not BUNDLED | below | **Medium (process)** |
| 4 | **Q5** | The download-and-execute trust boundary is disclosed only in a CLI reference | doc gap | **Medium (security)** |
| 5 | **Q4** | Corrupt/truncated/non-archive input exits with a raw `tar` error and no guidance | below | Low (grace) |
| 6 | **Q6** | An interrupted install wedges into an F7 refusal that misdiagnoses the cause | test 27 | Low (grace) |
| 7 | **Q3** | `aerollm-api` **is** on public PyPI; ARCHITECTURE §2/§11 say it is not | below | Low (factual) |
| 8 | **Q8** | `bundle: channel: unknown (...)` prints a duplicated label | test 9 output | Info |
| 9 | **A7** | Carried from REVIEW round 3, still open: the "real dist untouched" snapshot is taken *after* the subprocess | `tests/test_aerollm_bundle_install.py:232` | Info |

### Q1 — the documented out-of-band digest is the wrong object (Medium, security)

`docs/cli.md`, §`deep <op>`, "What the sha256 check does and doesn't guarantee":

> If you need a digest independent of that origin, pass
> `AEROLLM_BUNDLE_SHA256` explicitly from a value you obtained out-of-band
> (e.g. the committed `THIRD-PARTY-LICENSES/aerollm/BUNDLE.json`).

Doing exactly that:

```console
$ BUNDLE_SHA=$(python3 -c "import json;print(json.load(open('THIRD-PARTY-LICENSES/aerollm/BUNDLE.json'))['sha256'])")
$ AEROLLM_BUNDLE_SHA256=$BUNDLE_SHA \
  AEROLLM_BUNDLE_FILE=dist/aerollm-bundle/aerollm-api-v1.1.0-macos-arm64.tar.gz \
  bash scripts/build-aerollm.sh bundle
• Using local bundle tarball: .../aerollm-api-v1.1.0-macos-arm64.tar.gz (offline path).
✗ Checksum mismatch — refusing to install.
!   expected: 2776d188f71c98bfb46b1e87f2f5e8aa4f30146541d0748e3321cd0364650f9a
!   actual:   d3a7a9dd19987350963422ab7647a2d4ad607e78397b57f70c55362c0b95ecce
EXIT=1
```

`BUNDLE.json.sha256` is the digest of `aerollm_api.abi3.so` (`2776d188...`);
`AEROLLM_BUNDLE_SHA256` is compared against the *tarball* (`d3a7a9dd...`).
Different objects; they can never match. Consequences:

- The only mitigation offered for the acknowledged same-origin trust weakness
  cannot be used, and the user who tries it is told the artifact is corrupt.
- REVIEW round 1's A3 recommendation — "recommend the installer prefer
  [`BUNDLE.json.sha256`] over the sidecar" — is likewise unimplementable as
  written, which is presumably why it was never implemented.
- `MANIFEST.json.sha256` travels *inside* the tarball and is never verified
  against the extracted `.so` at any point. A trusted, committed pin exists in
  git and is dead weight.

**Recommended fix (follows this repo's own `ai_eng_sha256` precedent):** add
`aerollm_bundle_sha256` to `pyproject.toml [tool.arail.package-sources]` next
to `aerollm_bundle_tag`, holding the **tarball** digest; have `setup.sh`
forward it as `AEROLLM_BUNDLE_SHA256` exactly as it now forwards
`AEROLLM_BUNDLE_TAG`; add a `docs/releasing.md` step-4 bullet to bump it.
Separately and cheaply: after extraction, verify the `.so` against
`MANIFEST.json.sha256`. Then correct the `docs/cli.md` sentence.

### Q2 — the §9.1 acceptance recipe selects the wrong channel (Medium, process)

```console
$ env -i HOME=... PATH=... PYTHON=<fresh venv> \
    ARAIL_AEROLLM_REPO=/nonexistent \
    AEROLLM_INDEX_URL=https://unreachable-index.invalid/simple/ \
    AEROLLM_BUNDLE_FILE=dist/aerollm-bundle/aerollm-api-v1.1.0-macos-arm64.tar.gz \
    bash scripts/build-aerollm.sh auto
• Release-index credentials configured → installing the published wheel (release channel).
...
Successfully installed aerollm-api-0.1.0rc2
• AeroLLM ready (release wheel 0.1.0-rc.2) — the 2nd inference.
EXIT=0
```

`_release_creds_configured()` (`build-aerollm.sh:278`) returns true for *any*
non-default `AEROLLM_INDEX_URL`, so §9.1 step 3's instruction — added
specifically to prevent a RELEASE rescue — guarantees a RELEASE run. The
acceptance bar as written has therefore never been executed as specified;
BUILD_LOG round 2 and REVIEW round 2 both note they omitted
`AEROLLM_INDEX_URL`, which is what made their runs land on BUNDLED. The
channel does work (reproduced, §Setup below) — the *recipe* is wrong and must
be corrected so the next person does not get a false green.

**Fix:** §9.1 step 3 should say "leave `AEROLLM_INDEX_URL` unset", relying on
`ARAIL_AEROLLM_REPO=/nonexistent` + no `PIP_*` + no netrc. Test 14 pins the
real dispatch behaviour.

### Q7 — `setup.sh` sends outside users to maintainer-only routes (Medium, onboarding)

`scripts/setup.sh:668-670`:

```sh
warn "AeroLLM not installed (see above). The lab runs without the"
warn "2nd inference until you run: ./arailctl deep rebuild (or: deep update)"
```

`deep rebuild` needs the private aeroLLM source repo; `deep update` needs
`pypi.qukaizen.com` credentials. The outside user this sprint exists for has
neither, and the one route that would work — `./arailctl deep install` — is
not named. The comment block above this code *was* updated in `c18855a`; the
user-visible string was not. The Apple-Silicon-only `else` branch two lines
below has the same problem.

This is exactly the B1/B2 class the reviewer already caught twice: the
mechanism is right, the string a human reads points elsewhere.

### Q4 — malformed archives exit with a raw `tar` error (Low, grace)

ARCHITECTURE.md §4.1 promises "a one-screen actionable message" on any
failure. `tar xzf` at `build-aerollm.sh:247` has no error handling, so under
`set -e`:

```console
$ AEROLLM_BUNDLE_FILE=<truncated tarball w/ matching sidecar> bash scripts/build-aerollm.sh bundle
• Checksum verified (sha256 2e673879f6c5…).
aerollm_api.abi3.so: truncated gzip input: Unknown error: -1
tar: Error exit delayed from previous errors.
EXIT=1

$ AEROLLM_BUNDLE_FILE=<non-archive file> ...
tar: Error opening archive: Unrecognized archive format
EXIT=1
```

Fails closed and installs nothing (verified) — but no `✗`, no retry advice, no
`AEROLLM_BUNDLE_FILE` hint. This is also the disk-full-mid-extract path. Wrap
the `tar` call in the same `if ! ...; then err/warn; fi` shape `curl` uses.

### Q6 — an interrupted install misdiagnoses itself (Low, grace)

Interrupt between the `cp` of the `.so` (L260) and the `cp` of the marker
(L261) — Ctrl-C, full disk, power loss — and the machine keeps an unmarked,
unloadable `.so`. Thereafter:

```console
$ bash scripts/build-aerollm.sh status
    aerollm_api:  not installed — run: ./arailctl deep install (...)
    channel:      none

$ bash scripts/build-aerollm.sh bundle          # follow that advice
✗ aerollm_api.abi3.so is already installed at .../aerollm_api.abi3.so without a
✗ bundle provenance marker — looks like a DEV or RELEASE install owns it.
! Refusing to overwrite. Re-run with --force to install the bundled channel anyway.
EXIT=1
```

`status` and `bundle` contradict each other, and the diagnosis ("a DEV or
RELEASE install owns it") is false on a machine with neither. `--force` is at
least named, so the user is not stuck — hence Low. **Fix:** skip the F7 guard
when `import_ok` already fails (nothing owns a broken `.so`), and/or write the
marker first, and/or `cp` to a temp name + `mv` for atomicity. This is the
same over-broad guard that produced REVIEW round-2 B4.

### Q3 — `aerollm-api` is already on public PyPI (Low, factual)

ARCHITECTURE.md §2 states "the documented public-PyPI fallback has nothing
published on it", and §11 lists "No public-PyPI publication of `aerollm-api`"
as a non-goal. Both are false today:

```console
$ curl -s https://pypi.org/pypi/aerollm-api/json | ...
name: aerollm-api   version: 0.1.0rc2
author: Charles Darnell charlesadarnell@gmail.com
  0.1.0rc1 aerollm_api-0.1.0rc1-cp39-abi3-macosx_11_0_arm64.whl  2026-05-23
  0.1.0rc2 aerollm_api-0.1.0rc2-cp39-abi3-macosx_11_0_arm64.whl  2026-06-08
```

It is the maintainer's own package, so this is not name-squatting, and
`pip_install()`'s `--extra-index-url https://pypi.org/simple/` is not a live
dependency-confusion hole *because the name is owned* — keep it owned. But it
does mean an outside user already had a credential-free deep-mode path via the
RELEASE channel's public fallback, which is the gap §2 says does not exist.
The sprint is still worth shipping — the bundle carries a newer aeroLLM
(`0.1.0` @ `9e08230`) than PyPI's two-month-old `rc2`, and does not depend on
PyPI at all — but §2/§11 should be corrected before this is presented as "the
only way outside users get deep mode". Two adjacent hygiene notes: the PyPI
metadata's `Homepage` points at `github.com/cdarnell/aerollm` (not the real
repo name), and `AEROLLM_PIP_SPEC` defaults to a bare, unpinned `aerollm-api`
at `build-aerollm.sh:51`.

---

## Setup on a clean machine (30%)

Ran as an outside user with **no** special-casing for this machine's existing
aeroLLM build (REVIEW round-1/2's F7 trap): a brand-new
`/usr/bin/python3 -m venv`, `HOME` redirected to an empty dir, `env -i` with
`AEROLLM_CHANNEL` / `AEROLLM_INDEX_URL` / `PIP_*` all unset, and
`ARAIL_AEROLLM_REPO=/nonexistent`.

**The sideload path is real, documented, and works.** `AEROLLM_BUNDLE_FILE` is
implemented at `build-aerollm.sh:186-197`, documented in `docs/cli.md`'s
env-knob table, and is the mechanism for both offline installs and pre-upload
local testing:

```console
$ env -i HOME=<empty> PATH=/usr/bin:/bin PYTHON=<fresh venv>/bin/python3 \
    ARAIL_AEROLLM_REPO=/nonexistent \
    AEROLLM_BUNDLE_FILE=dist/aerollm-bundle/aerollm-api-v1.1.0-macos-arm64.tar.gz \
    bash scripts/build-aerollm.sh auto
• No sibling repo, no release credentials → installing the bundled binary (bundled channel).
• Using local bundle tarball: .../aerollm-api-v1.1.0-macos-arm64.tar.gz (offline path).
• Checksum verified (sha256 d3a7a9dd1998…).
• Installing → .../qa/v2/lib/python3.9/site-packages/aerollm_api.abi3.so
• AeroLLM ready (bundled 0.1.0) — the deep-mode 2nd inference.
EXIT=0

$ ... bash scripts/build-aerollm.sh status
    aerollm_api:  importable ✓ (version 0.1.0)
    channel:      bundled
    bundle:       aerollm 0.1.0 (9e08230, built 2026-08-05T13:59:09Z)
```

**Today's real outside-user experience (asset not yet uploaded)** — clean,
actionable degradation, the right pre-upload state:

```console
$ ... bash scripts/build-aerollm.sh bundle
• Downloading AeroLLM bundle from https://github.com/cdarnell/qukaizen-arail/releases/download/v1.1.0/aerollm-api-v1.1.0-macos-arm64.tar.gz…
curl: (56) The requested URL returned error: 404
✗ Could not download the bundle asset: ...
! Either this ARAIL release has no bundled AeroLLM (run: ./arailctl deep status),
! or you're offline — set AEROLLM_BUNDLE_FILE to a local tarball instead.
EXIT=1
```

**Fully offline (DNS blackhole)** — same message, same exit 1. Good.

**Hardware-pending (carried, unchanged):** "a real chat turn routed through
`AeroLLMBackend` returns non-empty text" (§9.1 step 6, last clause) still has
no model checkpoint in this environment. Import, version and provenance are
proven; inference is not. Correctly disclosed by BUILD_LOG; not downgraded.

---

## Security review (30%)

| Surface | What I actually checked | Findings |
|---|---|---|
| **Deserialization / code execution** | Whether `bundle_install()` does *anything* beyond a sha256 before `cp`-ing a `.so` into site-packages and `import`-ing it. It does not: no Mach-O magic check, no `file`/`lipo` arch check, no `codesign --verify`, no notarization check, no signature of any kind. I built a **benign** arm64 `.so` with a `__attribute__((constructor))` that writes a marker file, gave it a regenerated matching sidecar, and installed it. | **Q5.** Payload ran: `arbitrary code executed at import time`. `verify_or_die`'s `import` *is* the execution. The F1 rollback then deleted the `.so` — removing the evidence *after* the code had already run. Blast radius: full user-level RCE. |
| **Transport / origin** | `https://`-only guard at L201 fires before `curl` (verified with `http://`, `file://`, `ftp://`, a bare path and `javascript:`). `curl -fsSL --retry 2`, no `-k`, no `--proxy-insecure`. Digest sidecar is same-origin (L215-219). `AEROLLM_BUNDLE_URL` accepts **any** https origin — a fork/mirror is fully trusted with its own sidecar. | Scheme guard sound. Same-origin trust is the accepted v1 posture, honestly documented in `docs/cli.md` — but **only** there (Q5), and its stated mitigation is broken (Q1). |
| **Integrity ordering** | Verify at L223-241, first `cp` at L260 — re-confirmed by execution: a tampered tarball installs nothing. Fail-closed when no digest is obtainable ("Refusing to install an unverified artifact"). | OK |
| **File I/O / path traversal** | Extraction into a fresh `mktemp -d` under `$TMPDIR`; crafted a tarball with a `../../../ESCAPED.txt` member and ran it. macOS bsdtar rejects it (`Path contains '..'`) and `set -e` aborts the install; no file written outside the temp dir. Symlink-member escape is bounded by the `-C` dir plus the four-name copy-out allowlist. The `EXIT` trap cleaned `$BUNDLE_TMP` on every exit path exercised. | Safe on the only supported platform. REVIEW's INFO A4 (the comment overclaims *why*) stands as a comment-accuracy nit; `--no-same-owner --no-xattrs` and an explicit member list would make it true, and would matter if the platform guard ever widens. |
| **Env / config injection** | `grep -rn AEROLLM_BUNDLE scripts/ src/` — only `AEROLLM_BUNDLE_TAG` is read from `pyproject.toml`. `AEROLLM_BUNDLE_URL` / `_FILE` / `_SHA256` / `_REPO` come from the ambient environment **only**; no `.env`, `lab.conf`, `secrets.env` or World bundle can set them. | Good — a mounted World cannot redirect the download origin. |
| **Shell quoting** | `AEROLLM_BUNDLE_FILE` is never `eval`'d; `cp -f -- "$AEROLLM_BUNDLE_FILE"` uses `--`; `curl -- "$url"`. `shellcheck -x` clean on both scripts. | One nit: the marker path is interpolated into a Python string literal at L171 and L321 (`json.load(open('$dest_marker'))`) — a `platlib` containing `'` breaks it. Not attacker-controlled in practice; use `sys.argv`. |
| **Secrets** | No token, netrc content or index URL is printed by `bundle_install()` or `status` (the `index:` line shows only the configured URL, already public). No credential handling added. | OK |
| **Dependencies** | Zero new Python or system dependencies. `curl`, `tar`, `shasum`, `xattr` are all macOS base. | OK |
| **Supply chain (upstream)** | Whether `aerollm-api` on public PyPI is the maintainer's or a squatter's. | Maintainer's own (Q3) — keep the name owned; `pip_install()`'s `--extra-index-url https://pypi.org/simple/` would otherwise be a live dependency-confusion path. |
| **Licence / redistribution** | Re-verified the artifact chain end to end: tarball sha == sidecar; `BUNDLE.json` == in-tarball `MANIFEST.json`; in-tarball `LICENSE`/`NOTICE` == repo copies; `LICENSE` is full Apache-2.0 (204 lines, not the 17-line upstream stub). | OK |

**Net position.** The `.so` is executed with only a same-origin integrity
check, one hop of trust from a GitHub Release. That is a *defensible* v1
posture for a public repo. It is **not** defensible while (a) the documented
escape hatch is broken, (b) the caveat appears nowhere a downstream user reads
before running `./arailctl setup`, and (c) the repo already fail-closes on an
out-of-band pin for a *less* dangerous artifact (`ai_eng_sha256`). Fix Q1 + Q5
and this drops to Low/accepted.

---

## Onboarding clarity (20%) — `docs/releasing.md` + help text, end to end

**`docs/releasing.md` — good.** The B1/B2/B3 lessons are genuinely encoded:
step 3 spells out the filename convention with a worked example and names the
tag-mismatch invariant as "the single most important invariant in this
checklist"; step 4's LICENSE bullet is emphatic ("DO NOT sync this from
upstream") with the why and a pointer at the guarding test. The `gh release
upload <tag> dist/aerollm-bundle/*.tar.gz dist/aerollm-bundle/*.tar.gz.sha256`
glob is correct (the first glob does not also match the sidecar).

Gaps a fresh contributor would hit:

- **R1.** Step 4 omits `aerollm_bundle_sha256` because it does not exist yet
  (Q1). If Q1 is fixed, this checklist must gain the bullet or the next
  release ships a stale pin — the exact F10 drift class the compliance test
  exists for.
- **R2.** The checklist never says **"verify the upload before announcing"**.
  Since the pre-upload state is a silent 404 for every outside user, one
  `curl -fsI` (or a `deep install` from a scratch venv) against the live URL
  belongs as a step 7. This is the mistake most likely to happen next.
- **R3.** Step 1 (`git pull`) plus step 4 (refresh `BUNDLE.json`) can silently
  disagree with the tarball if a maintainer does step 1 but re-uses an old
  `dist/`. Worth one line: "re-run step 2 after any step-1 pull." Live
  example: `BUNDLE.json` pins `9e08230`, which is no longer the sibling repo's
  `HEAD` (now `075fe7f`, from unrelated concurrent work).

**`./arailctl` help text.** `deep <op>  AeroLLM 2nd inference: install
(bundled binary) | rebuild (source) | update (wheel) | status` — clear, and
`install` is listed first. Unknown ops exit non-zero with the enumeration. Two
notes: `deep install` dispatches to `bundle` (not `auto`), so on a maintainer
machine it goes straight into the F7 refusal rather than picking DEV —
arguably correct, but not what the help text implies; and `--force` is plumbed
through `install` only and is undocumented in `--help`.

**`docs/cli.md`** is thorough and the sha256 caveat's framing is honest — its
only defect is the broken example (Q1).

---

## Regression (10%)

No behaviour attributable to this sprint changed for the maintainer's own
machine. All verified by execution:

| Check | Result |
|---|---|
| `auto` with the sibling repo present → DEV | OK — `• Local sibling repo found → building from source (dev channel).`, then a stub `cargo` invoked with the exact expected args |
| `AEROLLM_CHANNEL=release` → pip against `AEROLLM_INDEX_URL` | OK — `• Installing aerollm_api from index ...`, never reaches bundle |
| `AEROLLM_CHANNEL` dev/release/bundle honoured; anything else exits 2 | OK — `✗ AEROLLM_CHANNEL must be one of: dev \| release \| bundle`, EXIT=2 |
| Unknown mode / unknown `deep` op | OK — exit 2 / exit 1 with enumerations, unchanged |
| Maintainer-machine `status` | OK — `channel: dev`, no `bundle:` line, pre-existing lines unchanged in shape |
| F7 guard protects a DEV install; `--force` overrides | OK — both |
| `dist/aerollm-bundle/` survived the full suite | OK — `d3a7a9dd...` unchanged (round-2 B3 stays fixed) |
| Sibling `~/ProJects/qukaizen-aerollm` | OK — zero writes from this QA pass; its `HEAD` moved only via unrelated concurrent grammar work |
| arail working tree after all probing | OK — clean except the new test file |

**Full suite** (`pytest tests/ -q -p no:randomly`, ambient env scrubbed):
**4016 passed / 81 failed / 7 skipped / 3 xfailed / 7 errors in 23:39.**
`-k aerollm` slice: **144 passed / 9 failed**, matching REVIEW round 3 exactly.

All 81 are pre-existing. I bisected the six closest to this sprint's blast
radius against the merge-base (`739b9df`) in a `git worktree`:

| Test | At `739b9df` | At `HEAD` | Verdict |
|---|---|---|---|
| `test_shell_source_safety.py::...injection_safe` | fail (`No module named 'tomllib'`, py3.9) | fail | pre-existing |
| `test_cli_qa_edge.py::test_qa_edge_driver_scenarios` | fail | fail | pre-existing |
| `test_cli_warmup.py::test_warmup_driver_scenarios` | fail | fail | pre-existing |
| `test_deep_default_and_tier.py` x2 | pass in isolation | pass in isolation | full-suite ordering pollution (pre-existing class) |
| `test_aerollm_compute_source.py::test_active_provider_accepts_aerollm` | pass in isolation | pass in isolation | same |

The 9 `-k aerollm` failures are the same `AeroLLMBackend._shared` cross-file
singleton-cache pollution rounds 1-3 identified. **Zero regressions introduced
by this sprint.**

---

## Performance

N/A. A one-time ~6.8 MB download plus a `cp`; not on any inference or request
hot path. Confirmed the tarball streams to `$TMPDIR` (L206) rather than being
buffered in a shell variable, per ARCHITECTURE §9.

---

## Coverage delta

Bundle-channel tests before: 14 (`test_aerollm_bundle_install.py` +
`test_aerollm_bundle_compliance.py`) plus 1 backend-message contract test.
After: **+30** (`test_aerollm_bundle_qa_hardening.py`), 29 green, 1 red on a
real defect.

Behaviour classes with **zero** prior coverage now covered: malformed archive
bodies, missing archive members, path-traversal members, corrupt/empty
provenance markers, the marker-corruption reinstall path, the `auto` →
RELEASE-on-index-override dispatch, non-https URL rejection beyond a single
`http://` case, digest-object semantics, F7-after-interruption, and the
`setup.sh` remediation-string contract.

---

## Required before `gh release upload`

1. **Q1** — add a tarball-digest pin (`aerollm_bundle_sha256` in
   `pyproject.toml`, forwarded by `setup.sh`, bumped in `docs/releasing.md`
   step 4), verify the extracted `.so` against `MANIFEST.json.sha256`, and fix
   the `docs/cli.md` sentence.
2. **Q7** — name `./arailctl deep install` in `scripts/setup.sh`'s AeroLLM
   failure warning (and the Apple-Silicon-only branch). Turns test 30 green.
3. **Q5** — put the "prebuilt binary, downloaded and executed, integrity not
   authenticity" disclosure somewhere a downstream user sees *before*
   installing: `SECURITY.md` and the maximus section of `README.md` /
   `docs/INSTALL.md` at minimum.
4. **Q2** — correct ARCHITECTURE.md §9.1 step 3 (leave `AEROLLM_INDEX_URL`
   unset) so the acceptance bar can be executed as written.

Recommended, non-blocking: **Q4** (wrap `tar` in the same error shape as
`curl`), **Q6** (narrow the F7 guard / make the two `cp`s atomic), **Q3**
(correct ARCHITECTURE §2/§11), **R2** (post-upload verification step in
`docs/releasing.md`), **Q8**, **A7**, **A5**, **A4**.

---

## Notes for the next QA pass

- **The strings a human reads are this sprint's weak spot, not the code.**
  B1, B2, B5, Q1, Q2, Q5 and Q7 are all the same failure: a correct mechanism
  described incorrectly somewhere a human acts on it. Future changes here
  should be reviewed with `grep` over every user-visible string that names a
  route, a filename or a digest — the mechanics will be fine.
- **The F7 provenance guard is over-broad and has now bitten twice** — the
  reviewer's own tests in round 2 (B4), and any user with an interrupted
  install (Q6). A third time will be a real support ticket.
- **Under-tested and still hardware-pending:** a real inference turn through
  `AeroLLMBackend` against the bundled `.so`. Everything proven so far stops at
  `import`. When a checkpoint is available, that is the first test to add.
- **Never verified by anyone:** the live `curl` from `github.com` against a
  real asset. It cannot be until the upload happens. Do it from a scratch venv
  immediately after upload, before announcing (R2).
- The 81 full-suite failures are a growing, unowned debt (recap x24,
  world-forge x6, portal x7, bench-harness x5). Not this sprint's, but they
  make "did I break anything?" a 24-minute question with a noisy answer.
  Worth its own sprint.
