# Test report: Provider-aware chat dropdown (4-layer expanded sprint)

**Date:** 2026-05-20
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `40d8523` (branch `qukaizen/arail-provider-aware-chat-dropdown`)
**Review:** [REVIEW.md](./REVIEW.md) loop 2 — PASS, 3 carryovers handed to QA
**Verdict: WEAK_PASS**

WEAK_PASS, not PASS, on one ground only: a **test-hygiene defect this sprint
introduced** — `tests/test_chat_default.py`'s L4 SET-path tests write the
**real** `lab/data/secrets.env` and leak `os.environ` keys (finding QA-1). It is
**not** a product bug and trips **none** of the FAIL gates (no XSS reaches the
DOM unescaped, every cloud path checks airgap before doing work, no token is
echoed, set-ctx traversal is blocked, F-DEFAULT-LEAK holds end-to-end, and the
full suite has zero new failures attributable to this sprint). The product is
shippable; the test suite needs a one-fixture fix before merge to stop it
clobbering developers' secrets and contributing to env-leak pollution.

---

## Test allocation breakdown

Architect's reallocation for a post-setup UI feature: 40% provider-flip UX /
30% security / 20% race & failure / 10% regression. **51 new QA tests** added
(50 paranoid + 1 JS-render wrapper running 4 JS assertions), on top of the
builder's 124 sprint tests.

| Bucket | Target | New QA tests | Notes |
|---|---|---|---|
| Provider-flip UX edge | 40% | 20 (8 UX-* paranoid + 3 JS-render: B1 cards, B1 empty, F-RACE) + share of XSS | flip-restore, 403-listing, 200-cap, per-provider CTA, case/whitespace, empty-list |
| Security | 30% | 15 (7 SEC-* + 1 JS XSS + parametrized airgap ×20 cases counted as 2 tests) | XSS (server + real-JS render), airgap ×10 on 2 paths, token-echo, traversal battery |
| Race & failure | 20% | 11 (8 RF-* + boundary param + dispatch-wiring) | F-DEFAULT-LEAK e2e, F-CACHE purge, ctx boundaries, timeout injection, num_ctx dispatch |
| Regression | 10% | 5 (4 REG-* + catalog back-compat) | R1 no-cloud-leak, R1 nested type-stability, R4, parser exactness |

Counts overlap by design (XSS spans UX+security). Bucket emphasis matches the
40/30/20/10 split.

New test files:
- `tests/test_qa_provider_dropdown_paranoid.py` — 50 tests (UX/SEC/RF/REG)
- `tests/test_qa_js_render_cloud_dropdown.py` — 1 pytest wrapper (skips w/o node)
- `tests/js/cloud_render_harness.mjs` — Node JS-render harness (4 assertions)

---

## Test inventory (new QA tests)

