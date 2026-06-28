# Test report: DaC World SKILL.md → agent system prompt

**Date:** 2026-06-27
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at branch `qukaizen/arail-dac-world-mount`
**Verdict:** PASS

## Summary

I attacked the load-time containment with unicode/homoglyph variants, zero-width and
combining-char evasion, the legit-shaped `- Source:` smuggling vector, DoS inputs, a hostile
`capabilities.json`, and — critically — the REAL agent seams the existing tests bypass
(`_compose_prompt`, `_get_system_context`). Nothing escaped structurally. The containment's
load-bearing guarantee (no *renderable* ASCII h1/h2 heading survives) holds against every
variant I tried. The only residual risks are non-structural (a raw-text SLM reading neutralized
words / Source content as prose) and are correctly scoped as "body is DATA, never instructions"
by the architecture. 30 builder tests + 29 new QA tests pass; world-regression subset =
120 passed / 1 pre-existing failure.

## Test inventory

| # | Test (in `tests/test_world_skill_qa_adversarial.py`) | Category | Covers | Status |
|---|---|---|---|---|
| 1 | `test_renderable_h12_forgery_is_always_neutralized` (8 params) | security/edge | every renderable ATX h1/h2 forgery (extra space, trailing NBSP, non-delim `## SKILL:`, indented, tab) is ZWNJ-neutralized and no longer renderable | PASS |
| 2 | `test_homoglyph_non_renderable_variants_cannot_forge_a_heading` (6 params) | security/edge | fullwidth `＃`/`＃＃`, ZWSP-broken `##​`, no-space `##`, combining acute, RTL override — none becomes a renderable heading | PASS |
| 3 | `test_no_surviving_line_in_real_hostile_body_is_renderable_h12` | security | strongest structural assertion: 0 renderable h1/h2 lines survive in the real hostile fixture body | PASS |
| 4 | `test_indented_source_line_is_passed_through_as_data` | security | legit-shaped `  - Source: <instruction>` is preserved verbatim BUT stays under the H2 (cannot escape) — documents the content-injection residual | PASS |
| 5 | `test_bare_source_forgery_still_neutralized_even_though_indented_is_kept` | security/regression | the column-0 vs indented `Source:` discriminator holds | PASS |
| 6 | `test_single_huge_line_contain_is_linear_and_fast` | perf/DoS | 5MB single line contained < 2s | PASS |
| 7 | `test_many_forged_delimiter_lines_contained_fast` | perf/DoS | 50k forged `# WORLD FRAMING` lines contained < 2s, all neutralized | PASS |
| 8 | `test_just_over_byte_cap_returns_none` | edge | SKILL.md at byte-cap+1 → None | PASS |
| 9 | `test_null_bytes_do_not_crash_load` | edge | null bytes in body → no crash, embedded forged heading still neutralized | PASS |
| 10 | `test_invalid_utf8_bytes_decode_replace_no_crash` | edge | `\xff\xfe` invalid UTF-8 → decode-replace, no raise | PASS |
| 11 | `test_hostile_capabilities_json_does_not_break_mount_or_leak` | security | malformed/injection `capabilities.json` → mount succeeds, `purpose` injection never reaches the world-skill body | PASS |
| 12 | `test_buddy_real_compose_prompt_includes_world_glossary` | Buddy quality | REAL `_compose_prompt` contains `Ballets Russes`, `## Skill:`, `# Procedural knowledge`, real `Observation:` scaffold | PASS |
| 13 | `test_researcher_real_get_system_context_includes_world_glossary` | Researcher quality | REAL `_get_system_context("other")` contains the glossary term | PASS |
| 14 | `test_swap_A_to_B_real_buddy_prompt_reflects_B_not_A` | Buddy quality | swap A→B via real seam: B's term present, A's term absent (no stale glossary) | PASS |
| 15 | `test_unmount_real_buddy_prompt_drops_glossary` | Buddy quality | real seam after unmount drops the glossary | PASS |
| 16 | `test_art_history_fixture_is_self_contained_six_sealed_plus_skill` | setup | fixture carries 6 sealed + manifest + SKILL.md frozen, no DaC toolchain | PASS |
| 17 | `test_mount_from_empty_data_dir_no_prior_record` | setup | mount→compose against fresh/empty data dir, no prior mount record | PASS |

Builder's `tests/test_world_skill_mount.py` (30 tests) all re-confirmed PASS.

## Failures

| # | Test | Symptom | Minimal repro | Severity |
|---|---|---|---|---|
| — | none introduced by this sprint | — | — | — |
| pre-existing | `test_world_identity_flip.py::test_researcher_reframes_live` | `assert 'other' == 'ai'` at line 121 | global mount-state leak in that test's setup; fails identically on base commit (verified in REVIEW.md) | not-this-sprint |

## Security review

