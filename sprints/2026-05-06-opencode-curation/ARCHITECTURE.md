# Architecture: opencode default model + lab curation (Sprint 2)

**Date:** 2026-05-06
**Spec:** [SPRINT.md](./SPRINT.md) + approved plan at `~/.claude/plans/also-want-to-consider-synthetic-wreath.md` (§"Sprint 2 — opencode default model + lab curation [PLANNED]")
**Product:** arail (max-tier surface)
**Builds on:** Sprint 1 ARCHITECTURE.md @ `50ce5ad` (direct-iframe Path A; subprocess lifecycle owned by `services/opencode.py`).

---

## Restatement

Sprint 1 made opencode runnable inside the Workbench tab as a fifth iframe-card next to Jupyter/Marimo/Open-Notebook, and wired it to whatever Compute Source the Chat tab is on. It left five gaps the user calls out: (1) cold-start has no lab context — opencode doesn't know about CLAUDE.md, agents, sprints, the KB; (2) `/api/opencode/start` will spawn the binary even with no model loaded, so the first prompt fails opaquely; (3) AirLLM has no HTTP server, so when My-Machine is on AirLLM the env-var-only wiring points at a non-existent Ollama default and opencode is effectively unusable; (4) there is no curated coder starter model — users must go shop for one; (5) RAM doubles if the user picks a different model in opencode's TUI alongside chat. Sprint 2 closes all five with a single coherent move: build a lab-side OpenAI-compatible shim at `/api/openai/v1/*` that opencode points at, generate a per-start `opencode.json` in a *lab-scoped* config directory that locks opencode to the lab's currently-active model and ships six lab-aware slash commands plus a CLAUDE.md-aware system prompt, gate `start` on actual LLM-readiness with an explicit 4-state UI on the Workbench card, and add a `--with-coder` Qwen2.5-Coder-3B starter to `setup.sh` so first-run max users have something curated to point opencode at. The Sprint 1 provider-switch fire-and-forget restart hook is extended to regenerate the config first.

## Assumptions

A1. **`OPENCODE_CONFIG_DIR` is the right env var.** Verified at design time by string-grepping the v1.14.31 binary: `OPENCODE_CONFIG_DIR`, `OPENCODE_CONFIG`, `OPENCODE_CONFIG_CONTENT`, `OPENCODE_DISABLE_PROJECT_CONFIG`, `OPENCODE_DISABLE_AUTOUPDATE`, `OPENCODE_DISABLE_MODELS_FETCH` are all present. The plan/SPRINT.md says `OPENCODE_CONFIG_HOME` — that name does **not** appear in the binary. **Decision: use `OPENCODE_CONFIG_DIR`.** SPRINT.md decisions log entry should be amended at builder-kickoff. The semantic remains "lab-scoped config directory under `LAB_ROOT`."