| # | Test | Category | Covers | Status |
|---|---|---|---|---|
| UX-1 | flip cloud→my_machine restores local gallery | UX edge | no stale cloud cards on restore | PASS |
| UX-2 | token valid but /models 403 | UX edge | architect open-q #2; empty catalog, no 500, no local fallthrough | PASS |
| UX-3 | OpenRouter returns 250 → 200-cap holds | UX edge | cap + UI doesn't choke | PASS |
| UX-4 | two token-less providers → per-provider CTA | UX edge | no stale CTA carryover | PASS |
| UX-5 | unknown provider → CTA never 500/local | UX edge | F-VALIDATE fallthrough | PASS |
| UX-6 | "  Claude  " normalized | UX edge | case/whitespace robustness | PASS |
| UX-7 | cloud current never a local id | UX edge | F-CLOUD-CURRENT belt | PASS |
| UX-8 | token + empty list → "no models" not CTA | UX edge | architect open-q #2 tail | PASS |
| SEC-1 | XSS model id escaped (server stores raw, escapeHtml neutralizes) | security | F7 / FAIL-gate | PASS |
| SEC-2 | template grep: every cloud id insertion escaped | security | F7 source pin | PASS |
| SEC-3 | airgap refusal on /api/chat/models ×10 providers | security | F-AIRGAP / FAIL-gate, no outbound call | PASS |
| SEC-4 | airgap refusal on /api/chat/default ×10 providers | security | F-DEFAULT-LEAK set-time / FAIL-gate | PASS |
| SEC-5 | no endpoint echoes a token | security | token-echo / FAIL-gate | PASS |
| SEC-6 | set-ctx traversal battery rejected | security | F-VALIDATE traversal | PASS |
| SEC-7 | set-ctx colon-ollama accepted / slash rejected | security | F-VALIDATE needle | PASS |
| RF-1 | F-DEFAULT-LEAK end-to-end (set cloud hybrid→airgap→resolve) | race/fail | FAIL-gate | PASS |
| RF-2 | per-message value wins over default | race/fail | A8 | PASS |
| RF-3 | bad-JSON default does not raise | race/fail | degradation | PASS |
| RF-4 | set-ctx purges cache for model only | race/fail | F-CACHE | PASS |
| RF-5 | ctx override flows into ollama dispatch num_ctx + /api/chat | race/fail | B2 / F-OLLAMA-SHIM | PASS |
| RF-6 | ctx boundaries 256/1M ok, 255/1M+1/0/neg reject | race/fail | F-OOM boundary | PASS |
| RF-7 | non-integer ctx rejected | race/fail | input validation | PASS |
| RF-8 | upstream /models timeout → empty, no 500 | race/fail | failure injection | PASS |
| REG-1 | no-provider payload has no cloud-only fields | regression | R1 spirit | PASS |
| REG-2 | R1 nested type-stability (deep/compact scalars) | regression | carryover #2 | PASS |
| REG-3 | CatalogEntry legacy-row back-compat | regression | R4 / F-CATALOG | PASS |
| REG-4 | context_tokens exact parse values | regression | parser | PASS |
| JS-1 | gallery.catalog entries paint cards (real JS) | UX edge | B1 / carryover #1 | PASS |
| JS-2 | empty catalog → "No models returned" (real JS) | UX edge | B1 | PASS |
| JS-3 | flip A→B, A resolves last → grid shows B (real JS) | race | F-RACE / carryover #1 | PASS |
| JS-4 | malicious id escaped in rendered DOM string (real JS) | security | F7 | PASS |

**Sprint suite (builder 124 + QA 51): 175 passed, 0 failed.**

---

## Failures (bugs found)

| # | Finding | Symptom | Minimal repro | Severity | Fix rec | Locking test |
|---|---|---|---|---|---|---|
| QA-1 | L4 SET-path tests clobber the REAL `lab/data/secrets.env` and leak `os.environ` | Running `tests/test_chat_default.py::test_chat_default_set_cloud_in_hybrid_ok` rewrites `lab/data/secrets.env` to test artifacts (e.g. `COMPUTE_SOURCE=claude`), destroying any saved provider tokens; `os.environ["COMPUTE_SOURCE"]` persists into later tests | `rm lab/data/secrets.env && pytest "tests/test_chat_default.py::test_chat_default_set_cloud_in_hybrid_ok"` → file recreated with test data | **non-blocker (test-only), high-priority** | In `tests/test_chat_default.py::_make_client`, monkeypatch `portal_app._secrets_path` to a tmp file and delenv `COMPUTE_SOURCE`/`ARAIL_CHAT_DEFAULT_MODEL` after — exactly the `isolated_secrets` fixture pattern in `tests/test_qa_provider_dropdown_paranoid.py`. Apply the same to any other SET-path test. | My QA suite proves the correct pattern (51 tests, real file untouched — verified by `rm` then run then file-absent check) |

**No product/security defect found.** QA-1 is a test-isolation bug, not a
runtime bug: the `/api/chat/default` endpoint correctly writes secrets.env in
production (that is its job). The defect is that the *test* doesn't redirect the
path. It is reported here because (a) it silently destroys a developer's real
secrets/tokens on any `pytest` run — drift from the CLAUDE.md secrets-hygiene
contract — and (b) it is the concrete mechanism behind carryover #3's "env-leak
pollution" for the COMPUTE_SOURCE family.

---

## Carryover disposition

### Re-review carryovers (REVIEW.md loop 2)

