# Test report: ARAIL Two-Tier Model Architecture

**Date:** 2026-06-14
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 9d6875f
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) · **Review:** [REVIEW.md](./REVIEW.md)
**QA host:** Apple Silicon (arm64), 36 GB RAM, macOS 25.5, Ollama 0.x present
**Verdict:** WEAK_PASS

---

## Verdict rationale

The two hard ship gates **pass**:

- **F11 reasoning gate (blocks ship per VISION): maximus beats minimalist 5/5.**
  The wedge holds — the deep tier is not theater.
- **Llama disclosure (hard license gate): present and machine-verified on every
  surface** (Modelfile SYSTEM, README, catalog, NOTICE with verbatim attribution
  + AUP, `licenses/` both files, tier-selection doc).

But three things keep this off a clean PASS:

1. **A NEW sprint test is order-dependent and FAILS in the full suite**
   (`test_model_separation.py::test_ollama_model_starts_with_llama`). It passes
   in isolation, fails after other tests run, because it reads the live
   `MODEL_NAME` env which `.env` sets to the stale `ai-engineer:latest`. This is
   a test-quality defect introduced by this sprint (severity: medium — the test
   that guards the disclosure-naming contract is flaky and currently red).
2. **The minimalist smoke set scored exactly 8/10 — at the floor, not above it.**
   Both failures were code/command tasks where the 1B gave a *confident wrong*
   answer (broken `lsof` command; a "bash one-liner" that was invalid Python).
   That is precisely the "embarrasses itself" risk the trust gate exists to
   catch. It clears the bar but with zero margin.
3. **Known F8 tech debt** (`backend_notice` emitted in SSE but not rendered) —
   confirmed exactly as the architect flagged; carried as documented follow-up.

