# Test report: Model-Hosting Strategy Reframe

**Date:** 2026-05-30
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 7972b43 (review at 7972b43, REVIEW.md WEAK_PASS)
**QA commit:** 5124019 (`test(model-hosting-reframe): qa setup-ladder + sentinel/qwen-hiding guards`)
**Verdict:** WEAK_PASS

## Summary

The committed code is correct, fail-closed, OOM-safe, in-scope, and free of new
regressions. 43 new QA tests pass; the 17 existing failures are pre-existing /
belong to the parallel aerollm-budget sprint and are unchanged with or without
the new tests. The single non-blocking-but-must-resolve finding is the architect's
[ASK-LICENSE] item, which I independently re-verified against the live HuggingFace
API and confirm is factually correct. It is a product/legal decision above the
code; it does not break anything committed (zero weights ship), so this is a
WEAK_PASS, not a FAIL — matching the architect's verdict.

Two additional findings surfaced during testing, both **pre-existing** and neither
introduced by this sprint:
- **TIMEOUT-GAP (Medium):** every ai-eng install branch is wrapped in `timeout 900 …`
  but stock macOS — the documented 36 GB Apple Silicon reference machine — ships no
  `timeout` binary (it is `gtimeout` from coreutils). Pre-existing (2 uses before the
  sprint; the sprint propagated it to 5). On a clean macOS box with no coreutils,
  `timeout` is "command not found" and every ai-eng path fails to the warn+continue
  branch. Setup still exits 0 (no crash), but ai-eng is never installed on the
  headline platform. Recommend a `timeout`/`gtimeout` shim in setup.sh.
- **STALE-ENV (Informational / OOM):** the deep-model sentinel guard only trips when
  `AIRLLM_MODEL` resolves to the sentinel. A pre-existing local `.env` carrying
  `AIRLLM_MODEL=meta-llama/Llama-3.1-70B-Instruct` bypasses the guard and (with a
  warm AirLLM cache) will load a 70B. This is a stale operator-config issue, not a
  code defect — the sprint correctly repointed the *defaults* to the sentinel. It is
  worth a one-line setup migration that warns when `.env` still pins a 70B/405B
  AIRLLM_MODEL. (My worker-guard test is hardened with a fake `airllm` so QA itself
  can never trigger a real load.)

## Test inventory

