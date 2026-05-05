# Architecture: airgap-honest-mode

**Date:** 2026-05-05
**Spec:** [VISION.md](./VISION.md), [PLAN.md](./PLAN.md) (both at branch `qukaizen/arail-airgap-honest-mode`)
**Product:** arail
**Mode:** design

---

## Restatement

ARAIL today ships with `LAB_MODE=airgapped` as the default and tells users in
the README that "the lab makes zero network calls" — but the only thing
airgapped actually blocks is the cloud-LLM provider endpoints in the Chat
tab. Any agent that writes `requests.get("https://...")` reaches the
internet, and Buddy already does (HF papers fetch behind a separate
`LAB_INTERNET_ENABLED` flag). This sprint lands a Python-level egress
choke point so airgapped means *"agents cannot collect information from
the public internet."* Local services (loopback + RFC1918 + link-local)
stay reachable so the common LAN-GPU-box workflow keeps working. Blocks
raise `EgressBlocked` (a `RuntimeError` subclass) loudly, append a
structured line to `lab/data/egress.jsonl`, surface in a nav-badge modal
backed by `GET /api/airgap/status`, and trigger a Buddy chat heads-up.
The README + PRIVACY.md get rewritten to match reality. The threat model
is *well-meaning agent code*, not an adversary on the host.

---

## Assumptions

1. **In-process agent execution.** Every shipped agent loads via
   `src/arail/agents/loader.py` and runs in the portal's Python process.
   A subprocess or out-of-process agent (planned for aerollm Phase-2
   HTTP bindings) would bypass this guard entirely; that's flagged as a
   known gap in §13 and called out in the modal copy.
2. **`requests` is the dominant HTTP client in agent space.** Grep
   confirms 8 files use `requests`/`urllib.request`. `httpx` appears in
   3 files (see Bypass Triage §6). `aiohttp` is *not* in tree.
3. **DNS resolution is trustworthy enough for the threat model.** We
   resolve the URL host to an IP via `socket.gethostbyname` and check
   the *resolved IP* against the local-net ranges, not just the
   hostname. This defeats trivial DNS-rebinding to `127.0.0.1` for a
   public domain. We do not defend against an adversary who controls
   the user's resolver.
4. **`lab/data/` is writable.** Write failures (disk full, RO fs) must
   not crash the guard — record_block returns silently after logging
   to stderr. The block itself still raises (correct behavior: airgapped
   is the contract; logging is best-effort).
5. **`setup.sh` runs before the portal boots.** Initial weight downloads
   are out of scope. The guard installs at portal-startup and
   agent-loader time only.
6. **The Compute Source pivot's existing checks remain authoritative.**
   The new guard sits *below* the per-domain consent layer — in hybrid,
   the guard is a pass-through and the existing curator-consent logic
   keeps gating cloud calls. We are not redesigning the consent model.
7. **`@allow_egress("reason")` is intended for *user-initiated* hybrid-mode
   bypasses only.** In airgapped mode the decorator hard-raises. The
   one engineered exemption — `BUDDY_EGRESS_PROBE=1` — is documented as
   the *only* exemption and is itself opt-in.

---

## Data flow

```
                                ┌─ portal startup ─┐
                                │  app.py @ boot   │
                                │  → install_guard()
                                └──────┬───────────┘
                                       │ (idempotent)
                                       ▼
                          ┌────────────────────────┐
                          │ requests.adapters       │
                          │   default HTTPS adapter │
                          │   replaced by           │
                          │   GuardedAdapter        │
                          │ urllib.request          │
                          │   default opener        │
                          │   replaced by           │
                          │   guarded opener        │
                          └────────────────────────┘
                                       ▲
                                       │ (idempotent)
                                       │
                        ┌──────────────┴───────────┐
                        │ agents/loader.py @ first │
                        │   load_all() invocation  │
                        │   → install_guard()      │
                        └──────────────────────────┘

agent code path:

  agent.py: requests.get("https://huggingface.co/...")
       │
       ▼
  GuardedAdapter.send(req)
       │
       ├─ url_host = parse(req.url).hostname
       ├─ resolved_ip = gethostbyname(url_host)  (catches DNS rebind)
       ├─ if is_local_host(url_host) or is_local_ip(resolved_ip):
       │     → super().send(req)  [pass through]
       ├─ if is_airgapped() and not _allow_egress_active():
       │     → record_block(url, caller, reason="airgapped")
       │     → raise EgressBlocked(...)
       └─ else (hybrid OR allow_egress active):
             → super().send(req)  [pass through]

block log path:

  record_block()
       │
       ├─ open lab/data/egress.jsonl in append mode
       ├─ if file size > 5MB: rotate to .1 (drop .2 if exists)
       ├─ write json line {ts, url_host, caller, reason, lab_mode}
       └─ flush + close

UI path:

  user clicks nav-badge
       │
       ▼
  GET /api/airgap/status
       │
       ├─ lab_mode = airgap.lab_mode()
       ├─ recent_blocks = read_jsonl_tail(LAB_DATA / "egress.jsonl", 5)
       ├─ host_can_reach_internet = probe() if BUDDY_EGRESS_PROBE else None
       └─ {lab_mode, definition, recent_blocks, host_can_reach_internet}
       │
       ▼
  airgap_modal.html populates from JSON

buddy watcher path:

  buddy._watch_airgap_events() (every 90s tick)
       │
       ├─ read state.last_jsonl_offset
       ├─ tail egress.jsonl from offset → list of new blocks
       ├─ if new blocks: pick most recent, emit suggestion, advance offset
       ├─ read state.last_lab_mode
       ├─ current_mode = airgap.lab_mode()
       └─ if current != last: emit toggle suggestion, persist
```

---

## Module map

### New: `src/arail/airgap.py`

The single source of truth for "what mode are we in" and "is this URL
allowed?" Pure helpers; no I/O beyond env reads and DNS resolution.

```python
"""airgap — single source of truth for ARAIL's outbound network policy.

Every other module that wants to ask "are we airgapped?" or
"is this URL local?" goes through this module. Five duplicated
helpers across the codebase collapse to delegations into here.
"""

class EgressBlocked(RuntimeError):
    """Raised when an outbound network call is denied by the airgap guard.

    Subclass of RuntimeError so agents that ``except Exception:`` already
    let it bubble visibly rather than swallow it as a generic IOError.
    Carries ``url_host``, ``caller``, and ``reason`` attributes for the
    audit log and any catch-and-translate in agent code.
    """
    def __init__(self, url_host: str, caller: str, reason: str): ...

def lab_mode() -> str:
    """Return the current lab mode: 'airgapped' or 'hybrid'.

    Reads LAB_MODE → ARAIL_MODE → 'airgapped' (the canonical fallback
    chain used in 5+ places today). Strips/lowers; anything not 'hybrid'
    collapses to 'airgapped' (fail-closed)."""

def is_airgapped() -> bool:
    """True iff lab_mode() != 'hybrid'."""

def is_local_host(host: str) -> bool:
    """True iff host is loopback, RFC1918, or link-local.

    Accepts hostnames *and* IP literals. Handles:
      - 'localhost', '127.0.0.1', '::1'
      - '10.x.y.z', '172.16.0.0/12', '192.168.x.y'
      - '169.254.x.y', 'fe80::*'
    For non-IP hostnames (e.g. 'my-gpu-box.local'), resolves via
    ``socket.gethostbyname`` and re-checks the resolved IP. Resolution
    failures count as 'not local' (fail-closed)."""

def is_local_ip(ip: str) -> bool:
    """True iff the given IP literal is loopback, RFC1918, or link-local.

    Uses ``ipaddress.ip_address(ip).is_private`` plus
    ``.is_loopback`` plus ``.is_link_local``. Pure stdlib."""

def should_allow_egress(url: str) -> tuple[bool, str]:
    """Decide whether a URL should be allowed out.

    Returns (allowed, reason). Reason strings:
      - "local"     — host resolves to loopback/RFC1918/link-local
      - "hybrid"    — lab_mode is hybrid; consent layer takes over
      - "allowed"   — @allow_egress context active (audited)
      - "airgapped" — denied; airgapped + non-local + no allow context
      - "invalid"   — URL did not parse; denied
    Does NOT raise. Callers (the guard) decide what to do with False."""
```

