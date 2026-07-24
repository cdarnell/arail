"""Explicit lab checkup — the user-invoked home for every probe.

Because the portal boots quietly (no automatic package/version/model checks —
see ``arail.autochecks``), this module is where a user goes to actually run
them. Invoked via ``./arailctl doctor`` (which also does the venv/import
smoke-test). Everything here is on-demand: probing packages, models, and the
network is fine *because the user asked*.

Sections:
  • Environment   — lab mode + egress guard state (load-bearing airgap check)
  • Models        — one registry preflight + the tier table
  • Knowledge base— PKB index readiness/staleness
  • Components     — installed package versions (importlib.metadata)
  • Updates        — remote update check (``--updates``; hybrid only)

Run: ``python -m arail.doctor`` or ``python -m arail.doctor --updates``.
Exit code is 0 unless a hard problem is found (import failure, missing venv);
model-not-installed and airgapped are reported, not treated as failures.
"""

from __future__ import annotations

import argparse
import os
import sys
from importlib import metadata as importlib_metadata


def _p(line: str = "") -> None:
    print(line, flush=True)


def _section(title: str) -> None:
    _p()
    _p(f"── {title} " + "─" * max(0, 60 - len(title)))


def check_environment() -> None:
    _section("Environment")
    try:
        from arail import airgap
        mode = airgap.lab_mode()
        _p(f"  lab mode          : {mode}"
           + ("  (airgapped — no cloud egress)" if airgap.is_airgapped()
              else "  (hybrid — cloud providers allowed)"))
    except Exception as e:  # noqa: BLE001
        _p(f"  lab mode          : ? ({type(e).__name__}: {e})")
    try:
        from arail import egress
        # doctor runs in its own process — install the guard here too so this
        # checkup's own probes (esp. --updates) obey the same airgap policy the
        # portal enforces, and the report reflects a genuinely guarded process.
        egress.install_guard()
        installed = bool(getattr(egress, "_INSTALLED", False))
        _p(f"  egress guard      : {'installed' if installed else 'NOT installed'}")
    except Exception as e:  # noqa: BLE001
        _p(f"  egress guard      : ? ({type(e).__name__}: {e})")
    _p(f"  ARAIL_AUTOCHECKS  : {os.getenv('ARAIL_AUTOCHECKS', '0')} "
       "(background checks/warmers; default off = quiet boot)")


def check_models() -> None:
    _section("Models")
    try:
        from arail.registry import get_registry, health
        reg = get_registry()
        reg._ensure_loaded()
        # One explicit preflight — announce=False so we format the table here
        # instead of spraying the activity log.
        health.run_preflight(reg, announce=False)
        entries = list(reg.entries.values())
        if not entries:
            _p("  (no models configured)")
            return
        for e in entries:
            if not e.enabled:
                continue
            h = e.health
            where = e.endpoint or ("aerollm (in-process)"
                                   if e.provider_type == "aerollm" else "local")
            lat = f", {h.latency_ms:.0f}ms" if h.latency_ms is not None else ""
            detail = f" — {h.detail}" if h.detail else ""
            tier = f"tier{e.tier}" if e.tier is not None else "     "
            _p(f"  [{tier}] {e.display_name} @ {where} "
               f"({h.status}{lat}){detail}")
    except Exception as e:  # noqa: BLE001
        _p(f"  model check failed: {type(e).__name__}: {e}")


def check_knowledge_base() -> None:
    _section("Knowledge base (PKB index)")
    try:
        from arail.pkb_index import ensure_ready
        ensure_ready()
        _p("  pkb_pages index   : ready")
    except Exception as e:  # noqa: BLE001
        _p(f"  pkb_pages index   : NOT ready ({type(e).__name__}: {e})")
    try:
        from arail.pkb import _pkb_root
        _p(f"  pkb root          : {_pkb_root()}")
    except Exception:  # noqa: BLE001
        pass


def check_components() -> None:
    _section("Components (installed package versions)")
    # importlib.metadata only — no subprocess. The portal's Admin "Check
    # versions" button covers shell tools (ollama/npm/docker) on demand.
    for pkg in ("fastapi", "uvicorn", "lancedb", "pydantic", "requests",
                "httpx", "neo4j"):
        try:
            _p(f"  {pkg:<16}: {importlib_metadata.version(pkg)}")
        except importlib_metadata.PackageNotFoundError:
            _p(f"  {pkg:<16}: not installed")
        except Exception:  # noqa: BLE001
            _p(f"  {pkg:<16}: ?")
    # ollama is a shell tool, not a Python package — probe it here because the
    # user explicitly asked for a checkup.
    import shutil
    import subprocess as sp
    if shutil.which("ollama"):
        try:
            r = sp.run(["ollama", "--version"], capture_output=True,
                       text=True, timeout=5)
            _p(f"  ollama          : {r.stdout.strip() or r.stderr.strip() or '?'}")
        except Exception:  # noqa: BLE001
            _p("  ollama          : present (version probe failed)")
    else:
        _p("  ollama          : not on PATH")


def check_updates() -> None:
    _section("Updates (remote check)")
    try:
        from arail import airgap
        if airgap.is_airgapped():
            _p("  skipped — lab is airgapped (set LAB_MODE=hybrid to check)")
            return
    except Exception:  # noqa: BLE001
        pass
    import json
    import subprocess as sp
    from pathlib import Path
    manifest_path = Path.cwd() / "components.json"
    if not manifest_path.exists():
        _p("  no components.json found")
        return
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as e:  # noqa: BLE001
        _p(f"  could not read components.json: {e}")
        return
    checked = 0
    for c in manifest.get("components", []):
        ccmd = c.get("check_cmd")
        if not ccmd:
            continue
        checked += 1
        try:
            r = sp.run(ccmd, shell=True, capture_output=True, text=True, timeout=30)
            status = "ok" if r.returncode == 0 else f"exit {r.returncode}"
            head = (r.stdout or r.stderr or "").strip().split("\n")[0][:80]
            _p(f"  {c.get('name', '?'):<24}: {status}  {head}")
        except Exception as e:  # noqa: BLE001
            _p(f"  {c.get('name', '?'):<24}: probe failed ({type(e).__name__})")
    if not checked:
        _p("  no components define a check_cmd")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m arail.doctor",
        description="Explicit lab checkup (models, KB, components, egress).")
    ap.add_argument("--updates", action="store_true",
                    help="also run the remote update check (hybrid mode only)")
    args = ap.parse_args(argv)

    _p("ARAIL doctor — explicit checkup (nothing here runs automatically at boot)")
    check_environment()
    check_models()
    check_knowledge_base()
    check_components()
    if args.updates:
        check_updates()
    _p()
    _p("doctor: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