None of these is a stop-ship on their own, but the flaky new test should be
fixed before merge (it's a one-line `monkeypatch.delenv` / env-isolation fix in
the test, builder's job). Hence **WEAK_PASS**, not PASS.

---

## Test matrix

| # | Test / check | Category | Result | Notes |
|---|---|---|---|---|
| 1 | 17 new unit tests in isolation | unit | PASS | `17 passed in 0.02s` — disclosure (10) + separation (7) |
| 2 | Full suite re-run | regression | **MISMATCH** | Observed **42 failed / 2364 passed / 1 skip / 1 xfail**, NOT the build log's 40/2373. See Regressions. |
| 3 | `test_ollama_model_starts_with_llama` in full suite | regression | **FAIL** | Order-dependent; reads live `MODEL_NAME=ai-engineer:latest` from `.env`. Passes alone. NEW sprint test. |
| 4 | F1 — `ollama_default_enabled()` tier-gate | setup | PASS (code) | setup.sh:47 gates on `LAB_TIER`, well-commented "do NOT revert". Edge gap below (maximus+mlx). |
| 5 | F1 runtime — `llama-ai-eng` installed | setup | N/A on host | NOT installed on this box (had `ai-engineer:latest`, `qwen2.5:7b`). Clean-machine create-step not exercised end-to-end; QA pulled `llama3.2:1b` to run F11. |
| 6 | F5 — CUDA AeroLLM-not-ready notice | setup | PASS | upgrade.sh:127–140 prints honest "Apple-Silicon-only today" + AirLLM opt-in + cloud. Weights NOT auto-downloaded. |
| 7 | F8 — `backend_notice` data path | happy | PASS (data) | Emitted in all 4 `final` SSE events (app.py:5602/5633/5674/5814). **No template/JS renders it** — gap confirmed. |
| 8 | F7 — 16 GB RAM floor warning | setup | PASS (code) | setup.sh:1198 `< 17179869184` → honest downgrade msg. Not runtime-fired (host is 36 GB). |
| 9 | F9 — Llama disclosure surfaces | security/license | PASS | Modelfile, README, catalog, NOTICE (+verbatim attribution +AUP), licenses/ both files, tier-doc. |
| 10 | F10 — model separation defaults | regression | PASS (defaults) | `llama-ai-eng` ≠ `Qwen2.5-7B-Instruct-4bit`; but the naming test is flaky under env pollution (#3). |
| 11 | F11 — maximus beats minimalist reasoning | quality (ship gate) | **PASS 5/5** | See below. Hard gate cleared with margin. |
| 12 | Minimalist 10-prompt smoke set | quality (trust gate) | **PASS 8/10** | At the floor. Both misses are confident-wrong code/command answers. |
| 13 | Minimalist latency (TTFT / full short) | performance | PASS | First token immediate; full short reply ~0.18–0.21 s on this host. (36 GB, not 16 GB.) |
| 14 | Airgapped egress (minimalist) | security | PASS | Ollama is localhost (`/api/*` on 11434); only network call is the setup-time pull; `huggingface-cli` line is printed, never auto-run. |
| 15 | docs/tier-selection.md present | happy | PASS | Canonical which-tier copy + per-tier disclosure (Llama / Apache). |

---

## Win condition assessment (5 from VISION)

| Win condition | Threshold | Result | Evidence |
|---|---|---|---|
| Minimalist TTFT | < 2 s | **PASS** | Streaming first token returns immediately on this host |
| Minimalist full short reply | < 8 s | **PASS** | ~0.18–0.21 s measured (3 runs) |
| Minimalist smoke set | ≥ 8/10 coherent | **PASS (floor)** | 8/10 — Q4 wrong `lsof` cmd, Q6 invalid bash-as-Python both failed |
| Maximus beats minimalist | ≥ 4/5 reasoning | **PASS** | **5/5** (bat-and-ball, transitivity, apples-today, all-but-9-sheep, missing-dollar) |
| Llama disclosure compliance | hard gate | **PASS** | All surfaces machine-verified; NOTICE carries verbatim attribution + AUP |

**Caveat on hardware:** All latency / no-OOM / smoke results were collected on a
**36 GB** arm64 box. VISION's thresholds are written for **16 GB M-series**. The
1B (~1.3 GB) and 7B-4bit (~4.7 GB) both fit with large headroom here, so this
run does **not** prove the 16 GB floor (F3/F4/F7 runtime behavior). It proves
the models work and the logic is correct; it does not prove the resource floor.

### F11 reasoning detail (the ship gate)

| Prompt | Minimalist (llama3.2:1b) | Maximus (qwen2.5:7b) | Winner |
|---|---|---|---|
| Bat & ball ($1.10) | $0.45 (wrong) | $0.05 (correct) | maximus |
| Transitive Bloops→Lazzies | "No" (wrong) | "Yes" + reason (correct) | maximus |
| 3 apples today, ate 2 yesterday | "1 apple" (wrong) | "3" + reason (correct) | maximus |
| 17 sheep, all but 9 die | "8" (wrong) | "9" (correct) | maximus |
| Missing-dollar puzzle | confused/wrong | correct accounting | maximus |

5/5. The deep tier earns its existence. *(Note: QA used `qwen2.5:7b` via Ollama
as the maximus stand-in; the shipped maximus path serves the same Qwen2.5-7B
lineage via AeroLLM/MLX. The model family is identical; the serving runtime
differs — quality result is representative, latency on AeroLLM is not measured
here.)*

### Smoke-set misses (the 2 of 10)

- **Q4 "find process on port 8080":** returned `lsof -p :8080` — wrong (`-p` is
  for PID; correct is `lsof -i :8080`) plus a fabricated output table.
- **Q6 "bash one-liner to count lines in .py files":** returned invalid Python
  (a generator with `for ... print`) labeled as bash — wrong language, won't run.

Both are confident-wrong on *executable* tasks. Coherent-but-wrong code is the
highest-trust-cost failure mode for a "lab partner." 8/10 holds but is fragile.

---

## Regressions — full baseline test count

| | Build log claim | QA observed (full suite) |
|---|---|---|
| Failing | 40 | **42** |
| Passing | 2373 | **2364** |
| Skipped / xfail | — | 1 / 1 |

The build log's "-1 failing / +18 passing" delta did **not** reproduce. I cannot
cleanly diff against the pre-sprint baseline (working tree is dirty with
unrelated changes and 15 stashes; checking out the parent commit was unsafe), so
I classify by file ownership instead:

- **40 of the 42 failures are in modules this sprint did not touch** —
  `test_recap_*`, `test_docs_routes*`, `test_swarm_goal_surfaces`,
  `test_aerollm_defaults`, `test_system_metrics`, `test_qa_airgap*`,
  `test_opencode_*`, etc. These are pre-existing / unrelated and outside sprint
  scope. (The count drift from "41 baseline" likely reflects the dirty tree and
  unrelated in-flight work, not this sprint.)
- **1 failure IS sprint-owned and IS a real regression introduced here:**
  `test_model_separation.py::test_ollama_model_starts_with_llama` (the flaky
  env-pollution failure, #3 above).

So: net effect of *this sprint* on the suite is **+16 reliably-green tests
(10 disclosure + 6 stable separation) and +1 flaky red test**, not the claimed
+18 clean. The "no new failures" claim in the build log is **false** — there is
one new failure, and it's in a sprint test.

---

## Security review

| Surface | Checked | Findings |
|---|---|---|
| User input | upgrade notice + backend label are output-only static literals | No interpolation of untrusted data; no injection vector into SSE payload. Clean. |
| Network I/O | Confirmed Ollama backend is localhost (`:11434`); only setup-time network call is `ollama pull`; `huggingface-cli download` is printed for manual run, never auto-executed | Airgapped posture preserved on the minimalist path. Clean. |
| File I/O | `licenses/` reads; Modelfile path under repo root | No path-traversal surface added. Clean. |
| Deserialization | None added | N/A |
| Crypto | None added | N/A |
| Dependencies | maximus extra (Anthropic SDK, LangChain) is opt-in via `upgrade maximus`, not pulled on minimalist | No new deps on the default path. |

No security finding above INFO. Matches the architect's read.

---

## Tech debt found (beyond architect's two flags)

The architect already ticketed (1) F8 render gap and (2) the two-Qwen-IDs
footgun in setup.sh. **Additional items QA surfaced:**

1. **`test_ollama_model_starts_with_llama` is not env-isolated (NEW, fix before
   merge).** It reads process `MODEL_NAME`, which `.env` sets to the legacy
   `ai-engineer:latest`. The test passes alone, fails in-suite. Fix:
   `monkeypatch.delenv("MODEL_NAME", raising=False)` (and `AEROLLM_MODEL`) at
   the top of each separation test so it asserts the *default*, not whatever the
   ambient env carries. As written it both flakes AND fails to actually test the
   default it documents.
2. **`.env` ships a stale `MODEL_NAME=ai-engineer:latest`.** This is the
   pre-v1.0.0 deep persona name, not the minimalist `llama-ai-eng`. On a machine
   with this `.env`, the resolver lands on the 7B persona as the "default" model,
   not the 1B. Worth a doctor/migration check — it's the exact 1B/7B conflation
   (F10) the sprint set out to prevent, leaking in via config rather than code.
3. **Maximus + Apple-Silicon clean-machine gap (F1 edge).**
   `ollama_default_enabled()` returns false for `maximus + mlx`, so on a clean
   *maximus* M-series setup Ollama is skipped and `llama-ai-eng` (the everyday
   1B that maximus *also* includes) never installs. The minimalist clean path is
   covered; the maximus clean path is not. Low severity (maximus is opt-in) but
   it contradicts "maximus = minimalist + deep."
4. **No 16 GB hardware in the QA loop.** Every resource win condition (F3/F4/F7,
   no-OOM, KV source != floor) was validated on a 36 GB box. The 16 GB floor —
   the literal headline of VISION's win condition — remains unproven. This is a
   coverage gap, not a defect.

---

## Coverage delta

- New tests added by sprint: **17** (10 disclosure + 7 separation).
- Reliably green from this sprint: **16**.
- Flaky/red from this sprint: **1** (`test_ollama_model_starts_with_llama`).
- Full suite: **2364 passing / 42 failing / 1 skipped / 1 xfailed** on this host.
- Sprint-attributable failures: **1** (the rest are unrelated/pre-existing).

---

## Ship readiness — prerequisites before merge

**Must fix (blocks PASS, not necessarily ship):**
1. Make `test_model_separation.py` env-isolated (delenv `MODEL_NAME` /
   `AEROLLM_MODEL`) so the disclosure-naming test is deterministic and actually
   tests the default. (Builder, ~5 min.)

**Should do:**
2. Resolve / document the stale `.env` `MODEL_NAME=ai-engineer:latest` — it
   re-introduces 1B/7B conflation via config. Add to doctor.
3. Re-run F11 + smoke set + latency on a real or constrained **16 GB** M-series
   to actually prove VISION's headline floor (F3/F4/F7 runtime). Until then the
   resource win condition is asserted, not demonstrated.

**Carried as known debt (architect-ticketed, not blocking):**
4. F8 `backend_notice` frontend render.
5. setup.sh two-Qwen-IDs disambiguation comment.

**Cleared and durable:** Llama disclosure (machine-verified, stop-ship gate
live), F11 reasoning wedge (5/5), minimalist latency, airgapped posture.

---

## Notes for the next QA pass

- The separation tests assert `os.getenv("MODEL_NAME", default)` — that pattern
  tests *ambient env*, not the *code default*. Any test that reads process env
  to "check a default" is a latent flake; audit the other env-reading tests
  (`test_aerollm_defaults`, `test_dispatch_35b_enforcement`) the same way.
- The smoke-set failures clustered on **executable code/command** prompts, not
  prose. If the trust bar is ever tightened, weight code prompts higher — that's
  where the 1B leaks confidence-without-correctness.
- Get a 16 GB box into the loop. Three failure modes (F3/F4/F7) and the entire
  resource win condition are currently theory on this hardware.
