"""egress — Python-level outbound network guard.

Installs a custom requests HTTPAdapter and a urllib opener that consult
``arail.airgap.should_allow_egress`` before passing a request through.

Usage (called automatically at portal startup and agent-loader time):

    from arail import egress
    egress.install_guard()

The guard is idempotent — subsequent calls are no-ops.  Tests that need
a fresh install call ``egress._reset_for_tests()``.

Bypass context manager (hybrid mode only):

    with egress.allow_egress("test the openrouter endpoint"):
        r = requests.get("https://openrouter.ai/api/v1/models", ...)

In airgapped mode, ``allow_egress`` raises ``EgressBlocked`` immediately
on entry — there is no escape hatch.  The only intentional exception is
``BUDDY_EGRESS_PROBE=1``, which uses a raw socket and never touches this
context manager (see ``probe_internet``).
"""

from __future__ import annotations

import contextlib
import inspect
import json
import logging
import os
import socket
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
import requests.adapters
import requests.sessions

from arail.airgap import EgressBlocked, is_airgapped, is_local_host, is_local_ip

try:
    from contextvars import ContextVar
except ImportError:  # pragma: no cover — Python < 3.7 guard
    raise RuntimeError("arail.egress requires Python 3.7+")

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

# Thread- and task-safe flag: when set, the current call stack is inside an
# @allow_egress context.  The value is the *reason* string supplied by the
# caller.  None means "no bypass active."
_allow_egress_var: ContextVar[Optional[str]] = ContextVar(
    "_allow_egress_var", default=None
)

# Idempotency guard — install_guard() is a no-op after the first call.
_INSTALLED: bool = False

# The original HTTPAdapter class before we monkeypatched it.
_ORIGINAL_HTTP_ADAPTER: type = requests.adapters.HTTPAdapter

# Process-level cache for the internet probe result {result: bool, ts: float}.
_PROBE_CACHE: dict = {}
_PROBE_CACHE_TTL: float = 60.0

# Path to the egress audit log (overridable for tests).
def _lab_data() -> Path:
    return Path(os.getenv("ARAIL_DATA_DIR", "lab/data"))


# ---------------------------------------------------------------------------
# Caller identification
# ---------------------------------------------------------------------------

_SKIP_MODULES = frozenset({
    "arail.egress",
    "arail.airgap",
    "requests.adapters",
    "requests.sessions",
    "requests.models",
    "requests.api",
    "urllib.request",
    "urllib3.connectionpool",
    "urllib3.connection",
})


def _current_caller() -> str:
    """Walk the stack and return the first frame outside the guard modules.

    Falls back to ``"unknown"`` if no useful frame is found.
    """
    try:
        for frame_info in inspect.stack():
            module = frame_info.frame.f_globals.get("__name__", "") or ""
            if module and not any(module.startswith(s) for s in _SKIP_MODULES):
                qualname = frame_info.frame.f_code.co_qualname if hasattr(
                    frame_info.frame.f_code, "co_qualname"
                ) else frame_info.frame.f_code.co_name
                return f"{module}.{qualname}"
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def record_block(url: str, caller: str, reason: str) -> None:
    """Append one structured line to ``lab/data/egress.jsonl``.

    Schema::

        {"ts": "2026-05-05T14:33:01Z",
         "url_host": "huggingface.co",
         "caller": "arail.agents._builtin_buddy._suggest_internet_correlation",
         "reason": "airgapped",
         "lab_mode": "airgapped"}

    Errors are caught and logged to stderr — the block itself still raises
    in the caller; logging failure must NOT prevent loud enforcement.

    Rotation: if file > 5 MB, rename to ``.1`` (overwriting any existing
    ``.1``). Then create a new empty file.
    """
    try:
        parsed = urlparse(url)
        url_host = parsed.hostname or url[:64] or "?"
    except Exception:  # noqa: BLE001
        url_host = "?"

    from arail.airgap import lab_mode as _lab_mode
    line = json.dumps({
        "ts": _utcnow(),
        "url_host": url_host,
        "caller": caller,
        "reason": reason,
        "lab_mode": _lab_mode(),
    }) + "\n"
    _write_jsonl_line(line)


def record_allow(url: str, caller: str, reason: str) -> None:
    """Audit trail for ``@allow_egress`` contexts that actually fired.

    Same schema as ``record_block`` but with ``reason='allow:<context-reason>'``.
    """
    try:
        parsed = urlparse(url)
        url_host = parsed.hostname or url[:64] or "?"
    except Exception:  # noqa: BLE001
        url_host = "?"

    from arail.airgap import lab_mode as _lab_mode
    line = json.dumps({
        "ts": _utcnow(),
        "url_host": url_host,
        "caller": caller,
        "reason": f"allow:{reason}",
        "lab_mode": _lab_mode(),
    }) + "\n"
    _write_jsonl_line(line)


