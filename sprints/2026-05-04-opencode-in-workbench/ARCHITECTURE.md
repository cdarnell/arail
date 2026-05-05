# Architecture: opencode in Workbench (Sprint 1)

**Date:** 2026-05-04
**Spec:** [SPRINT.md](./SPRINT.md) + approved plan at `~/.claude/plans/also-want-to-consider-synthetic-wreath.md`
**Product:** arail (max-tier surface)

---

## Restatement

We add `opencode` (sst/opencode, MIT, Go binary) as a fifth card on the
existing `notebooks` surface — concurrently renamed to **Workbench** in
the UI while the URL stays `/notebooks`. opencode is reached through a
new `/opencode` page (3-state: not-installed / installed-not-running /
running) that iframes the upstream opencode HTTP server (`opencode
serve`, default `127.0.0.1:4096`) **through a same-origin reverse
proxy** at `/opencode/proxy/{path:path}`. The proxy injects HTTP Basic
auth server-side from a per-install password persisted to
`lab/data/secrets.env`, so the credential never reaches the browser.
opencode inherits the lab's currently-active Compute Source via env
vars (`OPENCODE_API_BASE`, `OPENCODE_MODEL`, `OPENCODE_API_KEY`) wired
on `start()` and on every `/api/providers/active` switch (auto-restart).
The whole surface is gated max-only by piggybacking on the existing
`"notebooks" in _visible_surfaces()` check; a min-tier user gets `404`
on every `/opencode*` route and the Workbench tab itself is hidden in
nav.

## Assumptions

A1. **opencode HTTP transport is HTTP/1.1 + SSE only.** Plan flags WS
    as TBD. We design for SSE-only and document a contingency for WS
    (see Failure Mode F-PROXY-7). Builder must run
    `opencode serve --help` and grep the binary's docs at kickoff;
    if WS is used by any UI surface we proxy, switch to the
    contingency design before implementing the iframe.

A2. **opencode's HTTP server respects `--hostname 127.0.0.1`** and
    binds loopback only. We do NOT firewall it ourselves; loopback
    binding plus basic-auth is the perimeter.

A3. **opencode reads `OPENCODE_*` env vars at process start** (not
    per-request). This is why we restart the subprocess on Compute
    Source switch rather than push config.

A4. **Single-tenant lab.** Only one operator at a time uses opencode.
    No multi-user session isolation needed. Concurrent operators on
    the same lab is out of scope and would require a different auth
    model anyway.

A5. **`secrets.env` is the canonical secret store** and the existing
    `_read_secrets()` / `_write_secrets()` helpers maintain `chmod 0600`.
    `OPENCODE_SERVER_PASSWORD` lives there alongside provider tokens;
    it is *not* a "provider token" semantically but storing it there
    is consistent with the existing convention and avoids a second
    secrets file.

A6. **Process supervision is best-effort.** When the portal exits
    cleanly the opencode child is terminated; on portal crash the
    child is orphaned and the user must `./arail` start to reclaim
    port 4096. (Same as Jupyter today.) `os.setsid` is intentionally
    NOT used — see Tech Debt note.

A7. **`shutil.which("opencode")` returning truthy implies a usable
    binary.** Version-too-old detection is out of scope this sprint
    (see F-INSTALL-2 contingency); operator owns binary maintenance.

A8. **The portal process has write access to `lab/logs/`.** We will
    create the directory if missing.

A9. **`httpx` is acceptable as a runtime dep.** It's already used
    elsewhere in arail (verify with `grep -r "import httpx" src/`);
    if not we add it to `pyproject.toml`.

## Data flow