### New: `src/arail/egress.py`

The HTTP-layer guard. Mounts adapters, owns the audit log, exposes
the bypass context manager.

```python
"""egress — Python-level outbound network guard.

Installs a custom requests HTTPAdapter and a urllib opener that consult
arail.airgap.should_allow_egress before passing a request through.
"""

import contextvars

# Thread-/task-safe flag for "this stack frame requested an egress
# bypass." MUST be a contextvars.ContextVar so concurrent agents in
# threads or asyncio tasks don't leak the bypass to each other.
_allow_egress_var: contextvars.ContextVar[Optional[str]]

def install_guard() -> None:
    """Install the egress guard. Idempotent; safe to call N times.

    Mounts a GuardedHTTPAdapter onto a module-level
    ``requests.Session`` *and* monkey-patches
    ``requests.adapters.HTTPAdapter`` so any future ``requests.Session()``
    constructor inherits the guarded behavior. (Without the
    monkey-patch, an agent calling ``requests.Session()`` directly
    gets a fresh default adapter and bypasses the guard — see §13.)

    Also installs a urllib opener via ``urllib.request.install_opener``
    that runs ``should_allow_egress`` in a request-handler hook before
    delegating to the default chain.

    Idempotency is enforced via a module-level ``_INSTALLED`` flag.
    Re-imports during test runs (which monkeypatch openers) don't
    re-install; tests that need to reset must call ``_reset_for_tests()``
    explicitly."""

def record_block(url: str, caller: str, reason: str) -> None:
    """Append one structured line to lab/data/egress.jsonl.

    Schema:
      {"ts": "2026-05-05T14:33:01Z",
       "url_host": "huggingface.co",
       "caller": "buddy._suggest_internet_correlation",
       "reason": "airgapped",
       "lab_mode": "airgapped"}

    Caller is best-effort: walks the stack with ``inspect.stack()``
    and picks the first frame whose ``__name__`` is not in
    {arail.egress, arail.airgap, requests.*, urllib.*}. Falls back to
    ``"unknown"`` if no useful frame found.

    Rotation: if file > 5MB, rename to .1 (overwriting any existing
    .1 — single rotation, no .2). Then create a new empty file.

    Errors are caught and logged to stderr — the block itself still
    raises in the caller; logging failure must NOT prevent the loud
    failure."""

def record_allow(url: str, caller: str, reason: str) -> None:
    """Audit trail for @allow_egress contexts that actually fired.

    Same schema as record_block but with reason='allow:<context-reason>'.
    Used so the egress.jsonl tail in the modal shows both denials and
    audited allowances — full picture for the user."""

def read_recent_blocks(n: int = 5) -> list[dict]:
    """Bounded read for the modal — last N entries by timestamp.

    Reads the tail of egress.jsonl using a chunked-from-end strategy
    (seek to end, read up to ~64KB, split lines, take last N). Never
    full-file slurp. If file missing or unreadable, returns []."""

@contextlib.contextmanager
def allow_egress(reason: str):
    """Context manager / decorator that bypasses the guard for *its
    own stack frame* with an audit-logged reason.

    HARD RULE: in airgapped mode, allow_egress raises EgressBlocked
    *immediately on entry*, before yielding. The only exception is the
    BUDDY_EGRESS_PROBE pathway, which uses raw socket and never
    touches this context manager. Any future contributor who wants
    to allow egress in airgapped must edit this module and re-justify
    in a new sprint. This is intentional ratchet logic.

    Also usable as a decorator: ``@allow_egress("test the openrouter
    endpoint")``. Decorator form wraps the function in
    ``with allow_egress(reason): return func(*args, **kw)``.

    Reason validation:
      - non-empty string, < 200 chars (otherwise ValueError)
      - logged via record_allow when bypass is consumed by a guard check

    Scope: applies to the calling stack frame and all sub-calls within
    the with-block / decorated function. Sub-threads spawned inside
    the block do NOT inherit the bypass (contextvars semantics —
    see §13 for the asyncio.create_task subtlety)."""
```

### Internal: `GuardedHTTPAdapter` (in `src/arail/egress.py`)

```python
class GuardedHTTPAdapter(requests.adapters.HTTPAdapter):
    """HTTPAdapter that consults the airgap policy before sending."""

    def send(self, request, **kwargs):
        url = request.url or ""
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
        except Exception:
            host = ""

        # 1. Local hosts always pass — that's the LAN-GPU-box rule.
        if host and (is_local_host(host) or _is_local_resolved(host)):
            return super().send(request, **kwargs)

        # 2. Allow-context wins if active (audit-logged).
        active = _allow_egress_var.get(None)
        if active is not None:
            record_allow(url, _current_caller(), active)
            return super().send(request, **kwargs)

        # 3. Airgapped + non-local + no allow → deny loudly.
        if is_airgapped():
            caller = _current_caller()
            record_block(url, caller, "airgapped")
            raise EgressBlocked(host or "?", caller, "airgapped")

        # 4. Hybrid + non-local + no allow → pass through.
        #    Per-domain consent is a separate layer (curator/consent).
        return super().send(request, **kwargs)
```

### Internal: urllib opener wrapper

```python
class _GuardedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        _check_egress_or_raise(req.full_url)
        return super().http_open(req)

class _GuardedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        _check_egress_or_raise(req.full_url)
        return super().https_open(req)

def _check_egress_or_raise(url: str) -> None:
    # Same 4-step decision tree as GuardedHTTPAdapter.send, but for
    # urllib. Factored into a helper to keep the two code paths
    # locked-in-step — any future change applies to both.
```

The opener install:

```python
opener = urllib.request.build_opener(_GuardedHTTPHandler, _GuardedHTTPSHandler)
urllib.request.install_opener(opener)
```

---

## install_guard() idempotency + ordering

**Calls:**

1. `src/arail/portal/app.py` — at the very top of the FastAPI startup
   block (before any cloud-provider test endpoint, before the agent
   loader, before the security scan).
2. `src/arail/agents/loader.py:load_all()` — first line of the function,
   before any `_import_from_path()` call. Ensures that user-forged agents
   importing `requests` at module-import time still get the guarded
   adapter via the monkey-patched `HTTPAdapter`.

**Idempotency:** module-level `_INSTALLED: bool` flag. Second-and-later
calls are no-ops. Tests that need a fresh install call
`egress._reset_for_tests()` (test-only public; not part of the agent
contract).

**Ordering invariant:** `install_guard()` must run **before** any
`requests.Session()` is constructed by an agent. This is enforced two ways:

1. The module-level monkeypatch on `requests.adapters.HTTPAdapter`
   (replacing the class itself, not just an instance). Any
   `requests.Session()` constructed *after* `install_guard()` gets the
   guarded adapter. Sessions constructed *before* are not retrofitted.
2. The portal startup ordering ensures `install_guard()` runs before
   `load_all()`. The loader's own first-line call is a belt-and-braces
   defense — if a future entry point bypasses the portal startup (e.g.
   a CLI command that loads agents without booting the Flask app), the
   loader still installs the guard.

**Known limit (called out in §13):** any `requests.Session` constructed
at module-import time of an agent (i.e. before `load_all()` runs) bypasses
the guard. Today three files do this in `src/arail/router/backends.py`
(at lines 231, 440, 590) — but those backends only target localhost, so
the bypass is empty in practice. Documented as known gap.

---

## Bypass triage table

