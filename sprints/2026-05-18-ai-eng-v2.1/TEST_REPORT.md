# Test report: ai-eng v2.1 — commit 1 (build/bench tooling)

**Date:** 2026-05-18
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 79ff686
**Review:** [REVIEW.md](./REVIEW.md) (WEAK_PASS, 5 carryovers)
**Branch:** qukaizen/arail-ai-eng-v2.1

## Verdict: WEAK_PASS

CO-1 reproduces but is now **locked down by an xfail regression test**
that flips to a passing test the moment the builder applies the
2-line fix. No security blockers. No new test failures in the full
suite. The operator runbook walks cleanly except for CO-1 itself
(Step 1 dry-run on the documented 16 GB-default threshold passes by
2.1 GB of headroom on this dev box; would fail on a box with <16 GB
free).

Verdict is WEAK_PASS rather than PASS because CO-1 is a real user-facing
defect that the review surfaced and that this QA pass confirmed
reproducible. It is not FAIL because (a) the bug is locked down with a
test that will catch the fix landing, (b) it does not affect any
shipped runtime path — only the operator-facing dry-run smoke, and
(c) the rest of the build/bench surface is well-covered.

## Test allocation (this sprint — adapted from ARAIL 30/30/20/10/10)

| Bucket                              | Target | Actual | Notes |
|-------------------------------------|--------|--------|-------|
| Operator runbook / setup-clarity    | 30%    | 5/16   | runbook walked; --help, unknown-subcommand, dry-run-lockdown, bench dry-run schema, low-RAM dry-run |
| Bench-harness correctness (Buddy-sub) | 30%  | 5/16   | prompts schema, prompts IDs unique, h2h IDs resolve, probe-format invalid/missing JSON |
| Security                            | 20%    | 4/16   | no shell=True, HF token not in argv, sanitise_log_line on realistic 401, _verify_no_token_in_config |
| Happy path                          | 10%    | 1/16   | CO-1 dry-run lockdown (xfail until fixed) |
| Regression                          | 10%    | 1/16   | sprint did not touch setup.sh/pyproject/catalog/Modelfile.* |

(15 passing + 1 xfailed = 16 new tests in `tests/test_build_ai_eng_dry_run_works_on_lowram.py`.)

## Carryover disposition

| ID | Title | Reproduces? | Severity | Disposition | Locked-down by |
|----|-------|-------------|----------|-------------|----------------|
| CO-1 | Dry-run RAM gate fires even in dry mode | YES (clean build/, --min-free-ram-gb 999999, rc=20) | non-blocker | open — assigned back to builder | `test_dry_run_exits_zero_with_huge_ram_threshold` (xfail; flips when fixed) |
| CO-2 | Bench ollama preflight silent on missing qwen2.5:7b | not reproduced (would require running bench against a missing model); reviewed code at OllamaHandle.generate:229–232 — confirms silent `[ERROR: ...]` strings populate outputs | minor | accepted as tech debt; matches `project_warmup_overlay_invisible` rule but defers to operator-side runbook gate | not blocked; suggested fix lives in `run_bench`'s entry point |
| CO-3 | GGUF conversion failure path untested | confirmed via inspection | minor | resolved | `test_gguf_conversion_failure_exits_50` |
| CO-4 | build_candidate_a degraded-return comment | nit | minor | accepted | n/a (code-readability nit; no test) |
| CO-5 | hf-token regex coverage docstring | nit | minor | accepted as future-proofing; covered partially by `test_sanitize_log_line_strips_token_from_realistic_hf_error` | partial |

## Bug-find log

