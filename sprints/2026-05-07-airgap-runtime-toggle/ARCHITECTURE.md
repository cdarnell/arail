# Architecture: airgap-runtime-toggle

**Date:** 2026-05-07
**Sprint:** 2026-05-07-airgap-runtime-toggle
**Spec:** [VISION.md](./VISION.md), [SPRINT.md](./SPRINT.md)
**Prior art:** [../2026-05-05-airgap-honest-mode/ARCHITECTURE.md](../2026-05-05-airgap-honest-mode/ARCHITECTURE.md) (PR #35 — `arail.airgap`, `arail.egress`, `_airgap_modal.html`).

## Restatement

PR #35 made `LAB_MODE` a real security boundary but left the only mode-flip mechanism as `vim .env && restart`. This sprint adds a UI-driven persistent toggle: a button in the existing Network Policy modal that flips `LAB_MODE` between `airgapped` and `hybrid`. The flip is (a) immediate (mutates `os.environ` so the next `arail.airgap.lab_mode()` call sees the new value), (b) durable (rewrites `.env` atomically, preserving comments / quotes / blank lines / BOM / line endings byte-for-byte), (c) hard to fire by accident (two-step modal-confirm + 3s cool-down), and (d) refused outright when the portal is bound to a non-loopback address (the LAN-CSRF attack surface). Buddy's existing `_watch_airgap_events` tick already detects the new mode through `state.json`; no Buddy wiring changes.

## Assumptions

- Portal binds via `BIND_ADDR` env var (default `127.0.0.1`), read in `scripts/start.sh` and `app.py` siblings (lines 1163, 1230, 5980, etc.). The toggle endpoint reads the same env var to decide loopback vs LAN.
- The user's canonical config file is `.env` at the repo/lab root (per Decisions log, post-audit). NOT `lab/data/secrets.env` (that's API keys only). The path is resolvable as `Path(__file__).resolve().parents[N] / ".env"` from `app.py`; we wrap this in a `_resolve_env_path()` helper rather than guessing depth.
- `arail.airgap.lab_mode()` reads `os.getenv("LAB_MODE")` per call (verified — `airgap.py:56`). This means `os.environ["LAB_MODE"] = ...` makes the change effective immediately for in-process readers without a restart.
- Buddy's `_watch_airgap_events` polls `lab_mode()` per tick and writes `airgap_last_lab_mode` into `state.json` via the existing read-merge-write pattern (`_builtin_buddy.py:478-535`). No new direct writers needed; the toggle endpoint stays out of `state.json`.
- The portal is FastAPI (not Flask, despite legacy CLAUDE.md wording). Tests use `fastapi.testclient.TestClient`.
- Multiple concurrent toggle clicks come from at most a handful of browser tabs; in-memory token table sized for O(1) entries is fine.

## Data flow

```
   ┌────────────────┐       ┌──────────────────────────────────┐
   │ Network Policy │ click │  POST /api/airgap/toggle         │
   │   modal (UI)   │──────▶│   {target}                        │
   │ confirm panel  │       │   1. bind-address gate ───────────┼──▶ 403 (LAN bind)
   │  (3s cooldown) │       │   2. Origin / Sec-Fetch-Site CSRF─┼──▶ 403 (cross-origin)
   └────────────────┘       │   3. acquire per-path lock        │
          ▲                 │   4. issue confirm_token (TTL 30s)│──▶ 409 + token
          │                 │   5. on 2nd POST w/ token:        │
          │ pill update     │      • read .env, parse           │
          │ + recent-toggle │      • mutate LAB_MODE line       │
          │ row             │      • atomic write (.tmp+replace)│
          │                 │      • chmod 600                  │
          │                 │      • os.environ["LAB_MODE"] = … │
          │                 │      • append airgap_audit.jsonl  │
          │                 │      • emit activity-log line     │
          └─────────────────┤   6. release lock, return 200     │
                            └──────────────────────────────────┘
                                            │
                                            ▼
                          (next Buddy tick)  _watch_airgap_events
                                            │
                                            ▼
                                    state.json updated
                                    Observation posted
```

## Interface contracts

### `src/arail/env_writer.py` (NEW)

Public API:

