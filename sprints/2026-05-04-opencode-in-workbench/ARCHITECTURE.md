# Architecture: opencode in Workbench (Sprint 1) — REVISED

**Date:** 2026-05-04 (revised after kickoff probes)
**Spec:** [SPRINT.md](./SPRINT.md) + approved plan at `~/.claude/plans/also-want-to-consider-synthetic-wreath.md`
**Product:** arail (max-tier surface)
**Supersedes:** initial design at commit 55c7dde (reverse-proxy approach abandoned — see §Decision)

---

## Decision: Path A — direct iframe to 127.0.0.1:4096

The original design used a same-origin reverse proxy at `/opencode/proxy/{path:path}`
to inject HTTP Basic auth server-side. Kickoff probes invalidated that path:

1. **opencode ships a single-page web UI at `/` with a strict CSP**
   (`default-src 'self'`) and **root-absolute asset paths**
   (`/favicon-96x96-v3.png`, `/site.webmanifest`, presumably `/assets/*.js`
   for the SPA bundle). Reverse-proxying at `/opencode/proxy/` means the
   browser would request `/favicon-96x96-v3.png` (root-absolute) which hits
   the Flask portal — 404 — and CSP `default-src 'self'` forbids loading
   from any other origin. The web UI breaks.
2. Workarounds (HTML rewriting to inject `<base href="/opencode/proxy/">`,
   path rewriting in JS) cannot reach the SPA's in-app `fetch()` calls
   without modifying the upstream SPA bundle. Service Worker injection is
   overkill.
3. **Inconsistent threat model.** The lab already iframes Jupyter
   (`127.0.0.1:8888?token=…`), Marimo (`127.0.0.1:2718?access_token=…`),
   and Open Notebook (`127.0.0.1:8502`) directly. All three have
   equivalent arbitrary-code-execution capability to opencode (Jupyter
   notebooks can `os.system`, Marimo runs arbitrary Python). Applying a
   stricter perimeter to opencode is security theater unless we also
   migrate the others — which is explicitly out of scope.
4. **The lab's actual trust boundary is "you have local access to
   `127.0.0.1` on the lab host."** Anyone who can reach `127.0.0.1:4096`
   already has shell on the lab host and can run `opencode` directly.
   Defense-in-depth via basic-auth at this boundary buys little, costs
   the proxy-rewriting work above, and creates a one-off pattern.

**Decision:** drop the reverse proxy entirely. opencode binds
`127.0.0.1` only and is iframed directly. **Do NOT set
`OPENCODE_SERVER_PASSWORD`.** Treat opencode like Jupyter/Marimo. The
trust-model statement ("127.0.0.1 = trusted") is documented in
PRIVACY.md as a follow-up sprint.

---

## Restatement

We add `opencode` (sst/opencode, MIT, Go binary) as a fifth card on the
existing `notebooks` surface — concurrently renamed to **Workbench** in
the UI while the URL stays `/notebooks`. opencode is reached through a
new `/opencode` page (3-state: not-installed / installed-not-running /
running) that **iframes `http://127.0.0.1:4096/` directly**, matching
the existing pattern for Jupyter/Marimo/Open-Notebook. opencode
inherits the lab's currently-active Compute Source via env vars
(`OPENCODE_API_BASE`, `OPENCODE_MODEL`, `OPENCODE_API_KEY`) wired on
`start()` and on every `/api/providers/active` switch (auto-restart).
The whole surface is gated max-only by piggybacking on the existing
`"notebooks" in _visible_surfaces()` check; a min-tier user gets `404`
on every `/opencode*` route and the Workbench tab itself is hidden in
nav.

## Assumptions

A1. **opencode HTTP server respects `--port 4096 --hostname 127.0.0.1`.**
    Confirmed at kickoff: `opencode serve --help` shows both flags.
    Note: opencode's default `--port` is `0` (OS-assigned). We MUST
    pass `--port 4096` (or `--port $OPENCODE_PORT`) explicitly; relying
    on a default port is wrong.

A2. **opencode binds loopback when `--hostname 127.0.0.1` passed.**
    We do NOT firewall it ourselves; loopback binding is the perimeter,
    matching Jupyter/Marimo/Open-Notebook.

