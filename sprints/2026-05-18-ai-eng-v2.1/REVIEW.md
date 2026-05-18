# Review: ai-eng v2.1 — commit 1 (build/bench tooling)

**Date:** 2026-05-18
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 79ff686
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at f0b38f5
**Range under review:** ad25c88..79ff686 (6 commits)

## Verdict: WEAK_PASS

No BLOCKs. A small number of low-severity findings are filed below as
carryovers — none of them prevent QA from proceeding, but each should be
addressed (in a follow-up patch or by QA exercising the runbook).

---

## Spec adherence

Cross-referenced every §4 failure mode against the code:

| FM  | Spec'd behaviour | In code | Test |
|-----|------------------|---------|------|
| F1  | adapter_config.json keys validated; exit 40 on missing | `probe_adapter_format` at build_ai_eng.py:213 | `TestProbeAdapterFormat` (3 cases) |
| F2  | mlx_lm.fuse failure → continue with Candidate B alone | build_ai_eng.py:294-301 (no sys.exit; writes error log) | covered indirectly via dry-run stubs |
| F3  | mlx→PEFT key translation before merge_and_unload | `_translate_mlx_to_peft` at 311; called at 406-411; catches KeyError at 444 | dry-run path exercises mlx-format branch |
| F4  | Free-RAM probe before each heavy step | `check_free_ram_gb` at 71; called at top of build_candidate_a/b, convert_to_gguf, ollama_create | `TestPreflightChecks` exit 20 path |
| F5  | Bench exit 1 → ship A | bench_ai_eng.py:351-362 (perplexity 1.2× and MMLU 3pp gates) | `TestGateLogic::test_ship_a_perplexity_cliff` |
| F6  | Bench exit 2 → sprint shelved; do not publish | build_ai_eng.py:790-792 raises exit 10; sh:145-149 surfaces it | `TestGateLogic::test_abort_both` |
| F7  | GGUF conversion failure → exit 50 | build_ai_eng.py:528-530, 547-548 | dry-run smoke; failure path not directly tested (LL-1) |
| F8  | ollama create failure → exit 60 | build_ai_eng.py:672-675 | sentinel test |
| F9  | SYSTEM SHA drift exits 60 | generate_modelfile verify at 608-617 | `TestF9SystemaSHADrift` (2 cases) |
| F10 | huggingface-cli whoami probe at publish | _run_publish at 836-842 | not unit-tested (publish out of scope this commit) |
| F17 | HF token redaction in any disk write | `sanitize_log_line` at 59; `_write_safe` wrapper | `TestSanitizeLogLine` (4 cases) + dry-run no-token-leak assertion |
| F18 | No HF token in saved config.json | `_verify_no_token_in_config` at 463; called after merge | dry-run B asserts no-token-in-json |