- `read_env_var(path: Path, key: str) -> str | None`
  Pre: `path` may or may not exist. `key` matches `[A-Za-z_][A-Za-z0-9_]*`.
  Post: returns the *unquoted* current value (last assignment wins, matching dotenv semantics) or `None` if absent / file missing.

- `set_env_var(path: Path, key: str, value: str) -> dict`
  Pre: `path`'s parent directory exists. `path` is either absent, a regular file, or refuses to write. `key` matches identifier regex; `value` contains no NUL byte and no newline.
  Post: returns `{"old_value": str | None, "new_value": str, "changed": bool, "appended": bool}`. On `changed=False`, the file is not rewritten (no temp churn). On success the file's mode is `0o600` and the on-disk LAB_MODE matches `value`.
  Raises: `EnvWriterError` (subclass of `OSError`) on symlink target, on parent-dir non-existent, on EISDIR. Never raises for "key missing" — appends.

Internal:

- `_parse_lines(text: str) -> list[Line]` — `Line` is a small dataclass: `{kind: 'blank'|'comment'|'assign'|'malformed', raw: str, key: str|None, value_raw: str|None, quote: ''|'"'|"'", inline_comment: str}`. Preserves the trailing newline style of each line.
- `_serialize_lines(lines, key, value) -> str` — finds *first* `assign` matching `key`, replaces its `value_raw` with the requoted `value` (preserving original `quote` style), preserves `inline_comment`. If no match, appends a new `assign` line with a leading marker comment `# set by arail portal toggle (UTC <isoformat>)` and quoting only when value contains spaces or `#`. Multiple matches → mutate first; emit `logging.warning("env_writer: %d duplicate definitions of %s in %s", n, key, path)`. Ensures final newline.
- `_atomic_write(path: Path, text: str, encoding: str, has_bom: bool, newline: str) -> None` — see §5.
- `_LOCKS: WeakValueDictionary[Path, threading.Lock]` keyed on the **resolved absolute path** so multiple `Path` objects pointing at the same file share a lock. Helper `_lock_for(path: Path) -> threading.Lock` does `path.resolve()` then dict insert under a module-level `_LOCKS_GUARD = threading.Lock()`. WeakValueDictionary lets the lock object GC away when no one holds it.

### `POST /api/airgap/toggle` (NEW route in `src/arail/portal/app.py`)

Request: `{"target": "airgapped" | "hybrid", "confirm_token": str | null}` JSON body.

Response (200, success):
```json
{
  "lab_mode": "hybrid",
  "previous": "airgapped",
  "env_path": "/path/to/.env",
  "took_effect_at": "2026-05-07T18:22:01.123Z",
  "appended": false
}
```

Errors:

| Code | When | Body |
|---|---|---|
| 400 | missing or invalid `target` (not in `{"airgapped","hybrid"}`) | `{"error":"invalid_target"}` |
| 403 | `BIND_ADDR` not in `{"127.0.0.1","::1","localhost"}` | `{"error":"bind_not_loopback","message":"Edit `.env` directly — toggle disabled when bound to non-loopback."}` |
| 403 | `Origin` / `Sec-Fetch-Site` not same-origin (cross-tab CSRF) | `{"error":"cross_origin"}` |
| 409 | `confirm_token` missing, mismatched, expired, or scoped to a different `target` | `{"error":"need_confirm","confirm_token":"<new>", "expires_in":30}` |
| 500 | `EnvWriterError` raised (or unexpected) | `{"error":"env_write_failed"}` — **path/contents must NOT appear in body**; logged server-side only |

Confirm-token table (module-level, in `app.py` near the route):

```python
_TOGGLE_TOKENS: dict[str, _TokenEntry] = {}
_TOGGLE_TOKENS_LOCK = threading.Lock()

@dataclass(frozen=True)
class _TokenEntry:
    token: str          # secrets.token_urlsafe(24)
    target: str         # "airgapped" | "hybrid"
    issued_at: float    # time.monotonic()
    expires_at: float   # issued_at + 30.0
```