A3. **opencode reads `OPENCODE_*` env vars at process start** (not
    per-request). This is why we restart the subprocess on Compute
    Source switch rather than push config.

A4. **Single-tenant lab.** Only one operator at a time uses opencode.
    No multi-user session isolation needed.

A5. **`secrets.env` remains the canonical secret store** for provider
    tokens. `OPENCODE_SERVER_PASSWORD` is NOT stored — see Decision.
    If a future sprint adds it, the existing `_read_secrets()` /
    `_write_secrets()` helpers maintain `chmod 0600`.

A6. **Process supervision is best-effort.** When the portal exits
    cleanly the opencode child is terminated; on portal crash the
    child is orphaned and the user must `./arail` start to reclaim
    port 4096. (Same as Jupyter today.) `os.setsid` is intentionally
    NOT used — see Tech Debt.

A7. **`shutil.which("opencode")` returning truthy implies a usable
    binary.** Confirmed at kickoff: `/opt/homebrew/bin/opencode`
    version 1.14.31 on the dev host. Version-too-old detection is
    out of scope (see F-INSTALL-2 contingency).

A8. **The portal process has write access to `lab/logs/`.** We will
    create the directory if missing.

A9. **Readiness probe is `GET /doc`** — the OpenAPI JSON endpoint.
    There is NO `/healthz`. Confirmed at kickoff: the only documented
    operations are `PUT /auth/{providerID}`, `DELETE /auth/{providerID}`,
    `POST /log`. `/doc` returns 200 with `application/json` (the OpenAPI
    spec). `/` returns 200 with the SPA HTML; we choose `/doc` because
    it's smaller and unambiguous.

A10. **`requests` (already in `pyproject.toml`) is sufficient.** With
    the proxy gone, no streaming HTTP-client work is needed inside the
    portal; the readiness probe is one short GET. No `httpx` add.

## Data flow

```
Operator browser
   │
   │  GET /opencode               (HTML 3-state page)
   │  POST /api/opencode/start    (button)
   │  POST /api/opencode/stop     (button)
   │
   │  iframe src="http://127.0.0.1:4096/"   ──────────────┐
   ▼                                                       │
┌──────────────── ARAIL Portal (Flask, :8080) ──────────┐  │
│                                                        │  │
│  Gate:  "notebooks" in _visible_surfaces()  →  404    │  │
│                                                        │  │
│  Route handlers                                        │  │
│   ├─ /opencode               → render opencode.html    │  │
│   ├─ /api/opencode/start     → opencode.start()        │  │
│   └─ /api/opencode/stop      → opencode.stop()         │  │
│                                                        │  │
│  Hooks                                                 │  │
│   └─ /api/providers/active   → after env write, if     │  │
│                                opencode.is_running()   │  │
│                                then opencode.restart() │  │
│                                                        │  │
│  Module: src/arail/portal/services/opencode.py         │  │
│   ├─ is_installed() / is_running()                     │  │
│   ├─ start() → subprocess.Popen(env=...)               │  │
│   ├─ stop()  → lsof + kill                             │  │
│   ├─ restart() → stop, wait_port_free, start, ready    │  │
│   ├─ _compute_source_env() → reads provider helpers    │  │
│   └─ install_hint()                                    │  │
└────────────────────────────────────────────────────────┘  │
                       │                                    │
                       ▼                                    │
                  opencode subprocess  ◄────────────────────┘
                  (loopback :4096, no auth — same as Jupyter)
                       │
                       │  OPENCODE_API_BASE / MODEL / API_KEY
                       ▼
                  Active Compute Source
                  (My Machine OpenAI-compat / cloud / custom)
```

The browser talks to **two origins**: `http://127.0.0.1:8080` (portal)
for the page chrome and control buttons, and `http://127.0.0.1:4096`
(opencode) inside the iframe. Same pattern as Jupyter/Marimo today.

## Interface contracts

### Module `src/arail/portal/services/opencode.py`

All functions are pure-of-side-effects-on-import. Module imports must
not touch the filesystem, env, or spawn processes.

