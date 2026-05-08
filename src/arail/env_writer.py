"""env_writer — atomic, comment-preserving .env file writer.

Public API
----------
read_env_var(path, key) -> str | None
set_env_var(path, key, value) -> dict

Design constraints from ARCHITECTURE.md:
- Preserves comments, blank lines, quoting style, inline comments, BOM, CRLF.
- Atomic write via O_EXCL temp + os.replace (POSIX atomic, same filesystem).
- Per-path threading.Lock via WeakValueDictionary.
- Symlink refusal (no following).
- Never uses dotenv.set_key.
- value with newline or NUL → EnvWriterError.
- Invalid key → EnvWriterError.
- Multiple definitions → mutate first, warn about extras.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from weakref import WeakValueDictionary

_log = logging.getLogger(__name__)

# Identifier regex: must match the full key.
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Per-path lock registry.
_LOCKS: WeakValueDictionary[Path, threading.Lock] = WeakValueDictionary()
_LOCKS_GUARD = threading.Lock()


class EnvWriterError(OSError):
    """Raised by set_env_var on illegal pre-conditions."""


def _lock_for(path: Path) -> threading.Lock:
    resolved = path.resolve()
    with _LOCKS_GUARD:
        lk = _LOCKS.get(resolved)
        if lk is None:
            lk = threading.Lock()
            _LOCKS[resolved] = lk
    return lk


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Line dataclass
# ---------------------------------------------------------------------------

@dataclass
class Line:
    """One line of a .env file, retaining every byte except the content we replace."""

    kind: str          # "blank" | "comment" | "assign" | "malformed"
    raw: str           # full text including trailing newline (or "" for bare last line)
    key: Optional[str] = None
    value_raw: Optional[str] = None   # value as stored (possibly quoted)
    quote: str = ""                    # "" | '"' | "'"
    inline_comment: Optional[str] = None
    _term: str = field(default="", repr=False)   # \r\n or \n or ""
    _prefix: str = field(default="", repr=False) # leading whitespace before key=

    @property
    def unquoted_value(self) -> Optional[str]:
        if self.value_raw is None:
            return None
        if self.quote and self.value_raw.startswith(self.quote) and self.value_raw.endswith(self.quote) and len(self.value_raw) >= 2:
            return self.value_raw[1:-1]
        return self.value_raw

    def with_value(self, new_value: str) -> "Line":
        """Return a new Line with the value replaced, preserving quote style."""
        if self.quote:
            new_value_raw = f"{self.quote}{new_value}{self.quote}"
        else:
            new_value_raw = new_value
        # inline_comment is stored as captured by the regex group after " #",
        # so it may have a leading space. Normalise to exactly " # <stripped>".
        if self.inline_comment is not None:
            ic_part = f" # {self.inline_comment.lstrip()}"
        else:
            ic_part = ""
        new_raw = f"{self._prefix}{self.key}={new_value_raw}{ic_part}{self._term}"
        return Line(
            kind=self.kind,
            raw=new_raw,
            key=self.key,
            value_raw=new_value_raw,
            quote=self.quote,
            inline_comment=self.inline_comment,
            _term=self._term,
            _prefix=self._prefix,
        )

    @classmethod
    def blank(cls, nl: str) -> "Line":
        return cls(kind="blank", raw=nl, _term=nl)

    @classmethod
    def comment(cls, text: str, nl: str) -> "Line":
        return cls(kind="comment", raw=f"{text}{nl}", _term=nl)

    @classmethod
    def assign(cls, key: str, value: str, nl: str, quote: str = "") -> "Line":
        if quote:
            value_raw = f"{quote}{value}{quote}"
        else:
            value_raw = value
        raw = f"{key}={value_raw}{nl}"
        return cls(
            kind="assign",
            raw=raw,
            key=key,
            value_raw=value_raw,
            quote=quote,
            inline_comment=None,
            _term=nl,
            _prefix="",
        )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

# Matches: optional-leading-ws KEY = <rest> [optional-inline-comment] <terminator>
# The terminator group matches \r\n, \n, or end-of-string.
_ASSIGN_RE = re.compile(
    r"^(?P<prefix>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=(?P<rest>.*?)(?P<term>\r\n|\n|$)",
    re.DOTALL,
)

# Matches an inline comment at the tail of a value (unquoted): ws # <comment>
_INLINE_RE = re.compile(r"^(?P<val>.*?)\s+#(?P<ic>.*)$")


def _parse_lines(text: str) -> list[Line]:
    """Split text into Line objects, preserving terminators."""
    lines: list[Line] = []
    # Split preserving line terminators.
    parts: list[str] = []
    i = 0
    while i < len(text):
        j = text.find("\n", i)
        if j == -1:
            parts.append(text[i:])
            break
        # Include the \n (and preceding \r if any) as part of this chunk.
        parts.append(text[i:j + 1])
        i = j + 1

    for raw in parts:
        stripped = raw.rstrip("\r\n")
        term = raw[len(stripped):]  # \r\n or \n or ""

        if stripped.strip() == "":
            lines.append(Line(kind="blank", raw=raw, _term=term))
            continue

        if stripped.lstrip().startswith("#"):
            lines.append(Line(kind="comment", raw=raw, _term=term))
            continue

        m = _ASSIGN_RE.match(raw)
        if m:
            prefix = m.group("prefix")
            key = m.group("key")
            rest = m.group("rest")
            # rest may end with \r\n or \n — strip those before parsing value.
            rest = rest.rstrip("\r\n")

            # Detect quoting.
            quote = ""
            value_raw = rest
            inline_comment: Optional[str] = None

            if rest.startswith('"') and rest.endswith('"') and len(rest) >= 2:
                quote = '"'
                # Check for inline comment inside double-quoted: not standard, treat whole thing as value.
                value_raw = rest
            elif rest.startswith("'") and rest.endswith("'") and len(rest) >= 2:
                quote = "'"
                value_raw = rest
            else:
                # Unquoted: look for inline comment.
                ic_m = _INLINE_RE.match(rest)
                if ic_m:
                    value_raw = ic_m.group("val")
                    inline_comment = ic_m.group("ic")
                else:
                    value_raw = rest

            lines.append(Line(
                kind="assign",
                raw=raw,
                key=key,
                value_raw=value_raw,
                quote=quote,
                inline_comment=inline_comment,
                _term=term,
                _prefix=prefix,
            ))
        else:
            lines.append(Line(kind="malformed", raw=raw, _term=term))

    return lines


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

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
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_env_var(path: Path, key: str) -> Optional[str]:
    """Return the unquoted value of *key* from *path*, or None if absent/missing."""
    try:
        text = path.read_text(encoding="utf-8-sig")  # handles BOM
    except FileNotFoundError:
        return None
    lines = _parse_lines(text)
    result: Optional[str] = None
    for ln in lines:
        if ln.kind == "assign" and ln.key == key:
            result = ln.unquoted_value
    return result


def set_env_var(path: Path, key: str, value: str) -> dict:
    """Rewrite *key=value* in *path* atomically, preserving all formatting.

    Returns:
        {"old_value": str|None, "new_value": str, "changed": bool, "appended": bool}

    Raises:
        EnvWriterError on symlink target, missing parent dir, EISDIR,
        newline/NUL in value, or invalid key identifier.
    """
    # Pre-condition checks.
    if path.is_symlink():
        raise EnvWriterError(f"refusing to write through symlink: {path}")
    if not _IDENT.fullmatch(key):
        raise EnvWriterError(f"invalid key: {key!r}")
    if "\n" in value or "\x00" in value:
        raise EnvWriterError("value contains forbidden chars (newline or NUL)")
    if not path.parent.exists():
        raise EnvWriterError(f"parent directory does not exist: {path.parent}")
    if path.exists() and path.is_dir():
        raise EnvWriterError(f"path is a directory: {path}")

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

        # Detect dominant newline style.
        crlf_count = text.count("\r\n")
        lf_count = text.count("\n") - crlf_count
        nl = "\r\n" if crlf_count > lf_count else "\n"

        # 3. Parse.
        lines = _parse_lines(text)

        # 4. Find key occurrences.
        old_value: Optional[str] = None
        first_match: Optional[int] = None
        dup_count = 0

        for i, ln in enumerate(lines):
            if ln.kind == "assign" and ln.key == key:
                if first_match is None:
                    first_match = i
                    old_value = ln.unquoted_value
                else:
                    dup_count += 1

        if dup_count:
            _log.warning(
                "env_writer: %d extra '%s=' lines in %s; left untouched",
                dup_count, key, path,
            )

        if first_match is not None:
            ln = lines[first_match]
            if ln.unquoted_value == value:
                # No-op: file already has the correct value.
                return {"old_value": old_value, "new_value": value,
                        "changed": False, "appended": False}
            lines[first_match] = ln.with_value(value)
            appended = False
        else:
            # Append.
            if lines and lines[-1].kind != "blank":
                lines.append(Line.blank(nl))
            lines.append(Line.comment(
                f"# set by arail portal toggle ({_utcnow_iso()})", nl
            ))
            lines.append(Line.assign(key, value, nl, quote=""))
            appended = True

        # 5. Serialize; ensure final newline.
        out_text = "".join(ln.raw for ln in lines)
        if not out_text.endswith("\n"):
            out_text += nl

        # 6. Atomic write.
        out_bytes = (b"\xef\xbb\xbf" if has_bom else b"") + out_text.encode("utf-8")
        _atomic_write(path, out_bytes)

        return {"old_value": old_value, "new_value": value,
                "changed": True, "appended": appended}
