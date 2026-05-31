# Review: Model-Hosting Strategy Reframe

**Date:** 2026-05-30
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 7972b43
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) (REVISED v2) at 5b6f3de
**Reviewer:** architect (review mode), paranoid pass

## Verdict: WEAK_PASS

The implementation is clean, fail-closed, OOM-safe, in-scope, and free of
regressions. The code is shippable. **However**, there is one
non-code, non-blocking-the-merge but **must-resolve-before-public-ship**
finding: the Qwen Research License on the 3B base genuinely conflicts with
ARAIL's MIT "fork-and-commercialize" blueprint thesis. The builder handled
it correctly within the sprint's authority (attribution is accurate and
present), but the *product decision* it forces is above the builder's pay
grade and must reach the user/visionary before the ai-eng GGUF is packaged
and distributed. This is flagged as [ASK-LICENSE] below and is why this is a
WEAK_PASS, not a PASS. No BLOCK because nothing in the committed code is
broken, insecure, or pulls a heavy model — the legal question is about a
not-yet-existent uploaded artifact, and the code path is fail-closed until
that upload happens.

---

## Spec adherence

Excellent. The per-file edit list in ARCHITECTURE.md was followed item by
item. Verified:

- Sentinel `__TODO_DEEP_MODEL__` present in exactly 16 locations across the
  5 deep-default files (pyproject, setup.sh, backends.py, airllm_worker.py,
  app.py) + the catalog placeholder row + setup.sh comments. Matches
  BUILD_LOG's claim.
- Self-hosted fetch ladder implemented as designed: HF primary → GitHub
  mirror (sha256-verified) → optional CDN → preview net.
- 70B/405B AirLLM keys deprecated-not-deleted; `ARAIL_INSTALL_AIRLLM=1`
  opt-in path untouched.
- Implementation order from §"Recommended implementation order" followed
  (NOTICE first, then sentinels, then setup, then packaging, then copy).
- Sprint commits touched **only** in-scope files (`git diff --name-only
  38b4480~1 7972b43` = the 16 expected files + BUILD_LOG). No scope drift.
  The uncommitted `lab_brain.py` / `cache_prewarm.py` / `chat-highlight.js`
  in `git status` belong to a parallel sprint and are NOT part of these
  commits — confirmed.

## Failure-mode cross-reference (every row from ARCHITECTURE.md §Failure modes)

| Failure mode | Handled? | Evidence |
|---|---|---|
| GGUF not uploaded (HF+GitHub 404) | YES | HF pull non-zero → falls through ladder → preview net. setup never aborts. |
| Host unreachable (timeout/5xx/DNS) | YES | `timeout 900` + `curl -fL -m 900`; each failure → next mirror → preview → warn+continue. |
| Partial/corrupted download | YES | `sha256sum` compared to pinned digest; mismatch → discard file, warn, skip. Never `ollama create` from unverified blob. |
| Pinned digest still placeholder | YES | `_install_from_gguf` returns 1 immediately if `_sha256 == "__PLACEHOLDER_SHA256__"` — **fail-closed, no download-and-trust.** Verified line-by-line. |
| Wrong/unavailable quant tag | YES | `ollama pull hf.co/repo:<quant>` 404 → host-miss → next fallback. Default quant is placeholder `Q4_K_M`. |
| Ollama too old for hf.co native pull | YES | GitHub mirror (raw download + create) covers it. (NOTE: min Ollama version is NOT recorded anywhere — see [INFO-1].) |
| Network down / airgapped | YES | All pulls/curls fail → warn + continue, exit 0, manual command printed. No crash, no partial state. |
| Sentinel reaches a backend loader | YES | `backends.py` + `airllm_worker.py` raise `RuntimeError` on sentinel before any load; `app.py` surfaces a notice. NO download, NO 70B fallback. |
| Deep mode clicked, no model set | YES | Same sentinel guard → friendly notice. Zero bytes downloaded. |
| Sentinel/placeholder accidentally resolved | YES | `ai_eng_sha256 = "__PLACEHOLDER_SHA256__"`, repo/url marked `__PLACEHOLDER__`; sentinel is not a resolvable id. |
| Qwen attribution missing | YES (accurate) | NOTICE present, names Qwen2.5-3B + Qwen Research License + upstream URL + redistribution/HF-card/GitHub-release clause. **License correctness independently verified — see Security.** |
| package_ai_eng.sh fabricates/downloads weights | YES | No weight URLs, no credentials; missing `--base-dir`/`--lora-dir` → prints manual steps, `exit 1`. |
| Modelfile.preview deleted prematurely | YES | Present, retains `FROM qwen2.5:7b`. |
| Maximus copy still "frontier-scale" | YES | grep of README:64, CLAUDE:54, tuning.html:111, pyproject maximus desc → zero matches. |
| OOM during testing | YES | No live LLM loads in this review; ran only the threshold-fixture unit subset. |

