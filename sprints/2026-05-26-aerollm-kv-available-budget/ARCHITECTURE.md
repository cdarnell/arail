# Architecture: aerollm-kv-available-budget

**Date:** 2026-05-26
**Spec:** [SPRINT.md](./SPRINT.md) (no VISION.md — visionary skipped; win condition obvious)
**Branch:** `qukaizen/arail-kv-available-budget`, branched off `qukaizen/arail-chat-md-render` head (commit `22b9688`). Confirmed — the chat-md-render WIP touches `chat.html` + a JS file; no overlap with `src/arail/router/backends.py`. Branching off main would force a rebase chain through unmerged work for zero gain.

## Restatement

`AeroLLMBackend.__init__` currently computes its KV cache budget from `psutil.virtual_memory().total * AEROLLM_KV_BUDGET_PCT` (defaulting `.env` to 0.60). On a 36 GB box already running Ollama, Chrome, and the portal, that yields ~21.6 GB — larger than what is actually free, so the aerollm Rust runtime sizes its KV pool past real headroom and the box swaps or OOMs. The fix: cap the budget by what is *available* right now, with a floor so a transiently-busy box never starves the model and an explicit safety headroom so we don't claim the last byte. Honor `AEROLLM_KV_BUDGET_PCT` as a *ceiling expressed against total*, not an absolute claim. Log the resolved budget once, via `activity_log`, so the operator can see why aerollm got the number it got.

## Assumptions