Every Python network primitive gets an explicit decision. *In tree?*
column reflects 2026-05-05 grep on
`/Users/netsushi/ProJects/arail`.

| Primitive | In tree? | Decision | Enforcement | Test |
|---|---|---|---|---|
| `requests.get/post/...` (module-level helpers) | yes — `src/arail/portal/app.py:1091,1121,5032,5048`, `src/arail/agents/curator.py:118` | **wrap** | `install_guard()` monkeypatches `requests.adapters.HTTPAdapter` | `tests/test_egress_guard.py::test_requests_get_blocked_airgapped` |
| `requests.Session()` (constructed post-guard) | yes — `src/arail/router/backends.py:231,440,590` (all localhost) | **wrap** (inherits from monkeypatched adapter class) | same as above | `tests/test_egress_guard.py::test_session_post_install_uses_guarded_adapter` |
| `requests.Session()` (constructed pre-guard at module import) | yes (the 3 backends.py sites) | **document loudly as known gap** + audit (those 3 are localhost-only, so empty in practice). Builder MUST add a one-line `# noqa-airgap: localhost-only` comment at each site. | n/a — see §13 | n/a (regression test would require restart-time fixture) |
| `urllib.request.urlopen` | yes — `src/arail/chat/__init__.py:99,160`, `src/arail/agents/_builtin_buddy.py:784`, `src/arail/agents/_builtin_sre.py:269,272`, `src/arail/portal/app.py:5939` | **wrap** | `urllib.request.install_opener(...)` with guarded handlers | `tests/test_egress_guard.py::test_urllib_urlopen_blocked_airgapped` |
| `urllib3` direct (i.e. `urllib3.PoolManager`) | **not in tree** | **document** in PRIVACY.md "known gaps" + modal "agents that bypass" footnote. `requests` ships urllib3 internally but goes through our adapter. | n/a | n/a (out-of-scope for v1) |
| `httpx.{get,post,AsyncClient,...}` | **yes — surprising** — `src/arail/open_notebook_seed.py:19+`, `core/knowledge-canvas/client.py:25+`, `core/knowledge-canvas/backend/app/services/llm_router.py:32` | **document** for v1 + add to "known gaps" footnote in modal. *AND* audit each call site: open_notebook_seed and knowledge-canvas hit `localhost:<port>` for surreal/MLX/Ollama — local-only, empty bypass in practice. Builder MUST add `# noqa-airgap: localhost-only` at each site and PRIVACY.md MUST list httpx as a non-wrapped client. | known-gap doc only | n/a v1; QA bypass-attempt suite tries `httpx.get("https://example.com")` and asserts it succeeds (i.e. not wrapped) so the test pins the documented behavior |
| `aiohttp.ClientSession` | **not in tree** | **document** in PRIVACY.md "known gaps." | n/a | QA bypass-attempt suite asserts `aiohttp.get("https://example.com")` succeeds (pins documented behavior) |
| `socket.socket().connect((host, port))` | yes (test only — `tests/test_pkb_index_qa.py`) + the planned `BUDDY_EGRESS_PROBE` opt-in probe | **document.** Wrapping `socket.socket` would break the SRE health-check loopback path and the urllib's own underlying connection, since `requests`/`urllib` ultimately use sockets. Instead, our guard works *above* sockets — at URL-parse time. Raw `socket.connect((8.8.8.8, 80))` is undetectable by us. | known-gap doc only; the `BUDDY_EGRESS_PROBE` opt-in is the only intentional raw-socket exemption | QA bypass-attempt suite tries `socket.socket().connect(("8.8.8.8", 80))` and asserts it succeeds (documented gap) |
| `subprocess.run(["curl", url])` / `Popen(["curl", ...])` | **not in tree** for curl/wget specifically | **document.** Subprocess agents are out of scope for v1 (per VISION.md and PLAN.md). | known-gap doc | QA bypass-attempt: `subprocess.run(["curl", "https://example.com"])` succeeds; pin documented behavior |
| `os.system("curl ...")` | **not in tree** | **document** as subset of subprocess gap | known-gap doc | QA bypass-attempt: `os.system("curl ...")` succeeds; pin |

**Surprises from grep:**

- `httpx` IS in tree, in 3 files. None of them hit the public internet
  in normal use (all localhost), but the README's "zero network calls"
  promise was already false in two ways the PLAN didn't fully name.
  PRIVACY.md MUST mention httpx as an unwrapped client and MUST audit
  the call sites are localhost-only.
- `aiohttp` and explicit `urllib3`/`subprocess curl` are NOT in tree.
  Documented-gap is the right call for v1.