```python
PORT_DEFAULT: int = 4096
HOST: str = "127.0.0.1"
LOG_PATH = Path("lab/logs/opencode.log")
READINESS_PATH: str = "/doc"   # GET 200 means opencode is ready

def is_installed() -> bool
    """True iff `shutil.which("opencode")` is truthy.
    Promises: never raises. No subprocess spawn.
    Bad input: n/a."""

def is_running(port: int = PORT_DEFAULT) -> bool
    """TCP probe via existing _port_open(HOST, port). Sub-second.
    Promises: returns within ~300ms.
    Note: TCP-open does NOT mean opencode is *ready*. Use
    _wait_ready() during start-up to disambiguate."""

def start(port: int = PORT_DEFAULT) -> dict
    """Spawn `opencode serve --port <port> --hostname 127.0.0.1`.
       Note: `--port` is REQUIRED — opencode's default is 0 (OS-assigned).
    Pre: is_installed() True. is_running(port) False.
    Post: returns {"ok": True, "pid": int} on success;
          {"ok": False, "error": str} on failure.
    Side effects: writes lab/logs/opencode.log (append).
    Env injected: see _compute_source_env(). NO OPENCODE_SERVER_PASSWORD
                  (see §Decision).
    Bad input: if port already in use → {"ok": False, "error": "port busy"} (do not kill).
    Subprocess stdout/stderr → opencode.log; never returned in response body."""

def stop(port: int = PORT_DEFAULT) -> dict
    """Mirror notebook_stop at app.py:1191.
    `lsof -ti :<port>` then SIGTERM each pid; if any pid still
    listening after 2s, SIGKILL.
    Pre: none.
    Post: returns {"ok": True, "killed": [pid,...]}; never raises.
    Bad input: if `lsof` missing → {"ok": False, "error": "lsof unavailable"}."""

def restart(port: int = PORT_DEFAULT) -> dict
    """Best-effort restart sequence:
       1. stop(port)
       2. wait up to 3.0s for port to be free (poll _port_open every 100ms)
       3. start(port)
       4. wait up to 10.0s for GET http://127.0.0.1:<port>/doc to return 200
    Returns {"ok": True} only after step 4 confirms readiness.
    On any timeout: {"ok": False, "error": "<phase>: <detail>"}.
    Caller (providers_active hook) must NOT block its own response on this — fire-and-forget."""

def _wait_ready(port: int, timeout_s: float) -> bool
    """Poll GET http://127.0.0.1:<port>/doc every 200ms until 200 OK
    or timeout. Returns True on 200, False on timeout. Uses `requests`
    with a short per-call timeout (1.0s)."""

def _compute_source_env() -> dict[str, str]
    """Translate active Compute Source → opencode env vars.
    Reads (no writes): _load_active_provider, _provider_token, _PROVIDER_META.
    Returns env-var dict suitable for merging into os.environ for Popen.

    Mapping rules:
      provider == 'my_machine':
        OPENCODE_API_BASE = os.getenv('MODEL_API_BASE') or 'http://127.0.0.1:11434/v1'
        OPENCODE_MODEL    = os.getenv('MODEL_NAME', '')
        OPENCODE_API_KEY  = 'not-needed'
      provider in _CLOUD_PROVIDERS:
        OPENCODE_API_BASE = _PROVIDER_META[provider]['base']
                            (or for 'custom': os.getenv('MODEL_API_BASE'))
        OPENCODE_MODEL    = os.getenv('MODEL_NAME', '')
        OPENCODE_API_KEY  = _provider_token(provider)

    Bad input: unknown provider → falls back to my_machine mapping.
    Never logs token values."""

def install_hint() -> dict
    """Return {'platform': 'darwin'|'linux'|'wsl'|'windows'|'other',
               'command': str,
               'docs_url': str}.
    Pure: reads platform.system() + os.uname() only. No I/O."""
```

**No `reverse_proxy` function. No `_server_password` function.** Both
deleted from the original design.

### Flask route gate

Single source of truth — define once, decorate three routes:

```python
def _require_workbench():
    """Helper called at the top of each handler. Returns a Flask
    Response (404) when min tier; returns None when allowed.
    404 (not 403) so route existence isn't disclosed."""
    if "notebooks" not in _visible_surfaces():
        return abort(404)
    return None

# usage at the top of each handler:
@app.get("/opencode")
def opencode_page():
    if (gate := _require_workbench()) is not None:
        return gate
    ...
```

The gate runs **before** any logging, body parse, or subprocess. Builder
MUST verify this ordering with a test that asserts no log line is
emitted on a min-tier 404.