```
Operator browser
   │
   │  GET /opencode               (HTML 3-state page)
   │  GET /opencode/proxy/        (iframe src)
   │  POST /api/opencode/start    (button)
   │  POST /api/opencode/stop     (button)
   ▼
┌──────────────── ARAIL Portal (FastAPI, :8080) ─────────────────┐
│                                                                 │
│  Gate:  "notebooks" in _visible_surfaces()  →  404 if min       │
│                                                                 │
│  Route handlers                                                 │
│   ├─ /opencode               → render opencode.html             │
│   ├─ /api/opencode/start     → opencode.start()                 │
│   ├─ /api/opencode/stop      → opencode.stop()                  │
│   └─ /opencode/proxy/{path}  → reverse_proxy(request)           │
│                                                                 │
│  Hooks                                                          │
│   └─ /api/providers/active   → after env write, if              │
│                                opencode.is_running() then       │
│                                opencode.restart() (best-effort) │
│                                                                 │
│  Module: src/arail/portal/services/opencode.py                  │
│   ├─ is_installed() / is_running()                              │
│   ├─ start() → subprocess.Popen(env=_compute_source_env())      │
│   ├─ stop()  → lsof + kill                                      │
│   ├─ restart() → stop, wait_port_free, start, wait_healthy      │
│   ├─ _compute_source_env() → reads provider helpers             │
│   ├─ _server_password() → read-or-generate, chmod 0600          │
│   └─ reverse_proxy(request) → httpx.AsyncClient.stream          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
        │                                              │
        │  injects Authorization: Basic <b64>          │  reads secrets
        ▼                                              ▼
   opencode subprocess                          lab/data/secrets.env
   (loopback :4096, basic-auth)                  (chmod 0600)
        │
        │  OPENCODE_API_BASE / MODEL / API_KEY at process start
        ▼
   Active Compute Source (My Machine OpenAI-compat / cloud / custom)
```

Secrets flow (write-once):

```
first start() call
   │
   ├─ _server_password() → read secrets.env
   │     │
   │     ├─ if OPENCODE_SERVER_PASSWORD present → return it
   │     └─ else → secrets.token_urlsafe(32), persist via _write_secrets()
   │
   └─ env["OPENCODE_SERVER_PASSWORD"] = pw  →  Popen child inherits
   
reverse_proxy(request)
   │
   └─ headers["Authorization"] = "Basic " + b64("opencode:" + pw)
```

## Interface contracts

### Module `src/arail/portal/services/opencode.py`

All functions are pure-of-side-effects-on-import. Module imports must
not touch the filesystem, env, or spawn processes.