| # | Severity | Finding | Repro | Recommended fix | Test |
|---|----------|---------|-------|------------------|------|
| BUG-1 | non-blocker | **CO-1 confirmed:** `./scripts/build_ai_eng.sh dry-run` invokes `check_free_ram_gb` from `build_candidate_a` before the `if dry_run:` short-circuit. On any dev box where free RAM is below `--min-free-ram-gb` (default 16) the dry-run exits 20 before exercising the rest of the code paths. Reproduced with `rm -rf build/ && bash scripts/build_ai_eng.sh dry-run --min-free-ram-gb 9999` → rc=20. | see above | Gate `check_free_ram_gb` (and `check_free_disk_gb` if applicable) behind `if not dry_run:` in `build_candidate_a`, `build_candidate_b`, `convert_to_gguf`, `ollama_create`. Matches the pattern already used in `_main` lines 762–764. | `test_dry_run_exits_zero_with_huge_ram_threshold` (xfail) |
| BUG-2 | minor / privacy | Bench script writes `socket.gethostname()` into BENCH-v2.1.md (line 374) and the operator runbook copies that file into `models/ai-eng/BENCH-v2.1.md` for commit. If the operator's hostname is real (e.g. `netsushi-mbp.local`), it lands in the public repo. | manual: `python3 scripts/bench_ai_eng.py --dry-run` writes the literal "localhost" string in dry mode — the real run will write the real hostname. The committed *template* is safe (placeholders escaped); the danger is at copy-after-bench time. | Sanitize hostname before write — either redact to the platform.machine() chip name only, or document in BUILD_LOG runbook Step 3.5 "scrub host line before commit". Today's committed template is clean (this QA test guards regression on the template). | `test_committed_bench_template_has_no_hostname_or_home_leak` |
| BUG-3 | minor | `OllamaHandle.generate` returns `f"[ERROR: {r.stderr[:100]}]"` and populates the outputs dict silently when `qwen2.5:7b` is not installed (CO-2). The h2h gate then treats those error strings as "incumbent output" and the length-proxy heuristic may spuriously make Candidate A "win". | not reproduced (skipped — requires real bench run with missing model) | Preflight in `run_bench`: `ollama list | grep -q qwen2.5:7b` else log a clear "incumbent requires `ollama pull qwen2.5:7b`" and abort with a distinct exit code. | open (CO-2 disposition) |

## Security review

| Surface | Checked | Findings |
|---------|---------|----------|
| User input (`--adapter-repo`, `--build-dir`, `--license`, etc.) | Yes — every argparse field passed to `subprocess.run` as a list element (argv), not interpolated into a shell string. `shell=True` grep returns zero hits across `scripts/build_ai_eng.{py,sh}` and `scripts/bench_ai_eng.py`. | Clean. |
| HF token handling | `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` read once into `env=` dict in `download_adapter`; never appears in argv (verified by `test_hf_token_never_in_argv_construction`). The `huggingface-cli download` invocation places the repo id positionally and the token is consumed by the underlying lib via env. | Clean. |
| Token leakage in error logs | `_write_safe` wraps every error capture in `sanitize_log_line` which strips `hf_[A-Za-z0-9]{10,}`. Regression test exercises a realistic 401 stderr embedding a token; redaction confirmed. Caveat: only `hf_` prefix is covered; OAuth-style and `nv_`-style tokens are not (CO-5). | Acceptable for v2.1; flag for v2.2. |
| Persistence of secrets to disk | Build artifacts under `build/` are git-ignored except the 4-line allowlist for committed corpora. No `lab/data/secrets.env` writes from these scripts. | Clean. |
| Path traversal via `--build-dir` | `Path(args.build_dir).resolve()` — symlinks resolved but no allowlist. An operator who passes `--build-dir /etc/passwd-dir` could in principle write sentinels there. Operator-trusted surface; flagging only because no validation exists. | Low risk (operator-only entry point; not a network surface). |
| Deserialization | `safetensors.torch.load_file` for the adapter — safe parser (no pickle). `yaml.safe_load` for prompts file. `json.loads` for adapter_config. | Clean. |
| Subprocess invocations | All use list-form argv. No `os.system`. Timeouts present on `ollama run`. | Clean. |
| Hostname / HOME leakage | BENCH-v2.1.md template clean (placeholders only); live runs embed `socket.gethostname()` — BUG-2 above. | Documented; not blocking. |
| Dependencies (`mlx-lm`, `peft`, `transformers`, `safetensors`, `psutil`, `pyyaml`) | All operator-side install; not added to runtime arail deps. | Clean. |

