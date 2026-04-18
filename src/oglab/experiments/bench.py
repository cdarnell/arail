"""oglab.experiments.bench — Benchmark runner for the 1 TB
research model.

We run a fixed prompt through AirLLM N times, capture a BenchRun
per call (TTFT, decode tok/s, bytes read from disk, peak RSS), and
append each run as a line of JSONL to
`lab/data/airllm-bench.jsonl`.

This file extends the existing bench capture in portal/app.py with
two things the autoresearch loop needs:

  1. Git context on every record: current SHA, branch, and the
     full knob snapshot that produced this result. Otherwise the
     dashboard can't tell which commit introduced which win.
  2. Aggregation helpers that filter by commit / branch / variant
     so the page can show baseline-vs-current cleanly.

The measurement loop is deliberately conservative:

  - We don't assume AirLLM exposes a streaming generator, so TTFT
    and decode-rate are approximated by splitting the total call
    into a small "prefill-and-one-token" warmup and the remaining
    generation. Sub-token precision isn't needed for an optimization
    loop that's looking for tens-of-percent wins.
  - Disk bytes read come from /proc/self/io on Linux (best effort)
    and psutil.Process().io_counters() everywhere else. Apple
    silicon via unified memory may show zero — that's not a bug,
    it's the hardware.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Data model ───────────────────────────────────────────────────────

@dataclass
class BenchRun:
    """One measurement of the research model's performance."""
    ts: str                          # ISO 8601 UTC
    git_sha: str                     # full commit SHA at measurement time
    git_short_sha: str
    git_branch: str
    git_dirty: bool
    model: str                       # e.g. "deepseek-ai/DeepSeek-R1"
    prompt: str
    prompt_chars: int
    max_tokens: int
    tokens_out: int

    # Timing
    total_latency_ms: float          # wall-clock end-to-end
    ttft_ms: Optional[float]         # time-to-first-token
    decode_tok_per_sec: Optional[float]

    # Resources
    bytes_read: Optional[int]        # process I/O bytes during the run
    peak_rss_mb: Optional[float]

    # Config that produced this run
    knob_values: Dict[str, Any] = field(default_factory=dict)

    # Free-form label for the UI; agent populates this with the
    # candidate name from docs/airllm-fork-guide.md
    variant_label: Optional[str] = None

    # Status + notes for rows that failed
    status: str = "ok"
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Runner ───────────────────────────────────────────────────────────

def _bench_file() -> Path:
    # We intentionally point at the same file portal/app.py uses so
    # the existing /api/airllm/bench endpoint keeps working.
    from oglab.config import DATA_DIR
    return DATA_DIR / "airllm-bench.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_io_bytes() -> Optional[int]:
    """Best-effort read bytes for this process. Returns None if not
    available on this platform."""
    # Linux: /proc/self/io has a read_bytes counter
    proc_io = Path("/proc/self/io")
    if proc_io.exists():
        try:
            for line in proc_io.read_text().splitlines():
                if line.startswith("read_bytes:"):
                    return int(line.split()[1])
        except OSError:
            pass
    # Fallback: psutil
    try:
        import psutil  # type: ignore
        proc = psutil.Process()
        io = proc.io_counters()  # type: ignore[attr-defined]
        return int(getattr(io, "read_bytes", 0))
    except Exception:
        return None


def _peak_rss_mb() -> Optional[float]:
    try:
        import psutil  # type: ignore
        return round(psutil.Process().memory_info().rss / (1024 * 1024), 1)
    except Exception:
        return None


def _apply_knob_env(knob_values: Dict[str, Any]) -> None:
    """Translate the knob names in tuning.yml into the environment
    variables the AirLLMBackend actually reads. Keeping the mapping
    centralized here means the agent never has to know the env-var
    names — it just writes to tuning.yml and this function does the
    translation before the backend is constructed."""
    mapping = {
        "airllm_compression": "AIRLLM_COMPRESSION",
        "airllm_max_length":  "AIRLLM_MAX_LENGTH",
    }
    for knob, env_key in mapping.items():
        if knob in knob_values:
            os.environ[env_key] = str(knob_values[knob])
    # Prefetch / expert cache knobs don't have env-var hooks yet —
    # they require fork-level code changes. The autoresearch loop
    # still records the knob value in the bench row so we can diff
    # runs once the fork ships the hook.