All 15 failure modes handled.

## Code quality findings

- [INFO] `install_models()` is now ~120 lines but cleanly sectioned with a
  local `_install_from_gguf` helper; complexity is justified by the
  fallback ladder. The helper correctly centralizes the fail-closed digest
  check so it can't be bypassed by one mirror path. Good structure.
- [INFO] tmp-file hygiene is correct: `rm -f "$_gguf_tmp"` on every error
  branch and a final cleanup. The generated Modelfile is also removed.
- [INFO] BUILD_LOG line 9 has a typo: "Qwen Research License Agreement
  (release date 2026-09-19)". The NOTICE file correctly says 2024-09-19.
  Cosmetic; the NOTICE (the shipped artifact) is right.

## Security findings

- [PASS] **Deep-model sentinel is genuinely un-pickable.** No code path
  resolves `__TODO_DEEP_MODEL__` to a real weight; backends raise before
  load. Deep mode degrades to a notice, downloads nothing. The OOM/SSD
  risk from the old 70B default is eliminated. Confirmed against the
  workspace MEMORY note on OOM pressure.
- [PASS] **Digest verification is fail-closed in committed code, not
  commented.** Re-read `_install_from_gguf` line by line: placeholder
  digest → `return 1` *before* any curl; real digest mismatch → discard +
  `return 1`; only an exact match reaches `ollama create`. The HF primary
  path relies on Ollama's native HF manifest digest verification (correct —
  no raw blob is fed to `create` on path 1).
- [PASS] **No heavy-model surprise pull.** The placeholder HF repo
  (`hf.co/qukaizen/ai-eng-3b-gguf:Q4_K_M`) does not exist yet → 404 → falls
  through. The only thing that can be pulled today is the documented
  preview base (qwen2.5:7b, ~5 GB) as the intentional last-resort net, gated
  behind the existing Ollama-present + `ARAIL_SKIP_OLLAMA` guards. No 70B,
  no 405B, no auto-download of a deep model anywhere.
- [PASS] **package_ai_eng.sh / check_ai_eng_artifact.sh are clean.** No
  embedded credentials, no hardcoded weight-download URLs (only manual
  `# TODO` upload blocks and a documented base-model download command the
  user runs deliberately). `check_ai_eng_artifact.sh` uses HEAD (`-I`)
  probes only — never downloads the blob. Both exit nonzero appropriately.
- [PASS] **LAB_MODE=airgapped untouched.** No cloud-egress gating changed;
  the self-hosted fetch is a model-pull of the same class as the existing
  `ollama pull`, guarded as before.
- [PASS] **License facts independently verified against the live source.**
  HF API confirms `Qwen/Qwen2.5-3B-Instruct` = `license:other` /
  `license_name: qwen-research` (Qwen Research License), and
  `Qwen/Qwen2.5-7B-Instruct` = `apache-2.0`. The NOTICE is factually
  accurate. Builder did the research correctly.