```python
PORT_DEFAULT: int = 4096
HOST: str = "127.0.0.1"
LOG_PATH = Path("lab/logs/opencode.log")
SECRETS_KEY = "OPENCODE_SERVER_PASSWORD"
BASIC_AUTH_USER = "opencode"   # opencode's docs say user is fixed; verify at kickoff

def is_installed() -> bool
    """True iff `shutil.which("opencode")` is truthy.
    Promises: never raises. No subprocess spawn.
    Bad input: n/a."""

async def is_running(port: int = PORT_DEFAULT) -> bool
    """TCP probe via existing _port_open(HOST, port). Sub-second.
    Promises: returns within ~300ms.
    Note: TCP-open does NOT mean opencode is *ready*. Use
    _wait_healthy() during start-up to disambiguate."""

def start(port: int = PORT_DEFAULT) -> dict
    """Spawn `opencode serve --port <port> --hostname 127.0.0.1`.
    Pre: is_installed() True. is_running(port) False.
    Post: returns {"ok": True, "pid": int} on success;
          {"ok": False, "error": str} on failure.
    Side effects: writes lab/logs/opencode.log (append),
                  may write secrets.env on first call.
    Env injected: see _compute_source_env() + OPENCODE_SERVER_PASSWORD.
    Bad input: if port already in use → {"ok": False, "error": "port busy"} (do not kill).
    Subprocess stdout/stderr → opencode.log; never returned in response body."""

def stop(port: int = PORT_DEFAULT) -> dict
    """Mirror notebook_stop at app.py:1191.
    `lsof -ti :<port>` then SIGTERM each pid; if any pid still
    listening after 2s, SIGKILL.
    Pre: none.
    Post: returns {"ok": True, "killed": [pid,...]}; never raises.
    Bad input: if `lsof` missing → {"ok": False, "error": "lsof unavailable"}."""

async def restart(port: int = PORT_DEFAULT) -> dict
    """Best-effort restart sequence:
       1. stop(port)
       2. wait up to 3.0s for port to be free (poll _port_open every 100ms)
       3. start(port)
       4. wait up to 10.0s for /healthz-equivalent to respond
    Returns {"ok": True} only after step 4 confirms readiness.
    On any timeout: {"ok": False, "error": "<phase>: <detail>"}.
    Caller (providers_active hook) must NOT block its own response on this — fire-and-forget via background task."""

def _compute_source_env() -> dict[str, str]
    """Translate active Compute Source → opencode env vars.
    Reads (no writes): _load_active_provider, _provider_token, _PROVIDER_META.
    Returns env-var dict suitable for merging into os.environ for Popen.
    
    Mapping rules:
      provider == 'my_machine':
        OPENCODE_API_BASE = os.getenv('MODEL_API_BASE') or 'http://127.0.0.1:11434/v1'
        OPENCODE_MODEL    = os.getenv('MODEL_NAME', '')   # may be empty; opencode picks default
        OPENCODE_API_KEY  = 'not-needed'                  # opencode requires non-empty
      provider in _CLOUD_PROVIDERS:
        OPENCODE_API_BASE = _PROVIDER_META[provider]['base']
                            (or for 'custom': os.getenv('MODEL_API_BASE'))
        OPENCODE_MODEL    = os.getenv('MODEL_NAME', '')
        OPENCODE_API_KEY  = _provider_token(provider)     # may be ''
    
    Bad input: unknown provider → falls back to my_machine mapping (matches _load_active_provider's own fallback at app.py:902).
    
    Never logs token values. Returns dict; logging boundary is the caller's responsibility (caller MUST not log this dict)."""

def _server_password() -> str
    """Lazy-create. Read `OPENCODE_SERVER_PASSWORD` from
    _read_secrets(); if absent, generate via secrets.token_urlsafe(32)
    and persist via _write_secrets() (which sets chmod 0600).
    Returns the password.
    Promises: idempotent across calls within a process; never logged;
              never appears in any HTTP response body."""

def install_hint() -> dict
    """Return {'platform': 'darwin'|'linux'|'wsl'|'windows'|'other',
               'command': str,
               'docs_url': str}.
    Pure: reads platform.system() + os.uname() only. No I/O."""

async def reverse_proxy(request: Request, path: str) -> Response
    """Forward an HTTP request to opencode at HOST:PORT_DEFAULT/<path>.
    
    Header rules:
      Drop from request:    Host, Content-Length, Connection,
                            Transfer-Encoding, Upgrade, Authorization
                            (any client-supplied auth is stripped)
      Inject:               Authorization: Basic b64('opencode:' + pw)
      Forward all others.
    
    Body: streamed both ways (do NOT buffer; opencode SSE responses
    may be unbounded).
    
    Response:
      Status:   echo upstream
      Headers:  echo upstream MINUS Connection, Transfer-Encoding,
                Content-Length (FastAPI sets these)
      Media:    echo upstream Content-Type
      Body:     StreamingResponse over httpx.aiter_raw()
    
    Errors:
      ConnectError (opencode down)        → 502 'opencode not running'
      TimeoutException (>30s headers)     → 504 'opencode timeout'
      Other httpx.HTTPError               → 502 with sanitized message
                                            (NEVER include req body or auth header)
    
    Pre:  caller has gated on `"notebooks" in _visible_surfaces()`.
    Post: never echoes BASIC_AUTH password into response body or headers."""
```

### FastAPI route gate

Single source of truth — define once, decorate four routes:

```python
def _require_workbench():
    """Dependency. Raises HTTPException(404) on min tier.
    404 (not 403) so route existence isn't disclosed."""
    if "notebooks" not in _visible_surfaces():
        raise HTTPException(status_code=404, detail="Not found")

# usage
@app.get("/opencode", response_class=HTMLResponse,
         dependencies=[Depends(_require_workbench)])
async def opencode_page(request: Request): ...
```