| # | Test | Category | Covers | Status |
|---|---|---|---|---|
| 1 | hf_primary_success_single_pull_no_create_no_mirror | setup/happy | WC#1 single `ollama pull hf.co/...`, no create/curl/preview | PASS |
| 2 | hf_primary_success_respects_env_repo_and_quant | setup | env override flows into HF ref | PASS |
| 3 | hf_404_then_github_mirror_digest_match_creates | setup | HF 404 → mirror download → sha MATCH → create | PASS |
| 4 | mirror_digest_mismatch_fails_closed_no_create | setup/security | sha MISMATCH → discard, no create, fall through | PASS |
| 5 | placeholder_digest_disables_mirror_no_download | setup/security | placeholder sha → mirror disabled, NO curl (fail-closed) | PASS |
| 6 | all_hosts_fail_falls_to_preview_net | setup | artifact-not-uploaded reality → preview net | PASS |
| 7 | preview_net_narrative_has_no_qwen_marketing | setup/security | neutral `info` wording, no qwen in narrative | PASS |
| 8 | total_failure_exits_clean_and_prints_manual_command | setup | offline → exit 0 + manual command | PASS |
| 9 | total_failure_does_not_pull_any_heavy_deep_model | setup/security | no 70B/405B/sentinel pull on any failure path | PASS |
| 10 | skip_ollama_makes_zero_pull_attempts | setup | ARAIL_SKIP_OLLAMA=1 → zero network | PASS |
| 11 | already_installed_is_idempotent_skip | setup | ai-eng present → no pull/curl | PASS |
| 12 | legacy_ai_engineer_aliased_not_repulled | setup | legacy → `ollama cp` alias, no re-download | PASS |
| 13 | cdn_skipped_when_url_empty | setup | empty CDN url → no 2nd mirror curl | PASS |
| 14 | cdn_fires_when_url_set | setup | set CDN url → GitHub+CDN = 2 attempts | PASS |
| 15 | sentinel_is_not_a_resolvable_model_id | security | sentinel has no org/tag shape | PASS |
| 16 | airllm_worker_raises_on_sentinel_before_any_load | security/OOM | guard raises before AutoModel load (faked) | PASS |
| 17 | backends_raises_on_sentinel_before_any_load | security/OOM | backend RuntimeError on sentinel | PASS |
| 18 | no_deep_default_resolves_to_a_real_weight | regression | no 70B/405B reintroduced as a default | PASS |
| 19 | app_default_model_is_sentinel | regression | optional-backend default stays sentinel | PASS |
| 20 | no_qwen_in_ai_eng_identity_lines | security | README/CLAUDE/tuning ai-eng lines qwen-free | PASS |
| 21 | catalog_ai_eng_description_has_no_qwen | security | catalog ai-eng entry qwen-free | PASS |
| 22 | modelfile_preview_is_the_only_user_facing_qwen_FROM | security | lone permitted `FROM qwen2.5:7b`; SYSTEM qwen-free | PASS |
| 23 | notice_exists_and_names_qwen_base_and_license | security | NOTICE names 3B + Qwen Research License + URL | PASS |
| 24 | notice_states_redistribution_attribution_requirement | security | HF-card/release attribution clause present | PASS |
| 25 | license_points_to_notice | security | LICENSE → NOTICE pointer | PASS |
| 26 | package_script_embeds_no_credentials | security | no hf_/ghp_/key literals; manual login | PASS |
| 27 | package_script_exits_nonzero_on_missing_inputs | security | missing inputs → manual steps + nonzero, no download | PASS |
| 28 | package_script_weight_download_is_only_documentation | security | hf download is heredoc/doc-only, never executed | PASS |
| 29 | package_script_passes_bash_syntax | regression | `bash -n` clean | PASS |
| 30 | check_artifact_script_passes_bash_syntax | regression | `bash -n` clean | PASS |
| 31 | setup_sh_passes_bash_syntax | regression | `bash -n` clean | PASS |
| 32 | setup_mirror_create_is_gated_behind_sha256_check | security | fail-closed digest gate present in source | PASS |
| 33 | check_artifact_uses_head_not_blob_download | security | HEAD probe, no blob download | PASS |
| 34 | resilient_chat_default_returns_installed_ai_eng | buddy | ai-eng:latest resolves when installed | PASS |
| 35 | resilient_chat_default_aliases_legacy_ai_engineer | buddy | legacy ai-engineer still resolves Buddy's brain | PASS |
| 36 | no_reference_to_removed_modelfile_production_tag | buddy | install is hf.co pull; dead ollama.ai tag gone | PASS |
| 37 | modelfile_preview_persona_is_ai_eng | buddy | preview Modelfile yields ai-eng persona | PASS |
| 38–41 | no_frontier_scale_in_rewritten_surfaces[README/CLAUDE/tuning/pyproject] | regression | honest-framing grep | PASS |
| 42 | pyproject_self_hosted_keys_are_placeholder_marked | setup/security | sha placeholder, hf_repo, preview key present | PASS |
| 43 | check_artifact_returns_nonzero_today | setup | documents 2b deferral (artifact not live) | PASS |

## Failures