- [ASK-LICENSE] **(HARD GATE — the headline finding.) The Qwen Research
  License on the 3B base conflicts with ARAIL's MIT-blueprint
  "fork/redistribute/commercialize" thesis.** The Qwen Research License is
  a *research-only, non-commercial* custom license (it restricts use to
  non-commercial research and requires a separate commercial license from
  Alibaba Cloud for commercial use), unlike the Apache-2.0 7B base. The
  merged-LoRA GGUF is a derivative and inherits those restrictions. This
  means:
  1. The bottled ai-eng-3b GGUF, once distributed, is **NOT freely
     redistributable for commercial use** by downstream forkers — directly
     at odds with CLAUDE.md's "users are expected to fork, rename, and
     adapt" and the VISION's "everyone gets ai-eng" framing.
  2. The NOTICE correctly *documents* the obligation but cannot *resolve*
     it. Shipping a research-licensed model as the default everyday
     assistant of an MIT blueprint that invites commercialization is a real
     legal exposure for both QuKaiZen (as redistributor) and downstream
     users (who may unknowingly violate the license).

  **This is exactly the disconfirming signal VISION.md §"Disconfirming
  evidence" item 3 named** ("If hiding the qwen lineage draws a credible
  attribution/licensing objection… the branding line is not worth a license
  violation"). It is credible and it is raised here.

  **Severity: must-resolve-before-distribution, NOT merge-blocking.** The
  committed code is fail-closed and ships zero weights — the GGUF does not
  exist yet. Nothing the user merges today violates anything. But the user
  must make one of these product decisions **before running
  `package_ai_eng.sh` and uploading**:
    (a) Re-base ai-eng on an Apache-2.0 / MIT / permissively-licensed model
        (e.g. the Apache-2.0 Qwen2.5-7B, or a permissive 3B such as a
        Llama-3.2-3B-with-its-own-terms, Phi, or an Apache small model) so
        the blueprint thesis holds; OR
    (b) Keep the Qwen-3B base but explicitly reposition ai-eng as
        "research/personal-use, not for commercial redistribution" in the
        README, NOTICE, and HF model card — which weakens the
        "fork-and-commercialize" promise and should be a conscious choice; OR
    (c) Obtain a commercial license from Alibaba Cloud for the base.

  Route this to the visionary/user. Do not let `package_ai_eng.sh` run
  against the Qwen-3B base until the decision is recorded in the sprint
  ledger.

- [INFO] The preview net's base (Qwen2.5-7B, Apache-2.0) is itself
  redistribution-clean — note the *production* base is the problem, not the
  preview base. If route (a) is chosen, the preview net is already on a
  compliant base.

## Test coverage assessment

- BUILD_LOG reports 17→16 failed baseline; I did not run the full suite
  (OOM-safety per the workspace MEMORY note). I ran the regression-critical
  subset the architecture flagged: `frontier`/`threshold`/`must_stream`/
  `dispatch_35b` → **83 passed, 0 failed**. These assert the
  streaming-threshold regex, not the deep default, so the sentinel swap
  correctly did not disturb them — matches the architecture's prediction.
- All shell scripts pass `bash -n`; Python files compile (BUILD_LOG, and
  the imports succeeded under pytest collection of app.py).
- **Coverage gap:** the dedicated setup-ladder tests described in
  ARCHITECTURE.md §Test strategy (HF-success mock, digest-mismatch mock,
  placeholder-fail-closed mock, offline mock, package_ai_eng missing-input
  mock) are **not yet written** — they are QA's deliverable, not the
  builder's. I confirmed the *code* satisfies each scenario by reading; QA
  must write the assertions. Flagged for the QA phase, not a review BLOCK.

## Performance assessment

N/A — config/copy/shell sprint, no hot path, no benchmark required (per
architecture).

## Tech debt delta

Matches ARCHITECTURE.md prediction (net neutral-to-negative). One debt item
the architect did not fully weight, now surfaced: **the choice of base model
is itself a debt** if route (b) above is taken (a research-licensed default
constrains the blueprint). File this under the existing follow-up ticket
"package and upload the ai-eng GGUF" — that ticket MUST NOT be actioned
until [ASK-LICENSE] is resolved. No *new code* debt introduced.

## Required actions before merge

1. **None block the merge of this branch as code.** The diff is clean,
   fail-closed, in-scope, regression-free.

## Required actions before public ship / before packaging the GGUF

1. **[ASK-LICENSE] Resolve the Qwen Research License vs MIT-blueprint
   conflict** (routes a/b/c above) and record the decision in the sprint
   ledger. Do not run `package_ai_eng.sh` against the Qwen-3B base until
   this is decided. Route to visionary/user.
2. (Minor) Fix the BUILD_LOG date typo (2026 → 2024). NOTICE is already
   correct.
3. (Minor, [INFO-1]) Record the minimum Ollama version required for
   `hf.co/...` native pull in the NOTE / docs (architecture called for it;
   the GitHub mirror covers old Ollama, so this is informational).
4. (QA phase) Write the setup-ladder mock tests enumerated in
   ARCHITECTURE.md §Test strategy. No live downloads (mock ollama/curl).