The dependency runs **before** the handler body — short-circuits before
any logging, any body parse, any subprocess. Builder MUST verify this
ordering with a test that asserts no log line is emitted on a min-tier
404.

### Compute Source hook (in `app.py`)

Modify `providers_active` (line 997). After `os.environ["COMPUTE_SOURCE"] = provider`:

```python
# Trigger best-effort opencode restart so the new baseURL is picked up.
# Does NOT block the response — restart can take 5-10s.
if "notebooks" in _visible_surfaces():
    try:
        from arail.portal.services import opencode as oc
        if await oc.is_running():
            asyncio.create_task(oc.restart())  # fire-and-forget
    except Exception:
        pass  # provider switch must succeed even if restart wiring breaks
```

The provider switch returns success regardless of restart outcome.
In-flight opencode sessions get a connection drop and reconnect — this
is documented in `opencode.html` UI text, not handled by code.

### `/api/notebooks/status` shape extension

Append the fifth entry (mirrors existing entries):

```python
{
    "id": "opencode",
    "name": "opencode",
    "installed": opencode.is_installed(),
    "alive": opencode_alive,           # _port_open(bind, 4096)
    "url_internal": "/opencode",
    # NB: NO url_external — direct access would expose basic-auth.
    #     The frontend MUST NOT render an external link for opencode.
}
```

`url_external` is intentionally absent. Builder MUST NOT add one.

### System health probe extension (line 5846 / 6056)

Add to the parallel `asyncio.gather`:

```python
opencode_port = int(os.getenv("OPENCODE_PORT", "4096"))
# ... add to gather ...
opencode_up = await _port_open(bind, opencode_port)
# ... in optional_services ...
"opencode": opencode_up,
```

`opencode_up` follows the existing "hide when down" optional-services
pattern.

## Failure modes