| # | Test | Symptom | Minimal repro | Severity |
|---|---|---|---|---|
| — | (none in this sprint's scope) | All 43 new QA tests pass. | — | — |

Pre-existing / parallel-sprint failures (NOT this sprint, unchanged with or without
my files): 17 total — `test_aerollm_defaults` (kv-budget, parallel sprint),
`test_opencode_*`, `test_docs_routes*`, `test_dashboard_layout_v2`,
`test_swarm_goal_surfaces`, `test_system_metrics`, `test_qa_airgap_*`. Confirmed
identical (17 failed / 2093 passed) with the new test files excluded → zero NEW
failures introduced.

## Security review

| Surface | Checked | Findings |
|---|---|---|
| Deep-model sentinel | `__TODO_DEEP_MODEL__` has no org/`/` and no `:tag`; `airllm_worker._load_model` and `backends` raise `RuntimeError("…not configured")` before `AutoModel.from_pretrained`; app surfaces a notice. Verified the guard trips with a fake `airllm` so a regression can never load a real 70B. | PASS. STALE-ENV caveat above: guard is bypassed if an operator `.env` pins a real `AIRLLM_MODEL`; recommend a migration warn. |
| Supply-chain / digest | `_install_from_gguf` returns 1 on `__PLACEHOLDER_SHA256__` BEFORE any curl (no download-and-trust); on real digest, downloads → `sha256sum` → discards on mismatch → only an exact match reaches `ollama create` via a generated Modelfile. Asserted both the static structure and the runtime fail-closed behavior (tests 4, 5, 32). | PASS — genuinely fail-closed. |
| File I/O (tmp GGUF) | `_gguf_tmp` and the generated Modelfile are `rm -f`'d on every error branch and at function end. No predictable-name race exploited; uses `$TMPDIR`. | PASS (informational: fixed tmp filename, not `mktemp` — low risk, single-user local setup). |
| Packaging script | No `hf_…`/`ghp_…`/`api_key=`/`password=` literals; `huggingface-cli login` and `gh auth login` are manual steps; the only `huggingface-cli download` lives inside a documentation heredoc and never executes; missing `--base-dir`/`--lora-dir` → prints manual steps + `exit 1`, fetches nothing. | PASS |
| Artifact probe | `check_ai_eng_artifact.sh` uses HEAD (`-I -o /dev/null`) only; never downloads the blob; exits 1 today (artifact not live). | PASS |
| Network I/O / airgapped | The self-hosted fetch is a model-pull of the same class as the existing `ollama pull`, gated by the existing Ollama-present + `ARAIL_SKIP_OLLAMA` guards; no cloud-provider egress gating touched (`LAB_MODE=airgapped` invariant preserved). | PASS |
| Attribution / license | NOTICE names Qwen2.5-3B-Instruct, the Qwen Research License (flagged NOT Apache-2.0), the upstream URL, and the redistribution/HF-card/GitHub-release clause; LICENSE points to NOTICE; the lone permitted user-facing qwen ref is `Modelfile.preview`'s FROM line. | PASS for accuracy; see [ASK-LICENSE]. |

### [ASK-LICENSE] — independently re-verified, must-resolve-before-distribution

I queried the live HuggingFace model API:
- `Qwen/Qwen2.5-3B-Instruct` → `license: other`, `license_name: qwen-research`,
  `license_link: …/blob/main/LICENSE` — i.e. the **Qwen Research License**
  (research-only / non-commercial; commercial use requires a separate Alibaba
  Cloud license).
- `Qwen/Qwen2.5-7B-Instruct` → `apache-2.0`.

**Assessment:** the architect's [ASK-LICENSE] finding is factually correct. The
bottled ai-eng GGUF is a derivative of the 3B base and inherits the Qwen Research
License's non-commercial restriction, which conflicts with ARAIL's MIT
"fork / rename / commercialize" blueprint thesis. This is exactly VISION.md's named
disconfirming signal. It does **not** FAIL the committed code: the code is
fail-closed, the placeholder repo 404s, and **zero weights ship today** — nothing
merged violates anything. But the user/visionary MUST decide one of routes (a)
re-base ai-eng on a permissive model (e.g. the Apache-2.0 Qwen2.5-7B, or a permissive
3B), (b) explicitly reposition ai-eng as research/personal-use (weakening the
blueprint promise), or (c) obtain a commercial license — **before** running
`package_ai_eng.sh` against the Qwen-3B base and uploading. Record the decision in
the sprint ledger and freeze the "package and upload the ai-eng GGUF" follow-up
ticket until then.

## Performance

N/A — config/copy/shell sprint, no hot path. No benchmark required (per architecture
and review).

## Coverage delta

New behavioral coverage added for surfaces that previously had **no** automated tests:
- `scripts/setup.sh` ai-eng self-hosted fetch ladder (14 ladder-state tests via a
  PATH-stub harness; the function had zero prior coverage).
- Deep-model sentinel guards in `airllm_worker.py` / `backends.py` / `app.py`.
- `scripts/package_ai_eng.sh` and `scripts/check_ai_eng_artifact.sh` (new scripts,
  now covered for security + exit-code behavior).
- qwen-hiding and honest-framing regression grep gates.

Existing suite: 2093 → 2136 passing (+43 new). Pre-existing failures: 17, unchanged.

## Notes for the next QA pass

- **TIMEOUT-GAP** (Medium, pre-existing): add a `timeout`/`gtimeout` shim to setup.sh
  so the ai-eng ladder works on stock macOS, the headline reference platform.
  Without it, the HF pull / mirror create / preview create all fail to the
  warn+continue branch on a clean Apple Silicon box.
- **STALE-ENV** (Info): a setup migration that warns when `.env` still pins a
  70B/405B `AIRLLM_MODEL` would close the only remaining route to an accidental
  heavy load on this OOM-sensitive machine.
- The setup-ladder harness (`tests/setup_ladder/run_install_models.sh`) exercises the
  back half of `install_services()`; note ARCHITECTURE.md refers to it as
  `install_models()` — naming mismatch only, not a defect. If the function is ever
  renamed/split, update the harness `step()/ensure_node()/ollama_default_enabled()`
  stubs.
- The 2b follow-up (delete Modelfile.preview + preview net) is gated on
  `check_ai_eng_artifact.sh` returning 0; test 43 locks that it returns nonzero today.
  Re-run that test after any upload to confirm the flip before deleting the preview net.
- When [ASK-LICENSE] is resolved toward route (a), re-point the NOTICE production base
  and the preview base to the same compliant model and re-run tests 20–25.

---

# Test report (Phase 2): Two-tier model strategy v2 (MODEL-TIERS-V2)

**Date:** 2026-05-31
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) "Two-tier model v2" section at `9004eaf`
**QA commits:** `85f6c25`, `0757f9b`, `7a2abfc`
**Verdict:** PASS