A2. **`LAB_ROOT` is the canonical lab home.** Defined at `src/arail/config.py:69` as `_resolve("LAB_ROOT", "lab")`. Default: relative `lab/` (resolved against the portal's CWD, which is the repo root). The opencode config dir is `LAB_ROOT / ".opencode"` (i.e. `lab/.opencode/` by default). The directory is git-ignored under the existing `lab/` rules.

A3. **AirLLM has no HTTP server today.** The `arail.optional.airllm` and `arail.optional.aerollm` backends are in-process Python objects accessed via `_OPTIONAL_CHAT_BACKEND_CACHE` (`app.py:4829`) and `_run_chat_completion[_stream]` (`app.py:4565` / `:4413`). The OpenAI-compat shim at `/api/openai/v1/*` is the bridge — it routes through the same `_run_chat_completion[_stream]` helpers Chat already uses, so AirLLM/AeroLLM/MLX/Ollama/cloud are all addressable through one OpenAI-shaped HTTP endpoint.

A4. **The portal binds `127.0.0.1` on the same port opencode talks back to.** `BIND_ADDR` defaults to `127.0.0.1`; `PORTAL_PORT` defaults to 8080. opencode runs as a child of the portal process — same host, same loopback. The shim URL opencode reads from `opencode.json` is therefore `http://127.0.0.1:<PORTAL_PORT>/api/openai/v1`.

A5. **`_run_chat_completion` and `_run_chat_completion_stream` already exist** at `app.py:4565` and `:4413` — they're the shared core of `/api/chat` and `/api/chat/stream`. The plan said "extract the inner handler of `/api/chat/completions`" but **no `/api/chat/completions` route exists** today. The shim wraps the existing `_run_chat_completion[_stream]` helpers; it does not require a separate extraction. (See §Tech Debt for what this means for the "shared helper" framing in the plan.)

A6. **opencode reads `opencode.json` at process start, not per-request.** Same posture as Sprint 1's env-var assumption (A3 in the prior architecture). Provider/model swaps therefore require a process restart, which the Sprint 1 fire-and-forget hook already does.

A7. **opencode supports `enabled_providers`.** Plan-level decision (SPRINT.md decisions log) — locking the picker to one provider is the RAM-pressure mitigation. **Builder MUST verify at kickoff** by reading [opencode.ai/docs/config](https://opencode.ai/docs) for the v1.14.x schema. If the field is renamed or removed, fall back to: omit other providers from the `provider` map AND set `OPENCODE_DISABLE_MODELS_FETCH=true` to prevent runtime model discovery. Either way, the user gets a single-model picker.

A8. **Loaded model identity is what `_CHAT_MODEL_LOAD_STATE.model` reports.** Format: an opaque string that varies by runtime (`"meta-llama/Llama-3.1-70B"` for AirLLM, the directory name from `_scan_local_models()` for MLX, etc.). The shim's `/api/openai/v1/models` returns this as the `id`. Opencode's `model: "lab-local/<id>"` reference in `opencode.json` matches.

A9. **The `/api/openai/v1/*` shim is **not** an authenticated surface.** It binds the same `127.0.0.1` perimeter as the rest of the portal, mirroring the Sprint 1 trust-boundary posture. No `OPENCODE_API_KEY` validation; the shim accepts any `Authorization: Bearer …` and ignores it (or accepts none). In airgapped mode, the shim still works — it never reaches a cloud endpoint when the active provider is `my_machine`.

A10. **`huggingface-cli` is on PATH after `setup.sh` runs.** `download_model()` already uses it for the chat starter (line ~1205); the coder starter reuses the same primitive. If `huggingface-cli` is missing, the `--with-coder` branch falls back to `python3 -c "from huggingface_hub import snapshot_download; …"` — same pattern as the MLX branch at line 1198.

A11. **`min`-tier users may still pre-download the coder model** but cannot use opencode. Per plan: don't reject `--with-coder` on min — log "downloaded; will be unused until you upgrade to max." This avoids a confusing setup-time gate when the user's intent is "prep both tiers now."

A12. **The portal-side LLM-ready check is allowed to be cached.** A 5 s TTL is sufficient — model-load transitions are second-scale, and cloud-provider-token validity probes (if added) are network-bound. We cache the *full* `{ok, reason, hint}` result, keyed by `(provider, model_signature)`, and invalidate on `_set_chat_model_load_state` or `providers_active` writes.

A13. **No multi-tenant concern.** Single operator, one running portal, one opencode subprocess. Module-level locks suffice for serializing config-write + restart pairs (extends Sprint 1's `_lock`).

## Data flow

```
Operator browser
   │
   │  GET /opencode                              (4-state HTML — adds "needs LLM")
   │  GET /api/notebooks/status                  (drives card UI; now carries llm_ready bool)
   │  POST /api/opencode/start                   (now LLM-gated)
   │  POST /api/providers/active                 (extended hook)
   │
   │  iframe src="http://127.0.0.1:4096/"        (unchanged from Sprint 1)
   ▼
┌──────────────────── ARAIL Portal (FastAPI, :8080) ─────────────────────┐
│                                                                          │
│   Tier gate: "notebooks" in _visible_surfaces() → 404                    │
│                                                                          │
│   ┌── Sprint 2 NEW ──────────────────────────────────────────────────┐   │
│   │  /api/openai/v1/models           → openai_compat.list_models()   │   │
│   │  /api/openai/v1/chat/completions → openai_compat.chat()          │   │
│   │     - Translates OpenAI request → _run_chat_completion[_stream]  │   │
│   │     - Translates lab response   → OpenAI envelope (SSE for stream)│  │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│   ┌── Sprint 1 (extended) ──────────────────────────────────────────┐   │
│   │  /api/opencode/start                                              │   │
│   │     1. _require_workbench()                  (Sprint 1)           │   │
│   │     2. opencode.llm_ready_check()    NEW     → 409 on no_llm/no_token│
│   │     3. opencode.start(port)          NEW: _render_opencode_config │   │
│   │                                            writes lab/.opencode/   │
│   │                                            opencode.json before    │
│   │                                            Popen.                  │
│   │  /api/notebooks/status — opencode entry now has llm_ready: bool    │
│   │  /api/providers/active                                              │
│   │     hook order (NEW): regenerate_config() → restart()               │
│   │                       under a single lock; failure = leave running  │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│   Module: src/arail/portal/openai_compat.py            (NEW ~150 lines) │
│   Module: src/arail/portal/services/opencode.py        (extended)       │
│      ├─ _render_opencode_config(state)  NEW             (pure, testable)│
│      ├─ llm_ready_check()               NEW                             │
│      ├─ regenerate_config()             NEW             (writes file)   │
│      ├─ _config_path()                  NEW             (LAB_ROOT/.opencode)│
│      └─ _compute_source_env()           UPDATED         (cloud env names)│
└──────────────────────────────────────────────────────────────────────────┘
                       │
                       ▼  (subprocess, env from _compute_source_env)
              opencode child  ◄── reads lab/.opencode/opencode.json at boot
                       │            (LAB_ROOT/.opencode via OPENCODE_CONFIG_DIR)
                       │
                       │  for cloud: reads ANTHROPIC_API_KEY etc. from env
                       │  for my_machine: HTTP → 127.0.0.1:<PORTAL_PORT>/api/openai/v1
                       ▼
                 (chat backend or cloud endpoint)
```

The shim creates a *new* loop: when My-Machine is active, opencode → portal → backend. The Compute Source pivot still drives behavior, but for the local case the network hop is a localhost shim instead of a non-existent Ollama.

## Interface contracts

### Module `src/arail/portal/openai_compat.py` (NEW)

Public surface mounted on the existing FastAPI `app`. Two routes; no module-level side effects on import.

```python
# Mounted in app.py at startup, before other route imports if possible.

@app.get("/api/openai/v1/models")
async def openai_compat_models() -> dict
    """Return loaded + locally-available models in OpenAI envelope.

    Promises:
      - Returns 200 with shape {"object": "list", "data": [{...}]}.
      - Each entry: {"id": str, "object": "model",
                     "created": int (epoch s),
                     "owned_by": "arail-lab"}.
      - Includes EVERY model from _scan_local_models()['models']
        (not only loaded ones) — opencode's UI lists them all and the
        actual usable subset is enforced by the LLM-ready gate.
        Rationale: opencode shows greyed entries that won't run; users
        see what's available without surprise.
      - When _CHAT_MODEL_LOAD_STATE.state == "ready" AND its 'model'
        field is set, that id is also injected (covers the "loaded
        from a runtime, not in lab/models/ on disk" case — e.g.
        ollama-served models).
      - When LAB_MODE=airgapped and Compute Source is my_machine, this
        is the full list of usable IDs. When cloud, falls through to
        the active provider's catalogue (NOT cross-provider — opencode
        only sees its current pinned provider via opencode.json).
      - Never raises; returns {"object": "list", "data": []} on any
        error.

    Pre: tier gate via `_visible_surfaces()` IS NOT applied — the shim
    is reachable from any tier so blueprint-tier (min) automation can
    use it too. Loopback is the perimeter.

    Bad input: n/a (no input)."""

@app.post("/api/openai/v1/chat/completions")
async def openai_compat_chat(request: Request) -> Response | StreamingResponse
    """OpenAI-compatible chat-completions proxy.

    Request body (subset of OpenAI fields we honor):
      {
        "model": "<model-id>",          # required; matched against /models
        "messages": [{"role","content"}, ...],  # required, len >= 1
        "temperature": 0.0..2.0,        # default 0.7
        "top_p": 0.0..1.0,              # default 1.0
        "max_tokens": int,              # default 512
        "stream": bool,                 # default False
      }

    Ignored OpenAI fields (silently): n, presence_penalty,
    frequency_penalty, logit_bias, user, response_format, tools,
    tool_choice, seed, stop, logprobs, top_logprobs.

    Behavior:
      - messages: concatenate non-system roles into a single
        prompt; latest user turn becomes 'message' for
        _run_chat_completion. system messages are joined and prefixed.
        history-as-list is the prior turns.
      - temperature/top_p/max_tokens map directly.
      - When stream=False:
          → call _run_chat_completion(...)
          → return JSON
              {
                "id": "chatcmpl-<hex>",
                "object": "chat.completion",
                "created": <epoch s>,
                "model": <body.model>,
                "choices": [{
                  "index": 0,
                  "message": {"role":"assistant","content":<reply>},
                  "finish_reason": "stop"
                }],
                "usage": {
                  "prompt_tokens": <approx tokens_in from cost_tracker>,
                  "completion_tokens": <result.tokens_used or 0>,
                  "total_tokens": <sum>
                }
              }
      - When stream=True:
          → media_type = 'text/event-stream'
          → headers: Cache-Control: no-cache, X-Accel-Buffering: no,
                     Connection: keep-alive
          → emit `data: <chunk>\n\n` lines, where each <chunk> is:
              {
                "id": "chatcmpl-<hex>",        (constant for the stream)
                "object": "chat.completion.chunk",
                "created": <epoch s>,
                "model": <body.model>,
                "choices": [{
                  "index": 0,
                  "delta": {"role":"assistant","content": <delta>}
                                                  on first chunk include role,
                                                  on subsequent omit role,
                  "finish_reason": null
                }]
              }
          → final chunk: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}
          → terminator: `data: [DONE]\n\n`
          → consume from `_run_chat_completion_stream(...)`:
            * type="start" → emit role-only delta
            * type="delta" → emit content delta
            * type="final" → emit finish_reason chunk + [DONE]
            * if 'error' present in any final → emit OpenAI error envelope
              before [DONE]:
              {"error":{"message":<err>,"type":"backend_error","code":null}}

    Promises:
      - Returns within ~50 ms for the request-validation phase; payload
        latency depends on backend (no portal-side budget).
      - Errors return OpenAI-shaped envelope:
          400 → {"error":{"message":"...","type":"invalid_request_error"}}
          500 → {"error":{"message":"...","type":"server_error"}}
        AND a top-level non-2xx status code.

    Bad input handling:
      - Missing 'messages' or empty list → 400
      - Missing 'model' → 400 (we don't infer)
      - Body-not-JSON → 400
      - Unknown 'model' (not in /models list) → 200 anyway and let the
        backend report — opencode's locked picker means this is rare
        and we don't want to over-validate.
      - 'stream' is non-bool → coerce to bool(value) ('true'/'false' strings ok)

    Side effects:
      - Hits cost_tracker (existing chat surface does the same).
      - May trigger _CHAT_MODEL_LOAD_STATE transition if it's the
        first chat with a runtime backend (existing behavior).

    Threading: the route is `async def`. Synchronous backend calls go
    through `_run_chat_completion[_stream]` which already use
    `asyncio.to_thread` + `scheduler.inference_slot` (see
    app.py:4651-4660). No new threading model needed.

    Logging: NEVER log request 'messages' content (could include
    secrets the user paste). Log only model id, stream flag, latency_ms,
    finish_reason. Same posture as /api/chat today."""
```

**Module shape detail:** declare a private helper `_to_chat_args(body)` that maps OpenAI body → kwargs for `_run_chat_completion[_stream]`. Define `_make_chunk(delta, model, stream_id, role=None, finish_reason=None) -> str` that returns the SSE-formatted line. Constant: `_OWNED_BY = "arail-lab"`. No global state.

### Module `src/arail/portal/services/opencode.py` (extended)

Functions added or modified — all callers serialize through the existing module-level `_lock` from Sprint 1.

```python
# NEW — module-level constants

_LLM_READY_TTL_S: float = 5.0
_LLM_READY_CACHE: dict[str, Any] = {"key": None, "result": None, "ts": 0.0}

# Map active provider id → opencode env-name that the cloud token
# should appear under, so opencode.json can use {"env": ["NAME"]}
# instead of embedding the secret. Mirrors _PROVIDER_KEY_ENVS in app.py.
_PROVIDER_TOKEN_ENV: dict[str, str] = {
    "claude":      "ANTHROPIC_API_KEY",
    "nvidia":      "NVIDIA_API_KEY",
    "openrouter":  "OPENROUTER_API_KEY",
    "huggingface": "HF_TOKEN",
    "custom":      "MODEL_API_KEY",
}


def _config_path() -> Path
    """Return Path to lab/.opencode/opencode.json.

    Rooted at config.LAB_ROOT (default 'lab/'). The parent dir is
    created on first write.
    Pure: reads only env at call time.
    """

def _config_dir() -> Path
    """Return Path to lab/.opencode/ (the directory passed via
    OPENCODE_CONFIG_DIR to opencode subprocess).
    Pure.
    """

def llm_ready_check(force: bool = False) -> dict
    """Decide whether opencode CAN start meaningfully right now.

    Returns:
      {
        "ok": bool,
        "reason": str | None,           # 'no_llm' | 'loading' | 'no_token' | 'shim_down' | None
        "hint": str | None,             # human-readable next step
        "chat_url": "/chat" | None,     # CTA target for the UI
        "provider": str,                # active provider id at check time
        "model": str | None,            # active model id (my_machine only)
      }

    Logic:
      provider = _load_active_provider()  (lazy import from app.py)

      if provider == 'my_machine':
        load = _get_chat_model_load_state()  (lazy import)
        if load['state'] == 'ready' and load.get('model'):
          # OPTIONAL: probe the shim (see Failure mode F-GATE-3)
          # Default: skip the probe. Cached <5s. The shim is local
          # and the same FastAPI process — if it's down, the portal
          # is down.
          return ok=True, model=load['model']
        if load['state'] == 'loading':
          return ok=False, reason='loading',
                 hint='Model is loading — try again in a moment.',
                 chat_url='/chat'
        if load['state'] == 'error':
          return ok=False, reason='no_llm',
                 hint='Model load failed — check Chat tab.',
                 chat_url='/chat'
        # state == 'ready' but model is None — the lab is on the
        # default router but has never loaded anything; treat as
        # no_llm. Cold-start tells the user where to go.
        return ok=False, reason='no_llm',
               hint='Load a model in Chat first.',
               chat_url='/chat'

      else:  # cloud provider
        token = _provider_token(provider)
        if not token:
          return ok=False, reason='no_token',
                 hint=f'Save a {provider} API key in Chat → Manage providers.',
                 chat_url='/chat'
        # We DO NOT probe the cloud endpoint by default — adds
        # 200ms+ latency and false-negatives on flaky networks.
        # SPRINT 2+ may add an opt-in deeper check.
        return ok=True

    Caching:
      Cache key = (provider, load.state, load.model). Cache value =
      result dict. Cache invalidates on any _set_chat_model_load_state
      call (we add a tiny notify hook), on any /api/providers/active
      success, or on TTL expiry (5 s). force=True bypasses cache.

    Bad input: n/a. Never raises (lazy-imports wrapped in try/except).

    Promises:
      - Returns within 5 ms typical (cache hit) / 50 ms cold.
      - Never blocks on a network call by default."""

def _render_opencode_config(*,
                             provider: str,
                             model: str | None,
                             portal_port: int,
                             tier: str,
                             models_list: list[dict] | None = None,
                             ) -> dict
    """Pure function: build the dict that becomes opencode.json.

    Parameters:
      provider     — 'my_machine' | 'claude' | 'nvidia' | 'openrouter' |
                     'huggingface' | 'custom'
      model        — active model id (None when no model loaded; caller
                     should use llm_ready_check before invoking this)
      portal_port  — int, used in the 'lab-local' provider baseURL
      tier         — 'min' | 'max' (governs the agent prompt — max
                     mentions the Workbench surfaces)
      models_list  — optional pre-fetched _scan_local_models()['models'];
                     when provider='my_machine' and provided, included as
                     the lab-local provider's models map. When None, only
                     the active model is registered.

    Returns the schema-valid opencode.json dict (Decision: schema-validation
    is a soft check — we generate, opencode either accepts it or fails-closed
    with a log line. F-CONFIG-2.).

    Output dict shape (canonical, my_machine + AirLLM):

      {
        "$schema": "https://opencode.ai/config.json",
        "share": "disabled",                           # never share lab transcripts
        "autoupdate": false,                           # lab pins binary version
        "instructions": [
          "AGENTS.md",
          "CLAUDE.md",
          "docs/agents.md"
        ],
        "provider": {
          "lab-local": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "ARAIL Lab",
            "options": {
              "baseURL": "http://127.0.0.1:8080/api/openai/v1"
            },
            "models": {
              "<active-model-id>": {
                "name": "<active-model-id>",
                "tools": true,
                "reasoning": false
              }
              # plus other entries when models_list is provided
            }
          }
        },
        "enabled_providers": ["lab-local"],            # locks the picker
        "model": "lab-local/<active-model-id>",         # default model
        "small_model": "lab-local/<active-model-id>",   # same — single-model lock
        "agent": {
          "build": {
            "model": "lab-local/<active-model-id>",
            "prompt": "<see lab-system-prompt below>",
            "tools": {
              "write": true, "edit": true, "bash": true,
              "read": true, "grep": true, "glob": true, "list": true
            }
          },
          "plan": {
            "model": "lab-local/<active-model-id>",
            "prompt": "<see lab-system-prompt below>",
            "tools": {
              "write": false, "edit": false, "bash": false,
              "read": true, "grep": true, "glob": true, "list": true
            }
          }
        },
        "command": {
          "lab-status": {
            "description": "Summarize lab status — active goal, sprint, agents, KB stats.",
            "agent": "build",
            "template": "Read $REPO_ROOT/lab/data/goals/active.json (if present), the latest sprints/<id>/SPRINT.md by mtime, and `ls $REPO_ROOT/lab/pkb/agents/`. Summarize: current goal, in-progress sprint phase, count of agents discovered, count of files in lab/pkb/sources/. Be terse."
          },
          "sprint-current": {
            "description": "Show the in-progress sprint's SPRINT.md and next undone phase.",
            "agent": "build",
            "template": "Find the most recently modified sprints/*/SPRINT.md. Read it. Identify the next phase whose Status is not 'done'. Print the phase name + the artifact path that would carry its output (VISION.md/ARCHITECTURE.md/BUILD_LOG.md/REVIEW.md/TEST_REPORT.md)."
          },
          "skills-list": {
            "description": "List skills installed under lab/pkb/skills/.",
            "agent": "build",
            "template": "Run `ls -1 $REPO_ROOT/lab/pkb/skills/`. For each entry, read the first heading from its SKILL.md if present. Output: skill-id  —  one-line summary."
          },
          "agents-status": {
            "description": "List agents and their last-activity timestamps.",
            "agent": "build",
            "template": "Run `ls -1 $REPO_ROOT/lab/pkb/agents/`. For each entry, read AGENT.md's first paragraph. If a state file exists at $REPO_ROOT/lab/data/agents/<id>/state.json, include the 'last_seen' field. Output one line per agent."
          },
          "kb-search": {
            "description": "Search the lab knowledge base for a query (LanceDB).",
            "agent": "build",
            "template": "Search the LanceDB-backed KB for: $ARGUMENTS. Curl `http://127.0.0.1:8080/api/wiki/search?q=...` and summarize the top 5 hits with file paths."
          },
          "claude-md": {
            "description": "Read CLAUDE.md and recap the conventions.",
            "agent": "build",
            "template": "Read $REPO_ROOT/CLAUDE.md. Output a 5-bullet summary covering: what ARAIL is, how to invoke /sprint, how agents are loaded, where secrets live, and the LAB_MODE airgap default."
          }
        },
        "permission": {
          "edit": "allow",
          "bash": {"*": "ask"}                          # opencode default; explicit
        }
      }

    Variant: my_machine + MLX. Identical except `tools.reasoning` is
    set per the model (MLX-coder may set true; Qwen3 base set false).
    Conservative default: false.

    Variant: cloud + claude. Differences:
      - "provider": {
          "anthropic": {                              # opencode's built-in id
            "name": "Anthropic",
            "options": {},                            # use defaults
            "models": {
              "<model-id>": { "name": "<model-id>", "tools": true }
            }
          }
        }
      - "enabled_providers": ["anthropic"]
      - "model": "anthropic/<model-id>"
      - agent build/plan model: same
      - **Critical:** the API key is provided to opencode by setting
        `ANTHROPIC_API_KEY` in the *subprocess env* (via
        _compute_source_env(), see below). **It does NOT appear in
        opencode.json text.** The opencode binary reads ANTHROPIC_API_KEY
        from process env at startup for its built-in providers.
        F-SEC-CRED-1.

    Pure function. No filesystem, no env reads beyond the explicit
    parameters. Deterministic — same inputs → byte-identical JSON
    (sort keys on serialize).

    Returns: dict (NOT json string — caller serializes)."""

def regenerate_config(*, force: bool = False) -> dict
    """Write lab/.opencode/opencode.json from current lab state.

    Steps:
      1. Read provider, model, tier via _load_active_provider() +
         _get_chat_model_load_state() + os.getenv('LAB_TIER', 'min').
      2. Build dict via _render_opencode_config(...).
      3. Atomically write: tmp = path.with_suffix('.json.tmp');
         json.dumps(d, indent=2, sort_keys=True); fsync; rename.
         (F-CONFIG-3 atomicity.)
      4. Set chmod 0644 on the file (no secrets — readable is fine).
         The directory itself: 0700 — the operator may have set keys
         in $HOME's opencode and we don't want lab dir leaking that
         posture. (Defense-in-depth.)
      5. Return {"ok": bool, "path": str, "model": str|None, "provider": str}.

    Bad input: when llm_ready_check() returns ok=False, we still write
    a config — just one with model=None and a placeholder provider entry
    that will fail at opencode start. The 4-state UI catches this case
    BEFORE start is ever called, so this is defense-in-depth only.

    Failure: write errors return {"ok": False, "error": str} and DO
    NOT delete an existing config (F-CONFIG-3 — keep last good config
    if write fails)."""

def lab_system_prompt(tier: str) -> str
    """Return the multi-line system prompt for the build agent.

    Pure. Tier-aware (max version mentions Workbench surfaces).
    Body (illustrative; builder may polish wording):

      You are coding inside ARAIL — an autoresearch AI lab blueprint.
      The repository root is the working directory.

      Read these files when relevant:
      - CLAUDE.md (the orientation file for AI agents in this repo)
      - AGENTS.md (the platform-porting manifest for new platforms)
      - docs/agents.md (the agent loader contract)

      Conventions:
      - Sprints live in sprints/<YYYY-MM-DD>-<slug>/. The /sprint skill
        orchestrates visionary → architect → builder → architect-review →
        qa → ship via committed artifacts (VISION/ARCHITECTURE/BUILD_LOG/
        REVIEW/TEST_REPORT).
      - Agents live in lab/pkb/agents/<id>/AGENT.md + <id>.py.
      - Secrets live in lab/data/secrets.env (chmod 0600, git-ignored).
        NEVER write credentials to other paths and NEVER echo them.
      - LAB_MODE defaults to 'airgapped' — do not reach external services
        unless the user explicitly enables hybrid mode.
      - The internal Python package name is `arail`. Imports must not
        break when the lab is rebranded (LAB_NAME / LAB_TAGLINE).

      Use the slash commands /lab-status, /sprint-current, /skills-list,
      /agents-status, /kb-search, /claude-md to orient quickly.

      Match the existing code style. Branch names use the qukaizen/<slug>
      prefix. Commit messages should be concise; prefer fixing root
      causes over masking symptoms.

    The prompt is included verbatim in opencode.json under
    agent.build.prompt and agent.plan.prompt."""

# UPDATED — _compute_source_env now sets the cloud provider's
# canonical env var name (not OPENCODE_API_KEY) so opencode.json
# can reference it via env=["ANTHROPIC_API_KEY"] etc.

def _compute_source_env() -> dict[str, str]
    """[UPDATED] Translate active Compute Source → subprocess env.

    Mapping (CHANGED from Sprint 1):
      provider == 'my_machine':
        # Point opencode at the lab-side OpenAI shim, NOT Ollama default.
        OPENCODE_API_BASE = f"http://127.0.0.1:{PORTAL_PORT}/api/openai/v1"
                              # PORTAL_PORT from os.getenv, default 8080
        OPENCODE_MODEL    = _CHAT_MODEL_LOAD_STATE['model'] or os.getenv('MODEL_NAME','')
        OPENCODE_API_KEY  = 'not-needed'

      provider in cloud:
        # Set BOTH the canonical provider env name AND the legacy
        # OPENCODE_* names. opencode.json's env=["ANTHROPIC_API_KEY"]
        # reads from process env at boot. The OPENCODE_API_KEY=... is
        # belt-and-suspenders for older opencode versions.
        env_var_name = _PROVIDER_TOKEN_ENV[provider]   # e.g. "ANTHROPIC_API_KEY"
        token        = _provider_token(provider)
        OPENCODE_API_BASE = _CLOUD_PROVIDER_BASES[provider]  # or MODEL_API_BASE for custom
        OPENCODE_MODEL    = _CHAT_MODEL_LOAD_STATE['model'] or os.getenv('MODEL_NAME','')
        OPENCODE_API_KEY  = token        # legacy compat
        <env_var_name>    = token        # NEW — what opencode.json references

    Returns: dict with these keys ONLY (no shadowing of unrelated
    env). Caller merges into os.environ for Popen.

    Promises:
      - Never logs token values (Sprint 1 F-SEC-2 carries forward).
      - When token is empty, sets the env var to '' (not absent) so
        opencode emits a clean auth error instead of a confusing
        "missing key" stack.

    Bad input: unknown provider → fall back to my_machine mapping
    (matches Sprint 1)."""

# UPDATED — start now writes the config first.

def start(port: int = PORT_DEFAULT) -> dict
    """[UPDATED] Spawn opencode with lab-curated config.

    Steps (under module _lock, same as Sprint 1):
      1. is_installed() / is_running() pre-checks (Sprint 1).
      2. _maybe_rotate_log() (Sprint 1).
      3. regenerate_config()                           # NEW
         If write fails: return {"ok": False, "error": "config_write: ..."}
      4. env = {**os.environ,
                "OPENCODE_CONFIG_DIR": str(_config_dir()),
                "OPENCODE_DISABLE_AUTOUPDATE": "true",
                **_compute_source_env()}
                                                       # NEW
      5. Popen ['opencode', 'serve', '--port', str(port),
                '--hostname', '127.0.0.1'] (unchanged — args don't change)
      6. Return {"ok": True, "pid": int} (unchanged shape).

    Promises:
      - When LLM is not ready, this function does NOT prevent start —
        the caller (`/api/opencode/start`) is responsible for the gate.
        (Defense-in-depth: config still gets written, opencode will
        boot but fail any prompt with a clean error message.)

    Bad input: unchanged from Sprint 1."""
```

### Route changes in `app.py`

```python
# UPDATED: /api/opencode/start gains the LLM-ready gate
@app.post("/api/opencode/start")
async def opencode_start():
    if (gate := _require_workbench()) is not None:
        return gate
    from arail.portal.services import opencode as oc
    ready = oc.llm_ready_check()
    if not ready["ok"]:
        return JSONResponse(status_code=409, content={
            "ok": False,
            "reason": ready["reason"],          # 'no_llm'|'loading'|'no_token'
            "hint": ready["hint"],
            "chat_url": ready.get("chat_url"),
        })
    port = int(os.getenv("OPENCODE_PORT", str(oc.PORT_DEFAULT)))
    result = oc.start(port=port)
    if result.get("ok"):
        activity_log.emit("notebooks", "opencode started.", "success")
    return result

# UPDATED: /api/notebooks/status — opencode entry adds llm_ready
# (existing block at app.py:1533–1541)
if "notebooks" in _visible_surfaces():
    ready = oc.llm_ready_check()
    notebooks.append({
        "id": "opencode",
        "name": "opencode",
        "installed": oc.is_installed(),
        "alive": opencode_alive,
        "url_internal": "/opencode",
        "url_external": f"http://127.0.0.1:{opencode_port}/",
        "llm_ready": ready["ok"],                # NEW
        "llm_reason": ready.get("reason"),       # NEW (only when not ok)
        "llm_hint": ready.get("hint"),           # NEW
    })
```

```python
# UPDATED: /api/providers/active hook (app.py:1063-1071)
if "notebooks" in _visible_surfaces():
    try:
        from arail.portal.services import opencode as _oc
        if _oc.is_running():
            # Order matters: regenerate THEN restart. Lock prevents
            # double-fire when two providers/active calls race.
            def _hook():
                cfg = _oc.regenerate_config()
                if not cfg.get("ok"):
                    # Leave the running opencode pointing at OLD config
                    # rather than restart blind into a broken state.
                    return
                _oc.restart()
            threading.Thread(target=_hook, daemon=True).start()
    except Exception:
        pass
```

```python
# /api/openai/v1/* mounted from openai_compat.py
# Ordering: register BEFORE the catch-all routes. Place the import +
# decorator block alongside the existing /api/chat block so the
# read-order in app.py reflects the dependency.
```

### Template changes — `templates/opencode.html` (4-state)

State machine:

| State id          | Conditions                                    | UI block                                      |
|-------------------|-----------------------------------------------|-----------------------------------------------|
| `not_installed`   | `!installed`                                  | Install hint (existing — unchanged)           |
| `installed_no_llm`| `installed && !running && !llm_ready`         | NEW: "Load a model in Chat first" + CTA `/chat` |
| `installed_idle`  | `installed && !running && llm_ready`          | "Start opencode" button (existing)            |
| `running`         | `installed && running`                        | iframe + topbar (existing)                    |

Transitions driven by:
- Page load: `GET /opencode` template-side checks (server renders the right initial state from `installed`, `running`, plus a NEW `llm_ready` boolean passed in the template context — needs to be added to the route handler at `app.py:1289-1304`).
- Status poll: `GET /api/notebooks/status` → JS toggles between `installed_no_llm` and `installed_idle` if the model state changes while the user is on the page.

DOM pattern (Jinja):

```jinja
{% if running %}
  ... existing block ...
{% elif installed and not llm_ready %}
  <div class="oc-install" data-state="installed_no_llm">
    <h1>Load a model first</h1>
    <p>
      <span class="status-pill status-installed">✓ opencode installed</span>
      <span class="status-pill status-warn">○ no model loaded</span>
    </p>
    <p>{{ llm_hint or "Open the Chat tab and pick a model — opencode reuses whatever's loaded." }}</p>
    <p>
      <a class="btn btn-sm" href="{{ llm_chat_url|default('/chat') }}"
         style="background:var(--blue);color:#000;font-weight:700;padding:0.4rem 1.2rem;">
        → Open Chat
      </a>
    </p>
    <p class="oc-notice">
      Why? opencode talks to whatever model the lab has loaded. Loading
      one in Chat shares it with opencode (no double-load, no extra RAM).
    </p>
  </div>
{% elif installed %}
  ... existing "installed-not-running" block ...
{% else %}
  ... existing "not-installed" block ...
{% endif %}
```

The Workbench card in `notebooks.html` follows the same 4-state pattern: card status label gains a fourth row "needs LLM — open Chat" when `nb.installed && !nb.llm_ready`. The status dot color: `warn` (amber) for needs-LLM, distinct from the existing `standby` (blue) and `alive` (green).

### Setup.sh — `--with-coder` (NEW branch)

```bash
# Argument parsing (NEW — at top of main() or before download_model):
WITH_CODER="${ARAIL_WITH_CODER:-0}"
for arg in "$@"; do
    case "$arg" in
        --with-coder)        WITH_CODER=1 ;;
        --no-coder)          WITH_CODER=0 ;;
        *) ;;
    esac
done

# Coder-model IDs (mirrors MODEL_MLX_ID/MODEL_HF_ID/MODEL_GGUF_ID).
# Builder MUST also add these to pyproject.toml [tool.arail.models]:
#     coder_mlx  = "mlx-community/Qwen2.5-Coder-3B-Instruct-4bit"
#     coder_cuda = "Qwen/Qwen2.5-Coder-3B-Instruct"
#     coder_cpu  = "Qwen/Qwen2.5-Coder-3B-Instruct-GGUF"
# and have load_pyproject_metadata() read them.
CODER_MLX_ID="mlx-community/Qwen2.5-Coder-3B-Instruct-4bit"
CODER_HF_ID="Qwen/Qwen2.5-Coder-3B-Instruct"
CODER_GGUF_ID="Qwen/Qwen2.5-Coder-3B-Instruct-GGUF"

download_coder_model() {
    if [[ "$WITH_CODER" != "1" ]]; then
        return 0
    fi
    step "8b/11  Coder starter model (Qwen2.5-Coder-3B-Instruct, ~2 GB Q4)"

    # Reject silently? No — log a notice when min tier so the user
    # knows the model is downloaded but unused until they upgrade.
    if [[ "$LAB_TIER" != "max" ]]; then
        warn "Tier is '${LAB_TIER}', not 'max'. The Workbench tab is max-only."
        warn "Downloading the coder model anyway — it will be unused until"
        warn "you run: ./arail upgrade max"
    fi

    local model_dir="lab/models"
    mkdir -p "$model_dir"
    local target=""

    if [[ "$ACCEL" == "mlx" ]]; then
        target="${model_dir}/Qwen2.5-Coder-3B-Instruct-4bit"
        if [[ -d "$target" ]]; then
            info "Coder model already downloaded ($target)."
            return 0
        fi
        info "Downloading $CODER_MLX_ID → $target"
        python3 -c "from huggingface_hub import snapshot_download; snapshot_download('${CODER_MLX_ID}', local_dir='${target}')" \
            || { warn "Coder model download failed — see error above. Continuing without coder."; return 0; }
    elif [[ "$ACCEL" == "cuda" ]]; then
        target="${model_dir}/Qwen2.5-Coder-3B-Instruct"
        if [[ -d "$target" ]]; then info "Coder model already downloaded."; return 0; fi
        info "Downloading $CODER_HF_ID → $target"
        python3 -c "from huggingface_hub import snapshot_download; snapshot_download('${CODER_HF_ID}', local_dir='${target}')" \
            || { warn "Coder model download failed."; return 0; }
    else
        target="${model_dir}/Qwen2.5-Coder-3B-Instruct-GGUF"
        if [[ -d "$target" ]]; then info "Coder model already downloaded."; return 0; fi
        info "Downloading $CODER_GGUF_ID (Q4) → $target"
        if command -v huggingface-cli >/dev/null 2>&1; then
            huggingface-cli download "$CODER_GGUF_ID" --include 'Q4_K_M*' \
                --local-dir "$target" --local-dir-use-symlinks False \
                || { warn "Coder model download failed."; return 0; }
        else
            python3 -c "from huggingface_hub import snapshot_download; snapshot_download('${CODER_GGUF_ID}', local_dir='${target}', allow_patterns=['*Q4_K_M*'])" \
                || { warn "Coder model download failed."; return 0; }
        fi
    fi

    info "Coder model ready at $target."
}

# Hook in main() right after download_model:
download_model
download_coder_model               # NEW
capture_goal
```

`scripts/upgrade.sh` similarly accepts `--with-coder` and re-uses the same `download_coder_model` body — extract to `scripts/_lib_models.sh` shared by both, OR simply duplicate (~30 lines, not worth abstraction yet). **Decision: duplicate.** Tech debt: a future sprint that adds another starter (qukaizen-distilled, etc.) gets to do the extraction.

`./arail upgrade max --with-coder` flow: parse `--with-coder`, set tier to max, call the same body. Builder verifies upgrade.sh integrates cleanly without breaking `./arail upgrade max` (no flag) backwards compat.

## Failure modes

| ID | Failure | Detection | Recovery |
|---|---|---|---|
| **F-SHIM-1** | OpenAI streaming envelope drift — opencode expects `"object":"chat.completion.chunk"` and `data: [DONE]\n\n` terminator; lab emits NDJSON-style `{type:"delta"}` events. | Test `test_shim_stream_envelope_round_trip`: stream a 3-token reply through `/api/openai/v1/chat/completions?stream=true`; assert response body matches regex `^data: \{...\}\n\n(data: \{...\}\n\n)+data: \[DONE\]\n\n$` AND each chunk parses as JSON with the OpenAI shape. | Translation layer in `openai_compat.openai_compat_chat`: consume `_run_chat_completion_stream`'s `{type:"start"|"delta"|"final"}` events, emit OpenAI-shaped chunks. Tested per branch. |
| F-SHIM-2 | Non-streaming response missing `usage` block (opencode's TUI parses it). | Test `test_shim_non_stream_includes_usage`: assert response JSON has `usage.prompt_tokens`, `usage.completion_tokens`, `usage.total_tokens`. | Always emit usage block; defaults: tokens_in = `len(prompt)//4`, tokens_out = `result.tokens_used or 0`. |
| F-SHIM-3 | `messages[]` history shape differs from lab's `history[]` (lab has alternating user/assistant; OpenAI allows arbitrary system+tool roles). | Test `test_shim_messages_to_history_mapping`: 3-message convo with system → mapped correctly. | `_to_chat_args`: separate system messages (concat into system prefix), pair user+assistant turns into history list, last user → `message`. Reject empty messages with 400. |
| F-SHIM-4 | Model id mismatch — opencode sends `lab-local/Qwen2.5-Coder-3B-Instruct` and the shim looks up by full string in `_scan_local_models()` which returns just `Qwen2.5-Coder-3B-Instruct`. | Test `test_shim_strips_provider_prefix`: request `model='lab-local/foo'` → backend sees `model='foo'`. | Strip `<provider>/` prefix on inbound; pass bare model id to `_run_chat_completion`. |
| F-SHIM-5 | Error envelope mismatch — backend exception emits raw stack trace; opencode chokes. | Test `test_shim_error_envelope_openai_shape`: force backend exception, assert response is `{"error":{"message":...,"type":"server_error"}}` JSON, not a dict with `error: <str>` like the lab's `/api/chat`. | Map: `result.get('error')` → OpenAI envelope. Top-level status code 500 on backend exceptions, 400 on validation. |
| F-SHIM-6 | `/api/openai/v1/models` returns models the user can't actually run (RAM-too-small, unloaded MLX, etc.). | Acceptable behavior per A8/§Interface. | Document: opencode will surface backend errors at chat time. The LLM-ready gate is the real safety net. |
| F-SHIM-7 | Cost-tracker double-charges when shim is called from opencode (already counted by Chat-tab path). | Test `test_shim_cost_tracker_source_label`: assert `cost_tracker.track(...)` called with `source='opencode'` (not `'ui'`). | Pass `source='opencode'` from the shim path so dashboard can split costs. |
| F-SHIM-8 | Streaming response doesn't flush eagerly — opencode's TUI hangs because Starlette buffers. | Test `test_shim_stream_yield_intervals`: instrument the iterator; assert each chunk is yielded within ~50 ms of the underlying delta. | Set `Cache-Control: no-cache` and `X-Accel-Buffering: no`; use `StreamingResponse(..., media_type='text/event-stream')`. Mirror existing `/api/chat/stream` pattern. |
| F-SHIM-9 | `/api/openai/v1/models` not gated by tier — leaks model list to min-tier scrapers. | Acceptable. Per A9 the shim is open to all tiers (loopback perimeter). | Documented; not gated. (Sprint 1 INFO-1 deferred analog.) |
| **F-CONFIG-1** | `opencode.json` schema changes between v1.14.x → v1.15.x and our generated dict is rejected. | Test `test_render_config_schema_smoke`: write rendered config to a temp dir, call `opencode --print-config-validate <path>` IF such a flag exists, else parse with `json.loads` and assert the keys we care about are present. Manual verification at sprint kickoff: the binary is v1.14.31; document. | Wrapped soft check — opencode logs a config error to its stderr (captured in `lab/logs/opencode.log`) and falls back to default config. The 4-state UI shows "running" because TCP is up but the user's prompt produces a strange response. **Mitigation:** version-pin opencode in install hint copy. Filed as Sprint 3 follow-up: add a `opencode --version` probe at start (Sprint 1's deferred F-INSTALL-2). |
| **F-CONFIG-2** | Provider token leaks into `opencode.json` text. | Test `test_render_config_no_token_in_plaintext`: render config with a fake-but-recognizable token (`'sk-FAKE-TOKEN-FOR-TEST'`) saved as the active provider's secret; assert the JSON output does NOT contain that string anywhere. Repeat for each cloud provider. | `_render_opencode_config` NEVER reads `_provider_token()`; cloud tokens go through `_compute_source_env()` (env var only). The dict references via `env=["NAME"]` (or via the built-in provider id which auto-reads from env). |
| F-CONFIG-3 | Atomicity — portal SIGKILLed mid-write leaves a corrupt `opencode.json`. | Test `test_regenerate_config_atomic_write`: simulate failure between tmp write and rename; assert original file (if present) is intact. | `regenerate_config` uses tmp-write + `fsync` + `os.replace`; on tmp-write failure, the original is untouched. |
| F-CONFIG-4 | `LAB_ROOT/.opencode/` directory creation race when two callers regenerate concurrently. | Test `test_regenerate_config_concurrent_calls`: 2 parallel calls to `regenerate_config()`; assert both succeed and final file is internally consistent. | All `regenerate_config` calls go through `_lock` (Sprint 1's module lock, reused). |
| F-CONFIG-5 | `OPENCODE_CONFIG_DIR` ignored by older opencode binaries; user's personal `~/.config/opencode/` overrides. | Manual check at kickoff: `opencode --version` >= 1.14.0. Builder probe: spawn opencode with `OPENCODE_CONFIG_DIR=/tmp/probe-xyz/`, write a recognizable config there, run `opencode debug config print` (or similar) and grep for our marker. | If the env var is ignored: fall back to symlinking `~/.config/opencode` → `lab/.opencode/` only when no existing `~/.config/opencode` is present (otherwise refuse to clobber). Document this in README/install hint as a fallback path. **Builder verifies at kickoff** before generating the config.|
| F-CONFIG-6 | Permissions on `lab/.opencode/` allow another user on the same host to read provider tokens (if they were written there). Since tokens go in env, NOT the file, this is theoretical — but we set 0700 on the dir for defense. | Test `test_config_dir_perms_0700`. | `regenerate_config` does `chmod 0o700` on `_config_dir()` after creation. |
| F-CONFIG-7 | The 6 slash commands point at paths that don't exist (e.g. user's lab is missing `lab/pkb/agents/`). | Test `test_render_config_command_paths_use_repo_root_var`: assert each command template references `$REPO_ROOT/lab/...` or relative paths, not absolute machine-local paths. | Templates use `$REPO_ROOT/lab/...` — opencode expands `$REPO_ROOT` at runtime to the project dir. If a path is missing, the slash command's bash returns a clean error (acceptable). |
| **F-GATE-1** | `/api/opencode/start` succeeds when no model is loaded — first prompt fails opaquely (the original Sprint 2 motivator). | Test `test_start_blocked_when_no_llm`: stub `_CHAT_MODEL_LOAD_STATE.state='ready', model=None`; POST `/api/opencode/start`; assert 409 with `reason='no_llm'`. | `llm_ready_check()` rejects; route returns 409 + structured `{ok:false, reason, hint, chat_url}`. UI shows the 4-state "needs LLM" block. |
| F-GATE-2 | Race: user clicks Start; between gate-check and Popen, the model unloads. | Test `test_start_race_unload_after_gate`: stub state to flip mid-call. | Acceptable. opencode launches and the first prompt fails — same as if the model had unloaded mid-session. The gate is a UX hint, not a hard guarantee. Documented. |
| F-GATE-3 | False-positive: gate says ok=True but the OpenAI shim is actually broken (e.g. shim raised on import). | Optional probe: `requests.get(f'http://127.0.0.1:{port}/api/openai/v1/models', timeout=0.5)` — but adds latency on every check. **Decision: skip.** The shim is in the same process; if it's down, the portal is down. | Documented limitation. If `/api/openai/v1/*` returns 500, opencode surfaces a backend error in its TUI. Acceptable. |
| F-GATE-4 | Cloud-provider `_provider_token` returns a non-empty but invalid token (revoked, typo). | Cheap probe: `providers_test()` exists at `app.py:1086`, but it makes a network call (~200-500ms). **Decision: don't probe in the gate.** | UX accepts the start, opencode reports auth error on first prompt. The gate's job is to catch the cold-start case (no token at all), not validity. |
| F-GATE-5 | LLM-ready cache is stale after manual `os.environ['COMPUTE_SOURCE']=...` in another thread. | Acceptable — `providers_active` invalidates the cache; ad-hoc env writes won't. | Documented. The portal owns provider switching via the API. |
| F-GATE-6 | Gate code path runs on min-tier despite `_require_workbench()` ordering. | Test `test_start_gate_runs_after_tier_gate`: assert `_require_workbench` is called BEFORE `llm_ready_check` (move the existing gate test pattern from Sprint 1). | Code review: route handler's first line is `_require_workbench()`, second is `llm_ready_check()`. |
| **F-RESTART-1** | Hook regenerates config but restart fails — opencode keeps running on STALE config. | Test `test_hook_regenerate_then_restart_serialized`: simulate restart failure; assert opencode still running with NEW config (not stale). | Sequence: regenerate succeeds → restart attempted → if restart fails, opencode is now down (because Sprint 1's restart kills then starts; if start fails we have a stopped opencode + new config). Next `/api/opencode/start` will pick it up. Acceptable. |
| F-RESTART-2 | Regenerate fails — restart proceeds with stale config (worse than not restarting). | Test `test_hook_aborts_restart_on_config_failure`: stub `regenerate_config` to return `{ok:false}`; assert restart NOT called. | Hook checks `cfg.get('ok')` before calling restart (see app.py snippet above). |
| F-RESTART-3 | Rapid double-switch — user flips provider twice in 100 ms; two regenerate-then-restart hooks race. | Test `test_concurrent_provider_switches_serialize`: spawn 2 threads calling the hook; assert final state matches the LAST switch (not interleaved). | Both hooks acquire the same module `_lock` (the Sprint 1 lock that already protects `start/stop/restart`). The second hook waits, then runs with the up-to-date `_load_active_provider()`. |
| F-RESTART-4 | Hook fires when opencode is_running=False (cold). Should it pre-write the config anyway? | Test `test_hook_skipped_when_opencode_not_running`: assert no file write occurs. | Sprint 1 already gates on `if _oc.is_running()`. We keep that gate. The next user-initiated `start` writes the config fresh (since `start` calls `regenerate_config` first). |
| **F-SETUP-1** | Coder model download mid-flight failure — partial directory left behind, next run thinks it's installed. | Test `test_with_coder_partial_download_handling`: simulate snapshot_download failure; assert no `Qwen2.5-Coder-3B-Instruct*` directory exists OR a marker file `.download-incomplete` is present. | `huggingface-cli` and `snapshot_download` both write atomically to `local_dir` only on success — but defensive: wrap the call to delete the dir on non-zero exit. (Match the existing `download_model` posture, which lets the user re-run on failure.) |
| F-SETUP-2 | Disk full during ~2GB download. | Bash exit code from snapshot_download. | `download_coder_model` warns and continues (does not abort setup). User re-runs after freeing disk. |
| F-SETUP-3 | `huggingface-cli` not on PATH on CPU branch. | Existing setup tests `command -v huggingface-cli`. | Falls back to `python3 -c "from huggingface_hub import …"` (same primitive); if neither works, warn and skip. |
| F-SETUP-4 | User runs `./arail upgrade max --with-coder` but min was set with no model dir. | `download_coder_model` ensures `lab/models/` exists with `mkdir -p`. | OK — same as setup. |
| F-SETUP-5 | Min tier user passes `--with-coder` and never upgrades to max — they have a 2 GB unused download. | Per A11, allowed. Warning logged. | Doc-only. User can `rm -rf lab/models/Qwen2.5-Coder-3B-Instruct*` if they want it back. |
| F-SETUP-6 | Re-running setup with `--with-coder` after first install — should it re-download? | Test: existing target dir → "already downloaded." log, return 0. | Idempotent: dir-exists check before download. |
| F-SETUP-7 | The model id in pyproject.toml diverges from what setup hardcodes. | Builder MUST add `coder_mlx`/`coder_cuda`/`coder_cpu` keys to `[tool.arail.models]` and have `load_pyproject_metadata()` read them; setup-script hardcoded fallbacks are SECONDARY (used only when pyproject.toml lacks the keys). | Single source of truth: pyproject.toml. The bash variables are populated from it via the existing `load_pyproject_metadata()` flow (see setup.sh lines 77-109). |
| **F-LOCK-1** | Locked picker UX — user opens opencode TUI's model picker, sees only one option, doesn't realize they need to swap in Chat. | Test `test_render_config_includes_picker_hint`: assert agent prompt mentions "to switch models, change Compute Source in Chat tab." | The build-agent system prompt (lab_system_prompt) includes a one-liner: "To switch which model handles your prompts, change the Compute Source in the lab's Chat tab — opencode picks up the new model on its next restart (automatic on switch)." |
| F-LOCK-2 | User wants to use a *different* model in opencode without affecting Chat. | Out of scope this sprint. | Documented; SPRINT.md decisions log already captured the locked-picker decision. Sprint 3+: an "opencode model override" toggle. |
| F-LOCK-3 | `enabled_providers` field renamed/removed in opencode v1.15+. | Builder MUST verify at kickoff (A7). | Fallback path: omit other providers from the `provider:` map AND set `OPENCODE_DISABLE_MODELS_FETCH=true`. Either way, only one model appears. |
| **F-SEC-CRED-1** | Cloud provider token written to `opencode.json` plaintext. (The most security-critical row.) | Test `test_render_config_no_token_in_plaintext` (already listed as F-CONFIG-2). Plus: `test_subprocess_env_carries_provider_token`: assert `_compute_source_env()` for `claude` provider returns dict containing `ANTHROPIC_API_KEY=<token>`. AND: `test_render_config_uses_env_reference_for_anthropic`: assert the `provider.anthropic.options.apiKey` field is NOT set; opencode reads `ANTHROPIC_API_KEY` from process env via its built-in provider. | Triple-check: (a) `_render_opencode_config` signature accepts no token arg; (b) `_compute_source_env` writes the cloud token under `_PROVIDER_TOKEN_ENV[provider]`; (c) tests assert non-leakage with a recognizable fake token. |
| F-SEC-CRED-2 | Cloud provider token leaks into opencode's own logs (Sprint 1 F-SEC-4 carried over). | Tail `lab/logs/opencode.log` after a cloud-provider start; grep for the saved token. Skip-test by default; flip to assert when log-redaction lands. | Sprint 1 deferred. **Decision: fold a partial fix in this sprint** — set `OPENCODE_DISABLE_AUTOUPDATE=true` and `OPENCODE_LOG_LEVEL=WARN` (env var probed in binary). Reduces log noise; doesn't fully redact. Full redaction (Sprint 1 F-SEC-4) deferred to Sprint 4+. |
| F-SEC-CRED-3 | `lab/.opencode/` accidentally committed to git. | Verify `.gitignore` covers `lab/` (the root `lab/` dir is ignored except whitelisted contracts; `.opencode/` is not whitelisted, so it's ignored). | One-line test: `git check-ignore lab/.opencode/opencode.json` returns 0 exit code. |
| F-SEC-CRED-4 | Shim `/api/openai/v1/chat/completions` echoes the token from `Authorization: Bearer ...` header into a log line. | Test `test_shim_does_not_log_authorization`: send `Authorization: Bearer SECRET-FAKE`; capture portal logs; assert no `SECRET-FAKE` substring. | Log only HTTP method, path, status, latency — never headers. (Mirrors the existing `/api/chat` posture.) |
| F-SEC-CRED-5 | Lab user's `~/.config/opencode/auth.json` (set up via `opencode auth`) leaks into the lab subprocess and overrides our keys. | Test (manual at kickoff): set `~/.config/opencode/auth.json` with a fake key; spawn lab opencode with `OPENCODE_CONFIG_DIR=lab/.opencode`; verify the lab key wins. | Per A1, `OPENCODE_CONFIG_DIR` is the override. **If verification fails**, also set `OPENCODE_DISABLE_PROJECT_CONFIG=true` and document. |
| **F-AIRGAP-1** | LAB_MODE=airgapped + Compute Source=my_machine + opencode running → opencode somehow contacts a cloud endpoint. | Test `test_airgap_shim_my_machine_only_loopback`: in airgapped mode, render config; assert `provider.lab-local.options.baseURL` is `http://127.0.0.1:*` AND no other provider entries exist. | The shim is loopback-only. The `enabled_providers: ["lab-local"]` lock prevents opencode from even trying any cloud provider. |
| F-AIRGAP-2 | LAB_MODE=airgapped but user has cloud-provider config in `lab/.opencode/opencode.json` from a previous hybrid session. | Test `test_airgap_regenerate_drops_cloud_providers`: stub `_lab_mode='airgapped'`; render config; assert no cloud providers listed. | `_render_opencode_config` consults `_lab_mode()` (lazy import or pass as param); when airgapped, force provider=my_machine regardless of `_load_active_provider()`. (The `providers_active` route already enforces this on switch — we just match its posture in the renderer.) |
| F-AIRGAP-3 | Provider switch in airgapped mode — should be rejected at the API layer; shim/config side should never see cloud. | Existing test in Sprint 1 covers the API rejection; new test asserts the renderer also defaults to my_machine in airgapped. | Defense-in-depth. |

## Test strategy

QA allocation per `arail/CLAUDE.md`: **30% setup / 30% Buddy / 20% security / 10% happy / 10% regression**. This sprint shifts that allocation: setup-heavy because of `--with-coder`, security-heavy because of provider-token paths in the shim/config layer.

### Unit tests

`tests/portal/test_openai_compat.py`:
- `test_models_endpoint_envelope` — shape `{"object":"list","data":[...]}` with at least one entry when `_scan_local_models` returns a model. (F-SHIM-1)
- `test_models_endpoint_owned_by` — every entry has `owned_by="arail-lab"`. (F-SHIM-1)
- `test_chat_non_stream_envelope` — full OpenAI shape with `usage`. (F-SHIM-2)
- `test_chat_stream_envelope` — round-trips through fake `_run_chat_completion_stream` emitting 3 deltas + final; assert SSE format with `[DONE]`. (F-SHIM-1)
- `test_chat_stream_first_chunk_includes_role` — first delta has `role:"assistant"`; subsequent omit. (F-SHIM-1)
- `test_chat_stream_yield_intervals` — instrument iterator; chunks emitted within ~50 ms of underlying source. (F-SHIM-8)
- `test_chat_messages_to_history_mapping` — system + user/assistant turns mapped correctly. (F-SHIM-3)
- `test_chat_strips_provider_prefix` — `model='lab-local/foo'` → backend sees `'foo'`. (F-SHIM-4)
- `test_chat_400_on_missing_messages` — 400 status, OpenAI error envelope. (F-SHIM-5)
- `test_chat_400_on_missing_model` — same.
- `test_chat_500_on_backend_exception` — backend raises → OpenAI error envelope, 500 status. (F-SHIM-5)
- `test_chat_cost_tracker_source_label` — `source='opencode'`. (F-SHIM-7)
- `test_chat_does_not_log_authorization_header` — capture logs, no token substring. (F-SEC-CRED-4)

`tests/portal/test_opencode_render_config.py`:
- `test_render_my_machine_airllm_golden` — golden against the canonical dict in §Interface (Sprint 1 + 2). (F-CONFIG-1)
- `test_render_my_machine_mlx_golden` — variant with `tools.reasoning=false`.
- `test_render_cloud_claude_golden` — `enabled_providers=["anthropic"]`, no apiKey field. (F-SEC-CRED-1)
- `test_render_no_token_in_plaintext_per_provider` — parametrized over claude/nvidia/openrouter/huggingface/custom; recognizable fake token in secrets, assert not in serialized JSON. (F-CONFIG-2, F-SEC-CRED-1)
- `test_render_six_slash_commands` — assert `command.lab-status / sprint-current / skills-list / agents-status / kb-search / claude-md` all present with non-empty `template` and `description`. (F-CONFIG-1)
- `test_render_command_paths_use_repo_root_var` — each command template uses `$REPO_ROOT/lab/...` or `lab/...`. (F-CONFIG-7)
- `test_render_includes_picker_hint_in_prompt` — `agent.build.prompt` mentions Chat-tab swap. (F-LOCK-1)
- `test_render_airgap_drops_cloud_providers` — `_lab_mode='airgapped'`, provider=claude → renderer falls back to my_machine. (F-AIRGAP-2)
- `test_render_deterministic` — same inputs → byte-identical JSON. (F-CONFIG-1)
- `test_render_includes_lab_tier_aware_prompt` — `tier='max'` mentions Workbench; `tier='min'` does not.

`tests/portal/test_opencode_llm_ready.py`:
- `test_llm_ready_my_machine_loaded` — `state='ready', model='Qwen-7B'` → ok=True. (F-GATE-1)
- `test_llm_ready_my_machine_no_model` — `state='ready', model=None` → ok=False, reason='no_llm'.
- `test_llm_ready_my_machine_loading` — `state='loading'` → ok=False, reason='loading'. (F-GATE-1)
- `test_llm_ready_my_machine_error` — `state='error'` → ok=False, reason='no_llm'.
- `test_llm_ready_cloud_with_token` — provider=claude, token saved → ok=True. (F-GATE-1)
- `test_llm_ready_cloud_no_token` — provider=claude, no token → ok=False, reason='no_token'. (F-GATE-1)
- `test_llm_ready_cache_invalidated_on_state_change` — call once, mutate state, call again with `force=False`, assert fresh result. (F-GATE-5)
- `test_llm_ready_cache_ttl_5s` — freeze time, call twice within TTL → cached; advance TTL → fresh.
- `test_llm_ready_never_raises_on_app_import_failure` — stub the lazy import to fail; assert returns `ok=False, reason='no_llm'` instead of raising.

`tests/portal/test_opencode_compute_source_env.py` (extends Sprint 1's):
- `test_compute_source_env_my_machine_points_at_shim` — `OPENCODE_API_BASE` ends with `/api/openai/v1` (NOT Ollama default). (UPDATED contract)
- `test_compute_source_env_cloud_sets_provider_env_var` — provider=claude, token='X' → env contains `ANTHROPIC_API_KEY='X'` AND `OPENCODE_API_KEY='X'`. (F-SEC-CRED-1)
- `test_compute_source_env_cloud_unknown_provider_falls_back` — unchanged from Sprint 1, but verify under new map.

### Integration tests

`tests/portal/test_opencode_routes.py` (extends Sprint 1's):
- `test_start_blocked_when_no_llm` — `state='ready', model=None` → POST /api/opencode/start returns 409 with `reason='no_llm'`. (F-GATE-1)
- `test_start_blocked_no_token_for_cloud` — cloud active, no token → 409 with `reason='no_token'`. (F-GATE-1)
- `test_start_blocked_includes_chat_url` — 409 body has `chat_url='/chat'`. (UI contract)
- `test_start_succeeds_with_loaded_model` — gate passes → start runs.
- `test_start_gate_after_tier_gate` — min-tier returns 404 (Sprint 1 still works); max + no_llm returns 409. (F-GATE-6)
- `test_notebooks_status_includes_llm_ready` — opencode entry has `llm_ready: bool`. (UI contract)
- `test_notebooks_status_llm_ready_flips_with_state` — toggle state, assert flip.

`tests/portal/test_opencode_config_lifecycle.py`:
- `test_start_writes_opencode_json_to_lab_scoped_dir` — start triggers config write at `lab/.opencode/opencode.json`. (F-CONFIG-3)
- `test_start_sets_OPENCODE_CONFIG_DIR_env` — Popen env contains `OPENCODE_CONFIG_DIR=<lab>/.opencode`. (A1)
- `test_config_dir_perms_0700` — after first write, dir mode is 0o700. (F-CONFIG-6)
- `test_regenerate_atomic_write` — kill mid-write, original file intact. (F-CONFIG-3)
- `test_regenerate_concurrent_calls_serialized` — 2 parallel calls; final file consistent. (F-CONFIG-4)
- `test_provider_switch_regenerates_then_restarts` — fake-running opencode + provider switch; assert regenerate called BEFORE restart, both within the lock. (F-RESTART-1, F-RESTART-3)
- `test_provider_switch_aborts_restart_on_config_failure` — stub regenerate to fail; assert restart NOT called. (F-RESTART-2)
- `test_provider_switch_skipped_when_opencode_not_running` — Sprint 1 invariant preserved. (F-RESTART-4)

### Setup tests

`tests/setup/test_with_coder_flag.py` (or shell-script smoke tests under `tests/scripts/`):
- `test_with_coder_mlx_branch` — `ACCEL=mlx ARAIL_WITH_CODER=1` → calls snapshot_download with `mlx-community/Qwen2.5-Coder-3B-Instruct-4bit`. (F-SETUP-1)
- `test_with_coder_cuda_branch` — same for CUDA.
- `test_with_coder_cpu_branch` — uses `huggingface-cli download ... --include 'Q4_K_M*'`.
- `test_with_coder_idempotent` — pre-existing target dir → no re-download. (F-SETUP-6)
- `test_with_coder_min_tier_warning` — LAB_TIER=min → warning logged, download proceeds. (F-SETUP-5, A11)
- `test_with_coder_default_off` — no flag → no download.
- `test_with_coder_partial_download_cleanup` — simulate failure, assert no dir or `.download-incomplete` marker. (F-SETUP-1)
- `test_pyproject_metadata_loads_coder_ids` — `load_pyproject_metadata()` reads `coder_mlx/coder_cuda/coder_cpu`. (F-SETUP-7)

### Security tests (consolidated, must-pass)

1. F-SEC-CRED-1 — `test_render_no_token_in_plaintext_per_provider` (5 providers).
2. F-SEC-CRED-1 — `test_subprocess_env_carries_provider_token`.
3. F-SEC-CRED-1 — `test_render_config_uses_env_reference_for_anthropic` (no `apiKey` in JSON).
4. F-SEC-CRED-3 — `lab/.opencode/` git-ignored.
5. F-SEC-CRED-4 — shim does not log Authorization header.
6. F-CONFIG-6 — `lab/.opencode/` 0700.
7. F-AIRGAP-1 — airgapped + my_machine → only loopback URL in config.
8. F-AIRGAP-2 — airgapped + (cloud-active state) → renderer drops cloud providers.

### Regression tests

- All Sprint 1 tests still pass (gate, no-credentials-in-iframe, hostname pinning, log rotation, provider-switch-doesn't-crash-on-restart-failure).
- `test_compute_source_env_cloud_unknown_provider_falls_back` — Sprint 1 invariant.
- `test_min_tier_no_side_effects_on_start` — Sprint 1's `test_min_tier_no_side_effects` still asserts the gate runs first.
- `test_existing_chat_route_unchanged` — `/api/chat` and `/api/chat/stream` still produce their existing NDJSON shape.
- `test_notebooks_status_existing_entries_unchanged` — first three entries (jupyter/marimo/open-notebook) shape unchanged. Sprint 1 regression test extended to also assert opencode entry has the NEW `llm_ready` field without breaking the others.

### Performance tests

Skipped — opencode is interactive. **One soft check:** `test_shim_stream_yield_intervals` (already listed under F-SHIM-8) covers the streaming-fanout latency budget.

### Live verification (post-merge, manual — recorded in TEST_REPORT.md)

1. Fresh `LAB_TIER=max ./arail upgrade max --with-coder` → confirm `lab/models/Qwen2.5-Coder-3B-Instruct-4bit` lands.
2. `./arail start` with no chat model loaded → Workbench card shows "needs LLM" with chat CTA.
3. Load Qwen2.5-Coder in Chat → opencode card flips to "installed-not-running" → click Start → opencode launches.
4. Inspect `lab/.opencode/opencode.json` → contains `enabled_providers:["lab-local"]`, six commands, no token strings.
5. Send `/lab-status` slash command in opencode TUI → templated prompt fires.
6. Switch chat model in Chat → opencode auto-regenerates config + restarts (~5–10s).
7. Switch provider to claude (with valid token in hybrid mode) → opencode restarts; `lab/.opencode/opencode.json` shows `provider.anthropic` with no token text; subprocess env (verifiable via `ps eww` on the opencode pid) contains `ANTHROPIC_API_KEY=...`.
8. Set `LAB_MODE=airgapped` → restart portal → `lab/.opencode/opencode.json` regenerates with my_machine only; cloud providers dropped.

## Tech debt

**Added:**

1. **The "shared chat-completions helper" framing in the plan was inaccurate.** No `/api/chat/completions` route exists; the existing `_run_chat_completion[_stream]` helpers ARE the shared core. The shim wraps them. Net: one new module file (`openai_compat.py`), no app.py extraction. This is a documentation-vs-reality drift the architect resolves here, not a code-level debt — but the plan should be updated post-sprint.

2. **`_render_opencode_config` is a fairly large pure function** (~150 LoC including the slash-command templates and system prompt). Split into smaller helpers if it grows further: `_render_provider_block`, `_render_commands`, `_render_agents`. Acceptable for v1.

3. **6 slash-command templates baked into the lab** vs deferable to a skill-pack ecosystem. **Decision: keep them baked in this sprint.** Rationale: they're the cold-start UX win — first-run users see useful commands immediately. Future: extract to `lab/pkb/skills/opencode-commands/` once Sprint 3 (Skills folded into Agents) lands and skills are first-class on min tier too. **Filed as Sprint 4+ tech debt.**

4. **Setup-script duplication between `setup.sh` and `upgrade.sh`** — both gain `download_coder_model`. Conscious choice (see §Setup). When a third caller appears (e.g. `./arail download <model>`), extract to `scripts/_lib_models.sh`.

5. **`OPENCODE_CONFIG_DIR` is a divergence from the user's personal opencode config.** If a user has been using opencode standalone, they have `~/.config/opencode/opencode.json` with their own settings (auth, models, customizations). The lab's `lab/.opencode/` is *additional*, not a replacement. The 4-state UI mentions this in the install hint copy. **Document in `docs/PRIVACY.md`** (folds into the Sprint 1 deferred PRIVACY.md item — see below).

6. **The shim does not implement OpenAI's full surface.** No `/embeddings`, `/audio`, `/images`, `/files`, `/assistants`. `chat/completions` and `models` only. Documented as "OpenAI-compat" with the *covered subset* spelled out in the module docstring. When opencode (or a future MCP client) needs a fuller surface, expand.

7. **Cost tracker has a new source label `'opencode'`.** The Dashboard's cost-by-source breakdown will need to know about it. **Defer to Sprint 3+** unless trivially adding the label to the existing display surfaces it. (Single grep on `source='ui'` in dashboard templates will find the call site.)

**Repaid:**

1. **Single OpenAI-compat surface.** Future MCP clients, Claude Desktop integrations, and qukaizen's teacher-inference path all get one entrypoint. Eliminates the "every consumer needs its own bridge" debt.

2. **AirLLM-via-shim eliminates the "you must run Ollama" punt** the plan called out as a Sprint 2 motivator. Lab's actual default backend works.

3. **LLM-ready gate removes the opaque-failure UX** Sprint 1 left. First-run feedback is grounded.

4. **Lab-scoped config dir prevents the user-personal-opencode-overlap risk** the plan called out as the locked-picker mitigation.

5. **CLAUDE.md-aware system prompt + slash commands** mean any future agent context (skill packs, KB search) can ride the same surface without re-architecting opencode integration.

**Net:** Slightly negative (the new module is bounded; the plan-vs-reality fix is a doc cleanup; the bigger debt items are explicitly deferred with named follow-up tickets).

### Sprint 1 follow-ups — fold-in decisions

| Item | Decision | Rationale |
|---|---|---|
| `/api/system/health` info-disclosure (INFO-1 from Sprint 1 QA) | **Defer to Sprint 3+.** | Cross-cutting; not opencode-specific. |
| PRIVACY.md trust-model paragraph | **Fold into this sprint.** | We're already adding `lab/.opencode/` posture; document the trust boundary while the context is hot. ~10 lines. |
| opencode version probe (F-INSTALL-2) | **Fold into this sprint.** | Schema drift (F-CONFIG-1) makes a version probe materially valuable. Builder adds `opencode --version` parse to `is_installed()` returning the version string in addition to the bool. |
| Token redaction in opencode logs (F-SEC-4) | **Partial fold-in.** | Set `OPENCODE_LOG_LEVEL=WARN` and `OPENCODE_DISABLE_AUTOUPDATE=true` to reduce log noise. Full redaction (Sprint 4+). |
| `os.setsid` cleanup (F-PROC-3) | **Defer to Sprint 3+.** | Orthogonal to this sprint's scope. |

## Recommended implementation order

1. **Builder kickoff probes** (verify before writing code):
   - Run `opencode --version` and confirm v1.14.x or later.
   - Run `OPENCODE_CONFIG_DIR=/tmp/probe-xyz/ opencode debug config print 2>&1 | head` (or similar). Confirm the env override is honored.
   - Confirm `enabled_providers` is the v1.14.x field name (read [opencode.ai/docs/config](https://opencode.ai/docs)).
   - Confirm `huggingface-cli` is on PATH on the dev host (or document the fallback).
   - Update SPRINT.md decisions log with `OPENCODE_CONFIG_DIR` (not `OPENCODE_CONFIG_HOME`) finding.

2. **`openai_compat.py` skeleton + unit tests.** All the F-SHIM-* tests green BEFORE wiring opencode. The module is tested in isolation against fake `_run_chat_completion[_stream]` mocks.

3. **Mount the shim in `app.py`.** One `from arail.portal.openai_compat import *` block alongside the existing `/api/chat` block.

4. **`_render_opencode_config()` + `lab_system_prompt()`** as pure functions in `services/opencode.py`. Golden-file tests for the 3 scenarios. F-CONFIG-2 and F-SEC-CRED-1 tests green.

5. **`llm_ready_check()` + cache.** F-GATE-* tests green.

6. **`regenerate_config()`** with atomic write, mode 0700 dir. F-CONFIG-3/4/6 green.

7. **Update `_compute_source_env()` and `start()` in `services/opencode.py`.** F-CONFIG-5 verified manually; integration tests for the new env wiring.

8. **Update `/api/opencode/start` route** to call `llm_ready_check` between `_require_workbench` and `oc.start`. Test for 409.

9. **Update `/api/notebooks/status`** to include `llm_ready` field.

10. **Update `providers_active` hook** with the regenerate-then-restart sequence. F-RESTART-* tests green.

11. **`opencode.html` 4-state UI + `notebooks.html` card status update.** UI tests for the 4-state DOM.

12. **`setup.sh` `--with-coder` branch + pyproject.toml model entries.** Script-level tests where possible; manual download verification on each platform. F-SETUP-* tests green.

13. **`scripts/upgrade.sh`** mirror of `--with-coder`. Defer the `_lib_models.sh` extraction.

14. **Sprint 1 follow-ups (folded):** opencode version probe; PRIVACY.md trust-model paragraph; `OPENCODE_LOG_LEVEL=WARN`/`OPENCODE_DISABLE_AUTOUPDATE=true` env adds.

15. **End-to-end live verification per §Test strategy.** Capture findings in BUILD_LOG.md.

16. **BUILD_LOG.md** documents: kickoff probe findings (especially the `OPENCODE_CONFIG_DIR` vs `OPENCODE_CONFIG_HOME` correction), any drift from this design, the deferred items.