§4.2 bench methodology was implemented faithfully:
- MMLU(50) from byte-stable `mmlu-sample-v2.1.json` (50 hand-authored CS+EE questions, seed=42 stamped)
- Perplexity over `perplexity-corpus.txt`
- 5-prompt head-to-head against `qwen2.5:7b` via Ollama CLI
- Verbatim per-prompt output capture in BENCH-v2.1.md
- Statistical caveat about n=50 95% CI ±14pp printed in the output (matches §4.2's "vibe gate" note)

The single documented deviation (gitignore allowlist for committed
corpora at `models/ai-eng/`) is correct, minimal (4 lines), and exactly
matches §4.3's "what is committed" list.

§8 commit split (3a vs 3b wire-in) correctly punted to a follow-up
sprint per BUILD_LOG.md §"What was NOT implemented". No setup.sh,
pyproject.toml, models_catalog.yaml, or Modelfile.* edits leaked into
this commit range — confirmed via `git diff --stat ad25c88^..79ff686`
(only scripts/, tests/, models/ai-eng/, sprints/, and .gitignore).

## Scope discipline

PASS. The 6 commits touch only:
- `scripts/{build_ai_eng.sh,build_ai_eng.py,bench_ai_eng.py}`
- `tests/{test_build_ai_eng_dry_run,test_bench_ai_eng_harness,test_modelfile_checksums}.py`
- `models/ai-eng/{bench-prompts.v2.1.yaml,mmlu-sample-v2.1.json,perplexity-corpus.txt,BENCH-v2.1.md}`
- `.gitignore` (4-line allowlist)
- `sprints/2026-05-18-ai-eng-v2.1/BUILD_LOG.md`

Zero scope drift.

## Atomic-commit hygiene

PASS. Each commit is one logical change:
- `ad25c88` corpora + prompts + gitignore allowlist (single thematic unit)
- `a1c060d` build_ai_eng.py only
- `70bb064` bench_ai_eng.py only
- `866bbb4` build_ai_eng.sh only
- `7cf00a5` 3 test files only
- `79ff686` BUILD_LOG.md only

`git revert` on any single commit would be painless.

## Code quality findings

- [INFO] `_main()` in build_ai_eng.py rewrites `args.subcommand = "build"`
  when `dry-run` is selected (line 727-728). Mildly surprising; a comment
  would have helped. Not blocking.
- [INFO] Both build_ai_eng.py and build_ai_eng.sh implement
  `check_portal_not_running`; minor duplication, but the shell version
  exits before invoking Python on a cold cache, which is a reasonable
  defense-in-depth.
- [INFO] `build_candidate_a` returns `out_dir` even on failure (line 301);
  caller relies on sentinel existence to know if A succeeded. The
  downstream `convert_to_gguf` call for winner A would fail. This is
  fine because bench result decides winner first; if A's directory is
  empty, A wouldn't win MMLU. Worth a comment.

## Security findings

- [INFO] `_HF_TOKEN_RE = re.compile(r"hf_[A-Za-z0-9]{10,}")` — pattern is
  appropriate for legacy `hf_` tokens but does not match
  `hf_oauth_*` longer-form tokens or the newer `nv_*`-style. For
  publish-step risk this is acceptable; raise to v2.2 if HF introduces
  a new prefix.
- [INFO] `huggingface-cli whoami` output's "anonymous" string is checked
  case-insensitively (publish gate F10). Good.
- [INFO] No HF token ever appears in argv — confirmed by reading every
  `subprocess.run` site; tokens pass through `env=` only.
- [PASS] Bench prompts grep'd for accidental training-data leakage —
  no Anthropic system prompts, Opus traces, or personal information.

## Test coverage assessment

- **70 new tests, all passing** (verified):
  `python -m pytest tests/test_build_ai_eng_dry_run.py tests/test_bench_ai_eng_harness.py tests/test_modelfile_checksums.py -q` → `70 passed in 0.07s`.
- **Full suite:** `1714 passed, 13 pre-existing failures, 1 xfailed`.
  The 13 failures match the builder's claim exactly (dashboard layout,
  docs routes, airgap toggle, swarm, opencode, system_metrics).
  Builder did NOT introduce a new failure.
- Spot-checks:
  - `test_modelfile_checksums.py::TestSystemBlockSha::test_generated_modelfile_system_matches_production` actually invokes `generate_modelfile` on the real production file and compares re-extracted SYSTEM text byte-for-byte. Real coverage, not smoke.
  - `TestModelfileProductionInvariants::test_system_block_mentions_honesty` enforces the "don't know" string in the production SYSTEM block — real semantic invariant matching the VISION honesty requirement.
  - `TestSanitizeLogLine` includes a multi-token line — real redaction coverage.
- **Coverage gap (LL-1):** GGUF conversion failure path (F7) is not
  directly unit-tested; only the success path is exercised in dry-run.
  Not blocking — the failure path is a `sys.exit(50)` after a subprocess
  rc check, which has a small surface area.

## Performance assessment

Not applicable this commit — no inference is run; the bench harness is
deterministic-by-design with seed=42, temperature=0.0, fixed max_tokens.
A real performance bake (latency p50, perplexity) will land when the
operator executes `./scripts/build_ai_eng.sh build` on the dev box.