- `socket.socket()` only appears in `tests/test_pkb_index_qa.py` (a test
  fixture that monkeypatches it, doesn't dial). Confirms the raw-socket
  threat surface is theoretical for current code.
- `BUDDY_EGRESS_PROBE=1` was the intended opt-in, but no implementation
  exists today. ARCHITECTURE specifies it below as a new addition.

---

## `@allow_egress` semantics

**Forms:** Both context manager *and* decorator.

```python
# Context manager
with allow_egress("test openrouter /models endpoint"):
    r = requests.get("https://openrouter.ai/api/v1/models", ...)

# Decorator (sugar over the context manager)
@allow_egress("save provider token by hitting /models for validation")
def test_provider(provider, token): ...
```

**Scope:** the immediate stack frame and all sub-calls within the
`with`-block / decorated function body. Implemented via
`contextvars.ContextVar`. **Sub-threads do NOT inherit the bypass**
(contextvars are per-task in asyncio and per-thread in threading; the
guard re-reads the var fresh on each `send()` call, so a thread spawned
inside the with-block will see the default `None`).

**asyncio subtlety:** `asyncio.create_task(coro)` *does* copy the
contextvars context to the task. This means an `allow_egress` block that
launches a task and returns will keep allowing egress in the task even
after the with-block exits. For v1 this is acceptable — the only
caller pattern is "save/test/list provider token" which awaits inline.
A regression test pins the pattern; future async usage adds a guard
loop test.

**Airgapped behavior (HARD RULE):**

```python
@contextlib.contextmanager
def allow_egress(reason: str):
    if not isinstance(reason, str) or not reason or len(reason) > 200:
        raise ValueError(f"allow_egress reason must be 1..200 chars; got {reason!r}")
    if airgap.is_airgapped():
        # Hard ratchet: no escape hatch in airgapped. The only intentional
        # exemption is BUDDY_EGRESS_PROBE which uses raw socket directly,
        # not this context manager. See ARCHITECTURE.md §3.
        raise EgressBlocked("?", _current_caller(),
                            f"allow_egress denied in airgapped: {reason!r}")
    token = _allow_egress_var.set(reason)
    try:
        yield reason
    finally:
        _allow_egress_var.reset(token)
```

**Reason logging:** when a request inside an `allow_egress` block
actually triggers a `send()`, the guard calls `record_allow(url, caller,
reason)` which writes a separate "allowed" line to `egress.jsonl`. The
modal shows both blocks and allowances under the same "recent activity"
list with a denied/allowed badge.

**URL sanity check inside `allow_egress`:** when a user-supplied URL is
passed through, the guard's normal local-host check still runs. If a
caller passes `http://127.0.0.1:.../redirect-to-badness`, the local
check passes, super().send() runs — that's the same risk the lab has
today (HTTP redirects from local services). Out of scope for this
sprint; documented in §13.

**One engineered exemption — `BUDDY_EGRESS_PROBE=1`:** opt-in TCP probe
to `1.1.1.1:443` with 1s timeout. Implemented in `egress.probe_internet()`
using **raw `socket.socket(AF_INET, SOCK_STREAM)`** — bypasses our own
guard intentionally. The function logs an explicit "BUDDY_EGRESS_PROBE
fired" line to `egress.jsonl` (reason="probe") so the user can see the
single audited bypass. PRIVACY.md and the modal banner BOTH state this
is the only exemption.

---

## `lab/data/egress.jsonl` rotation

**Path:** `${LAB_DATA}/egress.jsonl` (where `LAB_DATA` = `lab/data` by default).

**Schema (one JSON object per line):**

```json
{
  "ts": "2026-05-05T14:33:01Z",
  "url_host": "huggingface.co",
  "caller": "arail.agents._builtin_buddy._suggest_internet_correlation",
  "reason": "airgapped",
  "lab_mode": "airgapped"
}
```

For an `allow_egress` audit line:

```json
{
  "ts": "2026-05-05T14:34:12Z",
  "url_host": "openrouter.ai",
  "caller": "arail.portal.app.providers_test",
  "reason": "allow:test the openrouter endpoint",
  "lab_mode": "hybrid"
}
```

For a `BUDDY_EGRESS_PROBE` audit line:

```json
{
  "ts": "2026-05-05T14:35:00Z",
  "url_host": "1.1.1.1:443",
  "caller": "arail.egress.probe_internet",
  "reason": "probe",
  "lab_mode": "airgapped"
}
```

**Rotation strategy (single-step):**

- Before each append, `os.path.getsize(path)` if exists.
- If size > 5 MB: rename `egress.jsonl` → `egress.jsonl.1`, overwriting
  any existing `.1`. No `.2` — we keep at most one rotation. The user
  can grep history if they care; the modal only ever shows the live tail.
- After rotation, open new file and append the current line.
- Rotation failures (e.g. windows file lock) caught and logged to
  stderr; the block still raises in the caller.

**Bounded read (`read_recent_blocks(n=5)`):**

```python
def read_recent_blocks(n: int = 5) -> list[dict]:
    path = LAB_DATA / "egress.jsonl"
    if not path.exists():
        return []
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            f.seek(max(0, size - 64 * 1024))  # last 64KB
            tail = f.read().decode("utf-8", errors="replace")
        lines = [ln for ln in tail.splitlines() if ln.strip()]
        # If we sliced mid-line, drop the (partial) first line.
        if size > 64 * 1024 and lines:
            lines = lines[1:]
        out = []
        for ln in lines[-n:]:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
        return out
    except Exception:
        return []
```

Worst case: a single agent in a tight retry loop writes ~150 bytes/line,
~5MB = ~33k lines. The 64KB tail-read covers ~430 lines — way more than
the modal needs (5). Bounded.

---

## `GET /api/airgap/status` response shape

**Airgapped mode example:**

```json
{
  "lab_mode": "airgapped",
  "definition": "Agents cannot collect information from the public internet. Local services on this machine and your private network (loopback, RFC1918, link-local) stay reachable. Cloud-provider APIs are blocked. Toggle LAB_MODE=hybrid in .env to allow agent fetches.",
  "recent_activity": [
    {
      "ts": "2026-05-05T14:33:01Z",
      "url_host": "huggingface.co",
      "caller": "arail.agents._builtin_buddy._suggest_internet_correlation",
      "reason": "airgapped",
      "kind": "blocked"
    },
    {
      "ts": "2026-05-05T14:32:55Z",
      "url_host": "arxiv.org",
      "caller": "arail.research.program_drafter._fetch_external",
      "reason": "airgapped",
      "kind": "blocked"
    }
  ],
  "host_can_reach_internet": null,
  "known_gaps": [
    "httpx (used by open-notebook integration; localhost-only in tree)",
    "raw socket connections (BUDDY_EGRESS_PROBE is the only audited use)",
    "subprocess-spawned curl/wget (none in tree today)",
    "aiohttp (not in tree)"
  ],
  "guard_installed": true
}
```

**Hybrid mode example:**

```json
{
  "lab_mode": "hybrid",
  "definition": "Hybrid: cloud providers are reachable. Per-domain consent still gates curator and browser fetches. The egress audit log still records all outbound calls.",
  "recent_activity": [
    {
      "ts": "2026-05-05T14:34:12Z",
      "url_host": "openrouter.ai",
      "caller": "arail.portal.app.providers_test",
      "reason": "allow:test the openrouter endpoint",
      "kind": "allowed"
    }
  ],
  "host_can_reach_internet": null,
  "known_gaps": [
    "httpx (not wrapped)",
    "raw socket connections",
    "subprocess-spawned curl/wget",
    "aiohttp (not in tree)"
  ],
  "guard_installed": true
}
```

**With `BUDDY_EGRESS_PROBE=1` (airgapped):**

```json
{
  "lab_mode": "airgapped",
  "definition": "...",
  "recent_activity": [...],
  "host_can_reach_internet": true,
  "known_gaps": [...],
  "guard_installed": true
}
```

`host_can_reach_internet` is `null` by default; set to `true|false` only
when the env var is set. The probe is one TCP-connect to `1.1.1.1:443`
with 1s timeout — no DNS, no payload, no HTTP. Result is cached for 60
seconds in process memory so repeated modal opens don't hammer the test.

**Field semantics:**

| Field | Type | Notes |
|---|---|---|
| `lab_mode` | `"airgapped"` \| `"hybrid"` | Read from `airgap.lab_mode()`. |
| `definition` | string | Hardcoded copy keyed off `lab_mode`. |
| `recent_activity` | list[obj] | Up to 5 most recent egress.jsonl lines. `kind` is `"blocked"` if reason starts with "airgapped" or no `allow:`/`probe:` prefix; `"allowed"` if reason starts with `allow:` or equals `"probe"`. |
| `host_can_reach_internet` | `null` \| `true` \| `false` | Only populated when `BUDDY_EGRESS_PROBE=1`. Otherwise always `null`. |
| `known_gaps` | list[string] | Static list of unwrapped primitives. Identical across modes (the gaps don't change with the toggle). |
| `guard_installed` | bool | True once `install_guard()` has run. Defensive — if false, the user knows the modal is showing a misleading status. |

---

## Modal HTML — `src/arail/portal/templates/_airgap_modal.html`

Reuses the existing `mp-backdrop` / `mp-modal` pattern from
`chat.legacy.html` so the look matches without new CSS. Builder copies
the inline CSS from chat.legacy.html § lines 75–111 into a new included
partial OR moves those styles to `static/style.css` first (recommended:
move to `static/style.css` as a small, separate refactor commit so the
airgap modal can reference them by class name without inline duplication).
A pragmatic alternative: scope a copy of the CSS into the modal
template itself behind an `id="airgap-modal-styles"` guard.

```html
<!-- _airgap_modal.html -->
<!-- Included by base layout; visible only when activated by JS in nav.js -->
<style id="airgap-modal-styles">
  /* (Builder: import or duplicate the .mp-backdrop / .mp-modal block
     from chat.legacy.html lines 75-111. If style.css refactor lands
     in the same sprint, drop this <style> tag entirely.) */
</style>

<div class="mp-backdrop" id="airgap-backdrop" role="dialog"
     aria-modal="true" aria-labelledby="airgap-title">
  <div class="mp-modal">
    <div class="mp-head">
      <h3 id="airgap-title">
        <span id="airgap-mode-pill" class="mp-pill">airgapped</span>
        Network policy
      </h3>
      <button class="mp-close" id="airgap-close" type="button">Close</button>
    </div>

    <p class="chat-sub" id="airgap-definition" style="margin:0 0 12px">
      <!-- Populated from /api/airgap/status -->
    </p>

    <div id="airgap-host-probe" style="display:none; margin: 0 0 12px">
      <!-- Shown only when BUDDY_EGRESS_PROBE=1.
           Text varies: "Your host has internet but the lab refuses to use it." vs
           "Your host can't reach the internet either." -->
    </div>

    <h4 style="margin: 12px 0 4px; font-size: 13px;">Recent activity</h4>
    <div class="mp-models-list" id="airgap-activity-list">
      <!-- Populated rows like:
        <div class="airgap-row">
          <span class="mp-pill warn">blocked</span>
          <code>huggingface.co</code>
          <span class="chat-muted">arail.agents._builtin_buddy</span>
          <time datetime="...">14:33</time>
        </div>
      -->
    </div>
    <p class="chat-muted" id="airgap-activity-empty"
       style="display:none; margin-top: 6px;">
      No outbound network attempts recorded yet.
    </p>

    <details style="margin-top: 14px;">
      <summary class="chat-muted" style="cursor:pointer;">
        Known gaps — what isn't wrapped
      </summary>
      <ul id="airgap-gaps-list" class="mp-note" style="padding-left: 18px;">
        <!-- One <li> per known_gaps entry -->
      </ul>
      <p class="mp-note" style="margin-top: 6px;">
        The Python-level guard catches <code>requests</code> and
        <code>urllib.request</code>. Other clients
        (<code>httpx</code>, <code>aiohttp</code>, raw sockets,
        subprocess <code>curl</code>) are not wrapped — see
        <a href="/docs/PRIVACY.md">docs/PRIVACY.md</a> for the full
        list. The threat model is well-meaning agent code, not
        an adversary on this host.
      </p>
    </details>
  </div>
</div>
```

**JS hook (in `static/nav.js`):**

```js
// nav.js — add to existing setup
const badge = document.getElementById('mode-badge');
const backdrop = document.getElementById('airgap-backdrop');
if (badge && backdrop) {
  badge.style.cursor = 'pointer';
  badge.addEventListener('click', async () => {
    const r = await fetch('/api/airgap/status');
    const data = await r.json();
    document.getElementById('airgap-mode-pill').textContent = data.lab_mode;
    document.getElementById('airgap-mode-pill').className =
      'mp-pill ' + (data.lab_mode === 'airgapped' ? 'ok' : 'warn');
    document.getElementById('airgap-definition').textContent = data.definition;
    // ...populate recent_activity, known_gaps, host probe
    backdrop.classList.add('open');
  });
  document.getElementById('airgap-close').addEventListener('click',
    () => backdrop.classList.remove('open'));
  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) backdrop.classList.remove('open');
  });
}
```

The base template (`chat.legacy.html` and any other entrypoint that
includes `_nav.html`) gets a `{% include '_airgap_modal.html' %}` near
the bottom of `<body>`, alongside the existing `mp-backdrop` for
providers.

---

## Buddy watcher spec

**New function** in `lab/pkb/agents/buddy/buddy.py` and the parallel
`src/arail/agents/_builtin_buddy.py` (both must be updated; they are
parallel copies — see §13):

```python
def _watch_airgap_events() -> Optional[Observation]:
    """Tail egress.jsonl + detect LAB_MODE toggles.

    Polled on the standard 90s watcher cadence (same as the other
    _watch_* functions). Reads two pieces of per-agent state from
    state.json (under the buddy agent dir):

      - last_egress_offset: int — byte offset into egress.jsonl
      - last_lab_mode: str — last seen 'airgapped' | 'hybrid'

    Returns at most one Observation per tick — the most recent novel
    event wins. State is persisted via the host's update_workflow.

    Cooldown: 5 min on the airgap-event watcher key, layered on top
    of the global 5-min cooldown so a polling loop that triggers a
    block every 30s collapses to one suggestion every 5 min."""
```

**Cadence:** 90s (reuse). For a high-frequency polling agent that
generates a block every 5s, the per-watcher cooldown caps Buddy at one
suggestion per 5 min (matches the existing watcher cooldown convention
in `_OBSERVATION_COOLDOWNS`).

**State storage:** `lab/pkb/agents/buddy/state.json` already holds
per-watcher `last_emitted_at` timestamps. Add two top-level keys:

```json
{
  "last_emitted_at": { ... existing ... },
  "airgap_last_egress_offset": 12847,
  "airgap_last_lab_mode": "airgapped"
}
```

(Builder: extend the existing JSON schema; use `state.get(key, default)`
patterns so old state files still load.)

**Suggestion text — exact copy:**

| Trigger | Severity | Suggestion text |
|---|---|---|
| New block detected | `suggest` | `f"Just blocked an agent fetch to {url_host}. That's airgapped doing its job."` |
| Mode toggle airgapped → hybrid | `info` | `"Door's open now — agent fetches go through. Per-domain consent still gates browser/curator."` |
| Mode toggle hybrid → airgapped | `info` | `"Sealed back up. Agents can't reach the public internet."` |
| Host probe mismatch (probe=true, mode=airgapped) | `info` | `"Your host has internet, but the lab refuses to use it. That's the honest disclosure."` |

Suggestion `data` payload always includes `{"link": "/api/airgap/status"}`
so the chat heads-up can surface a "show details" button that opens the
modal.

**Acceptance test (`tests/test_buddy_airgap_watcher.py`):** fixture
writes a fake egress.jsonl with 3 blocks, monkeypatches the buddy
host's state read/write, calls `_watch_airgap_events()`, asserts the
returned Observation's `fact` matches the most-recent block's host.

---

## Test strategy

### Unit (`tests/test_airgap_helpers.py`)

- `lab_mode()` returns `"airgapped"` when env unset; `"hybrid"` when
  `LAB_MODE=hybrid`; `"airgapped"` when `LAB_MODE=garbage` (fail-closed).
- `is_local_host("127.0.0.1") == True`, `("localhost") == True`,
  `("::1") == True`, `("192.168.1.50") == True`,
  `("10.0.0.5") == True`, `("172.16.5.5") == True`,
  `("172.32.0.1") == False` (172.x is only RFC1918 in 16-31),
  `("169.254.1.1") == True`, `("8.8.8.8") == False`,
  `("huggingface.co") == False` (assuming no rebind).
- `is_local_ip("fe80::1") == True`, `("2001:db8::1") == False`.
- `should_allow_egress("https://huggingface.co/...")` → `(False, "airgapped")`
  in airgapped, `(True, "hybrid")` in hybrid.
- `should_allow_egress("http://127.0.0.1:11434/api/tags")` →
  `(True, "local")` in both modes.
- `should_allow_egress("not a url")` → `(False, "invalid")`.
- DNS-rebind defense: monkeypatch `socket.gethostbyname` to return
  `127.0.0.1` for `evil.example.com`; assert `is_local_host("evil.example.com")`
  returns True (we accept DNS-trust at this layer; this test pins the
  documented behavior).

**Monkeypatch surfaces:** `monkeypatch.setenv("LAB_MODE", "airgapped"|"hybrid")`,
`monkeypatch.setattr(socket, "gethostbyname", lambda h: ...)`.

### Integration (`tests/test_egress_guard.py`)

- `LAB_MODE=airgapped`, `install_guard()` called:
  - `requests.get("https://example.com")` raises `EgressBlocked`.
  - `requests.get("http://127.0.0.1:65535/x", timeout=0.1)` raises
    `ConnectionRefusedError` or `requests.ConnectionError` — *NOT*
    `EgressBlocked`. Pin this distinction explicitly.
  - `requests.get("http://192.168.1.50:11434/api/tags", timeout=0.1)` →
    guard passes; actual call may time out or fail if no LAN box, but
    `EgressBlocked` is NOT raised.
  - `requests.get("http://10.0.0.5/x", timeout=0.1)` → not `EgressBlocked`.
  - `urllib.request.urlopen("https://example.com")` raises `EgressBlocked`.
  - `urllib.request.urlopen("http://127.0.0.1:65535/x")` raises a
    connection error, not `EgressBlocked`.
  - `s = requests.Session(); s.get("https://example.com")` raises
    `EgressBlocked` (Session-level inheritance test).
- `LAB_MODE=hybrid`: all of the above attempt the actual call and either
  succeed or raise a connection error — NEVER `EgressBlocked`.
- `with allow_egress("test"): requests.get("https://example.com")` in
  hybrid → no `EgressBlocked`; `record_allow` line written.
- `with allow_egress("test")` in airgapped → raises `EgressBlocked`
  *immediately* on the `with` entry (before the body executes).
- `allow_egress("")` raises `ValueError`.
- A blocked attempt produces exactly one new line in egress.jsonl with
  expected schema.
- `EgressBlocked` is a `RuntimeError` subclass.
- `install_guard()` called twice in the same process → second call is
  a no-op (idempotency).

**Monkeypatch surfaces:** `monkeypatch.setenv("LAB_MODE", ...)`,
`monkeypatch.setattr(arail.airgap, "is_airgapped", lambda: ...)` (for
unit-of-the-guard tests that don't want the env round-trip),
`monkeypatch.setattr(arail.egress, "record_block", mock)`.

### Buddy watcher (`tests/test_buddy_airgap_watcher.py`)

- Fixture: a temp dir with `egress.jsonl` containing 3 sample blocks.
- Mock buddy host returning that path from `get_activity_log_path()`'s
  sibling-resolved egress file.
- Call `_watch_airgap_events()` once → returns an `Observation` whose
  `fact` mentions the most recent host.
- Advance state.last_egress_offset; call again → returns None (no novel
  event).
- Append a new block to the file; call again → returns Observation for
  the new block.
- Toggle env from airgapped to hybrid; call → returns the
  toggle-specific Observation; state.last_lab_mode updated.

### Bypass-attempt suite (QA security 20%)

QA runs these and pins documented behavior. Each tests both
`LAB_MODE=airgapped` and `hybrid`.

| Attempt | Airgapped expected | Hybrid expected |
|---|---|---|
| `requests.get("https://example.com")` | `EgressBlocked` | succeeds (or normal HTTP error) |
| `requests.Session().get("https://example.com")` | `EgressBlocked` | succeeds |
| `urllib.request.urlopen("https://example.com")` | `EgressBlocked` | succeeds |
| `httpx.get("https://example.com")` | succeeds (documented gap) | succeeds |
| `aiohttp.ClientSession().get("https://example.com")` (if installed) | succeeds (documented gap) | succeeds |
| `socket.socket().connect(("8.8.8.8", 80))` | succeeds (documented gap) | succeeds |
| `subprocess.run(["curl", "-s", "https://example.com"])` | succeeds (documented gap) | succeeds |
| `os.system("curl -s https://example.com")` | succeeds (documented gap) | succeeds |
| `requests.get("http://192.168.1.50/x", timeout=0.1)` | not `EgressBlocked` | not `EgressBlocked` |
| `requests.get("http://127.0.0.1:65535/x", timeout=0.1)` | not `EgressBlocked` | not `EgressBlocked` |

Pinning the documented gaps as *passing* tests is what makes the README's
new claim falsifiable. If a future sprint wraps `httpx`, the test flips
direction and the README updates.

### Regression

- `tests/test_program_drafter.py::test_drafter_skips_external_fetch_in_airgapped_mode`
  passes after the helper consolidation (replace inline env read with
  `not is_airgapped()`).
- `tests/test_setup_extras.py` and `tests/test_admin_security_endpoints.py`
  pass against the new helpers (they monkeypatch env vars; the
  consolidated helpers must honor the same names).
- `tests/test_pkb_index_qa.py` (the existing socket-monkeypatch fixture)
  still passes — our guard does not touch socket directly.

### Performance

Not a hot path. The `requests.send()` overhead per call is one
`urlparse()`, one `is_local_host()`, possibly one `socket.gethostbyname()`
for non-IP hosts. Acceptance: < 5 ms added latency per request. Not
benchmarked formally; QA spot-checks the curator loop's tick time
before/after.

### Security

The bypass-attempt suite *is* the security pass for this sprint
(QA's 20% allocation). Plus:

- `EgressBlocked` carries `url_host`/`caller`/`reason` but does NOT
  carry full URL or query string (avoid leaking secrets in tracebacks).
- `record_block` writes `url_host` only (host part of the URL); never
  query string, never path. Same reason.
- `egress.jsonl` is `chmod 0640` — readable only by the running user.
- The `BUDDY_EGRESS_PROBE` documentation must explicitly state: "this
  fires one TCP connect to 1.1.1.1:443. No payload, no data uploaded.
  It exists to surface the honest 'your host has internet' disclosure."

---

## Failure modes table

| Failure | Detection | Recovery |
|---|---|---|
| Agent constructs `requests.Session()` *before* `install_guard()` runs (e.g. backend.py module-level) | Session has the default adapter, not Guarded. Detected only by code review. | Document as known gap; audit current sites are localhost-only; add `# noqa-airgap: localhost-only` comments. |
| `@allow_egress` leaks across threads via copied contextvar in `asyncio.create_task` | Fired tasks see the bypass even after the with-block exits in the spawning frame. | Documented; v1 only uses `allow_egress` for inline awaits in provider test endpoints. Test pins this pattern; future async use needs a re-review. |
| Disk full / readonly fs when writing `egress.jsonl` | `open(..., "a")` raises `OSError`. | `record_block` catches, logs to stderr, returns. The `EgressBlocked` raise still happens — logging failure does not weaken enforcement. |
| Concurrent writers to `egress.jsonl` | Multiple agent tasks blocking simultaneously can interleave lines. | One write per `EgressBlocked` is a single `f.write(line)` — atomic on POSIX for sub-PIPE_BUF writes (~4KB). Lines are ~150 bytes. No locking needed. Documented. |
| Agent code wraps `requests.get` in `try: ... except Exception:` and swallows `EgressBlocked` | `EgressBlocked` is a `RuntimeError`, not subclass of `Exception` chain caught by typical "ignore network errors" patterns? — actually `RuntimeError IS an Exception subclass`, so a bare `except Exception:` *will* catch it. | Documented as a known limit. The block was still recorded to `egress.jsonl` (recovery: audit log is the source of truth, not the traceback). PRIVACY.md notes "agents that swallow exceptions still get logged in the audit log." |
| DNS rebinding: attacker's `evil.example.com` resolves to `127.0.0.1` | `socket.gethostbyname` returns `127.0.0.1`; our local-IP check passes; request goes through. | This is a known limit. Threat model is well-meaning agents, not adversarial DNS. We do the IP-resolved check (defeats trivial rebinds where the *hostname* is suggestive). Documented in PRIVACY.md. |
| IPv6 link-local with zone identifier (e.g. `fe80::1%en0`) | `ipaddress.ip_address("fe80::1%en0")` raises `ValueError`. | Strip zone suffix before parsing. Test covers. |
| `socket.gethostbyname` blocks for seconds on a slow resolver | Guard's local check stalls every request. | DNS resolution is wrapped with a 1.5s timeout via `socket.setdefaulttimeout()` context, OR cached for 60s in process-local LRU. Builder picks whichever is simpler; both are acceptable. |
| `install_guard()` runs but a future agent imports `requests` *before* the monkeypatch lands | Module-level adapter is mounted at adapter-class level; monkeypatch replaces the class, not instances. Pre-existing instances keep their old adapter. | Module-level monkeypatch on `requests.adapters.HTTPAdapter` ensures any *new* Session gets guarded. The 3 backends.py module-level Session sites are the only known pre-existing instances; documented. |
| Subprocess agent shells out to `curl` | Egress doesn't go through Python at all. | Out of scope (PLAN.md). Documented in §13 and PRIVACY.md. |
| User reads `egress.jsonl` directly with a tool that doesn't tolerate rotation | `.1` rotation can confuse logrotate-style consumers. | Single-step rotation is documented in the schema doc inside the modal's Known Gaps detail block. `.1` is a sibling, not a numbered chain. |
| Test isolation: a prior test's `install_guard()` poisons a later test's `requests` baseline | Adapter monkeypatch persists across tests. | `egress._reset_for_tests()` exposed for fixture teardown. Used in `tests/conftest.py` autouse fixture. |
| Buddy watcher reads stale `egress.jsonl` after rotation (offset > new file size) | Tail returns nothing; no false alert. | After rotation, `last_egress_offset` is invalid; next read sees `offset > size`, resets to 0, walks from start. State recovery built into the watcher. |

---

## README + PRIVACY.md replacement copy

The builder pastes these verbatim. No improvisation.

### `README.md:60-62` — replace

**Before:**
> External providers (Claude, NVIDIA NIM, OpenRouter, HuggingFace) are
> reachable in both tiers via plain HTTP — `max` just adds the official SDKs
> and LangChain/LangGraph for heavier orchestration. **Airgapped mode blocks
> every cloud provider by default.** Flip `LAB_MODE=hybrid` in `.env` to open
> the door.

**After:**
> External providers (Claude, NVIDIA NIM, OpenRouter, HuggingFace) are
> reachable in both tiers via plain HTTP — `max` just adds the official SDKs
> and LangChain/LangGraph for heavier orchestration. **Airgapped mode is the
> default: agents cannot collect information from the public internet.**
> Local services on this machine and your private network (loopback,
> RFC1918, link-local) stay reachable so a LAN GPU box keeps working. Flip
> `LAB_MODE=hybrid` in `.env` to allow agent fetches to cloud vendors.

### `README.md:96-99` — replace

**Before:**
> **Airgapped guard.** By default `LAB_MODE=airgapped` — all cloud providers
> are locked. The Compute Source row shows a banner, cloud radios grey out,
> and the save/test/models endpoints refuse. Set `LAB_MODE=hybrid` in `.env`
> and restart to enable external vendors.

**After:**
> **Airgapped guard.** By default `LAB_MODE=airgapped`. Agent-originated
> outbound calls through `requests` and `urllib` are denied unless the
> destination resolves to loopback, RFC1918, or link-local. Denials raise
> `EgressBlocked` and append one line to `lab/data/egress.jsonl` for audit.
> The Compute Source row shows a banner, cloud radios grey out, and the
> save/test/models endpoints refuse. Click the **Airgapped** badge in the
> nav to see the operational definition and the most recent blocks. Set
> `LAB_MODE=hybrid` in `.env` and restart to allow agent fetches.

### `README.md:143-145` — replace

**Before:**
> By default `LAB_MODE=airgapped` — the lab makes zero network calls. Every
> inference request goes to your machine. The dashboard has a badge that says
> *Airgapped* so you never wonder.

**After:**
> By default `LAB_MODE=airgapped` — agents in the lab cannot collect
> information from the public internet. Calls to loopback and your private
> network still work, so a LAN GPU box (Ollama, vLLM, an aerollm node)
> keeps inferring without changes. Cloud-provider APIs are blocked at the
> HTTP layer. The dashboard's **Airgapped** badge is clickable — it shows
> what is and isn't enforced, the recent blocks, and the known gaps
> (`httpx`, raw sockets, subprocess `curl`) the Python-level guard
> doesn't cover. The threat model is well-meaning agent code, not an
> adversary on this host — for that, run a host firewall.

### `docs/PRIVACY.md:28-48` — replace the "What hybrid mode sends" section with:

```markdown
## What airgapped mode enforces

`LAB_MODE=airgapped` (the default) blocks agent-originated calls
through `requests` and `urllib.request` to anything that isn't:

- Loopback: `127.0.0.0/8`, `::1`, `localhost`
- RFC1918: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
- Link-local: `169.254.0.0/16`, `fe80::/10`

The destination's hostname is resolved to an IP via the system
resolver and the IP is checked against those ranges (so a public
domain re-pointed at `127.0.0.1` is treated as local — that's a
known DNS-trust limit). Denials raise `EgressBlocked` (a
`RuntimeError` subclass) and append one structured line to
`lab/data/egress.jsonl`.

### Known gaps — what the Python-level guard does NOT catch

The guard wraps `requests` and `urllib.request`. It does NOT wrap:

- `httpx` — used by the open-notebook integration and the
  knowledge-canvas client, both for `localhost` only in this tree.
- `aiohttp` — not used in tree today.
- Raw sockets (`socket.socket()`) — wrapping these would break
  loopback connection paths underneath the wrapped libraries.
- Subprocess shells — `subprocess.run(["curl", ...])` and
  `os.system("curl ...")` go straight to the OS network stack.

These are documented gaps for the v1 guard. The threat model is
well-meaning agent code that uses standard libraries; it is not
an adversary on the host. For host-level enforcement, run a
firewall (`pf` on macOS, `iptables`/`ufw` on Linux).

### One opt-in network exemption — `BUDDY_EGRESS_PROBE`

Setting `BUDDY_EGRESS_PROBE=1` enables one outbound TCP connect to
`1.1.1.1:443` with a 1-second timeout. No payload, no DNS, no HTTP.
The probe exists so the airgap modal can show the honest disclosure
"your host has internet, but the lab refuses to use it." It is the
only audited exemption to the airgapped rule and is off by default.

## What hybrid mode sends

`LAB_MODE=hybrid` (opt-in) lets agent calls reach the public internet
via the same `requests`/`urllib` clients. The egress audit log still
records every outbound call (`reason: "hybrid"`) so the user can
inspect what was sent. Per-domain consent prompts (curator, browser)
remain in force on top of the guard.
```

(Builder: the rest of `PRIVACY.md` after this section stays. Only the
"What hybrid mode sends" header through the `Everything else stays
local.` line at line ~48 is replaced.)

---

## Tech debt

**Added:**

- A *third* place where the lab cares about modes (after `LAB_MODE`,
  `LAB_INTERNET_ENABLED`, `ARAIL_AUTORESEARCH_FETCH_EXTRAS`).
  Mitigated: `LAB_INTERNET_ENABLED` is dropped in this sprint;
  `ARAIL_AUTORESEARCH_FETCH_EXTRAS` is unchanged but now sits behind
  `is_airgapped()`.
- Two parallel buddy implementations (`lab/pkb/agents/buddy/buddy.py`
  and `src/arail/agents/_builtin_buddy.py`) — both must be edited
  in lockstep. This duplication predates the sprint; we don't fix it
  here. *Filed:* `learnings/2026-05-05-buddy-double-implementation.md`
  (builder writes a one-paragraph stub; full repaving is a separate
  sprint).
- Inline CSS for `mp-backdrop` / `mp-modal` in `chat.legacy.html`
  remains. The airgap modal copies the same classes; ideally those
  styles move to `static/style.css`. Recommendation: extract in a
  small follow-up commit, NOT this sprint.
- The contextvars-vs-asyncio.create_task semantics for `@allow_egress`
  are correct but subtle. Filed:
  `learnings/2026-05-05-allow-egress-task-scope.md` for the next
  contributor who reaches for it.

**Repaid:**

- Five duplicated `_is_airgapped()` / `_lab_mode()` helpers collapse
  to one (`src/arail/airgap.py`). Net win.
- The orphan `LAB_INTERNET_ENABLED` flag goes away — Buddy's HF papers
  fetch now sits behind the unified `is_airgapped()` gate.
- The lying README paragraphs become true. (Hard to call this "tech
  debt repaid" but it's the load-bearing user-trust improvement.)

**Net:** Negative debt. The new sources of truth replace more old
ones than they introduce.

---

## Files to touch (final)

Updated from PLAN.md. Builder reads only this table for implementation
order.

| # | File | Status | Change |
|---|---|---|---|
| 1 | `src/arail/airgap.py` | **new** | source of truth: `EgressBlocked`, `lab_mode`, `is_airgapped`, `is_local_host`, `is_local_ip`, `should_allow_egress` |
| 2 | `src/arail/egress.py` | **new** | `install_guard`, `record_block`, `record_allow`, `read_recent_blocks`, `allow_egress`, `probe_internet`, `GuardedHTTPAdapter`, `_GuardedHTTPHandler`/`_GuardedHTTPSHandler`, `_reset_for_tests` |
| 3 | `tests/conftest.py` | edit | add autouse fixture calling `egress._reset_for_tests()` between tests |
| 4 | `tests/test_airgap_helpers.py` | **new** | unit tests for §11 |
| 5 | `tests/test_egress_guard.py` | **new** | integration tests for §11 |
| 6 | `src/arail/config.py` | edit | re-export `lab_mode()` from `airgap`; drop `MODE` duplicate |
| 7 | `src/arail/portal/app.py` | edit | replace `_lab_mode()` / `_is_airgapped()` with `from arail.airgap import lab_mode, is_airgapped`; call `egress.install_guard()` at top of startup; add `GET /api/airgap/status` route |
| 8 | `src/arail/agents/loader.py` | edit | call `egress.install_guard()` first line of `load_all()` |
| 9 | `src/arail/research/program_drafter.py` | edit | replace `_allow_live_fetch` body with `not is_airgapped() and os.getenv(...) == "1"` |
| 10 | `src/arail/agents/curator.py` | edit | replace inline env reads (lines 73, 109) with `is_airgapped()` |
| 11 | `lab/pkb/agents/sre/sre.py` | edit | replace `_sre_lab_mode()` with `from arail.airgap import lab_mode` |
| 12 | `src/arail/agents/_builtin_sre.py` | edit | mirror sre.py changes (parallel implementation) |
| 13 | `lab/pkb/agents/buddy/buddy.py` | edit | drop `LAB_INTERNET_ENABLED` (line 758); fold the HF-papers fetch behind `is_airgapped()`; add `_watch_airgap_events()` and register in `WATCHERS` list |
| 14 | `src/arail/agents/_builtin_buddy.py` | edit | mirror buddy.py changes (parallel implementation) |
| 15 | `src/arail/agents/browser.py` | edit | replace local `_is_airgapped()` (line 54) with `from arail.airgap import is_airgapped` |
| 16 | `src/arail/router/backends.py` | edit | add `# noqa-airgap: localhost-only` comments at lines 231, 440, 590 (the pre-guard `requests.Session()` sites) |
| 17 | `src/arail/portal/templates/_nav.html` | edit | mark mode-badge clickable in *all* surfaces (not just dashboard); ensure it's wired to open the modal |
| 18 | `src/arail/portal/templates/_airgap_modal.html` | **new** | per §9 |
| 19 | `src/arail/portal/templates/chat.legacy.html` | edit | banner copy; `{% include '_airgap_modal.html' %}` at end of body; verify `mp-backdrop` CSS is shared |
| 20 | Other base templates that include `_nav.html` | edit (audit) | each must `{% include '_airgap_modal.html' %}` so the modal works on every page |
| 21 | `src/arail/portal/static/nav.js` | edit | wire badge → fetch `/api/airgap/status` → populate modal |
| 22 | `README.md` | edit | replace 60-62, 96-99, 143-145 with §11 copy verbatim |
| 23 | `docs/PRIVACY.md` | edit | replace 28-48 with §11 PRIVACY copy verbatim |
| 24 | `tests/test_buddy_airgap_watcher.py` | **new** | per §10 |
| 25 | `tests/test_program_drafter.py` | edit | extend existing `test_drafter_skips_external_fetch_in_airgapped_mode` to use new helper |
| 26 | `learnings/2026-05-05-buddy-double-implementation.md` | **new** | one-paragraph stub flagging the parallel-buddy debt |
| 27 | `learnings/2026-05-05-allow-egress-task-scope.md` | **new** | one-paragraph stub on contextvars semantics |

**Out of scope this sprint** (deliberately removed from the table):

- `static/style.css` extraction of `mp-*` modal classes — keep inline,
  follow-up.
- `core/knowledge-canvas/` httpx wrapping — that's a separate frontend
  service, not in the airgap threat surface.
- `src/arail/open_notebook_seed.py` httpx audit — already known
  localhost-only; no change needed.

---

## Recommended implementation order

1. **Layer 1 — single source of truth.** Write
   `src/arail/airgap.py` + `tests/test_airgap_helpers.py`. Get green
   before moving on.
2. **Layer 2 — egress guard.** Write `src/arail/egress.py` +
   `tests/test_egress_guard.py` + `tests/conftest.py` autouse fixture.
   Verify the guard is fully reset between tests.
3. **Wire in.** `portal/app.py` startup + `agents/loader.py` first-line
   `install_guard()`. Smoke-run `./arail start` and confirm boot is
   clean.
4. **Consolidate call sites.** Files 6, 9, 10, 11, 12, 15. Run the
   regression tests after each file.
5. **Buddy.** Files 13, 14, 24. Drop `LAB_INTERNET_ENABLED`; add the
   watcher; write the watcher test.
6. **API + modal.** Files 7 (`/api/airgap/status` route), 18, 19, 20,
   21. End-to-end click-the-badge smoke test.
7. **Docs.** Files 22, 23. Verbatim copy from §11. The README change
   is the load-bearing deliverable; don't paraphrase.
8. **Audit comments.** File 16. Add `# noqa-airgap: localhost-only`
   at the three known pre-guard Session sites.
9. **Learnings.** Files 26, 27. Two one-paragraph stubs.
10. **End-to-end manual demo.** Per VISION §3 and PLAN.md "End-to-end."
    Capture a screencap or asciicast in BUILD_LOG step 2.

---

## Failure modes + invariants — paranoid summary

Hard invariants the builder cannot break:

- `is_airgapped() == True` ⇒ no `requests.get(<non-local-host>)` returns
  successfully. Either pass-through to a local IP, or `EgressBlocked`.
- `EgressBlocked` is `isinstance(EgressBlocked(), RuntimeError)`.
- `install_guard()` is idempotent — second call is a no-op.
- `@allow_egress` in `airgapped` raises *before* the with-block body runs.
- `egress.jsonl` lines are valid JSON, one per line, with all five
  required fields.
- The README never says "zero network calls" again.
- The `BUDDY_EGRESS_PROBE` is the *only* documented exemption.

If any of these fail in REVIEW or QA, the verdict is BLOCK regardless
of test counts.

---

## Non-goals

Explicit, expanded from PLAN.md so QA doesn't write tests for them:

- **OS-level firewalling.** No `pf` / `iptables` / `ufw` shell-out.
- **Blocking the user's own shell / REPL.** Only Python imports go
  through the guard; `python -c "import requests; requests.get(...)"`
  in another terminal is not blocked.
- **Subprocess agents.** Out-of-process agents (e.g. aerollm Phase-2
  HTTP bindings, future `subprocess.Popen([python, agent.py])`) bypass
  the guard. Documented gap; revisit when subprocess agents land.
- **Wrapping `httpx`, `aiohttp`, `urllib3`, raw sockets.** Documented
  gaps; the threat model is well-meaning code using standard libraries.
- **Theme/UI toggle awareness.** Buddy only watches `LAB_MODE` and
  `egress.jsonl` in v1. Generic event-bus is a follow-up.
- **`setup.sh` enforcement.** Initial weight downloads are pre-portal.
- **DNS adversary.** We trust the system resolver. A compromised
  resolver can defeat the IP-based local check; out of scope.
- **HTTP redirects from local services.** A local server at
  `127.0.0.1:8000` that returns a 302 to `https://example.com` would
  cause `requests` to follow the redirect; the second `send()` call is
  guarded, so the redirect *is* caught. Pin this with a test if there's
  time, but it's a happy-path consequence, not a separate goal.
- **Egress logs on `lab/data/egress.jsonl` schema versioning.** v1
  schema; if it changes, that's a future migration concern.