### Iframe source

The `/opencode` page renders an iframe with:

```html
<iframe src="http://127.0.0.1:4096/" ...></iframe>
```

The hostname/port is rendered from the same `OPENCODE_PORT` env (default
4096) the start() call uses, so they cannot drift. **The iframe URL must
NEVER embed credentials** (no `http://user:pass@…`). Test enforced. This
matches the Jupyter/Marimo pattern (token-in-URL is acceptable for
Jupyter because Jupyter's auth model uses URL tokens; opencode has no
auth, so we embed nothing).

### Compute Source hook (in `app.py`)

Modify `providers_active`. After `os.environ["COMPUTE_SOURCE"] = provider`:

```python
# Trigger best-effort opencode restart so the new baseURL is picked up.
# Does NOT block the response — restart can take 5-10s.
if "notebooks" in _visible_surfaces():
    try:
        from arail.portal.services import opencode as oc
        if oc.is_running():
            threading.Thread(target=oc.restart, daemon=True).start()
    except Exception:
        pass  # provider switch must succeed even if restart wiring breaks
```

The provider switch returns success regardless of restart outcome.
In-flight opencode sessions get a connection drop — documented in
`opencode.html` UI text, not handled by code.

### `/api/notebooks/status` shape extension

Append the fifth entry (mirrors existing entries):

```python
{
    "id": "opencode",
    "name": "opencode",
    "installed": opencode.is_installed(),
    "alive": opencode_alive,           # _port_open(bind, 4096)
    "url_internal": "/opencode",
    "url_external": "http://127.0.0.1:4096/",
}
```

`url_external` is now PRESENT (matching Jupyter/Marimo entries). No
credentials embedded.

### System health probe extension

Add to the existing optional-services check:

```python
opencode_port = int(os.getenv("OPENCODE_PORT", "4096"))
opencode_up = _port_open(bind, opencode_port)
# ... in optional_services ...
"opencode": opencode_up,
```

`opencode_up` follows the existing "hide when down" optional-services pattern.

## Failure modes