| # | Carryover | Disposition | Evidence |
|---|---|---|---|
| 1 | B1 has server-contract test but no JS-render assertion; add jsdom (or closest) render + F-RACE seq-guard | **RESOLVED** | Repo has NO portal JS harness (jsdom/jest/vitest absent; only the separate knowledge-canvas React app has a package.json). Per the carryover's fallback clause, added `tests/js/cloud_render_harness.mjs` — extracts the REAL `escapeHtml()` from the template and runs the actual cloud-render + seq-guard against a DOM shim in Node. Asserts B1 cards paint from `gallery.catalog`, F-RACE flip A→B (A resolves last → grid shows B), and XSS escaping in the rendered DOM string. Wrapped by `test_qa_js_render_cloud_dropdown.py` (self-skips w/o node). |
| 2 | R1 nested dicts are required-subset, not byte-exact; tighten if value drift inside deep/compact is a silent-wrong risk | **ACCEPTED AS-IS (with a type-stability guard added)** | `deep`/`compact` values are environment-derived (`_extract_param_hint`, `_is_aerollm_installed`, `_show_airllm`, registry `spec`, `ARAIL_CHAT_DEEP_DEFAULT`, model name). A byte-exact value snapshot would be **non-deterministic across machines** — it would violate the QA determinism rule and flake in CI. Subset-matching is therefore correct for those nested values; R1's structural concern (a future legacy-branch edit adding/removing a top-level or gallery key) is already guarded by the exact top-level + gallery key-set checks. Added REG-2 as a middle ground: asserts the scalar identity fields inside `deep`/`compact` keep stable TYPES (catches a string→dict value drift) without coupling to environment-specific values. |
| 3 | Full-suite env-leak pollution (airgap-default + docs tests pass in isolation, fail in full run) — pre-existing on main; confirm none of THIS sprint's tests contribute | **CONFIRMED PRE-EXISTING; partial sprint contribution found and reported (QA-1)** | The airgap-default failures are present on **both** branch HEAD and origin/main and **pass in isolation** (verified: `pytest <two airgap tests>` → 2 passed). They are not new. **However**, QA-1 shows this sprint's `test_chat_default.py` DOES contribute to env pollution for the COMPUTE_SOURCE family (it sets `os.environ["COMPUTE_SOURCE"]` via the endpoint without cleanup) and clobbers the real secrets file. This does not add a NEW full-suite failure (the pre-existing airgap tests read LAB_MODE, not COMPUTE_SOURCE), but it is real env leakage and is filed as QA-1. Recommend a housekeeping ticket for the pre-existing pollution (env teardown between tests) AND the QA-1 fixture fix. |

### Prior REVIEW carryovers (loop 1, already cleared by builder fix-loop — re-verified)

| Item | Status |
|---|---|
| B1 cloud gallery renders empty | CLEARED — verified by JS-render (cards paint) + 3 builder contract tests |
| B2 Ollama ctx not wired into dispatch | CLEARED — RF-5 proves set-ctx→resolve→build→dispatch puts `options.num_ctx` in the `/api/chat` POST |
| C1 R1 hardening | CLEARED — exact top-level + gallery key sets; REG-2 adds nested type-stability |
| C2 ledger failure-count correction | Acknowledged; matches my independent count (13 branch / 15 main, zero new) |
| C3 ctx-overrides debt for MLX/AeroLLM/AirLLM | Filed; out of scope (Ollama + CPU wired, others deferred) |

---

## Security statement (explicit pass/fail)