| ID | Failure | Detection | Recovery |
|---|---|---|---|
| F-GATE-1 | min-tier user discovers `/opencode*` route | Test: GET `/opencode` with `LAB_TIER=min` returns 404 | Dependency `_require_workbench` short-circuits with 404 (not 403) — route existence not disclosed |
| F-GATE-2 | Gate added to 3 of 4 routes (forgot proxy) | Test: parametrize over all four paths | Single `Depends(_require_workbench)` defined once; review checks usage on every `/opencode*` decorator |
| F-GATE-3 | Side effect runs before gate (logging body, reading secrets) | Test: assert no `activity_log.emit` and no secrets read on min-tier 404 | FastAPI dependency runs before handler body; do NOT log inside `_require_workbench` |
| F-SEC-1 | Basic-auth password leaks into HTML response | Test: grep `secrets.env`'s `OPENCODE_SERVER_PASSWORD` value across every endpoint's response body | password never templated; only flows through `reverse_proxy` headers |
| F-SEC-2 | Password leaks into log line | Test: capture logs during start/stop/restart/proxy and grep for the value | log only `pid`, `port`, `provider`; opencode subprocess stdout goes to file, not portal logger |
| F-SEC-3 | Password appears in `/api/notebooks/status` or `/api/system/health` | Test: assert payload does not contain it | only `id/name/installed/alive/url_internal` exposed |
| F-SEC-4 | Client-supplied `Authorization` header overrides ours | Test: send proxy request with `Authorization: Bearer attacker` and confirm server still injects basic-auth | `reverse_proxy` strips inbound `Authorization` BEFORE injecting |
| F-SEC-5 | Path traversal in `/opencode/proxy/../something-internal` | Test: `/opencode/proxy/../api/system/health` must hit the proxy and 404/502, not the portal route | FastAPI `{path:path}` matches literally; we forward to `127.0.0.1:4096/<path>` so `..` is upstream's problem (and opencode loopback-binds, so worst case is a 404 from opencode) |
| F-SEC-6 | Provider token leaks into opencode subprocess logs | Test: tail `lab/logs/opencode.log` after start, grep for any saved token value | opencode controls its own logging; we accept it may log API key on its own — document, do NOT block. (Sprint 2 follow-up: redact.) |
| F-SEC-7 | LAB_MODE=airgapped + cloud Compute Source = leak path | Test: in airgapped mode, `_compute_source_env()` returns my_machine vars even if env var COMPUTE_SOURCE was set externally | `_load_active_provider` does NOT enforce airgapped; `providers_active` does. We ride that gate — if user manually sets `COMPUTE_SOURCE=claude` env, opencode will use it. Acceptable: airgapped is enforced at the API switching layer, not the env-read layer. Document. |
| F-PROXY-1 | opencode not running, proxy returns 500 with stack trace | Test: stop opencode, GET `/opencode/proxy/health` → 502 with clean message | Catch `httpx.ConnectError` → 502 |
| F-PROXY-2 | SSE stream buffers in proxy, breaking incremental render | Test: fake upstream emits chunked `text/event-stream`; assert chunks arrive in real time | Use `client.stream()` + `StreamingResponse` over `aiter_raw()`; do NOT call `.text` or `.json` |
| F-PROXY-3 | `Content-Length` mismatch from re-encoding | Test: response with explicit Content-Length round-trips | Strip `Content-Length` from upstream response headers; let Starlette set it (or use chunked) |
| F-PROXY-4 | Hop-by-hop headers leak (`Connection`, `Keep-Alive`, `Transfer-Encoding`, `Upgrade`) | Test: response inspection | Drop the hop-by-hop set on both directions |
| F-PROXY-5 | Long-lived SSE hits 30s timeout | Test: SSE stream past 30s | `httpx.Timeout(connect=5.0, read=None, write=10.0, pool=5.0)` — `read=None` for SSE |
| F-PROXY-6 | Request body buffered into RAM (large file upload through proxy) | Test: 10MB POST | Stream request body via `request.stream()` into `httpx` `content=` async generator |
| F-PROXY-7 | opencode uses WebSockets (Assumption A1 wrong) | Detection at kickoff: `opencode serve --help` and `curl /doc` for `ws://` references | Contingency: add second handler using `starlette.WebSocketRoute`; bridge via `httpx_ws` or `websockets` lib. NOT in scope this sprint unless detection at kickoff confirms WS is required for the iframe to function. If confirmed, builder STOPS and re-engages architect. |
| F-PROC-1 | `start()` succeeds but opencode crashes 200ms later | Test: spawn fake binary that exits immediately; assert `restart()` returns error within 10s | `restart()` waits for healthz; on timeout returns error and the 3-state UI surfaces "installed-not-running" |
| F-PROC-2 | Port 4096 occupied by something else | Test: bind a socket on 4096, call `start()`; expect `{"ok": False, "error": "port busy"}` | Pre-check via `_port_open` before Popen; do NOT kill foreign process |
| F-PROC-3 | Portal SIGTERM doesn't reach opencode child | Manual test: kill portal, check `lsof -ti :4096` | Documented limitation. Operator runs `./arail` start which calls `stop()` first; or `./arail opencode stop`. NOT using `os.setsid` — see Tech Debt. |
| F-PROC-4 | `stop()` race when called twice in parallel (concurrent restart) | Test: two `restart()` calls concurrent | Module-level `asyncio.Lock` guards start/stop/restart |
| F-PROC-5 | `lab/logs/` does not exist | First `start()` mkdir | `LOG_PATH.parent.mkdir(parents=True, exist_ok=True)` before opening log |
| F-PROC-6 | `opencode.log` grows unbounded | n/a (manual rotation) | Cap log file at 10MB via simple rotation: on start, if size > 10MB, rename to `opencode.log.1` (overwrite). Single-file rotation is enough for a dev surface. |
| F-RESTART-1 | Compute Source switch fails because opencode restart fails | Test: stub `restart` to raise; switch still returns ok | Restart is fire-and-forget `asyncio.create_task` wrapped in try/except |
| F-RESTART-2 | New env not picked up because `start()` reads stale env | Test: switch provider, verify new `Popen` env contains new vars | `start()` always calls `_compute_source_env()` fresh — no caching |
| F-RESTART-3 | Restart leaves orphan child if `stop()` partial-fails | Test: simulate `kill` failure on one of two pids | After `stop()`, poll port up to 3s; if still bound, return error and do NOT call `start()` |
| F-INSTALL-1 | Operator installs opencode AFTER portal start | UI re-detects on every `/opencode` page load (no caching) | `is_installed()` is a fresh `shutil.which` each call |
| F-INSTALL-2 | opencode binary present but too old (no `serve` subcommand) | Out of scope this sprint | Documented limitation. If `start()` fails because subcommand missing, the subprocess error surfaces in `opencode.log` and the 3-state page shows "not-running". Operator updates manually. (Sprint 2 follow-up: version probe.) |
| F-INSTALL-3 | Wrong platform install hint (e.g. Linux command on macOS) | Test: stub `platform.system()` over each value | `install_hint()` matches existing `scripts/setup.sh` platform detection |
| F-CONFIG-1 | `MODEL_API_BASE` unset on my_machine, opencode can't reach anything | Test: clear env, call `_compute_source_env()`, assert sane fallback | Default to `http://127.0.0.1:11434/v1` (Ollama default — most common local) |
| F-CONFIG-2 | `_provider_token` returns empty for active cloud provider | Test: cloud provider active, no saved token; assert `OPENCODE_API_KEY=''` not crash | Pass empty string; opencode will fail its own auth and surface the error in its UI. We do NOT block start — operator may have set the key via OS env outside `secrets.env`. |
| F-CONFIG-3 | Two parallel `start()` calls → two subprocesses | Same lock as F-PROC-4 | `asyncio.Lock` |