| ID | Failure | Detection | Recovery |
|---|---|---|---|
| F-GATE-1 | min-tier user discovers `/opencode*` route | Test: GET `/opencode` with `LAB_TIER=min` returns 404 | `_require_workbench` short-circuits with 404 (not 403) |
| F-GATE-2 | Gate added to 2 of 3 routes (forgot one) | Test: parametrize over all three routes | Single helper called first-line in every `/opencode*` handler; review checks usage |
| F-GATE-3 | Side effect runs before gate (logging body, reading secrets) | Test: assert no `activity_log.emit` and no secrets read on min-tier 404 | Gate is the first line of every handler; do NOT log inside `_require_workbench` |
| F-SEC-1 | iframe URL embeds credentials | Test: render `/opencode` page, assert iframe `src` matches regex `^http://127\.0\.0\.1:\d+/$` (no `@`) | Template hard-codes the format; no string interpolation of any token-like value |
| F-SEC-2 | Provider token leaks into log line | Test: capture logs during start/stop/restart and grep for any saved token value | Log only `pid`, `port`, `provider`; opencode subprocess stdout goes to file, not portal logger |
| F-SEC-3 | Provider token in `/api/notebooks/status` or `/api/system/health` | Test: assert payload does not contain it | only `id/name/installed/alive/url_internal/url_external` exposed |
| F-SEC-4 | Provider token leaks into opencode subprocess logs | Test: tail `lab/logs/opencode.log` after start, grep for any saved token value | opencode controls its own logging; documented limitation. (Sprint 2 follow-up: redact.) |
| F-SEC-5 | LAB_MODE=airgapped + cloud Compute Source = leak path | Test: in airgapped mode, `_compute_source_env()` returns my_machine vars | airgapped is enforced at the API switching layer (`providers_active`); we ride that gate |
| F-SEC-6 | opencode bound to 0.0.0.0 by mistake | Test: assert Popen args include `--hostname 127.0.0.1` | Hard-coded in `start()`; no env override permitted for hostname |
| F-PROC-1 | `start()` succeeds but opencode crashes 200ms later | Test: spawn fake binary that exits immediately; assert `restart()` returns error within 10s | `restart()` waits for `/doc` 200; on timeout returns error and the 3-state UI surfaces "installed-not-running" |
| F-PROC-2 | Port 4096 occupied by something else | Test: bind a socket on 4096, call `start()`; expect `{"ok": False, "error": "port busy"}` | Pre-check via `_port_open` before Popen; do NOT kill foreign process |
| F-PROC-3 | Portal SIGTERM doesn't reach opencode child | Manual test: kill portal, check `lsof -ti :4096` | Documented limitation. Operator runs `./arail` start which calls `stop()` first. NOT using `os.setsid` — see Tech Debt. |
| F-PROC-4 | `stop()` race when called twice in parallel (concurrent restart) | Test: two `restart()` calls concurrent | Module-level `threading.Lock` guards start/stop/restart |
| F-PROC-5 | `lab/logs/` does not exist | First `start()` mkdir | `LOG_PATH.parent.mkdir(parents=True, exist_ok=True)` before opening log |
| F-PROC-6 | `opencode.log` grows unbounded | n/a (manual rotation) | Cap log file at 10MB via simple rotation: on start, if size > 10MB, rename to `opencode.log.1` |
| F-RESTART-1 | Compute Source switch fails because opencode restart fails | Test: stub `restart` to raise; switch still returns ok | Restart is fire-and-forget thread wrapped in try/except |
| F-RESTART-2 | New env not picked up because `start()` reads stale env | Test: switch provider, verify new `Popen` env contains new vars | `start()` always calls `_compute_source_env()` fresh — no caching |
| F-RESTART-3 | Restart leaves orphan child if `stop()` partial-fails | Test: simulate `kill` failure on one of two pids | After `stop()`, poll port up to 3s; if still bound, return error and do NOT call `start()` |
| F-IFRAME-1 | Browser blocks mixed content (HTTPS portal + HTTP iframe) | N/A — portal binds 127.0.0.1 HTTP. Documented assumption; if a future sprint introduces HTTPS, the iframe URL must change too. | Documented; not in scope |
| F-IFRAME-2 | Browser refuses to load `127.0.0.1` iframe due to portal CSP | Test: render `/opencode` page; assert response `Content-Security-Policy` either absent or includes `frame-src http://127.0.0.1:4096` | Match the existing pattern used for Jupyter/Marimo iframes; no new CSP needed if those work today |
| F-IFRAME-3 | opencode running but iframe blank because page sent `X-Frame-Options: DENY` | Manual test at kickoff: `curl -I http://127.0.0.1:4096/` and check headers | If present and DENY/SAMEORIGIN, STOP and re-engage architect — direct iframe is impossible. (Kickoff probe: orchestrator's `curl -i /` did NOT report this header; assume absent.) |
| F-INSTALL-1 | Operator installs opencode AFTER portal start | UI re-detects on every `/opencode` page load (no caching) | `is_installed()` is a fresh `shutil.which` each call |
| F-INSTALL-2 | opencode binary present but too old (no `serve` subcommand) | Out of scope this sprint | Documented limitation. If `start()` fails, error surfaces in `opencode.log` and 3-state page shows "not-running" |
| F-INSTALL-3 | Wrong platform install hint | Test: stub `platform.system()` over each value | `install_hint()` matches existing `scripts/setup.sh` platform detection |
| F-CONFIG-1 | `MODEL_API_BASE` unset on my_machine | Test: clear env, call `_compute_source_env()`, assert sane fallback | Default to `http://127.0.0.1:11434/v1` |
| F-CONFIG-2 | `_provider_token` returns empty for active cloud provider | Test: cloud provider active, no saved token; assert `OPENCODE_API_KEY=''` not crash | Pass empty string; opencode surfaces auth error in its own UI |
| F-CONFIG-3 | Two parallel `start()` calls → two subprocesses | Same lock as F-PROC-4 | `threading.Lock` |

Removed from prior design (no longer applicable):
F-SEC-1 (basic-auth password leaks), F-SEC-4 (client Auth header
override), F-SEC-5 (path traversal in proxy), F-PROXY-1..7 (all
proxy-specific failures). The proxy doesn't exist.

## Test strategy

QA allocation per arail/CLAUDE.md is 30% setup / 30% Buddy / 20%
security / 10% happy / 10% regression. With the proxy gone, the
security surface area shrinks; we keep elevated coverage on the gate
(min-tier never sees the surface) and on env-var leakage paths.

### Unit tests (in this sprint)

`tests/portal/test_opencode_service.py`:

- `test_install_hint_per_platform` — parametrized over `darwin`,
  `linux`, `wsl`, `windows`. (F-INSTALL-3)
- `test_compute_source_env_my_machine` — assert dict shape. (F-CONFIG-1)
- `test_compute_source_env_my_machine_default_base` — clear
  `MODEL_API_BASE`; assert fallback to `http://127.0.0.1:11434/v1`.
- `test_compute_source_env_cloud_claude` — set provider claude with
  saved token; assert `OPENCODE_API_BASE='https://api.anthropic.com/v1'`
  and `OPENCODE_API_KEY=<token>`. (F-CONFIG-2)
- `test_compute_source_env_cloud_no_token` — provider with empty
  token; assert env returned with empty key (not crash). (F-CONFIG-2)
- `test_compute_source_env_never_logged` — capture logs across all
  `_compute_source_env` paths, assert no token value present. (F-SEC-2)
- `test_start_command_pins_port_and_hostname` — capture Popen args;
  assert `--port 4096` AND `--hostname 127.0.0.1` both present.
  (F-SEC-6, A1)

### Integration tests (in this sprint)

`tests/portal/test_opencode_routes.py`:

- `test_min_tier_404_all_three_routes` — parametrized over
  `GET /opencode`, `POST /api/opencode/start`, `POST /api/opencode/stop`;
  with `LAB_TIER=min`, all 404. (F-GATE-1, F-GATE-2)
- `test_min_tier_no_side_effects` — assert no `activity_log` entries
  and no secrets reads when min-tier route 404s. (F-GATE-3)
- `test_max_tier_page_renders_when_not_installed` — `LAB_TIER=max`,
  stub `is_installed=False`, GET `/opencode`, assert install hint in HTML.
- `test_max_tier_page_iframe_url_no_credentials` — `LAB_TIER=max`,
  stub `is_running=True`, GET `/opencode`, assert rendered HTML
  contains `src="http://127.0.0.1:4096/"` AND does NOT match the regex
  `src="http://[^/"]*@`. (F-SEC-1)
- `test_status_includes_opencode_entry` — `/api/notebooks/status`
  fifth entry shape, including `url_external`.
- `test_status_does_not_leak_token` — provision a saved provider token;
  GET `/api/notebooks/status`; assert token value not present in
  payload. (F-SEC-3)
- `test_health_includes_opencode` — `/api/system/health` optional_services
  contains `opencode` only when up.

### Lifecycle tests (in this sprint)

`tests/portal/test_opencode_lifecycle.py`:

- `test_start_returns_error_if_port_busy` — bind a socket on 4096,
  call `start()`. (F-PROC-2)
- `test_restart_after_provider_switch` — stub `is_running=True`;
  POST `/api/providers/active` with new provider; assert `restart()`
  scheduled (mock) and the response did NOT block on it. (F-RESTART-1)
- `test_restart_picks_up_new_env` — stub `_compute_source_env` to
  return value A then B; full restart cycle; assert second `Popen`
  called with B. (F-RESTART-2)
- `test_concurrent_restart_serializes` — two `restart()` calls in
  parallel threads; assert lock prevents overlap. (F-PROC-4)
- `test_provider_switch_succeeds_when_restart_fails` — stub
  `restart` to raise; switch still returns `{"ok": True}`. (F-RESTART-1)
- `test_log_rotation_at_10mb` — pre-seed log file > 10MB;
  `start()` rotates to `.log.1`. (F-PROC-6)
- `test_wait_ready_polls_doc_endpoint` — fake server that returns
  503 then 200; assert `_wait_ready` returns True within timeout.
  (A9 — readiness contract)
- `test_wait_ready_timeout` — fake server stays 503; assert
  `_wait_ready` returns False after timeout. (F-PROC-1)

### Regression tests (in this sprint)

- `test_existing_notebooks_status_unchanged_for_first_three` —
  jupyter/marimo/open-notebook entries unchanged shape.
- `test_workbench_label_in_nav_template` — render `_nav.html` with
  `notebooks` in surfaces; assert text "Workbench" not "Notebooks".

### Performance tests

Skipped — opencode is interactive, not throughput. With the proxy gone,
there's no streaming-latency concern in our code path; the iframe talks
to opencode directly.

### Security tests (consolidated, must-pass)

1. F-GATE-1 / F-GATE-2 / F-GATE-3 — min-tier never sees the surface.
2. F-SEC-1 — iframe URL never embeds credentials.
3. F-SEC-2 / F-SEC-3 — provider tokens never leak into logs or status JSON.
4. F-SEC-6 — opencode subprocess pinned to 127.0.0.1.

### Deferred to Sprint 2 / follow-up

- Version probe (F-INSTALL-2): opencode binary too old.
- Provider token redaction in opencode's own logs (F-SEC-4).
- `os.setsid` process group cleanup (F-PROC-3).
- Add a one-paragraph "trust model" note to `docs/PRIVACY.md`
  documenting that `127.0.0.1` is the lab's perimeter and that
  iframed services (Jupyter, Marimo, Open-Notebook, opencode) all
  share that boundary.
- "Skills folded into Agents" entire scope (Sprint 2 of the plan).

## Tech debt

**Added:**

1. **`opencode.log` rotation is single-file (10MB cap).** Fine for a
   dev surface. If opencode logs get noisy, swap for
   `logging.handlers.RotatingFileHandler`.
2. **No process supervision on portal crash (F-PROC-3).** Orphans the
   opencode child, occupying port 4096. Same shape as Jupyter today.
   Document in TROUBLESHOOTING.md as `lsof -ti :4096 | xargs kill`.
3. **Provider token visible to opencode subprocess** via env. Opencode
   may log it (F-SEC-4). Out of our control; document.
4. **`agents.html` size pressure.** Out of scope this sprint; Sprint 2
   warning.

**Repaid:**

1. **No new HTTP-proxying surface.** The original design introduced a
   reverse proxy that would have been the first of its kind in this
   codebase. Dropping it keeps the codebase consistent with the
   existing iframe-at-127.0.0.1 pattern (Jupyter, Marimo,
   Open-Notebook). Naming/architectural debt avoided.
2. **No new runtime dep (`httpx`).** With the proxy gone, the readiness
   probe uses the existing `requests` dep.
3. **Workbench rename clarifies the tab's purpose** for future surfaces.
4. **Trust model is now consistent across all four iframed surfaces.**
   The "127.0.0.1 = trusted" boundary is the only one. Follow-up
   sprint should write that down in PRIVACY.md.

**Net:** Zero or slightly negative (more repaid than added).
The Path-A decision retired the largest item from the original Added list.

## Recommended implementation order

1. **Skim kickoff probe findings in BUILD_LOG.md kickoff section**
   (orchestrator already ran the probes; document the findings
   verbatim from the orchestrator's report). Confirm
   `curl -I http://127.0.0.1:4096/` does NOT include
   `X-Frame-Options: DENY` (F-IFRAME-3); if it does, STOP and
   re-engage architect. (Orchestrator's `curl -i /` already showed
   the headers; this is a re-verification step.)

2. **`services/opencode.py` skeleton + unit tests** — every helper.
   Get `_compute_source_env`, `install_hint`, `start/stop/restart`,
   `_wait_ready` green.

3. **Route registration with gate** — `_require_workbench` helper,
   three routes (`GET /opencode`, `POST /api/opencode/start`,
   `POST /api/opencode/stop`); `min_tier_404` tests pass.

4. **`/opencode` page template** — 3-state HTML with iframe to
   `http://127.0.0.1:4096/` (no credentials). `iframe_url_no_credentials`
   test passes.

5. **`/api/notebooks/status` extension + frontend wiring** —
   `notebooks.html` fifth card; Workbench rename in `_nav.html`
   and template heading.

6. **`/api/system/health` extension** — `opencode` in optional_services.

7. **`providers_active` hook** — fire-and-forget restart;
   `test_restart_after_provider_switch` passes.

8. **Manual verification** — start opencode via the portal, confirm
   iframe loads the SPA, confirm switching Compute Source restarts
   the subprocess, confirm `pytest tests/portal/` green.

9. **BUILD_LOG.md** — record the kickoff findings (Path-A decision,
   `--port` not defaulting to 4096, `/doc` as readiness, no
   `X-Frame-Options`) and any line numbers touched.