def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_jsonl_line(line: str) -> None:
    """Write one line to egress.jsonl, rotating if > 5 MB."""
    try:
        lab_data = _lab_data()
        lab_data.mkdir(parents=True, exist_ok=True)
        path = lab_data / "egress.jsonl"

        # Rotate if oversized.
        if path.exists() and path.stat().st_size > 5 * 1024 * 1024:
            rotated = path.with_suffix(".jsonl.1")
            try:
                path.rename(rotated)
            except OSError as e:
                sys.stderr.write(f"[arail.egress] rotation failed: {e}\n")
                # Still attempt to write to the (possibly oversized) file.

        with path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()

        # chmod 0640 — readable by owner; group-read; no others.
        try:
            path.chmod(0o640)
        except OSError:
            pass  # Windows / containerized paths — best effort

    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[arail.egress] record failed: {e}\n")


def read_recent_blocks(n: int = 5) -> list[dict]:
    """Bounded read for the modal — last N entries by timestamp.

    Reads the tail of ``egress.jsonl`` using a chunked-from-end strategy
    (seek to end, read up to ~64KB, split lines, take last N).  Never
    full-file slurp.  If file missing or unreadable, returns ``[]``.
    """
    path = _lab_data() / "egress.jsonl"
    if not path.exists():
        return []
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            f.seek(max(0, size - 64 * 1024))
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
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Egress decision (shared logic for both adapter and urllib handler)
# ---------------------------------------------------------------------------