1. **Platform:** Apple Silicon (arm64) is the primary target (the only one currently shipping AeroLLM); Linux/CUDA is in the failure path — AeroLLMBackend still constructs there but the runtime is replaced. We assume `psutil.virtual_memory()` returns sane `.total` and `.available` on both Darwin arm64 and Linux. On Darwin, `.available` accounts for inactive + cached memory the kernel can reclaim — this is *exactly* the number we want.
2. **psutil availability:** `psutil` is a hard dependency in `pyproject.toml` (already imported unconditionally in backends.py path today). We still wrap the import + call in try/except because a corrupted venv is a real failure mode users have hit.
3. **aerollm Runtime contract for `kv_memory_budget`:**
   - Unset → runtime auto-detects ~80% of system RAM (too aggressive, the reason this code exists).
   - Set to a positive int → runtime sizes KV pool at exactly that many bytes; the runtime does **not** validate against current free RAM.
   - Set too small → runtime reduces max concurrent sequences / context length; in extreme cases (< model's minimum working set) it raises at `start()`. We define `MIN_FLOOR = 2 GiB` to stay above any 7B-class minimum.
   - Set too large → no error at construction; the OS kills us on first sustained use. This is the bug we are fixing.
4. **Singleton semantics:** Per `_shared` dict at backends.py:1308, there is exactly one `AeroLLMBackend` instance per `(models_dir, model)` per process. The budget is decided at first `__init__` and baked into the Runtime; subsequent constructors short-circuit at the `_initialized` guard. **Consequence:** budget resolution + the log emission must run *only* inside the first-init branch (after the `if getattr(self, "_initialized", False): return` line), not on every constructor call.
5. **Env override semantics:** `AEROLLM_KV_BUDGET_PCT` continues to mean "fraction of *total* RAM the operator is willing to dedicate"; we treat it as a ceiling and then clamp by available-RAM math. Empty / unset / non-numeric / out-of-range (≤0 or ≥1) values fall back to the new default `KV_PCT_DEFAULT = 0.60` (matching today's `.env`), so behavior on a healthy box is unchanged.
6. **Race-free first init:** AeroLLMBackend is constructed once on the FastAPI event-loop thread or on the executor worker. Concurrent first-construction in the same process is not currently possible (no locking around `_shared`), so we do not add locking — that is an orthogonal bug.

## Data flow

```
AeroLLMBackend.__init__
  └─ if _initialized → return  (singleton reuse, no budget work)
  └─ import aerollm_api
  └─ resolve model_path, draft_path
  └─ rt_kwargs = {}
  └─ if draft_path:  rt_kwargs["draft_model"]  = …
  └─ if AEROLLM_RING_DEPTH: rt_kwargs["ring_depth"] = …
  └─ (NEW) reasoning = _resolve_kv_budget()        ← pure function, mockable
        ├─ read AEROLLM_KV_BUDGET_PCT  (env)
        ├─ read psutil.virtual_memory().total / .available
        ├─ apply formula:
        │     ceil_total      = total      * pct
        │     ceil_available  = available  * AVAILABLE_FRACTION  - SAFETY_HEADROOM
        │     budget          = max(MIN_FLOOR, min(ceil_total, ceil_available))
        ├─ return {"budget_bytes": int|None, "reason": str, "fields": {...}}
  └─ if reasoning["budget_bytes"] is not None:
        rt_kwargs["kv_memory_budget"] = reasoning["budget_bytes"]
  └─ (NEW) _emit_budget_activity(reasoning)        ← lazy-imports activity_log
  └─ build executor, init runtime on worker
  └─ self._initialized = True
```

Interaction with other AEROLLM_* env vars: none. `AEROLLM_RING_DEPTH` and `AEROLLM_DRAFT_MODEL` are independent kwargs; they do not consume KV budget at construction time (draft model RAM cost is separate weight residency, not KV pool). Keep this sprint scoped to `kv_memory_budget`.

## Interface contracts

### New private module-level function

```python
# src/arail/router/backends.py (module scope, near AeroLLMBackend)

# 2 GiB. Below this, a 7B-class model's KV pool can't hold a useful
# context window (a single 4K-token Qwen sequence at 4-bit ~= 0.5 GiB;
# we want headroom for 2-4 concurrent sequences plus prefill scratch).
# Set as a floor so a transiently-busy box (e.g., during a Chrome spike)
# still gets a working model after the spike passes — better to risk
# light swap than to ship a runtime that refuses to start.
_AEROLLM_KV_MIN_FLOOR_BYTES: int = 2 * 1024 * 1024 * 1024

# 1.5 GiB. Reserved on top of the .available reading. Rationale: on
# Darwin .available already discounts inactive/cached, but it does NOT
# reserve room for (a) the portal's own growth during the same request
# that triggered backend construction, (b) the aerollm Runtime's own
# non-KV resident set (~150 MB on top of the weight file), or (c) the
# spec-decode draft when AEROLLM_DRAFT_MODEL is set. 1.5 GiB covers
# all three with margin on a 16 GB Mac without leaving a 36 GB box
# significantly under-utilized.
_AEROLLM_KV_SAFETY_HEADROOM_BYTES: int = int(1.5 * 1024 * 1024 * 1024)

# Apply 85% of .available rather than 100% — even after subtracting
# SAFETY_HEADROOM we want a buffer for short-lived allocations
# (browser tab open, file upload) that the operator should not have
# to think about. The two knobs compose: AVAILABLE_FRACTION absorbs
# *transient* spikes, SAFETY_HEADROOM absorbs *known* costs.
_AEROLLM_KV_AVAILABLE_FRACTION: float = 0.85

_AEROLLM_KV_PCT_DEFAULT: float = 0.60


def _resolve_kv_budget() -> dict[str, Any]:
    """Compute the kv_memory_budget bytes to pass to aerollm Runtime.

    Returns
    -------
    dict with keys:
        budget_bytes : int | None
            Bytes to pass as kv_memory_budget, or None to let aerollm
            auto-detect (psutil missing / total reads as 0).
        reason : str
            One-line human-readable summary for activity_log.
        fields : dict[str, Any]
            Structured detail (pct_used, total_gib, available_gib,
            ceil_total_gib, ceil_available_gib, floor_gib, headroom_gib,
            source: "env"|"default"|"floor"|"unavailable").
    """
```

**Preconditions:** none — pure function over `os.environ` + `psutil`. Always returns; never raises.

**Postconditions:**
- `budget_bytes is None` ⇒ caller MUST NOT set `kv_memory_budget` (aerollm auto-detects).
- `budget_bytes >= _AEROLLM_KV_MIN_FLOOR_BYTES` whenever non-None.
- `fields["source"] == "unavailable"` iff psutil failed or returned `total == 0`.
- `fields["source"] == "floor"` iff the min/max clamp forced the floor (operator should see this; it usually means the box is dangerously full).

### New private instance method

```python
def _emit_budget_activity(self, reasoning: dict[str, Any]) -> None:
    """Emit one info-level activity_log entry describing the resolved
    KV budget. Best-effort — import errors are swallowed so a
    headless test harness without the activity bus still works.
    """
```

Behavior matrix:

| `AEROLLM_KV_BUDGET_PCT` | psutil | Outcome |
|---|---|---|
| unset / "" | works | use default 0.60, clamp by available |
| "0.4" | works | use 0.4, clamp by available |
| "0" / "1.5" / "garbage" | works | warn-log invalid value, fall back to default 0.60 |
| any | ImportError | budget_bytes=None, log warning, aerollm auto-detects |
| any | call raises | budget_bytes=None, log warning, aerollm auto-detects |
| any | total=0 | budget_bytes=None (defensive; never seen in practice) |
| clamped result < floor | works | return floor, source="floor", log at warn level |

## Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| psutil ImportError | try/except around `import psutil` inside resolver | `budget_bytes=None`, `source="unavailable"`, activity_log warn; aerollm auto-detects (today's silent path becomes loud) |
| `psutil.virtual_memory()` raises | try/except around the call | same as above |
| `.available` < `MIN_FLOOR + HEADROOM` (box is critically full at construction time) | comparison after formula | return `MIN_FLOOR`, `source="floor"`, activity_log **warn** with the reason — operator gets visible signal that "your box is too full for safe operation; we're using the floor and you may swap" |
| `.total` < `.available` (psutil bug / container quirk) | `min(ceil_total, ceil_available)` naturally picks the smaller; floor still applies | benign |
| Env override `AEROLLM_KV_BUDGET_PCT="0"` | range check `0.0 < pct < 1.0` fails | fall back to default 0.60; log info noting the invalid value (don't crash — operators set this in `.env` and a typo shouldn't brick the lab) |
| Env override `> 1.0` | same range check | same fallback |
| Env override garbage (`"abc"`) | `float()` ValueError caught | same fallback |
| Concurrent first-init across threads | Out of scope — `_shared` dict is not lock-protected today; this sprint does not change that. Note in tech debt. | Existing behavior preserved (last-writer-wins on `_shared[key]`). |
| activity_log import fails inside `_emit_budget_activity` | try/except | swallow; runtime still constructs. The budget was applied; only the operator-visible log is missing. |
| Singleton re-use logs spam | gate placement: budget resolution + emit run only AFTER the `_initialized` early-return | exactly one emission per process per model |

## Test strategy

**Allocation note (per `arail` CLAUDE.md gating):** standard arail allocation is 30/30/20/10/10 (setup/Buddy/security/happy/regression). This sprint is a runtime allocation fix; the relevant slices are happy-path + regression + edge (OOM, psutil failure, env override). Treat this sprint as 70% unit + 30% regression; setup/Buddy/security tests are not impacted.

### Unit tests — new file `tests/router/test_aerollm_kv_budget.py`

All tests target `_resolve_kv_budget()` directly (pure function — no AeroLLMBackend instantiation, no aerollm_api import, no Runtime). Use `monkeypatch` for env and `unittest.mock.patch` for `psutil.virtual_memory`.

1. `test_default_pct_healthy_box` — total=36 GiB, available=20 GiB, env unset → expects `min(36*0.60, 20*0.85 - 1.5) = min(21.6, 15.5) = 15.5 GiB`; `source="default"`.
2. `test_env_pct_lower_than_available_ceiling` — total=36, available=30, env=0.30 → `min(10.8, 24)= 10.8`; `source="env"`.
3. `test_env_pct_higher_than_available_ceiling` — total=36, available=8, env=0.80 → `min(28.8, 5.3)=5.3`; `source="env"` (env was honored as ceiling, available won).
4. `test_floor_applied_when_box_starved` — total=36, available=3 → `min(21.6, 1.05) = 1.05` → bumped to `2 GiB`; `source="floor"`.
5. `test_env_zero_falls_back_to_default` — env="0", same numbers as #1 → identical to #1, fields note "invalid env value".
6. `test_env_garbage_falls_back_to_default` — env="abc".
7. `test_env_above_one_falls_back_to_default` — env="1.5".
8. `test_psutil_import_error` — patch `psutil` import to raise → `budget_bytes is None`, `source="unavailable"`.
9. `test_psutil_call_raises` — `psutil.virtual_memory` raises RuntimeError → `budget_bytes is None`.
10. `test_total_zero_returns_none` — defensive.
11. `test_returned_bytes_are_int` — type check (Rust runtime expects int, float would TypeError at PyO3 boundary).

### Integration test — `tests/router/test_aerollm_backend_budget_emit.py`

12. `test_budget_emit_called_once` — patch `_resolve_kv_budget` to return a known dict; patch `activity_log.emit`; patch aerollm_api so construction completes without a real Runtime (use `sys.modules["aerollm_api"] = fake`). Construct AeroLLMBackend twice with same model. Assert `activity_log.emit` called exactly once with category `"system"`, level `"info"` (or `"warn"` for `source="floor"`/`"unavailable"`), and message containing the GiB number + source.
13. `test_kv_memory_budget_kwarg_present` — same fakes; assert `rt_kwargs["kv_memory_budget"]` was the int we returned, and absent when resolver returns None.

### Regression test

14. `test_default_env_pct_060_preserves_legacy_value_on_idle_box` — ensure that on a *fresh* box with `available ≈ total`, we still produce ≈ `0.60 * total` (not a regression for the 16 GB Mac happy path). Specifically: total=16, available=14 → `min(9.6, 10.4) = 9.6`. Matches today's behavior to within HEADROOM/AVAILABLE_FRACTION slack.

### QA edge cases (for `/qa` to cover separately)

- Real run on the user's 36 GB box mid-Ollama-load: confirm the activity log shows a sub-20 GiB budget and the box does not swap during a 200-token chat.
- `pip uninstall psutil` in a scratch venv → confirm portal still starts, AeroLLMBackend logs the warning, aerollm runs at its own 80% auto-detect.
- `AEROLLM_KV_BUDGET_PCT=0` in `.env` → portal starts; activity log shows fallback notice.
- Smoke: with default `.env` on Apple Silicon, deep-mode chat still completes ≥1 turn.

## Tech debt assessment

**Added:**
- Two new tunable constants in `backends.py` module scope. They are *not* env-overridable by design (operators tune via `AEROLLM_KV_BUDGET_PCT`, not headroom). If a user needs to tune them, that's a follow-up.
- Lazy import of `activity_log` inside the emit helper — small repeated cost, but matches the pattern in `pkb_index.py` and `wiki.py`. Avoids the circular-import risk that a top-level import in `router.backends` could create later (activity → app → router chains).

**Repaid:**
- The current `total * pct` formula is a known footgun (it caused this sprint). Replacing it with an `available`-aware computation removes a class of OOM bug.
- Today's `pass` on psutil failure is silent; the new path emits a warning, repaying observability debt.

**Net:** Slightly negative (good). One pure function added, one silent failure made loud, one OOM class removed.

**Flagged for follow-up (do NOT touch in this sprint):**
- `_shared` dict has no lock around first-construction. If future code spawns AeroLLMBackend from two threads simultaneously, two Runtimes briefly exist. File as `aerollm-singleton-race` follow-up.
- `AEROLLM_MAX_LENGTH` (`.env` line 182) is parsed nowhere visible in backends.py — same "knob set but ignored?" smell. Verify in a separate audit sprint.
- `_init_runtime` calls `rt.start()` synchronously on the worker thread; a failed start leaves the singleton in an inconsistent state (`_runtime is None`, `_initialized = False` because the line raises before the flag set). Acceptable today; file as `aerollm-init-rollback`.

## Risks the reviewer will look for

The review-mode architect should verify each of these explicitly in REVIEW.md:

1. **Singleton gating** — the new `_resolve_kv_budget()` call and `_emit_budget_activity()` call live *after* the `if getattr(self, "_initialized", False): return` guard, so a re-used AeroLLMBackend does NOT re-resolve and does NOT re-emit. Grep for the call sites; confirm exactly one per `__init__`.
2. **Floor honored above env** — even when `AEROLLM_KV_BUDGET_PCT=0.99` and `available` is tiny, the returned value is `>= _AEROLLM_KV_MIN_FLOOR_BYTES`. Specifically the env override is a *ceiling*, never a *floor*.
3. **`.available` not `.total`** — the available-side ceiling reads `psutil.virtual_memory().available`, not `.total` (the bug being fixed) and not `psutil.swap_memory()` (a different number entirely).
4. **No circular import** — `activity_log` is imported lazily inside `_emit_budget_activity`, not at module top. Confirm by attempting `python -c "import arail.router.backends"` in isolation.
5. **Returned int, not float** — `rt_kwargs["kv_memory_budget"]` is `int(...)`. PyO3 will TypeError on float.
6. **Default path unchanged for the happy 16 GB case** — the regression test #14 passes; no operator on a healthy Mac sees a meaningful budget shift.
7. **Activity log emission level** — `"warn"` when `source in {"floor", "unavailable"}`, `"info"` otherwise. The floor case is the loud one — operators should see it.
8. **No new env var was invented** — `AEROLLM_KV_BUDGET_PCT` semantics are preserved (just clamped by available); we did NOT add `AEROLLM_KV_HEADROOM`, `AEROLLM_KV_MIN_FLOOR`, etc. Keep the surface narrow.
9. **`.env` line 184 area not modified** — this sprint does not change the shipped `0.60` default; behavior change is in the math, not the config.
10. **No new top-level imports added** to `backends.py` (psutil stays inside the try/except inside the resolver; `activity_log` lazy inside emit).

## Recommended implementation order

1. Add the four module-level constants + `_resolve_kv_budget()` pure function above the `AeroLLMBackend` class definition.
2. Write `tests/router/test_aerollm_kv_budget.py` (unit tests 1–11). Run; they should pass against the pure function alone.
3. Add `_emit_budget_activity()` method on `AeroLLMBackend`.
4. Replace the existing `kv_budget_pct_raw` block (backends.py:~1396-1416) with: call resolver → set kwarg conditionally → call emit. Place AFTER `_initialized` guard, BEFORE the executor build.
5. Write integration tests 12–13.
6. Write regression test 14.
7. Smoke: `./arailctl start`, open chat, send one Box B prompt, verify the activity feed shows the budget line and the chosen GiB is sub-20 on the dev box.
8. Update BUILD_LOG.md with the resolved budget seen on the dev box at smoke time (concrete number is good evidence for the reviewer).
