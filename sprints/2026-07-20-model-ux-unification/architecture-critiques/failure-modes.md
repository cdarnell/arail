# Pre-build critique — lens: FAILURE MODES

**Target:** `sprints/2026-07-20-model-ux-unification/ARCHITECTURE.md`
**Reviewer stance:** paranoid, pre-code. Every finding below is a failure mode the
architecture does not currently handle, grounded in the actual code it plans to touch.

**Note on ground truth:** ARCHITECTURE.md line 5 cites `PROMPT.md` as "Ground truth
(§2 gaps, §3 backend semantics, §5 phase plan)" at a relative path that does not resolve,
and no `PROMPT.md` exists in the sprint directory (only VISION.md, ARCHITECTURE.md, and
`vision-drafts/`). I reviewed against VISION.md + the source instead. The §2/§3/§5
references in the architecture cannot be verified against the cited file. Flagging so it
is fixed or the citation corrected before build.

The architecture is genuinely strong on the *display* honesty (fit chip, telemetry, badge
copy, dead-field deletion). Its blind spot is the **load/unload lifecycle** — the moving,
stateful, concurrent, cross-process part. That is precisely where the failure lens bites,
and where the sprint's own thesis ("every button that claims to do X must do X") is most
exposed. Findings are ordered by severity.

---

## BLOCK-class findings (a lying button survives, or an OOM/500 ships)

### F1 — The Cancel button is a lie of exactly the class this sprint exists to kill, and the architecture never touches it
`api_chat_model_load_cancel` (`app.py:7258-7266`) sets `state="canceled"` and returns —
but the actual load runs in `asyncio.to_thread(_get_runtime_backend, …)` inside
`_prepare_chat_model_load` (`app.py:7209-7215`), which **cannot be cancelled from the
outside**. The thread keeps running; the model still loads fully into memory. So "Cancel"
reports `canceled` while the machine keeps consuming RAM/VRAM and eventually holds the
model the operator thought they cancelled.

This is win-condition #3 verbatim ("No button reports success without effect") and the
same family as the aeroLLM eject lie the sprint was chartered to remove. ARCHITECTURE.md
C6 (line 112-116) lists `canceled` as a valid state and even trims the doc to include it,
but **never observes that cancel does not cancel.** There is no failure-mode row and no
test. If the aeroLLM eject button must be removed for lying, the Cancel button must be
either made real (hard — see F2) or removed/relabeled ("stops watching; the load
continues in the background") by the same standard. As written, Phase 0 ships a fifth
lying button while congratulating itself for removing four.

### F2 — The `ARAIL_LOAD_MAX_SEC` timeout guard (F-LOAD-HANG) fights an un-cancellable thread; it converts a hang into a *worse* lie
C6 (line 115) and the F-LOAD-HANG row (line 138) promise: "a hard wall-clock guard
(`ARAIL_LOAD_MAX_SEC`, default 180) transitions to `error` … rather than hanging." But
`asyncio.wait_for` around an `asyncio.to_thread` **abandons the awaiter, not the thread.**
The underlying `_get_runtime_backend`/`_get_optional_chat_backend` keeps loading. Sequence:

1. Load exceeds budget → state flips to `error`, chat input re-enables.
2. The orphaned thread finishes 30s later → the model is now fully resident.
3. UI says "Load failed"; operator clicks Load again → **second load → double residency →
   OOM** on the 32 GB Mac this sprint targets.

T-LOAD-BOUND (line 161) asserts only that the *state* reaches `error` within the budget —
it does not assert the underlying load was stopped or that memory was reconciled, so it
would pass while the OOM path stays open. The architecture treats the timeout as clean; on
this runtime it is not. It needs either a real cancellation story (Ollama load can be
cancelled via the daemon API / killing the request; in-process aeroLLM construction
cannot) or an explicit "load continues in background, state reconciles when it lands"
contract — not a fire-and-forget `error`.

### F3 — Concurrent Ollama load + aeroLLM preload race toward the same unified-memory ceiling with no mutex; chat-initiated loads bypass the scheduler that admin loads respect
Admin model loads take `scheduler.inference_slot("admin-model-load")` to serialize GPU
work (`app.py:5586, 5678`). But `_prepare_chat_model_load` invoked from
`POST /api/chat/model-load` (`app.py:7245-7255`) takes **no slot**. Meanwhile the
`model_warmth.py` preload loop re-warms aeroLLM whenever `metal_memory_pressure() < 0.60`
(A3, line 23). So on the exact target machine, an operator clicking "Load `gemma-4-26b-a4b`"
(~13.4 GB) can collide with a concurrent aeroLLM 7B warm-up — two heavy warm-ups racing to
the ceiling with zero coordination. Result on 32 GB unified memory: OOM-kill or swap
thrash. A3 treats the preload loop only as an *obstacle to freeing*; it never treats it as
a *competitor for a concurrent load*. Nothing in the design serializes chat loads against
each other or against the preload loop. No failure-mode row, no test. At minimum the chat
load path should take the same `inference_slot`, and the interaction with the preload loop
needs an explicit rule.

### F4 — Ollama eject that *fails* still returns `ok:true`; C5 leaves the ollama path's lie intact
`api_chat_eject` returns `{"ok": True, …}` unconditionally at `app.py:6911`, even when
`ollama stop` returned a non-zero code (6890-6891 only appends a *note*) or threw
(6892-6895 only appends a note). So an Ollama Unload that silently failed — daemon down,
wrong model name, 15s timeout — **reports success while the model stays resident.** C5
(line 104-107) says the ollama branch "on rc==0 returns `{ok:true…}`. **Unchanged.**" and
only fixes the aerollm/airllm false-success. But "unchanged" preserves the ollama
false-success on the failure path. This is win-condition #3 again ("No button reports
success without effect"), left standing for the most common runtime. T-EJECT-OLLAMA (line
158) tests only the happy path (was resident → gone), so the lie is untested. Fix: `ok`
must reflect `returncode == 0` and the absence of an exception.