| Surface | Verdict | What was actually checked |
|---|---|---|
| **XSS (F7)** | **PASS** | Server stores raw upstream model ids verbatim (correct — it's data). The defense is the frontend `escapeHtml()` (replaces `& < > " '`). Verified two ways: (1) SEC-1 mirrors the exact template escaper and proves `<img onerror=...>` and `"><script>` are neutralized; (2) JS-4 runs the REAL `escapeHtml()` extracted from the template inside the actual cloud-render and asserts the rendered DOM string contains `&lt;img`, never a live `<img` or `onerror="alert`. SEC-2 greps the template so a future edit can't drop the escape on a cloud id/provider interpolation. No unescaped upstream id reaches the DOM. |
| **Airgap bypass (all 10 providers)** | **PASS** | SEC-3 (×10) parametrizes `claude, nvidia, openrouter, huggingface, custom, xai, google, mistral, cohere, together` on `/api/chat/models?provider=` airgapped → `airgapped:true`, empty gallery, `requests.get/post.assert_not_called()` (proves airgap-first ordering, no work-before-check). SEC-4 (×10) does the same on `/api/chat/default` (cloud default refused, nothing persisted). Code-read confirms the cloud branch checks `_is_airgapped()` (app.py:6041) BEFORE token read (6054) and network (6074). |
| **Token never echoed** | **PASS** | SEC-5 plants a real-looking `ANTHROPIC_API_KEY`, hits `/api/chat/models` (cloud), `/api/chat/default`, `/api/chat/models/set-ctx`, asserts the secret string appears in NONE of the response bodies. |
| **set-ctx path traversal** | **PASS** | SEC-6 battery (`../etc/passwd`, `..\\..\\windows`, `/etc/shadow`, `models/../../../secrets.env`, `library/model`, `a/../b`, `....//....//etc`) all rejected. SEC-7 threads the F-VALIDATE needle: `qwen2.5:7b` (colon, valid ollama) accepted; `library/model` (slash) rejected. Gate is `..`/`/`/`\\` reject + must be in (scan ∪ ollama) id set; cloud ids rejected (display-only ctx). |

**Security verdict: PASS on all four FAIL-gate surfaces.** No finding above low
severity.

---

## Performance

N/A. Not a hot path. `_fetch_provider_models` keeps the 200-cap (UX-3 proves it
holds at 250 input → 200 output) and 12s timeout; sync `requests` in an async
route mirrors the existing pattern. VISION's p95 < 800ms picker target is not a
benchmark-gated inner loop. No regression. No BENCHMARK.md required (design said
so).

---

## Regression statement

Full-suite failure set, captured in one harness (`pytest tests/ -p no:cacheprovider`):

- **origin/main (`c45e9a3`/current):** 15 FAILED
- **branch HEAD (`40d8523`):** 13 FAILED
- **branch HEAD + my 51 new QA tests:** 13 FAILED (unchanged)

Set-diff **(branch ∪ QA) minus main = EMPTY** → **zero new failures
attributable to this sprint, including my own tests.** The 2 extra on main
(`test_docs_cross_links`, `test_docs_sprint3_qa`) are order-sensitive docs
cross-link tests that don't fire in the branch run order — pre-existing,
unrelated. All 13 branch failures are in unrelated surfaces (opencode
lifecycle, dashboard layout, docs routes, swarm, system metrics) plus the 2
airgap-default tests that **pass in isolation** (pre-existing env-leak
pollution, confirmed). This matches the architect's loop-2 finding exactly.

My QA suite was verified NOT to pollute: `rm lab/data/secrets.env` → run all 51
QA tests → real file remains absent (the `isolated_secrets` fixture redirects to
tmp and restores env). Contrast: `rm` → run the builder's
`test_chat_default.py::test_chat_default_set_cloud_in_hybrid_ok` → real
`lab/data/secrets.env` is recreated with test data (QA-1).

---

## Coverage delta

No coverage tooling is wired into this repo's test invocation; reporting by
test-count and surface instead:

- Builder sprint tests: 124. QA new: 51. **Total sprint-relevant: 175 passing.**
- New surfaces now covered that weren't: cloud→local restore round-trip,
  403-listing path, 200-cap at over-limit input, per-provider CTA isolation,
  case/whitespace normalization, end-to-end F-DEFAULT-LEAK (not just unit), ctx
  boundary table (256/1M/255/1M+1/0/neg), timeout failure injection, a REAL
  JS-execution render assertion (B1 + F-RACE + XSS), and the secrets-isolation
  contrast that surfaced QA-1.

---

## Notes for the next QA pass

- **QA-1 (secrets clobbering) is the priority.** Apply the `isolated_secrets`
  fixture pattern to every test that POSTs to a secrets-writing endpoint
  (`/api/chat/default`, `/api/providers/save`). Audit older tests too — this
  pattern (endpoint writing the real file) likely predates this sprint in the
  providers-save tests.
- **Pre-existing env-leak pollution** (airgap-default + docs cross-link tests):
  file a standalone housekeeping ticket for an autouse env-teardown fixture that
  snapshots/restores `LAB_MODE`, `COMPUTE_SOURCE`, `ARAIL_CHAT_DEFAULT_MODEL`,
  `ARAIL_MODEL_CTX_OVERRIDES`, `MODEL_NAME` between tests. Out of scope for this
  sprint per the carryover instruction (don't fix unrelated pre-existing
  pollution here).
- **MLX/AeroLLM/AirLLM ctx no-op** (C3 debt): `ARAIL_MODEL_CTX_OVERRIDES` is
  honored only by CPUBackend and OllamaNativeBackend. When MLX/AeroLLM gain ctx
  support, add the equivalent of RF-5 for those runtimes.
- **OpenRouter 200-cap UX**: the cap holds (UX-3) but the unsorted 200 reads
  dense — this is the VISION disconfirming-evidence (b) trigger, not a bug.
- **No jsdom in the repo**: if portal JS testing grows, consider adding jsdom +
  a small harness so render tests don't depend on string-extraction from the
  template. For now the Node harness is the closest available means and runs in
  CI via the pytest wrapper (skips gracefully where node is absent).