Every row above has a corresponding test in §Test strategy. If a row
has no test, it does not exist.

## Test strategy

QA allocation per arail/CLAUDE.md is 30% setup / 30% Buddy / 20%
security / 10% happy / 10% regression. Security is elevated this
sprint — treat as 30% security / 25% setup / 15% Buddy-equivalent
(opencode usability through proxy) / 15% happy / 15% regression.

### Unit tests (in this sprint)

`tests/portal/test_opencode_service.py`:

- `test_install_hint_per_platform` — parametrized over `darwin`,
  `linux`, `wsl`, `windows`; verify command + docs_url. (F-INSTALL-3)
- `test_compute_source_env_my_machine` — set `COMPUTE_SOURCE=my_machine`,
  set `MODEL_API_BASE`, set `MODEL_NAME`; assert dict shape.
  (F-CONFIG-1)
- `test_compute_source_env_my_machine_default_base` — clear
  `MODEL_API_BASE`; assert fallback to `http://127.0.0.1:11434/v1`.
- `test_compute_source_env_cloud_claude` — set provider claude with
  saved token; assert `OPENCODE_API_BASE='https://api.anthropic.com/v1'`
  and `OPENCODE_API_KEY=<token>`. (F-CONFIG-2)
- `test_compute_source_env_cloud_no_token` — provider with empty
  token; assert env returned with empty key (not crash). (F-CONFIG-2)
- `test_server_password_generates_once` — call twice, assert same
  value, assert secrets.env has it, assert mode 0600. (lifecycle)
- `test_server_password_reads_existing` — pre-seed secrets.env,
  assert `_server_password` returns the existing value (no rotation).
- `test_compute_source_env_never_logged` — capture logs across all
  `_compute_source_env` paths, assert no token value present. (F-SEC-2)

### Integration tests (in this sprint)

`tests/portal/test_opencode_routes.py`:

- `test_min_tier_404_all_four_routes` — parametrized over `GET
  /opencode`, `POST /api/opencode/start`, `POST /api/opencode/stop`,
  `GET /opencode/proxy/anything`; with `LAB_TIER=min`, all 404.
  (F-GATE-1, F-GATE-2)
- `test_min_tier_no_side_effects` — assert no `activity_log` entries
  written and no `secrets.env` reads when min-tier route 404s.
  (F-GATE-3) — implementation: stub `_read_secrets` and assert
  not called.
- `test_max_tier_page_renders_when_not_installed` — `LAB_TIER=max`,
  stub `is_installed=False`, GET `/opencode`, assert install hint
  in HTML.