def run_bench(
    *,
    research_model_name: str,
    prompt: str,
    max_tokens: int,
    knob_values: Dict[str, Any],
    variant_label: Optional[str] = None,
    _backend: Any = None,  # dependency injection for tests
) -> BenchRun:
    """Run the research model once on `prompt` and return a
    BenchRun. Caller is responsible for appending to the JSONL
    file via `append_run` if they want it persisted."""
    from oglab.experiments.git_ops import git_state

    # Snapshot git BEFORE we touch anything, so a record is always
    # pinnable to a SHA even if the call later crashes.
    gs = git_state()

    # Point the backend at the research model. AirLLMBackend reads
    # AIRLLM_MODEL on construction.
    os.environ["AIRLLM_MODEL"] = research_model_name
    _apply_knob_env(knob_values)

    t0 = time.time()
    io_start = _read_io_bytes() or 0
    tokens_out = 0
    text = ""
    status = "ok"
    error: Optional[str] = None
    ttft_ms: Optional[float] = None
    decode_tps: Optional[float] = None

    try:
        backend = _backend
        if backend is None:
            from oglab.router.backends import AirLLMBackend
            backend = AirLLMBackend()
        # Warmup call: 1 token to approximate TTFT. We do a real
        # short call rather than instrumenting .generate(), which
        # would require a fork. Sub-token precision isn't needed.
        t_warm = time.time()
        _ = backend.complete(prompt=prompt, max_tokens=1, temperature=1.0)
        ttft_ms = (time.time() - t_warm) * 1000.0

        # Full call
        resp = backend.complete(
            prompt=prompt, max_tokens=max_tokens, temperature=1.0
        )
        tokens_out = int(resp.tokens_used or 0)
        text = resp.text or ""
    except Exception as exc:
        status = "error"
        error = f"{type(exc).__name__}: {exc}"

    total_ms = (time.time() - t0) * 1000.0
    # Subtract the warmup token from the decode rate so it reflects
    # steady-state generation, not prefill.
    if tokens_out > 1 and ttft_ms is not None and total_ms > ttft_ms:
        decode_tps = round(
            (tokens_out - 1) / ((total_ms - ttft_ms) / 1000.0), 3
        )

    io_end = _read_io_bytes() or 0
    bytes_read = max(io_end - io_start, 0) if (io_end and io_start) else None

    run = BenchRun(
        ts=_now(),
        git_sha=gs.sha,
        git_short_sha=gs.short_sha,
        git_branch=gs.branch,
        git_dirty=gs.is_dirty,
        model=research_model_name,
        prompt=prompt,
        prompt_chars=len(prompt),
        max_tokens=max_tokens,
        tokens_out=tokens_out,
        total_latency_ms=round(total_ms, 2),
        ttft_ms=round(ttft_ms, 2) if ttft_ms is not None else None,
        decode_tok_per_sec=decode_tps,
        bytes_read=bytes_read,
        peak_rss_mb=_peak_rss_mb(),
        knob_values=dict(knob_values),
        variant_label=variant_label,
        status=status,
        error=error,
    )
    _ = text  # intentionally unused; we don't persist model output
    return run


def append_run(run: BenchRun, path: Path | None = None) -> None:
    """Append one run to the JSONL log. Never raises."""
    try:
        p = path or _bench_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            f.write(json.dumps(run.to_dict(), default=str) + "\n")
    except Exception:
        pass


def load_runs(
    *,
    limit: int = 200,
    path: Path | None = None,
) -> List[Dict[str, Any]]:
    """Load the most recent `limit` bench records. Returns oldest-first
    within the limit window. Silently tolerates malformed lines from
    older bench versions."""
    p = path or _bench_file()
    if not p.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        lines = p.read_text().splitlines()
    except OSError:
        return []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute aggregate stats used by the /tuning page. Handles
    the empty-history case gracefully (dashboard should still
    render with 'no data yet')."""
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    if not ok_rows:
        return {
            "count": 0,
            "ok_count": 0,
            "latest": None,
            "best_tok_per_sec": None,
        }
    # "Best" run = highest decode_tok_per_sec. Ties broken by
    # latest timestamp.
    scored = [
        (r.get("decode_tok_per_sec") or 0.0, r.get("ts", ""), r)
        for r in ok_rows
    ]
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    best = scored[0][2]
    return {
        "count": len(rows),
        "ok_count": len(ok_rows),
        "latest": ok_rows[-1],
        "best_tok_per_sec": best.get("decode_tok_per_sec"),
        "best_run": best,
    }