### F5 — aeroLLM singleton already constructed → a "load" of a *different* aeroLLM model returns `ready` instantly for the wrong model, or doubles memory
`_get_optional_chat_backend` (`app.py:7269-7281`) returns the cached instance if present
**without checking it is the requested model.** So requesting a load of aeroLLM model B
while model A is resident returns `ready` immediately for what is still model A — the
derived ETA countdown (C6) would tick down over a no-op, and the operator believes B is
loaded. Conversely, if `AeroLLMBackend._shared` is keyed per-model (A3 line 23 says
`_shared[key]`), loading B constructs a **second resident instance** — doubling unified
memory with no eject path (aeroLLM has no hot-free this sprint) → OOM. The architecture's
Load-path data flow (lines 74-78) bounds only `ollama`/`mlx-openai`; the optional/aeroLLM
branch's "already constructed" and "switch model" cases are unaddressed. Given the target
persona explicitly weighs "load the 26B" against a resident deep model, model-switching is
a first-class path, not an edge case.

### F6 — Concurrent load+unload race on the *unlocked* `_OPTIONAL_CHAT_BACKEND_CACHE`
`_CHAT_MODEL_LOAD_STATE` is guarded by `_CHAT_MODEL_LOAD_LOCK` (`app.py:7011, 7180`), but
`_OPTIONAL_CHAT_BACKEND_CACHE` is a bare dict mutated **without any lock** from three
directions: load writes `[name] = backend` (7280), eject does check-then-`del` (6875-6876),
and the catch-all eject iterates-and-deletes (6907-6908). Concurrent hazards:
- Two ejects race the TOCTOU at 6875-6876 → second `del` raises `KeyError` → **500 to the
  operator** (arail runs on someone else's machine; an unhandled 500 is a trust event).
- Eject fires mid-construction of the load → the load's write-after-delete leaves a
  resident backend the cache no longer references → **even the "restart to free" story
  breaks**, because the instance is now unreachable but still pinned.

C5 edits this endpoint but adds no locking and does not mention the race. The architecture
should put `_OPTIONAL_CHAT_BACKEND_CACHE` access under a lock (or reuse the load lock) as
part of the eject-honesty change it is already making here.

---

## ASK-class findings (cold-start / restart / corrupt-model honesty gaps)

### F7 — Initial and post-restart load state is itself a false "ready"
`_CHAT_MODEL_LOAD_STATE` initializes to
`{"state": "ready", "model": None, "message": "Model ready"}` (`app.py:7012-7022`). On
**cold start and after every portal restart**, `GET /api/chat/model-load` reports "Model
ready" while nothing is loaded (or the previously-loaded model is now unknown). C6's state
enumeration `{loading, ready, error, canceled}` has **no `idle`/`none` state**, so there is
no honest way to say "nothing loaded yet." T-COLD (line 155) makes the *memory snapshot*
honest on cold start but says nothing about the load state. "Model ready" over an empty
machine is the same false-green family the sprint is removing — just in the load widget
instead of the fit chip. Recommend an explicit `idle` initial state with `model: None`.

### F8 — Portal restart mid-load leaves the portal and the Ollama daemon disagreeing, with nothing to reconcile
Load state is in-memory only. Ollama is a **separate process**; a restart of the portal
does not stop an in-flight or completed Ollama load. After restart the portal resets to
`ready/model=None` (F7) while Ollama may be mid-load or already resident. Nothing
reconciles the load state against `ollama ps` on startup, so the rail's warm-dot can show
`cold` for a model that is actually warm (or the reverse). T-RESTART (line 160) covers
only aeroLLM RSS returning toward baseline — it does **not** cover restart-mid-Ollama-load.
For a screen whose entire charter is "the screen never contradicts the terminal," a
warm/cold dot that disagrees with `ollama ps` after a restart is exactly a contradiction.
Recommend deriving the warm-dot from a live `ollama ps` probe rather than trusting
in-memory load state.

### F9 — near-OOM: fit is computed once at render, never used as a load precondition and never re-checked at click time
The sprint makes the fit chip honest, but fit is advisory only — nothing stops the operator
clicking Load on a "Requires streaming" 26B, and nothing re-reads free memory at the moment
of load. `_local_memory_snapshot()` is read once when the list renders (`app.py:7772`); by
the time the operator clicks Load, the aeroLLM preload loop (gated on
`metal_memory_pressure() < 0.60`) may have warmed a 7B, so the "Marginal" chip the operator
trusted is stale and the real free figure is now below the model's need. A5/T-NOFLICK (line
25, 162) only cover *idle-machine* jitter across refreshes — not the **render-time →
load-time delta** on a machine that is actively warming models. At minimum, re-snapshot
free memory immediately before a load and surface a confirm ("14 GB needed, 6 GB free — load
anyway?") for Marginal/Requires-streaming, rather than letting the honest chip go stale at
the one moment it matters.

### F10 — Ollama daemon down is a silently-confusing state (and surfaces a raw traceback)
If the Ollama daemon is down, the gallery/tags scan returns nothing → the models the
operator pulled **vanish** from the rail (the `rail-empty` "none" path) while real free
memory is shown beside the emptiness. Nothing distinguishes "you have no models" from "the
daemon that serves your models is down." And a load attempt fails via C6's
`message=f"Load failed: {type(exc).__name__}: {exc}"` (`app.py:7230`) — a raw exception
string shown to a non-expert, which the arail paranoid checklist explicitly calls out
("tracebacks shown to non-experts," "jargon in onboarding"). No failure-mode row handles
daemon-down detection or a friendly banner. This is squarely in arail's blast radius
(someone else's machine, less patience than the operator).

### F11 — A corrupted/partial on-disk model looks loadable and honest until the moment it fails
An interrupted `ollama pull` leaves a model that still appears in the list with a plausible
manifest `size_gb`, therefore an honest-looking fit chip and a Load button. There is no
integrity/completeness check; the lie is only discovered at load time as a raw exception
(F10). Worse for C6's ETA: `on_disk_bytes` is planned as `size_gb * 1024³` (line 114),
i.e. the **manifest-declared** size, not the actual bytes on disk — so a partial model
gets an ETA computed off a size the file does not have, and the countdown will overrun with
no correction. No corrupt/partial-model test in the strategy. At least degrade the fit chip
to `Unknown` when declared size and on-disk size disagree, and derive `on_disk_bytes` from
the real file, not the manifest.

### F12 — The memory-snapshot fallback can lie in the *good* direction, re-introducing the fake-green chip
On the darwin non-psutil fallback (`app.py:8159-8166`), `free_gb = total_gb` — it reports
**all** memory as free. psutil is a hard dep (A2), so this "shouldn't" run, but if the
import ever fails, `_fit_verdict_label` computes against total instead of available and
flips "Requires streaming" back to "Good" — the exact fake-good lie this sprint removes,
reappearing through the back door. C1's bad-input contract (line 88) handles only
`free_gb == 0 → Unknown`; it does not handle `free_gb == total_gb` (the over-report). Add a
defensive rule: if the honest `available` probe failed, emit `Unknown`, never a number that
equals total.

---

## Coverage check against the requested scenarios

| Scenario (from the brief) | Handled by ARCHITECTURE.md? | Finding |
|---|---|---|
| Cold start | Partial — snapshot yes (T-COLD), load state no | F7 |
| Portal restart mid-load | No — only aeroLLM RSS (T-RESTART) | F8 |
| Near-OOM / memory-pressure ceiling | No — fit is display-only, read once | F3, F9 |
| Ollama daemon down | No | F4, F10 |
| aeroLLM singleton already constructed on fresh load | No | F5 |
| Concurrent load+unload race | No — cache is unlocked | F3, F6 |
| Model on disk but corrupted/partial | No | F11 |

Every one of the seven scenarios named in the brief maps to at least one unhandled failure
mode. None of them is filler; each is grounded in a specific line the architecture plans to
edit or rely on.

---

## Recommendation

The display-honesty half of Phase 0 (F-BLANK, F-FAKEFIT, F-HEADER, F-OVERSELL,
F-DEADFIELD) is sound and can proceed. The **load/unload lifecycle half is not yet
safe to build**: F1 (Cancel lies), F4 (Ollama eject false-success), and F6 (unlocked cache
→ 500/orphan) are the same lying-button / trust-break class the sprint was chartered to
eliminate, and F2/F3/F5 open real OOM paths on the exact 32 GB target machine. Before the
load path is coded, the architecture needs: an honest Cancel contract, a real (not
fire-and-forget) timeout story, a lock on `_OPTIONAL_CHAT_BACKEND_CACHE`, an `ok` that
tracks the actual `ollama stop` result, a model-identity check in
`_get_optional_chat_backend`, serialization of chat loads against the preload loop, and an
`idle` load state. These are cheap relative to shipping a sixth "the button lied" bug —
which is precisely the attempt-#7 pattern the leash exists to prevent.
</content>
</invoke>