- `test_status_includes_opencode_entry` — `/api/notebooks/status`
  fifth entry shape.
- `test_status_does_not_leak_password` — assert
  `OPENCODE_SERVER_PASSWORD` value not present in payload. (F-SEC-3)
- `test_health_includes_opencode` — `/api/system/health`
  optional_services contains `opencode` only when up.

`tests/portal/test_opencode_proxy.py` (uses a local fake upstream):

- `test_proxy_forwards_get` — fake upstream echoes path; proxy
  returns body unchanged.
- `test_proxy_injects_basic_auth` — fake upstream asserts on
  inbound `Authorization` header equal to expected basic-auth.
  (F-SEC-1)
- `test_proxy_strips_client_authorization` — request includes
  `Authorization: Bearer attacker`; fake upstream sees ours not theirs.
  (F-SEC-4)
- `test_proxy_streams_sse` — fake upstream sends 5 chunks of
  `text/event-stream` with 100ms gaps; assert client receives them
  in order with sub-200ms latency per chunk (NOT all at end).
  (F-PROXY-2)
- `test_proxy_502_when_upstream_down` — no server running on 4096;
  GET proxy → 502 with clean body (no stack trace, no password).
  (F-PROXY-1)
- `test_proxy_drops_hop_by_hop` — fake upstream returns
  `Connection: close, Transfer-Encoding: chunked, Keep-Alive: 1`;
  assert response to client does NOT include them. (F-PROXY-4)
- `test_proxy_streams_request_body` — POST 5MB body; assert proxy
  does not buffer (memory check or chunk-arrival timing on fake
  upstream). (F-PROXY-6)
- `test_proxy_path_traversal_does_not_hit_portal` — GET
  `/opencode/proxy/../../api/system/health` → does not return
  the portal's health response; goes to opencode (502 if down or
  404 from opencode). (F-SEC-5)

### Lifecycle tests (in this sprint)

`tests/portal/test_opencode_lifecycle.py`:

- `test_start_returns_error_if_port_busy` — bind a socket on 4096,
  call `start()`. (F-PROC-2)
- `test_restart_after_provider_switch` — stub `is_running=True`;
  POST `/api/providers/active` with new provider; assert
  `restart()` was scheduled (mock) and the response did NOT block
  on it. (F-RESTART-1)
- `test_restart_picks_up_new_env` — stub `_compute_source_env` to
  return value A then B; full restart cycle; assert second `Popen`
  was called with B. (F-RESTART-2)
- `test_concurrent_restart_serializes` — two `restart()` coroutines
  parallel; assert lock prevents overlap. (F-PROC-4)
- `test_provider_switch_succeeds_when_restart_fails` — stub
  `restart` to raise; switch still returns `{"ok": True}`.
  (F-RESTART-1)
- `test_log_rotation_at_10mb` — pre-seed log file > 10MB;
  `start()` rotates to `.log.1`. (F-PROC-6)

### Regression tests (in this sprint)

- `test_existing_notebooks_status_unchanged_for_first_three` —
  assert jupyter/marimo/open-notebook entries unchanged shape.
- `test_workbench_label_in_nav_template` — render `_nav.html`
  with `notebooks` in surfaces; assert text "Workbench" not
  "Notebooks". (UI rename safety)

### Performance tests (this sprint)

Skipped — opencode is interactive, not throughput. Spot-check
during QA: SSE chunk arrival latency < 200ms in
`test_proxy_streams_sse` is the closest thing.

### Security tests (consolidated, in this sprint)

The proxy + auth-injection pattern is novel for this codebase.
Required must-pass:

1. F-GATE-1 / F-GATE-2 / F-GATE-3 — min-tier never sees the surface.
2. F-SEC-1 / F-SEC-2 / F-SEC-3 — password never leaks (HTML, logs,
   status JSON).
3. F-SEC-4 — client `Authorization` header stripped before injection.
4. F-SEC-5 — path traversal does not escape the proxy boundary.

### Deferred to Sprint 2 / follow-up