## Summary

All 16 required coverage items are locked by explicit regression tests.
13 of 16 already had coverage from the builder's `aa24b30` test commit; QA
added **12 new tests** across 3 files to close the 3 remaining gaps:
deep-persona offer/gating *behavior*, `build_ai_eng.sh require_python`
resolution, and the model-building pack count + base-model primer.

- Targeted suite: 172 → **184 passed** (+12 new), zero failures.
- Full suite: **2200 passed / 17 failed / 1 xfailed** — all 17 failures are
  pre-existing and confirmed unchanged against the stashed baseline (none touch
  this sprint's surfaces). **Zero new failures introduced.**

OOM-safety honored throughout: every test mocks `ollama`/`curl`/`python3` via
PATH shims or asserts on source/config strings. No model pull, no
`ollama create`, no LLM load, no llama.cpp build, no uvicorn, no network.

## Required-coverage map (16 items)

| # | Item | Status | Where |
|---|---|---|---|
| 1 | Default pulls `llama3.2:1b` + creates `llama-ai-eng` (not GGUF) | EXISTS | `test_setup_ladder::test_default_path_pulls_llama_1b_and_creates_llama_ai_eng` |
| 2 | Self-hosted GGUF lane dormant unless `ARAIL_AI_ENG_SELFHOSTED=1` | EXISTS | `test_setup_ladder::test_selfhosted_flag_activates_hf_ladder`; `..._qa::test_self_hosted_ladder_gated_behind_env_flag` |
| 3 | Deep model offer/install + `ARAIL_INSTALL_DEEP_PERSONA` gating | **ADDED** | `test_setup_ladder::test_minimalist_default_does_not_offer_or_pull_deep_7b`, `::test_deep_persona_flag_auto_installs_7b_via_modelfile_deep`, `::test_deep_persona_auto_install_still_installs_1b_default`, `::test_existing_ai_engineer_not_repulled_when_deep_requested`, `::test_deep_7b_pull_failure_is_graceful`, `::test_maximus_deep_offer_is_command_not_autopull_in_source` |
| 4 | No 7B→1B mislabel alias (v1 footgun) | EXISTS | `test_setup_ladder::test_legacy_ai_engineer_not_aliased_to_1b_default`; `..._qa::test_no_mislabel_alias_7b_as_1b_default` |
| 5 | Two deep sentinels not conflated (frontier keeps sentinel) | EXISTS | `..._qa::test_surface_b_airllm_sentinel_unchanged`, `::test_app_default_model_is_sentinel`, `::test_no_deep_default_resolves_to_a_real_weight` |
| 6 | Back-compat resolver order `[llama-ai-eng, ai-eng:latest, ai-engineer:latest]` | EXISTS | `..._qa::test_resilient_chat_default_*` (4) |
| 7 | 16 GB-floor guard (default base is 1B) | EXISTS | `..._qa::test_default_base_is_16gb_safe_1b_llama` |
| 8 | Llama license + AUP files exist, non-trivial | EXISTS | `..._qa::test_llama_license_files_exist_and_nonempty` |
| 9 | "Built with Llama" verbatim in NOTICE+README+catalog+Modelfile.default | EXISTS | `..._qa::test_llama_attribution_present_in_required_locations`, `::test_notice_dual_base_structure` |
| 10 | Distributed default name begins with "Llama" | EXISTS | `..._qa::test_pyproject_has_two_tier_persona_keys`, `::test_modelfile_default_exists_and_has_llama_base` |
| 11 | NOTICE dual-base (Llama Community + Qwen Apache-2.0) | EXISTS | `..._qa::test_notice_dual_base_structure` |
| 12 | Qwen-hiding guard ALLOWS required Llama attribution | EXISTS | `..._qa::test_no_qwen_in_ai_eng_identity_lines`, `::test_catalog_llama_ai_eng_default_entry_has_no_qwen` |
| 13 | `_arail_timeout` shim: 3 branches | EXISTS | `test_timeout_shim.py` (3) |
| 14 | `build_ai_eng.sh` prefers `./.venv/bin/python3`, falls back to PATH | **ADDED** | `test_build_ai_eng_dry_run::TestRequirePythonResolution` (4) |
| 15 | `package_ai_eng.sh` is thin deprecation shim | EXISTS | `..._qa::test_package_ai_eng_is_retired_shim` |
| 16 | `09-choosing-a-base-model.md` in pack (count = 10) | **ADDED** | `test_pkb::test_model_building_pack_has_ten_files_including_base_model_primer`, `::test_base_model_primer_installs_to_disk` |

## New tests (12)

- **`tests/setup_ladder/test_setup_ladder.py` (+6):** deep-persona OFFER/gating
  (Surface A). The mock harness can't set `LAB_TIER` (setup.sh resets it to `""`
  at top level; the tier is only captured inside `main()`, which the harness
  skips), so the offer-only branch is asserted at source level while auto-install
  is exercised behaviorally via `ARAIL_INSTALL_DEEP_PERSONA=1`.