## Tech debt delta

Matches ARCHITECTURE §7 prediction. No surprise additions:
- 3 operator scripts, 4 committed corpora, 3 test files
- `TD-v2.2-bench-n` filed in BENCH-v2.1.md template body (n≥200 lift)
- `TD-v1.2-sunset-preview` (untouched this commit; setup.sh not edited)

Net debt change for this commit: slightly negative (reusable scripts +
codified gates pay forward for v2.2+).

## Carryovers (do before merging the full sprint)

These are low-priority follow-ups; they do not BLOCK QA:

- [ ] **CO-1: Dry-run RAM gate.** `build_candidate_a` calls
  `check_free_ram_gb` *before* the `if dry_run:` short-circuit
  (build_ai_eng.py:272-274). On a dev box with <16 GB free RAM the
  `./scripts/build_ai_eng.sh dry-run` command exits 20 before it can
  smoke the rest of the code paths. Fix: gate the RAM/disk pre-checks
  behind `if not dry_run:` (matches the existing pattern in
  `_main()` lines 762-764). Reproducer: running dry-run on this dev box
  during review halted at `OOM pre-check: only 15.2 GB free`. The unit
  tests still pass because they call the functions with low thresholds
  or in mocked environments, masking the runbook UX issue.
- [ ] **CO-2: Bench ollama preflight.** `OllamaHandle.generate` will
  silently populate per-prompt outputs with `[ERROR: ...]` strings if
  `qwen2.5:7b` is not installed. Add a one-shot
  `ollama list | grep qwen2.5:7b` preflight at the top of `run_bench`
  with a clear "incumbent comparison requires `ollama pull qwen2.5:7b`
  first" message. Matches the `project_warmup_overlay_invisible` rule:
  don't let bench silently produce error-tagged outputs.
- [ ] **CO-3: GGUF failure-path test.** Add a single unit test that
  injects a non-zero subprocess return from `convert_hf_to_gguf.py` and
  asserts `sys.exit(50)`. Covers the F7 detection path that BUILD_LOG
  claims is wired but is currently only implicit-tested.
- [ ] **CO-4: build_candidate_a degraded comment.** Add a one-line
  comment at build_ai_eng.py:301 explaining that the empty
  `out_dir` return is intentional and the caller relies on bench
  outcome (not sentinel) to skip A. Minor readability nit.
- [ ] **CO-5: hf-token regex coverage.** Note in `sanitize_log_line`
  docstring that the regex is for `hf_` prefix tokens; if HF introduces
  a new prefix (oauth, `nv_`-style), the redaction must be extended.

## QA brief

Hand off to `/qa` per ARCHITECTURE §6.6 with these specific asks
(re-stated from the architecture's QA allocation):

- 30% setup: simulated registry 404 / corrupt-pull fallback copy
  (deferred — this is commit 3a scope, not in range)
- 30% Buddy: 5-prompt AI-eng head-to-head **on the dev box, after
  operator runs `./scripts/build_ai_eng.sh build`**. Cannot be QA'd
  before the operator builds.
- 20% security: grep `build/` and sprint dir for `hf_` tokens (none
  expected; build hasn't been run yet, but the sanitisation path is
  tested)
- 10% happy: deferred to post-publish
- 10% regression: confirm `pyproject.toml`, `setup.sh`,
  `models_catalog.yaml` shapes unchanged (they are; sprint left them
  untouched)

Most of QA's bench-execution allocation is gated on the operator
running the build. QA can still:
- Re-run the 70-test new suite on their machine and confirm pass count
- Walk the runbook in BUILD_LOG.md cold and report whether Step 1
  (`dry-run`) actually completes (hint: it may not, see CO-1)
- Grep all committed files for accidental token strings

## Required actions before merge

None (WEAK_PASS). Address carryovers in a follow-up small patch or
have QA file them as TODOs in the sprint's TEST_REPORT.md.