- Token lookup is done under `_TOGGLE_TOKENS_LOCK`; on success the token is **deleted** (single-use).
- On every issuance/lookup the table is opportunistically purged of expired entries.
- Issuance for the **same target** invalidates any older outstanding token for that target (so two simultaneous "first" requests don't both succeed).

## Bind-address detection

```python
def _toggle_bind_is_loopback() -> bool:
    bind = os.getenv("BIND_ADDR", "127.0.0.1").strip().lower()
    return bind in {"127.0.0.1", "::1", "localhost"}
```

The compare is against the env var the portal was started with — same source of truth as `start.sh` and the rest of `app.py`. We do **not** introspect the running socket (uvicorn's bind isn't trivially queryable post-start, and disagreement between env and runtime would be an environment bug we don't try to paper over).

## The `.env` rewriter — exact pseudocode

```python
def set_env_var(path: Path, key: str, value: str) -> dict:
    # Refuse symlinks outright (security: no following).
    if path.is_symlink():
        raise EnvWriterError(f"refusing to write through symlink: {path}")
    if not _IDENT.fullmatch(key):
        raise EnvWriterError(f"invalid key: {key!r}")
    if "\n" in value or "\x00" in value:
        raise EnvWriterError("value contains forbidden chars")

    lock = _lock_for(path)
    with lock:
        # 1. Read (or treat absent as empty).
        try:
            raw_bytes = path.read_bytes()
        except FileNotFoundError:
            raw_bytes = b""

        # 2. Detect BOM, encoding, newline style.
        has_bom = raw_bytes.startswith(b"\xef\xbb\xbf")
        body = raw_bytes[3:] if has_bom else raw_bytes
        text = body.decode("utf-8")
        nl = "\r\n" if text.count("\r\n") > text.count("\n") - text.count("\r\n") else "\n"

        # 3. Parse line by line. Each line keeps its own trailing newline (or "" for last).
        lines = _parse_lines(text)

        # 4. Mutate.
        old_value = None
        changed = False
        appended = False
        first_match = None
        dup_count = 0
        for i, ln in enumerate(lines):
            if ln.kind == "assign" and ln.key == key:
                if first_match is None:
                    first_match = i
                    old_value = ln.unquoted_value
                else:
                    dup_count += 1

        if first_match is not None:
            ln = lines[first_match]
            if ln.unquoted_value == value:
                # No-op write — return early WITHOUT touching the file.
                return {"old_value": old_value, "new_value": value,
                        "changed": False, "appended": False}
            lines[first_match] = ln.with_value(value)  # preserves quote + inline_comment
            changed = True
            if dup_count:
                log.warning("env_writer: %d extra '%s=' lines in %s; left untouched",
                            dup_count, key, path)
        else:
            # Append. Add a separator blank if last line isn't blank.
            if lines and lines[-1].kind != "blank":
                lines.append(Line.blank(nl))
            lines.append(Line.comment(f"# set by arail portal toggle ({_utcnow_iso()})", nl))
            lines.append(Line.assign(key, value, nl, quote=""))
            changed = True
            appended = True

        # 5. Serialize, ensure final newline.
        out_text = "".join(ln.raw for ln in lines)
        if not out_text.endswith(nl):
            out_text += nl

        # 6. Atomic write.
        out_bytes = (b"\xef\xbb\xbf" if has_bom else b"") + out_text.encode("utf-8")
        _atomic_write(path, out_bytes)

        return {"old_value": old_value, "new_value": value,
                "changed": True, "appended": appended}
```

`_parse_lines` rules (per line, **exact**):

1. Split on `\r\n` or `\n`, retaining the terminator as part of the `raw` field.
2. If stripped line is empty → `kind="blank"`.
3. If first non-whitespace char is `#` → `kind="comment"`.
4. Else match regex `^\s*(?P<k>[A-Za-z_][A-Za-z0-9_]*)\s*=(?P<rest>.*?)(?:\s+#(?P<inline>.*))?\s*(?P<term>\r?\n|$)`. If matched:
   - `rest` is the value field. Detect quote: starts with `"` and ends with `"` → `quote='"'`, `value_raw` = inner; same for `'`. Otherwise `quote=""`.
   - `inline_comment` (if any) is preserved; on rewrite we re-emit it as ` # <inline>` after the new value.
5. Else `kind="malformed"` — passthrough untouched.

`Line.with_value(new_value)` rebuilds `raw`: indent + `key=` + (quoted-or-not per `quote`) + (` # ` + inline_comment if any) + terminator. Quoting rules: if original had a quote, keep that quote; if `value` contains a space, `#`, or `=`, force `"`-quoting on append-path only.

## Atomic write

```python
def _atomic_write(path: Path, data: bytes) -> None:
    parent = path.parent
    suffix = f".tmp.{os.getpid()}.{secrets.token_hex(4)}"
    tmp = parent / (path.name + suffix)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)  # explicit, in case umask interfered
        os.replace(tmp, path)  # POSIX atomic on same filesystem
    except BaseException:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise
```

Invariants:
- If the process crashes before `os.replace`, the original `.env` is untouched and a stray `.env.tmp.<pid>.<hex>` may remain (cleaned up next toggle if startup decides to sweep — out of scope this sprint; left as a follow-up).
- `os.replace` is atomic on POSIX (same filesystem) and on Windows since Python 3.3.
- `O_EXCL` ensures we never write through an attacker-pre-placed temp file.

## Concurrency

- Per-path `threading.Lock` (via `_lock_for(path)`) serializes all writers against a given resolved path. Two simultaneous successful confirm-tokens for opposite targets → first acquires the lock, writes; second waits, then reads the post-first-write state and decides changed vs no-op.
- Confirm-token issuance is serialized under `_TOGGLE_TOKENS_LOCK`. Issuing a new token for an existing target invalidates the prior one for that target. (So racing first-step requests cannot both end up holding "live" tokens for the same flip.)
- Buddy's watcher tick reads `lab_mode()` (a pure `os.getenv` call) and writes `state.json` via its own merge pattern. The watcher does **not** read `.env`, so a watcher tick interleaving mid-rewrite cannot see a torn file. The toggle endpoint sets `os.environ` only after `os.replace` succeeds.

## Side effects on toggle success (ordered, exact)

1. `os.replace(tmp, .env)` — durable.
2. `os.environ["LAB_MODE"] = target` — in-process visible to all subsequent `lab_mode()` calls.
3. Append to `lab/data/airgap_audit.jsonl` (NEW file; chmod 0600 on create) one line:
   `{"ts":"<iso>","from":"<previous>","to":"<target>","source_ip":"<request.client.host>","confirmed":true,"appended":<bool>}`.
   Reasoning for a new file vs `egress.jsonl`: `egress.jsonl` is "outbound network attempts." A mode toggle isn't one. Mixing them muddies the log shape and the modal's "Recent activity" rendering (which pills `kind: blocked|allowed`).
4. Emit activity-log line via the existing `arail.activity` (or whichever module the airgap status route reads from for "recent_activity" — verify in builder phase): `"agents can now reach the internet"` (→ hybrid) or `"all network access disabled"` (→ airgapped).
5. Return 200.

Order is load-bearing: `os.environ` mutated **after** disk write so a write failure doesn't leave the in-memory state lying about persistence. The audit-log append after `os.environ` so the audit reflects ground truth.

Buddy ordering: the next `_watch_airgap_events` tick (≤ 60s by default) reads the new `lab_mode()`, sees mismatch with `state.json["airgap_last_lab_mode"]`, posts the Observation, updates state. **No** changes to `_builtin_buddy.py` in this sprint — verified by re-reading `_watch_airgap_events` at lines 478-535.

## Frontend — toggle button + confirm flow

Edits to `src/arail/portal/templates/_airgap_modal.html`:

Add (after the `Recent activity` block, before `<details>`):

```html
<div id="airgap-toggle-section" style="margin-top: 14px; padding: 10px;
     border: 1px solid #2b2b2b; border-radius: 6px;">
  <div id="airgap-toggle-bind-warning" style="display:none; color:#e6b478; font-size:12px;">
    Edit <code>.env</code> directly — toggle disabled when the lab is bound
    beyond loopback (BIND_ADDR ≠ 127.0.0.1).
  </div>
  <button id="airgap-toggle-btn" type="button" class="mp-close"
          style="display:none;">…</button>
  <div id="airgap-toggle-confirm" style="display:none; margin-top: 10px;
       padding: 10px; background: #19140c; border: 1px solid #6a4d2f; border-radius:6px;">
    <p style="margin:0 0 8px; font-size: 12px; color:#e6b478;"
       id="airgap-toggle-confirm-copy"></p>
    <button id="airgap-toggle-confirm-btn" type="button"
            class="mp-close" disabled>Confirm (3)</button>
    <button id="airgap-toggle-cancel-btn" type="button"
            class="mp-close" style="margin-left:6px;">Cancel</button>
  </div>
  <div id="airgap-toggle-error" style="display:none; color:#e68080;
       font-size:12px; margin-top:6px;"></div>
</div>
```

Edits to `src/arail/portal/static/nav.js` (extending the existing badge-click handler around lines 138-200):

1. After populating modal status, fetch `/api/airgap/status` already returns `lab_mode`. Add a sibling field `bind_is_loopback` to that route (small backend tweak — single line) so the modal knows whether to show the toggle or the bind-warning.
2. Button label per current state:
   - `airgapped` → `"Allow agent fetches (switch to hybrid)"`
   - `hybrid` → `"Block agent fetches (switch to airgapped)"`
3. Click handler:
   1. Hide button, show confirm panel with explicit copy:
      - hybrid target: `"This allows agents to make outbound network calls to public hosts. Cloud-provider keys in lab/data/secrets.env will be used. Continue?"`
      - airgapped target: `"This blocks all agent outbound network calls. Cloud-provider Compute Sources will be unavailable until you flip back. Continue?"`
   2. Disable confirm button; start a 3-second countdown updating its label `Confirm (3)` → `(2)` → `(1)` → `Confirm`. Enable on 0.
   3. On confirm-click: `POST /api/airgap/toggle {target}`. Expect 409 with `confirm_token`; immediately re-POST with `{target, confirm_token}`. On 200, close modal, re-open it (forces refresh), update badge.
   4. On 403 `bind_not_loopback`: hide toggle section, show `airgap-toggle-bind-warning`.
   5. On 403 `cross_origin`: show generic "this action must be initiated from the lab UI" error.
   6. On 500: show `"Save failed — check server log"` (do not echo any path).
4. Cancel button restores idle button view.
5. CSRF: `fetch` defaults same-origin and includes `Origin`; backend asserts `Origin` host matches `Host` header.

## Tests

### `tests/test_env_writer.py`

Round-trip cases (each: create file with input bytes, run `set_env_var`, assert exact output bytes plus return dict):

| Case | Input | Expected |
|---|---|---|
| missing line — append | `FOO=bar\n` | original + blank + comment marker + `LAB_MODE=hybrid\n`; `appended=True` |
| existing simple replace | `LAB_MODE=airgapped\n` | `LAB_MODE=hybrid\n`; `changed=True` |
| existing double-quoted | `LAB_MODE="airgapped"\n` | `LAB_MODE="hybrid"\n` (quote preserved) |
| existing single-quoted | `LAB_MODE='airgapped'\n` | `LAB_MODE='hybrid'\n` |
| inline comment | `LAB_MODE=airgapped # default\n` | `LAB_MODE=hybrid # default\n` |
| comment line above | `# policy\nLAB_MODE=airgapped\n` | `# policy\nLAB_MODE=hybrid\n` |
| CRLF endings | `FOO=1\r\nLAB_MODE=airgapped\r\n` | `FOO=1\r\nLAB_MODE=hybrid\r\n` |
| BOM | `\xef\xbb\xbfLAB_MODE=airgapped\n` | `\xef\xbb\xbfLAB_MODE=hybrid\n` |
| no trailing newline (existing) | `LAB_MODE=airgapped` | `LAB_MODE=hybrid\n` (final NL ensured) |
| trailing whitespace | `LAB_MODE=airgapped   \n` | `LAB_MODE=hybrid\n` (trailing ws on the *replaced value line* removed; OK since we re-emit) |
| duplicate definitions | `LAB_MODE=airgapped\nLAB_MODE=airgapped\n` | first replaced, second untouched, warning logged |
| missing file | (does not exist) | file created, `appended=True`, mode 0o600 |
| value already equals | `LAB_MODE=hybrid\n` + set hybrid | no write, `changed=False` (assert mtime unchanged) |
| symlink | path is symlink | raises `EnvWriterError`, original target untouched |
| concurrent writers | 32 threads alternate target | final state is one of the two values, no torn line |
| value with newline | `set_env_var(p, "LAB_MODE", "x\ny")` | raises `EnvWriterError` |
| invalid key | `set_env_var(p, "1bad", "x")` | raises `EnvWriterError` |

### `tests/test_airgap_toggle_endpoint.py`

Uses `fastapi.testclient.TestClient`. Each test sets `BIND_ADDR` and `LAB_MODE` via `monkeypatch.setenv` and points the writer at a temp `.env`.

| Test | Scenario | Assert |
|---|---|---|
| `test_toggle_happy_two_step` | post w/o token → 409 + token; post w/ token → 200 | `.env` rewritten; `os.environ["LAB_MODE"]` updated; audit line appended |
| `test_toggle_invalid_target` | `target="banana"` | 400 |
| `test_toggle_missing_target` | empty body | 400 |
| `test_toggle_bind_gate_lan` | `BIND_ADDR=0.0.0.0` | 403 `bind_not_loopback`; `.env` untouched |
| `test_toggle_bind_gate_ipv4_lan` | `BIND_ADDR=192.168.1.10` | 403 |
| `test_toggle_bind_gate_ipv6_loopback_ok` | `BIND_ADDR=::1` | passes gate |
| `test_toggle_token_expired` | sleep 31s after step 1 | 409 again, fresh token |
| `test_toggle_token_replay` | use a token twice | second call → 409 |
| `test_toggle_token_wrong_target` | issue for hybrid, send airgapped | 409 |
| `test_toggle_cross_origin` | post with `Origin: http://evil.com` | 403 `cross_origin` |
| `test_toggle_writer_failure` | monkeypatch `set_env_var` to raise | 500; body has no `path` field; original `.env` untouched |
| `test_toggle_audit_log_shape` | happy path; read `airgap_audit.jsonl` | one line, expected fields, valid JSON |

### `tests/test_airgap_toggle_concurrency.py`

- Spawn 8 threads each issuing the full two-step flow concurrently against the same temp `.env`. Assert: final value is one of `{airgapped, hybrid}`, file always parseable, exactly N audit lines (N ≤ 8, ≥ 1). No torn writes.

### `tests/test_buddy_watcher_after_runtime_toggle.py`

- Set `LAB_MODE=airgapped`; seed Buddy `state.json` with `airgap_last_lab_mode: airgapped`; call the toggle endpoint to flip to `hybrid`; manually invoke `_watch_airgap_events()`; assert returned `Observation` is the "Door's open" mode-toggle one and `state.json["airgap_last_lab_mode"] == "hybrid"`.

### Regression

- `tests/test_airgap_status_endpoint.py` (existing from PR #35) must still pass; the new `bind_is_loopback` field added to its response is additive.

### Performance / Security

- Performance: not a hot path. No benchmark required.
- Security: bind-gate test; CSRF Origin test; symlink-refusal test; "value never echoed in error body" assertion.

## Tech debt

**Added:**
- A second small audit-log file (`lab/data/airgap_audit.jsonl`) joins the existing `egress.jsonl`. Two JSONL files mean two rotation strategies and two readers if anything ever wants a unified audit timeline.
- The hand-rolled `.env` parser is now a piece of code we own. dotenv-spec drift (e.g., `export FOO=bar` syntax, multiline values with `\\` continuation) will require updates here.
- Confirm-token in-memory table is process-local. If portal ever runs multi-worker (gunicorn `-w 4`), tokens issued by worker A won't validate at worker B. Documented; today portal is single-worker uvicorn.

**Repaid:**
- The "you must edit `.env` and restart" footgun is closed. PR #35's airgap claim becomes usable, not just true.
- Modal copy now states what the toggle does; previously the modal was read-only and silently misled users into thinking `.env` editing was the only path (it was, but that was a documentation gap).

**Net:** Slightly positive (one new file format, one new in-memory table). Acceptable given the UX win. Follow-up ticket: unify audit logs in a future sprint.

## Recommended implementation order

1. `src/arail/env_writer.py` + `tests/test_env_writer.py` — pure module, no portal coupling. Land all parser branches first.
2. `tests/test_airgap_toggle_concurrency.py` — exercise the lock with real threads against the writer.
3. `POST /api/airgap/toggle` route in `app.py`, including the bind gate, CSRF Origin check, and confirm-token table. Plus the `bind_is_loopback` field added to `/api/airgap/status`.
4. `tests/test_airgap_toggle_endpoint.py` — full endpoint matrix.
5. Audit-log writer (small helper in `arail.activity` or co-located in the route — builder picks; document choice in BUILD_LOG).
6. `tests/test_buddy_watcher_after_runtime_toggle.py` — end-to-end behavior.
7. Frontend: `_airgap_modal.html` additions + `nav.js` toggle handler + countdown.
8. Smoke-test the modal manually (load lab, click badge, click toggle, confirm, verify pill flips, verify `.env` mutated, restart, verify persisted).
9. README + `docs/PRIVACY.md` paragraph: how to toggle from the UI, what it persists, what the bind-address gate does.

## Files to touch

| File | Action | Notes |
|---|---|---|
| `src/arail/env_writer.py` | NEW | Public API + `_LOCKS` table |
| `src/arail/portal/app.py` | EDIT | New `POST /api/airgap/toggle`; add `bind_is_loopback` field to `/api/airgap/status` |
| `src/arail/portal/templates/_airgap_modal.html` | EDIT | Toggle section block (see §8) |
| `src/arail/portal/static/nav.js` | EDIT | Toggle handler + 3s countdown + 409→token→retry |
| `tests/test_env_writer.py` | NEW | All parser branches |
| `tests/test_airgap_toggle_endpoint.py` | NEW | Endpoint matrix |
| `tests/test_airgap_toggle_concurrency.py` | NEW | 8 threads, full two-step flow |
| `tests/test_buddy_watcher_after_runtime_toggle.py` | NEW | End-to-end |
| `lab/data/airgap_audit.jsonl` | NEW (runtime) | Created on first toggle, chmod 0600, gitignored |
| `README.md` | EDIT | One paragraph: "Toggling LAB_MODE from the UI" |
| `docs/PRIVACY.md` | EDIT | Toggle paragraph + bind-gate note |
| `.gitignore` | VERIFY | `lab/data/` already covered; confirm `airgap_audit.jsonl` not tracked |
| `src/arail/agents/_builtin_buddy.py` | NO CHANGE | Watcher already handles env-driven mode change |
| `src/arail/airgap.py` | NO CHANGE | Per-call `os.getenv` is the integration seam |

## Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| File-write race (two clients confirm simultaneously) | per-path `threading.Lock` | second writer waits, reads post-write state, no-ops or flips back |
| Power-cut mid-write | atomic `os.replace`; tmp file in same dir | original `.env` untouched; stale `.env.tmp.*` cleaned by a startup sweep (follow-up ticket) |
| `.env` is a symlink | `path.is_symlink()` check pre-write | `EnvWriterError`; 500 to client; original target untouched |
| `.env` permissions changed mid-write | `os.chmod(tmp, 0o600)` then `os.replace` | new file always 0o600 regardless of pre-state |
| Confirm-token replay | single-use deletion under `_TOGGLE_TOKENS_LOCK` | second use → 409 |
| Confirm-token brute-force | `secrets.token_urlsafe(24)` = 192 bits | infeasible |
| LAN-CSRF (peer on Wi-Fi) | bind-gate refuses on `BIND_ADDR ≠ loopback` | 403 with explicit message |
| Localhost-tab CSRF (malicious browser tab) | `Origin` / `Sec-Fetch-Site` same-origin check | 403 `cross_origin` |
| Path / value leakage in error response | error body contract: `{"error": "<code>"}` only | tested in `test_toggle_writer_failure` |
| Legacy client (cached JS posting w/o token field) | endpoint treats missing `confirm_token` as step-1 | returns 409 + token; client must redo step-2 (acceptable) |
| Multi-worker token-table inconsistency | documented; portal is single-worker today | follow-up ticket if portal ever scales out |
| Buddy watcher reads `.env` mid-write | watcher reads `os.environ`, not `.env` | no read path crosses write path |
| `os.environ` updated but disk write failed | order: disk first, then `os.environ` | failure stops before mutating in-memory state |
| Duplicate `LAB_MODE=` lines | parser counts, mutates first, warns | non-fatal; user keeps both copies until they clean up |

## Non-goals

- Editing other env vars via this endpoint (`LAB_MODE`-only).
- Multi-file rewriter; we never write `lab/data/secrets.env` here.
- Rollback / undo button (the inverse toggle is the undo).
- Auth beyond loopback + Origin (threat model is well-meaning operator, per VISION §4).
- Detecting if `BIND_ADDR` was changed at runtime via OS-level introspection.
- Cleaning up stray `.env.tmp.*` files from prior crashes (follow-up).
- Unifying `airgap_audit.jsonl` and `egress.jsonl` (follow-up).