def _check_egress_or_raise(url: str) -> None:
    """Run the 4-step decision tree; raise EgressBlocked if denied."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
    except Exception:
        host = ""

    # 1. Local hosts always pass.
    if host and (is_local_host(host) or is_local_ip(host)):
        return

    # 2. Allow-context wins if active (will be audit-logged by the caller).
    active = _allow_egress_var.get(None)
    if active is not None:
        return  # caller logs the allow via record_allow

    # 3. Airgapped + non-local + no allow → deny loudly.
    if is_airgapped():
        caller = _current_caller()
        record_block(url, caller, "airgapped")
        raise EgressBlocked(host or "?", caller, "airgapped")

    # 4. Hybrid + non-local + no allow → pass through.


# ---------------------------------------------------------------------------
# Guarded HTTP adapter (requests)
# ---------------------------------------------------------------------------

class GuardedHTTPAdapter(requests.adapters.HTTPAdapter):
    """HTTPAdapter that consults the airgap policy before sending."""

    def send(self, request, **kwargs):  # type: ignore[override]
        url = request.url or ""
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
        except Exception:
            host = ""

        # 1. Local hosts always pass — that's the LAN-GPU-box rule.
        if host and (is_local_host(host) or is_local_ip(host)):
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
        return super().send(request, **kwargs)


# ---------------------------------------------------------------------------
# Guarded urllib handlers
# ---------------------------------------------------------------------------

class _GuardedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        _check_egress_or_raise(req.full_url)
        return super().http_open(req)


class _GuardedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        _check_egress_or_raise(req.full_url)
        return super().https_open(req)


# ---------------------------------------------------------------------------
# install_guard / _reset_for_tests
# ---------------------------------------------------------------------------

def install_guard() -> None:
    """Install the egress guard.  Idempotent; safe to call N times.

    Mounts a GuardedHTTPAdapter via a monkey-patch on
    ``requests.adapters.HTTPAdapter`` so any future ``requests.Session()``
    constructor inherits the guarded adapter.  (Without the monkey-patch,
    an agent calling ``requests.Session()`` directly gets a fresh default
    adapter and bypasses the guard.)

    Also installs a urllib opener via ``urllib.request.install_opener``
    that runs ``should_allow_egress`` in a request-handler hook before
    delegating to the default chain.

    Idempotency is enforced via the module-level ``_INSTALLED`` flag.
    Re-imports during test runs (which monkeypatch openers) don't
    re-install; tests that need to reset must call ``_reset_for_tests()``
    explicitly.
    """
    global _INSTALLED, _ORIGINAL_HTTP_ADAPTER

    if _INSTALLED:
        return

    # 1. Monkeypatch both requests.adapters.HTTPAdapter AND
    #    requests.sessions.HTTPAdapter so new Sessions are guarded.
    #    Session.__init__ does: from requests.adapters import HTTPAdapter
    #    which means it holds a local reference inside requests.sessions
    #    that we must also replace.
    _ORIGINAL_HTTP_ADAPTER = requests.adapters.HTTPAdapter
    requests.adapters.HTTPAdapter = GuardedHTTPAdapter  # type: ignore[misc]
    requests.sessions.HTTPAdapter = GuardedHTTPAdapter  # type: ignore[attr-defined]

    # 2. Install the urllib opener.
    opener = urllib.request.build_opener(
        _GuardedHTTPHandler, _GuardedHTTPSHandler
    )
    urllib.request.install_opener(opener)

    _INSTALLED = True
    _log.debug("arail.egress: guard installed (mode=%s)", "airgapped" if is_airgapped() else "hybrid")


def _reset_for_tests() -> None:
    """Reset the guard to un-installed state.  TEST USE ONLY.

    Restores the original ``requests.adapters.HTTPAdapter`` class and
    resets the module-level ``_INSTALLED`` flag so the next
    ``install_guard()`` call re-installs cleanly.

    The urllib opener cannot be reset without re-importing urllib.request;
    tests that care about urllib isolation must monkeypatch
    ``urllib.request.urlopen`` or ``_GuardedHTTPSHandler.https_open``
    directly.
    """
    global _INSTALLED
    requests.adapters.HTTPAdapter = _ORIGINAL_HTTP_ADAPTER  # type: ignore[misc]
    requests.sessions.HTTPAdapter = _ORIGINAL_HTTP_ADAPTER  # type: ignore[attr-defined]
    _INSTALLED = False


# ---------------------------------------------------------------------------
# @allow_egress context manager / decorator
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def allow_egress(reason: str):
    """Context manager (and decorator) that bypasses the guard with an
    audit-logged reason.

    HARD RULE: in airgapped mode, ``allow_egress`` raises ``EgressBlocked``
    *immediately on entry*, before yielding.  The only exception is the
    ``BUDDY_EGRESS_PROBE`` pathway, which uses raw socket and never
    touches this context manager.  Any future contributor who wants to
    allow egress in airgapped must edit this module and re-justify in a
    new sprint.  This is intentional ratchet logic.

    Also usable as a decorator::

        @allow_egress("save provider token by hitting /models for validation")
        def test_provider(provider, token): ...

    Reason validation:
    - non-empty string, < 200 chars (otherwise ``ValueError``)
    - logged via ``record_allow`` when bypass is consumed by a guard check

    Scope: applies to the calling stack frame and all sub-calls within
    the with-block / decorated function.  Sub-threads spawned inside
    the block do NOT inherit the bypass (contextvars semantics).

    asyncio subtlety: ``asyncio.create_task(coro)`` *does* copy the
    contextvars context to the task.  This means an ``allow_egress`` block
    that launches a task and returns will keep allowing egress in the task
    even after the with-block exits.  For v1 this is acceptable — the only
    caller pattern is "save/test/list provider token" which awaits inline.
    See ``learnings/2026-05-05-allow-egress-task-scope.md``.
    """
    if not isinstance(reason, str) or not reason or len(reason) > 200:
        raise ValueError(
            f"allow_egress reason must be a non-empty string < 200 chars; got {reason!r}"
        )
    if is_airgapped():
        # Hard ratchet: no escape hatch in airgapped.  The only intentional
        # exemption is BUDDY_EGRESS_PROBE which uses raw socket directly,
        # not this context manager.  See ARCHITECTURE.md §7.
        caller = _current_caller()
        raise EgressBlocked(
            "?", caller,
            f"allow_egress denied in airgapped: {reason!r}"
        )
    token = _allow_egress_var.set(reason)
    try:
        yield reason
    finally:
        _allow_egress_var.reset(token)


# ---------------------------------------------------------------------------
# Internet probe (opt-in)
# ---------------------------------------------------------------------------

def probe_internet() -> Optional[bool]:
    """Check whether the host can reach the internet.  Opt-in.

    Only runs when ``BUDDY_EGRESS_PROBE=1``.  Uses raw
    ``socket.socket(AF_INET, SOCK_STREAM)`` — bypasses our own guard
    intentionally.  One TCP connect to ``1.1.1.1:443`` with 1s timeout.
    No payload, no DNS, no HTTP.

    Result is cached for 60 seconds in process memory so repeated modal
    opens don't hammer the test.

    Returns ``True`` if the host can reach the internet, ``False`` if it
    cannot, ``None`` if the env var is not set.

    Writes a ``reason="probe"`` line to ``egress.jsonl`` so the user can
    see the single audited bypass in the modal.
    """
    if not os.getenv("BUDDY_EGRESS_PROBE", "").strip() in ("1", "true", "yes"):
        return None

    now = time.monotonic()
    cached = _PROBE_CACHE.get("result")
    if cached is not None and (now - _PROBE_CACHE.get("ts", 0)) < _PROBE_CACHE_TTL:
        return cached

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        try:
            s.connect(("1.1.1.1", 443))
            result = True
        except (OSError, socket.timeout):
            result = False
        finally:
            s.close()
    except Exception:  # noqa: BLE001
        result = False

    from arail.airgap import lab_mode as _lab_mode
    line = json.dumps({
        "ts": _utcnow(),
        "url_host": "1.1.1.1:443",
        "caller": "arail.egress.probe_internet",
        "reason": "probe",
        "lab_mode": _lab_mode(),
    }) + "\n"
    _write_jsonl_line(line)

    _PROBE_CACHE["result"] = result
    _PROBE_CACHE["ts"] = now
    return result