## Operator runbook walkthrough (cold)

| Step | Status | Notes |
|------|--------|-------|
| Prereqs (stop portal, free RAM, free disk, `pip install`, `huggingface-cli login`, ollama running) | OK | unambiguous |
| Step 1 — dry-run | **DEGRADED** | CO-1: exits 20 on any box with free-RAM < `--min-free-ram-gb` (default 16). On this dev box's current 18 GB free, dry-run completes; on the 15.2 GB-free state described in REVIEW.md, it does not. |
| Step 2 — full build | not executed (out of scope per sprint guard — multi-GB downloads) | runbook documents wall-clock + RAM requirements clearly |
| Step 3 — review BENCH-v2.1.md | OK | exit-code decision tree printed; matches gate logic |
| Step 4 — publish | OK | clearly marked "out of scope for commit 1" |
| Step 5 — run tests | OK | command works; 70 + 16 = 86 new sprint tests collect |

Ambiguity gaps the runbook does NOT cover (filed as minor docs debt, not blockers):
- "What if `huggingface-cli` is not installed?" — script's `_run_publish` checks at publish time, but `download_adapter` would surface a `FileNotFoundError` from `subprocess.run` if the CLI is absent. A friendlier preflight would help.
- "What if `llama.cpp` is at a different commit than `b3500`?" — script `git fetch --depth=1 origin b3500 && git checkout b3500`; that fetch may fail if `b3500` is not a fetchable ref. Operator-side concern.
- "What if `ollama serve` is not running?" — `ollama create` would fail with a connect-refused; falls under F8 (exit 60); message is clear.
- CO-2: missing `qwen2.5:7b` produces silent `[ERROR: ...]` outputs through the bench rather than a hard abort.

## Coverage delta

| | Before | After |
|-|--------|-------|
| Tests passing | 1714 | 1729 |
| Tests failing | 13 (pre-existing; unchanged) | 13 |
| xfailed | 1 | 2 (added CO-1) |
| Sprint test files | 3 | 4 |
| Sprint tests | 70 | 86 |

**Regression statement:** 13 pre-existing failures, byte-for-byte
identical list. Zero new failures introduced by this QA pass or by
sprint commits ad25c88..79ff686.

## Notes for the next QA pass

- **CO-1 must be re-verified post-fix:** when the builder lands the
  `if not dry_run:` gate, the xfail flips to a passing test
  automatically; re-running the test file is the verification.
- **Bench-on-real-models (Buddy substitute) is gated on operator
  running `./scripts/build_ai_eng.sh build` on the dev box.** That can
  only happen once the v2.1 adapter is published. QA should rerun this
  TEST_REPORT pass after publish to:
  - Confirm BENCH-v2.1.md committed to repo carries no hostname / HOME
    paths (current test guards the template; the live-write path needs
    a manual review before each commit).
  - Run the 5-prompt AI-eng head-to-head inside the portal Chat UI per
    ARCHITECTURE §6.6.
- **CO-2 (ollama preflight) deserves a follow-up patch** before
  Phase 2 publish, even if non-blocking — silent error-string outputs
  could push h2h_a_wins arithmetic into spurious territory.
- **Path-traversal on `--build-dir`** is unvalidated; if this ever
  becomes web-reachable (it shouldn't), revisit.
- **`bench_ai_eng.HEAD_TO_HEAD_IDS` is a hard-coded set in the script
  body.** Any prompts-file rename of an `ae-0*` id will silently
  reduce the h2h ceiling. Tests in this report guard the current set;
  v2.2 retrain should move this into the YAML.