- **`tests/test_build_ai_eng_dry_run.py` (+4):** `require_python` resolution —
  extracts the shell function, drives it under a restricted PATH with mock
  venv/PATH interpreters, plus an OOM-safety assertion that it resolves a path
  and never executes python.
- **`tests/test_pkb.py` (+2):** model-building pack is exactly 10 primers
  including the base-model primer, in `_PACKS` and on disk.

## Failures

None in this sprint's surfaces. The 17 full-suite failures are pre-existing and
unrelated (`test_aerollm_defaults` kv-budget — the parallel KV sprint this
branch is named for; `test_docs_routes*`, `test_swarm_goal_surfaces`,
`test_dashboard_layout_v2`, `test_system_metrics`, `test_qa_airgap_*`,
`test_opencode_*`). Confirmed identical on the stashed baseline. Not this
sprint's bug; out of scope.

## Security review

| Surface | Checked | Findings |
|---|---|---|
| Llama 3.2 license | Verbatim notice string in NOTICE + license file; "Built with Llama" in NOTICE/README/catalog/Modelfile.default; name `llama-ai-eng` begins with "Llama"; AUP bundled+referenced | PASS |
| Dual-base NOTICE | §1 Llama Community, §2 Qwen Apache-2.0, §3 dormant; Qwen Research License absent | PASS |
| OOM / surprise pull | minimalist never auto-pulls 7B; maximus offers + gates behind flag; frontier sentinel intact; no 70B/405B default | PASS (honors OOM memory note) |
| Size-mislabel footgun | no `ollama cp`/`tag` aliasing 7B→1B in setup.sh | PASS |
| Self-hosted ladder gating | runs only under `ARAIL_AI_ENG_SELFHOSTED=1`; default makes zero HF/curl; placeholder sha fail-closed | PASS |
| Credentials | no `hf_…`/`ghp_…`/`api_key=…` literals in packaging/build scripts | PASS |
| `LAB_MODE=airgapped` | unchanged; model pull not a cloud-egress change | PASS |
| require_python | resolves venv-then-PATH; never executes python | PASS |

## Performance

N/A — config/copy/shell/persona-wrap sprint (per MODEL-TIERS-V2 §6).

## Coverage delta

- Targeted suite: 172 → **184 passed** (+12, 0 failures).
- Full suite: 2188 → **2200 passed**, 17 failed (unchanged), 1 xfailed. Net new
  failures: **0**.

## Notes for the next QA pass

- The mock harness can't set `LAB_TIER` (reset to `""` at module top level;
  tier captured only inside `main()`). True tier-driven behavioral coverage of
  the maximus offer-only branch would need a harness hook or a refactor that
  captures the tier in a function. The branch is currently source-asserted —
  adequate but structural, not behavioral.
- Dormant GGUF lane tooling (`check_ai_eng_artifact.sh`, `package_ai_eng.sh`)
  still references the `ai-eng-1.5b-gguf` placeholders, not a Llama-1B artifact
  (intentionally out of scope). If revived on a Llama base, update the
  artifact-name guard in `test_pyproject_self_hosted_keys_are_placeholder_marked`.
- The 17 pre-existing failures (notably `test_aerollm_defaults` kv-budget)
  belong to the parallel KV-budget work this branch is named for; triage in
  their own sprint.