- Version probe (F-INSTALL-2): opencode binary too old.
- Provider token redaction in opencode's own logs (F-SEC-6): out of
  our control; document as "opencode controls its own logging."
- WebSocket proxy (F-PROXY-7): only if kickoff confirms WS needed.
- `os.setsid` process group cleanup (F-PROC-3).
- "Skills folded into Agents" entire scope (Sprint 2 of the plan).

## Tech debt

**Added:**

1. **Reverse-proxy pattern is new for this codebase.** Future surfaces
   (Jupyter, Marimo, Open-Notebook) currently iframe `127.0.0.1:<port>`
   directly with token-in-URL. If we decide token-in-URL is unsafe for
   any of them, we now have a template to migrate to. Cost: ~40 lines
   of httpx streaming per surface. Worth ticketing as a follow-up
   audit.
2. **`opencode.log` rotation is single-file (10MB cap).** Cheap, fine
   for a dev surface. If opencode logs get noisy or operators want
   history, swap for `logging.handlers.RotatingFileHandler`.
3. **No process supervision on portal crash (F-PROC-3).** Orphans
   the opencode child, occupying port 4096. Same shape as Jupyter
   today. Acceptable for v1; document in TROUBLESHOOTING.md as
   `lsof -ti :4096 | xargs kill`.
4. **`agents.html` size pressure.** Out of scope this sprint, but
   Sprint 2 will balloon it past 1500 lines. Architect note for
   Sprint 2: extract `_skills_panel.html` BEFORE merging logic.
5. **Provider token visible to opencode subprocess** via env. Opencode
   may log it (F-SEC-6). Out of our control; document.

**Repaid:**

1. **Provider helper extraction (`providers.py`)** — the plan
   suggests this as optional. **Decision: defer.** Doing it now
   inflates this sprint's diff and risks breaking the chat-tab
   surface. The `services/opencode.py` module imports from `app.py`
   directly (acceptable: app.py is the canonical source).
   Follow-up ticket recommended after Sprint 2 ships.
2. **Workbench rename clarifies the tab's purpose** for future
   surfaces. Naming debt repaid.

**Net:** Slightly positive (more added than repaid). Acceptable
because items 1, 2, 3, 5 are documented and ticket-able; item 4
is a cross-sprint warning, not new debt.

## Recommended implementation order

1. **Kickoff probe (BUILDER MUST DO FIRST)**: install opencode
   locally, run `opencode serve --help` and `curl
   http://127.0.0.1:4096/doc` after start. Confirm:
   - basic-auth user is `opencode` (assumption A2.5; adjust
     `BASIC_AUTH_USER` constant if wrong)
   - no WebSocket endpoints used by the iframe UI (F-PROXY-7)
   - `--port` and `--hostname` flags exist
   - readiness endpoint name (assumed `/healthz`; may be `/health`
     or `/doc`)

   If WS is required: STOP and re-engage architect for F-PROXY-7
   contingency. Otherwise, document findings in BUILD_LOG.md
   §Kickoff Probe and proceed.

2. **`services/opencode.py` skeleton + unit tests** — every helper
   except `reverse_proxy`. Get `_compute_source_env`,
   `_server_password`, `install_hint`, `start/stop/restart` green.

3. **Route registration with gate** — `_require_workbench`
   dependency, four routes; `min_tier_404` tests pass.

4. **`reverse_proxy` + proxy tests** — fake upstream fixture (FastAPI
   app on a random port); SSE + auth tests pass.

5. **`/api/notebooks/status` extension + frontend wiring** —
   `notebooks.html` fifth card; Workbench rename in `_nav.html`
   and template heading.

6. **`/api/system/health` extension** — `opencode` in
   optional_services.

7. **`providers_active` hook** — fire-and-forget restart;
   `test_restart_after_provider_switch` passes.

8. **Manual verification** per plan checklist + `pytest tests/portal/`
   green.

9. **BUILD_LOG.md** — record kickoff probe findings, any deviations,
   and the actual line numbers touched (plan estimates may have
   drifted).