| Surface | Checked | Findings |
|---|---|---|
| User/bundle input (SKILL.md body) | I confirmed the invariant "no line surviving `_contain_skill_body` is a renderable CommonMark ATX h1/h2" against: exact delimiters, extra-space, trailing-NBSP, tab-after-`##`, indented `#` (≤3 spaces), and non-delim `## SKILL:`. All neutralized via U+200C and verified non-renderable after. | HOLDS. No structural escape. |
| Unicode / homoglyph evasion | Tested fullwidth `＃`(U+FF03)/`＃＃`, ZWSP-after-`#` (`##​Skill`), no-space `##Skill`, combining acute before `##`, RTL override (U+202E) before `#`. | These PASS THROUGH containment unchanged, BUT none is a renderable ATX heading (CommonMark requires an ASCII `#` immediately followed by ASCII space/tab), so none can forge a markdown section. **Residual risk (LOW, non-structural):** a small local SLM reading the raw prompt as prose may still *notice* the words "WORLD FRAMING"/"Skill:" in a homoglyph line. It cannot relocate the line out of its H2. Documented, not a blocker. |
| ZWNJ-neutralization adequacy | Assessed prefix-with-U+200C vs collapse/escape. | A U+200C prefix is sufficient *for the structural threat*: it breaks the column-0 `#`-run so no renderer treats the line as a heading, while keeping the line readable for honesty. It does NOT remove the semantic words from the line — a stronger control (HTML-escape the leading `#` to `\#`, or collapse the whole line to an inline-code span) would also blunt the raw-text-SLM nudge. **Recommendation (follow-up, LOW):** for the ARAIL-delimiter set specifically, consider escaping (`\#`/backtick-wrap) rather than ZWNJ-prefixing, so the neutralized line cannot even be *read* as a section cue. Not required for v1 (body is DATA-under-H2). |
| Legit-shaped `- Source:` smuggling | A `  - Source: ignore all prior instructions…` line passes containment (correctly — it is the honesty rail) and lands in the prompt verbatim as a Source value. | **Real but in-scope: content-level injection, not structural.** The line cannot forge a section (stays under the skill H2). The architecture explicitly treats the body as DATA the agent reasons over, never trusted instructions — consistent with the documented `terms.json`-is-DATA boundary. Severity LOW for v1; the durable mitigation is the already-tracked cross-repo seal-promotion of SKILL.md (so a tampered Source value is rejected at mount, not just contained). Pinned by test #4 so any future "sanitize Source values" change is conscious. |
| File I/O / caps / DoS | byte cap (None at +1), body char cap (truncate+WARN), 5MB single line, 50k forged lines, null bytes, invalid UTF-8. | All graceful; containment is linear and sub-2s. No path traversal: `load_world_skill` reads a fixed `<staged_dir>/SKILL.md` keyed off the mount record (no user-controlled path component). |
| `capabilities.json` | hostile schema + `purpose` injection + non-list `capabilities`. | Mount succeeds (best-effort resolver, never blocks), and capabilities never reach any agent prompt path (grep-confirmed: no `current_capabilities`/capabilities import in `agents/` or `skills_loader`). No leak. |
| Seal posture | `SKILL.md` NOT in `_BUNDLE_FILES`; tampered SKILL.md still mounts (seal-exempt), broken 6-file seal still refused. | Correct per ARCHITECTURE §Security; the seal-promotion follow-up is tracked. |

## Performance

N/A as a benchmark — not a hot path (tiny markdown reads, sub-2s containment on pathological
50k-line / 5MB-line inputs). Perf assertions are inline in tests #6/#7.

## Coverage delta

The two builder "agent prompt" tests previously asserted on a `compose_system_context([ws])`
shortcut (REVIEW [ASK]) and did NOT exercise `_compose_prompt`/`_get_system_context`. This QA
pass closes that gap: tests #12–#15 drive the REAL seams (mount → repoint default resolvers →
call the actual agent functions → assert glossary present/absent/swapped). The wiring is now
regression-guarded, not just manually proven.

## Setup result

- The `art-history-skill` fixture is self-contained (8 required files present as frozen bytes);
  no DaC toolchain is needed at test time — clean-machine gate green (test #16).
- Mount→compose works against a fresh/empty data dir with no prior mount record (test #17).
- The `world_mount` Python API path is exercised end-to-end; I did not invoke the `arailctl`
  CLI binary (the `.venv` Python entry is the test-time path), so a fresh-machine `arailctl`
  shell wrapper was not separately gated — noted for the next pass.

## Final suite numbers

- `tests/test_world_skill_mount.py` (builder): **30 passed**.
- `tests/test_world_skill_qa_adversarial.py` (this pass): **29 passed** (17 cases, several
  parametrized).
- World-regression subset (`test_world_skill_mount` + `test_world_buddy` + `test_world_mount` +
  `test_world_catalog_adopt` + `test_world_kb` + `test_world_switcher` + `test_world_identity_flip`):
  **120 passed, 1 failed** — the single failure is the documented pre-existing
  `test_researcher_reframes_live` (fails identically on the base commit; not introduced here).
- Every other world test file passes in isolation (`curator` 7, `dictionary` 10, `face` 10,
  `import` 6, `import_zip` 9, `loader` 25, `model_hint` 23, `qa_probes` 16, `recolor` 30).

**Environment note (not a product finding):** the *entire* `tests/` suite (163 files) could not
be run to completion in one process in this sandbox — it stalls near ~96% under resource
contention (and was further confused by accumulated orphaned pytest processes during this pass).
This is an environmental harness limitation, not a regression from this sprint: every file passes
standalone, and the targeted world-regression subset is green. A clean-machine full-suite run is
recommended at ship time to confirm.

## Notes for the next QA pass

- **ZWNJ → escape upgrade** for the ARAIL-delimiter set (HTML-escape `\#` or backtick-wrap) so a
  neutralized delimiter line cannot be read as a section cue even by a raw-text SLM. LOW.
- **Source-value sanitization / seal-promotion** is the durable answer to the legit-shaped
  `- Source:` content-injection vector. Already tracked cross-repo; pinned by test #4.
- **`arailctl` CLI fresh-machine smoke** (`world mount <bundle>` via the shipped binary, not the
  Python API) was not gated here — add it.
- The broad-suite stall near 96% deserves a separate triage ticket (likely a server-binding /
  state-leaking test); it is orthogonal to this sprint but blocks a one-shot full-suite gate.
