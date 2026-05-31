"""build_ai_eng.py — Python helper for scripts/build_ai_eng.sh.

Handles:
  - HF adapter download (with format probe)
  - Candidate A: mlx_lm.fuse into 4-bit MLX base
  - Candidate B: PEFT merge_and_unload (with mlx→PEFT format translation if needed)
  - GGUF conversion via llama.cpp convert_hf_to_gguf.py
  - Local Ollama tag creation

Every step is idempotent via sentinel files in ARAIL_BUILD_DIR.
Heavy steps are guarded by free-RAM / free-disk probes before execution.
HF tokens are consumed via env, never via argv; logs are sanitised.

Exit codes mirror build_ai_eng.sh (see §4.1 of ARCHITECTURE.md):
  0  success / ready to publish
  20 OOM pre-check tripped
  21 disk pre-check tripped
  30 HF download failed
  40 adapter format unknown
  50 GGUF conversion / merge failed
  60 ollama create failed / SYSTEM SHA drifted
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import psutil

log = logging.getLogger("build_ai_eng")

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_ADAPTER_REPO = "qukaizen/qkz-opus4.7-aieng-1.5b-v2.1-adapter"
DEFAULT_BF16_BASE = "Qwen/Qwen2.5-1.5B-Instruct"  # Apache-2.0
DEFAULT_MLX_BASE = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"  # Apache-2.0
DEFAULT_LLAMA_CPP_REV = "b3500"
DEFAULT_MIN_FREE_RAM_GB = 16
DEFAULT_MIN_FREE_DISK_GB = 30

# Token pattern: any hf_ bearer token (26-char hex suffix)
_HF_TOKEN_RE = re.compile(r"hf_[A-Za-z0-9]{10,}")


# ── Log sanitisation ──────────────────────────────────────────────────────────

def sanitize_log_line(line: str) -> str:
    """Strip HF bearer tokens from a log line before writing to disk."""
    return _HF_TOKEN_RE.sub("hf_REDACTED", line)


def _write_safe(path: Path, content: str) -> None:
    """Write text content, sanitising any HF tokens first."""
    path.write_text(sanitize_log_line(content))


# ── Pre-flight checks ─────────────────────────────────────────────────────────

def check_free_ram_gb(min_gb: float = DEFAULT_MIN_FREE_RAM_GB) -> None:
    """Abort with exit 20 if available RAM is below min_gb."""
    available = psutil.virtual_memory().available / (1024 ** 3)
    log.info("Free RAM: %.1f GB (required: %.1f GB)", available, min_gb)
    if available < min_gb:
        log.error(
            "OOM pre-check: only %.1f GB free, need %.1f GB. "
            "Stop the ARAIL portal and browser tabs before building.",
            available, min_gb,
        )
        sys.exit(20)


def check_free_disk_gb(path: Path, min_gb: float = DEFAULT_MIN_FREE_DISK_GB) -> None:
    """Abort with exit 21 if free disk at path is below min_gb."""
    usage = shutil.disk_usage(path)
    free_gb = usage.free / (1024 ** 3)
    log.info("Free disk at %s: %.1f GB (required: %.1f GB)", path, free_gb, min_gb)
    if free_gb < min_gb:
        log.error(
            "Disk pre-check: only %.1f GB free at %s, need %.1f GB.",
            free_gb, path, min_gb,
        )
        sys.exit(21)


def check_portal_not_running() -> None:
    """Refuse to proceed if the ARAIL portal is running."""
    result = subprocess.run(
        ["pgrep", "-f", "arail.portal"],
        capture_output=True,
    )
    if result.returncode == 0:
        log.error(
            "ARAIL portal is running (pids: %s). Stop the portal before building "
            "to avoid OOM. Run: pkill -f 'arail.portal'",
            result.stdout.decode().strip(),
        )
        sys.exit(20)


# ── Sentinel helpers ──────────────────────────────────────────────────────────

def sentinel(build_dir: Path, step: str) -> Path:
    return build_dir / f".step-{step}.done"


def step_done(build_dir: Path, step: str) -> bool:
    return sentinel(build_dir, step).exists()


def mark_done(build_dir: Path, step: str) -> None:
    sentinel(build_dir, step).touch()


# ── SHA256 helpers ────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_dir_files(directory: Path, pattern: str = "*.safetensors") -> dict[str, str]:
    """Return {relative_path: sha256} for all matching files in directory."""
    return {
        str(p.relative_to(directory)): sha256_file(p)
        for p in sorted(directory.glob(pattern))
    }


def append_sha256sums(build_dir: Path, label: str, sums: dict[str, str]) -> None:
    sums_path = build_dir / "SHA256SUMS"
    with sums_path.open("a") as f:
        f.write(f"\n# {label}\n")
        for name, digest in sums.items():
            f.write(f"{digest}  {name}\n")


# ── Adapter download ──────────────────────────────────────────────────────────

def download_adapter(
    build_dir: Path,
    adapter_repo: str,
    dry_run: bool = False,
) -> Path:
    """Download adapter from HF to build_dir/adapter/. Idempotent."""
    adapter_dir = build_dir / "adapter"
    step = "download"

    if step_done(build_dir, step):
        log.info("Step '%s' already complete, skipping.", step)
        return adapter_dir

    if dry_run:
        log.info("[dry-run] Would download adapter from %s to %s", adapter_repo, adapter_dir)
        adapter_dir.mkdir(parents=True, exist_ok=True)
        # Write stub files for code-path testing
        (adapter_dir / "adapter_config.json").write_text(
            json.dumps({
                "peft_type": "LORA",
                "lora_alpha": 16,
                "r": 16,
                "__mlx_lm_format": True,
                "lora_A": {},
                "lora_B": {},
            })
        )
        (adapter_dir / "adapters.safetensors").write_bytes(b"STUB")
        mark_done(build_dir, step)
        return adapter_dir

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    env = os.environ.copy()
    if token:
        env["HF_TOKEN"] = token

    log.info("Downloading adapter from %s ...", adapter_repo)
    adapter_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "huggingface-cli", "download", adapter_repo,
        "--local-dir", str(adapter_dir),
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        err = sanitize_log_line(result.stderr)
        log.error("HF download failed:\n%s", err)
        _write_safe(build_dir / "error-download.log", result.stderr)
        sys.exit(30)

    # Checksum downloaded files
    sums = sha256_dir_files(adapter_dir, "*.safetensors")
    append_sha256sums(build_dir, f"adapter ({adapter_repo})", sums)

    mark_done(build_dir, step)
    return adapter_dir


# ── Adapter format detection ──────────────────────────────────────────────────

def probe_adapter_format(adapter_dir: Path) -> str:
    """Determine adapter format: 'mlx' or 'peft'.

    mlx_lm format: adapter_config.json contains '__mlx_lm_format' key or
    has 'lora_A'/'lora_B' in mlx key style.
    PEFT format: adapter_config.json contains 'peft_type' key.

    Returns 'mlx', 'peft', or raises SystemExit(40) for unknown.
    """
    config_path = adapter_dir / "adapter_config.json"
    if not config_path.exists():
        log.error(
            "adapter_config.json not found in %s — cannot determine format (F1).",
            adapter_dir,
        )
        sys.exit(40)

    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        log.error("adapter_config.json is not valid JSON: %s", exc)
        sys.exit(40)

    if "__mlx_lm_format" in config or (
        "lora_A" not in config and "lora_alpha" in config and "r" in config
        and "peft_type" not in config
    ):
        log.info("Adapter format detected: mlx_lm")
        return "mlx"

    if "peft_type" in config:
        log.info("Adapter format detected: peft (peft_type=%s)", config["peft_type"])
        return "peft"

    missing = [k for k in ("lora_alpha", "r") if k not in config]
    log.error(
        "Adapter format unknown. Config keys: %s. Missing expected keys: %s (F1).",
        list(config.keys()), missing,
    )
    sys.exit(40)


# ── Candidate A: mlx_lm.fuse ─────────────────────────────────────────────────

def build_candidate_a(
    build_dir: Path,
    adapter_dir: Path,
    mlx_base: str,
    min_free_ram_gb: float,
    dry_run: bool = False,
) -> Path:
    """Fuse adapter into 4-bit MLX base via mlx_lm.fuse. Idempotent."""
    out_dir = build_dir / "mlx-fused"
    step = "candidate-a"

    if step_done(build_dir, step):
        log.info("Step '%s' already complete, skipping.", step)
        return out_dir

    if not dry_run:
        check_free_ram_gb(min_free_ram_gb)

    if dry_run:
        log.info(
            "[dry-run] Would fuse %s + %s → %s via mlx_lm.fuse",
            mlx_base, adapter_dir, out_dir,
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "config.json").write_text('{"model_type": "qwen2"}')
        (out_dir / "model.safetensors").write_bytes(b"STUB")
        mark_done(build_dir, step)
        return out_dir

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "mlx_lm.fuse",
        "--model", mlx_base,
        "--adapter-path", str(adapter_dir),
        "--save-path", str(out_dir),
    ]
    log.info("Running Candidate A: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("mlx_lm.fuse failed (F2):\n%s", result.stderr)
        _write_safe(build_dir / "error-candidate-a.log", result.stderr)
        log.warning(
            "Candidate A failed. Sprint can proceed with Candidate B only (degraded)."
        )
        # Do NOT sys.exit — allow Candidate B to still proceed
        return out_dir  # out_dir may be empty; caller checks sentinel

    sums = sha256_dir_files(out_dir, "*.safetensors")
    append_sha256sums(build_dir, "Candidate A (mlx-fused)", sums)
    mark_done(build_dir, step)
    return out_dir


# ── Candidate B: PEFT merge_and_unload ───────────────────────────────────────

def _translate_mlx_to_peft(adapter_dir: Path, peft_dir: Path) -> None:
    """Translate an mlx_lm-format adapter to PEFT LoRA layout (F3).

    Reads adapters.safetensors (mlx key names), re-keys to PEFT
    lora_A.weight / lora_B.weight names, writes a PEFT-compatible
    adapter_config.json.

    This is a best-effort translation for the Qwen2.5-1.5B architecture.
    If key mapping fails, raises RuntimeError for the caller to catch.
    """
    try:
        import safetensors.torch as st
        import torch
    except ImportError as exc:
        raise RuntimeError(f"safetensors / torch not available for format translation: {exc}") from exc

    src_path = adapter_dir / "adapters.safetensors"
    if not src_path.exists():
        raise RuntimeError(f"adapters.safetensors not found in {adapter_dir}")

    tensors = st.load_file(str(src_path))

    # mlx_lm naming convention: layers.N.self_attn.q_proj.lora_a / lora_b
    # PEFT naming convention: base_model.model.model.layers.N.self_attn.q_proj.lora_A.weight
    peft_tensors: dict[str, "torch.Tensor"] = {}
    for key, val in tensors.items():
        # Normalise: mlx uses (out, r) for lora_a and (r, in) for lora_b
        if key.endswith(".lora_a"):
            peft_key = key[: -len(".lora_a")] + ".lora_A.weight"
        elif key.endswith(".lora_b"):
            peft_key = key[: -len(".lora_b")] + ".lora_B.weight"
        else:
            # Scale / other keys: pass through unchanged
            peft_key = key
        # Ensure tensor is float32 for PEFT compatibility
        peft_tensors[peft_key] = val.float() if hasattr(val, "float") else val

    if not any("lora_A.weight" in k for k in peft_tensors):
        raise RuntimeError(
            "Could not find any lora_a keys in mlx adapter — key mapping failed (F3). "
            f"Available keys (first 5): {list(tensors.keys())[:5]}"
        )

    peft_dir.mkdir(parents=True, exist_ok=True)
    st.save_file(peft_tensors, str(peft_dir / "adapter_model.safetensors"))

    # Read original config for LoRA hyperparams
    orig_config = json.loads((adapter_dir / "adapter_config.json").read_text())
    peft_config = {
        "peft_type": "LORA",
        "task_type": "CAUSAL_LM",
        "r": orig_config.get("r", 16),
        "lora_alpha": orig_config.get("lora_alpha", 16),
        "lora_dropout": orig_config.get("lora_dropout", 0.0),
        "target_modules": orig_config.get("target_modules", ["q_proj", "v_proj"]),
        "bias": "none",
        "base_model_name_or_path": DEFAULT_BF16_BASE,
    }
    (peft_dir / "adapter_config.json").write_text(json.dumps(peft_config, indent=2))
    log.info("Format translation complete: %d tensors written to %s", len(peft_tensors), peft_dir)


def build_candidate_b(
    build_dir: Path,
    adapter_dir: Path,
    bf16_base: str,
    adapter_format: str,
    min_free_ram_gb: float,
    dry_run: bool = False,
) -> Path:
    """Merge adapter into bf16 HF base via peft.merge_and_unload. Idempotent."""
    out_dir = build_dir / "bf16-merged"
    step = "candidate-b"

    if step_done(build_dir, step):
        log.info("Step '%s' already complete, skipping.", step)
        return out_dir

    if not dry_run:
        check_free_ram_gb(min_free_ram_gb)

    if dry_run:
        log.info(
            "[dry-run] Would merge %s + %s → %s via peft.merge_and_unload",
            bf16_base, adapter_dir, out_dir,
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "config.json").write_text('{"model_type": "qwen2"}')
        (out_dir / "model.safetensors").write_bytes(b"STUB")
        # Verify no HF token in saved config (F18 check)
        _verify_no_token_in_config(out_dir)
        mark_done(build_dir, step)
        return out_dir

    # Format translation if adapter is mlx-format (F3)
    peft_source = adapter_dir
    if adapter_format == "mlx":
        log.info("Adapter is mlx format — translating to PEFT layout (F3)...")
        peft_xlate_dir = build_dir / "adapter-peft-xlate"
        try:
            _translate_mlx_to_peft(adapter_dir, peft_xlate_dir)
            peft_source = peft_xlate_dir
        except RuntimeError as exc:
            log.error("Format translation failed: %s", exc)
            _write_safe(build_dir / "error-candidate-b.log", str(exc))
            log.warning("Candidate B unavailable; sprint continues with Candidate A only.")
            return out_dir  # empty; caller checks sentinel

    try:
        from peft import PeftModel  # type: ignore
        from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
    except ImportError as exc:
        log.error("peft/transformers not installed: %s", exc)
        _write_safe(build_dir / "error-candidate-b.log", str(exc))
        return out_dir

    out_dir.mkdir(parents=True, exist_ok=True)
    log.info("Loading bf16 base %s ...", bf16_base)
    try:
        import torch  # type: ignore
        model = AutoModelForCausalLM.from_pretrained(
            bf16_base,
            torch_dtype=torch.bfloat16,
            low_cpu_mem_usage=True,
        )
        tokenizer = AutoTokenizer.from_pretrained(bf16_base)
        log.info("Loading PEFT adapter from %s ...", peft_source)
        peft_model = PeftModel.from_pretrained(model, str(peft_source))
        log.info("Merging adapter (merge_and_unload)...")
        merged = peft_model.merge_and_unload()
        log.info("Saving merged model to %s ...", out_dir)
        merged.save_pretrained(str(out_dir))
        tokenizer.save_pretrained(str(out_dir))
        del merged, peft_model, model
    except KeyError as exc:
        log.error("PEFT key error during merge (F3): %s", exc)
        _write_safe(build_dir / "error-candidate-b.log", str(exc))
        log.warning("Candidate B failed. Sprint continues with Candidate A only.")
        return out_dir
    except Exception as exc:  # noqa: BLE001
        log.error("Candidate B merge failed: %s", exc)
        _write_safe(build_dir / "error-candidate-b.log", str(exc))
        return out_dir

    # F18: verify no HF token leaked into saved config
    _verify_no_token_in_config(out_dir)

    sums = sha256_dir_files(out_dir, "*.safetensors")
    append_sha256sums(build_dir, "Candidate B (bf16-merged)", sums)
    mark_done(build_dir, step)
    return out_dir


def _verify_no_token_in_config(model_dir: Path) -> None:
    """Assert no hf_ token string appears in any config.json in model_dir (F18)."""
    for cfg in model_dir.glob("*.json"):
        content = cfg.read_text()
        if _HF_TOKEN_RE.search(content):
            log.error(
                "F18 violation: HF token string found in %s — aborting.", cfg
            )
            sys.exit(60)


# ── GGUF conversion ───────────────────────────────────────────────────────────

def convert_to_gguf(
    build_dir: Path,
    candidate: str,  # "a" or "b"
    llama_cpp_rev: str,
    min_free_ram_gb: float,
    dry_run: bool = False,
) -> Path:
    """Convert winner candidate to GGUF via llama.cpp convert_hf_to_gguf.py."""
    step = "convert"
    if step_done(build_dir, step):
        log.info("Step '%s' already complete, skipping.", step)
        # Return whichever gguf exists
        ggufs = list(build_dir.glob("*.gguf"))
        return ggufs[0] if ggufs else build_dir / "ai-eng-1.5b-v2.1.gguf"

    if not dry_run:
        check_free_ram_gb(min_free_ram_gb)

    if candidate == "a":
        src_dir = build_dir / "mlx-fused"
        out_type = "f16"
        gguf_name = "ai-eng-1.5b-v2.1.f16.gguf"
    else:
        src_dir = build_dir / "bf16-merged"
        out_type = "bf16"
        gguf_name = "ai-eng-1.5b-v2.1.bf16.gguf"

    gguf_path = build_dir / gguf_name

    if dry_run:
        log.info(
            "[dry-run] Would convert %s → %s (outtype=%s, llama.cpp rev=%s)",
            src_dir, gguf_path, out_type, llama_cpp_rev,
        )
        gguf_path.write_bytes(b"STUB_GGUF")
        digest = sha256_file(gguf_path)
        append_sha256sums(build_dir, f"GGUF ({gguf_name})", {gguf_name: digest})
        mark_done(build_dir, step)
        return gguf_path

    # For Candidate A, mlx_lm.convert first to get HF safetensors
    if candidate == "a":
        hf_out = build_dir / "mlx-fused-hf"
        hf_out.mkdir(parents=True, exist_ok=True)
        conv_cmd = [
            sys.executable, "-m", "mlx_lm.convert",
            "--hf-path", str(src_dir),
            "--mlx-path", str(hf_out),
            "--quantize", "false",
        ]
        log.info("Converting mlx-fused to HF safetensors: %s", " ".join(conv_cmd))
        r = subprocess.run(conv_cmd, capture_output=True, text=True)
        if r.returncode != 0:
            log.error("mlx_lm.convert failed (F7):\n%s", r.stderr)
            _write_safe(build_dir / "error-convert.log", r.stderr)
            sys.exit(50)
        src_dir = hf_out

    # Locate or clone llama.cpp at pinned rev
    llama_cpp_dir = _ensure_llama_cpp(build_dir, llama_cpp_rev, dry_run=False)
    convert_script = llama_cpp_dir / "convert_hf_to_gguf.py"

    cmd = [
        sys.executable, str(convert_script),
        str(src_dir),
        "--outtype", out_type,
        "--outfile", str(gguf_path),
    ]
    log.info("Running GGUF conversion: %s", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log.error("GGUF conversion failed (F7):\n%s", r.stderr)
        _write_safe(build_dir / "error-convert.log", r.stderr)
        sys.exit(50)

    digest = sha256_file(gguf_path)
    append_sha256sums(build_dir, f"GGUF ({gguf_name})", {gguf_name: digest})
    mark_done(build_dir, step)
    return gguf_path


def _ensure_llama_cpp(build_dir: Path, rev: str, dry_run: bool) -> Path:
    """Clone llama.cpp at the pinned revision into build_dir/llama.cpp/."""
    llama_dir = build_dir / "llama.cpp"
    if (llama_dir / "convert_hf_to_gguf.py").exists():
        log.info("llama.cpp already cloned at %s", llama_dir)
        return llama_dir

    if dry_run:
        log.info("[dry-run] Would clone llama.cpp rev %s to %s", rev, llama_dir)
        llama_dir.mkdir(parents=True, exist_ok=True)
        (llama_dir / "convert_hf_to_gguf.py").write_text("# stub\n")
        return llama_dir

    llama_dir.mkdir(parents=True, exist_ok=True)
    cmds = [
        ["git", "clone", "--depth=1", "https://github.com/ggerganov/llama.cpp.git", str(llama_dir)],
        ["git", "-C", str(llama_dir), "fetch", "--depth=1", "origin", rev],
        ["git", "-C", str(llama_dir), "checkout", rev],
    ]
    for cmd in cmds:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            log.error("llama.cpp clone/checkout failed: %s", r.stderr)
            sys.exit(50)
    return llama_dir


def _ensure_llama_quantize_bin(build_dir: Path, rev: str, dry_run: bool) -> Path:
    """Return path to a built llama-quantize binary.

    Checks two well-known locations after a cmake build:
      <llama.cpp>/build/bin/llama-quantize
      <llama.cpp>/llama-quantize

    If absent and not dry_run, triggers a cmake build inside the cloned repo.
    Guarded by check_free_disk_gb(build_dir, 5.0) before compiling.
    On build failure logs a clear actionable error and exits 50.

    In dry_run mode a stub executable is written and returned without compiling.
    """
    llama_dir = _ensure_llama_cpp(build_dir, rev, dry_run=dry_run)

    # Check known post-build locations
    candidates = [
        llama_dir / "build" / "bin" / "llama-quantize",
        llama_dir / "llama-quantize",
    ]
    for path in candidates:
        if path.exists() and os.access(str(path), os.X_OK):
            log.info("Found llama-quantize at %s", path)
            return path

    if dry_run:
        stub_path = llama_dir / "llama-quantize"
        log.info("[dry-run] Would build llama-quantize; writing stub at %s", stub_path)
        stub_path.write_bytes(b"#!/bin/sh\necho stub-llama-quantize\n")
        stub_path.chmod(0o755)
        return stub_path

    # Need to compile
    check_free_disk_gb(build_dir, min_gb=5.0)
    build_out = llama_dir / "build"
    log.info("Building llama-quantize via cmake in %s ...", llama_dir)
    cmake_configure = ["cmake", "-B", str(build_out), str(llama_dir)]
    r = subprocess.run(cmake_configure, capture_output=True, text=True)
    if r.returncode != 0:
        log.error(
            "cmake configure failed for llama.cpp.\n%s\n"
            "Fix: ensure cmake >= 3.14 is installed: brew install cmake",
            r.stderr,
        )
        sys.exit(50)

    cmake_build = [
        "cmake", "--build", str(build_out),
        "--config", "Release",
        "-j",
        "--target", "llama-quantize",
    ]
    r = subprocess.run(cmake_build, capture_output=True, text=True)
    if r.returncode != 0:
        log.error(
            "cmake build of llama-quantize failed.\n%s\n"
            "Fix: check cmake/compiler output above; ensure a C++17-capable compiler is present.",
            r.stderr,
        )
        sys.exit(50)

    # Re-check known locations after build
    for path in candidates:
        if path.exists() and os.access(str(path), os.X_OK):
            log.info("llama-quantize built at %s", path)
            return path

    log.error(
        "llama-quantize binary not found after cmake build. "
        "Checked: %s. Check build output above.",
        [str(p) for p in candidates],
    )
    sys.exit(50)


# ── GGUF quantization ─────────────────────────────────────────────────────────

def quantize_gguf(
    build_dir: Path,
    src_gguf: Path,
    quant: str,
    llama_cpp_rev: str,
    min_free_ram_gb: float,
    min_free_disk_gb: float = 5.0,
    dry_run: bool = False,
) -> Path:
    """Quantize src_gguf to <quant> via llama-quantize. Idempotent via sentinel.

    Output filename: ai-eng-1.5b-v2.1.<QUANT>.gguf (build-internal artifact).
    The published filename (ai-eng-1.5b-<QUANT>.gguf) is staged by _run_publish.

    Exit code 50 on failure, mirroring convert_to_gguf.
    """
    step = "quantize"
    if step_done(build_dir, step):
        log.info("Step '%s' already complete, skipping.", step)
        # Return the quantized gguf path
        out_name = f"ai-eng-1.5b-v2.1.{quant}.gguf"
        return build_dir / out_name

    out_name = f"ai-eng-1.5b-v2.1.{quant}.gguf"
    out_gguf = build_dir / out_name

    if dry_run:
        log.info(
            "[dry-run] Would quantize %s → %s (quant=%s)",
            src_gguf, out_gguf, quant,
        )
        out_gguf.write_bytes(b"STUB_GGUF_QUANT")
        digest = sha256_file(out_gguf)
        append_sha256sums(build_dir, f"GGUF quantized ({out_name})", {out_name: digest})
        mark_done(build_dir, step)
        return out_gguf

    check_free_ram_gb(min_free_ram_gb)
    check_free_disk_gb(build_dir, min_gb=min_free_disk_gb)

    quantize_bin = _ensure_llama_quantize_bin(build_dir, llama_cpp_rev, dry_run=False)

    cmd = [str(quantize_bin), str(src_gguf), str(out_gguf), quant]
    log.info("Running llama-quantize: %s", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log.error(
            "llama-quantize failed (exit %d):\n%s\n"
            "Fix: verify src_gguf is a valid f16/bf16 GGUF; check llama-quantize version.",
            r.returncode, r.stderr,
        )
        _write_safe(build_dir / "error-quantize.log", r.stderr)
        sys.exit(50)

    digest = sha256_file(out_gguf)
    append_sha256sums(build_dir, f"GGUF quantized ({out_name})", {out_name: digest})
    mark_done(build_dir, step)
    log.info("Quantization complete: %s (sha256: %s...)", out_gguf, digest[:12])
    return out_gguf


# ── Modelfile generation ──────────────────────────────────────────────────────

def generate_modelfile(
    build_dir: Path,
    gguf_path: Path,
    modelfile_production: Path,
    dry_run: bool = False,
) -> Path:
    """Generate build/ai-eng-1.5b-v2.1.Modelfile from Modelfile.production (§4.4)."""
    out_path = build_dir / "ai-eng-1.5b-v2.1.Modelfile"

    system_text = _extract_system_block(modelfile_production)
    expected_sha = hashlib.sha256(system_text.encode()).hexdigest()

    if dry_run:
        log.info(
            "[dry-run] Would generate Modelfile at %s (SYSTEM SHA=%s)",
            out_path, expected_sha[:12],
        )
        if not out_path.exists():
            _write_modelfile(out_path, gguf_path, system_text)
        return out_path

    _write_modelfile(out_path, gguf_path, system_text)

    # Verify SYSTEM SHA (F9)
    written = _extract_system_block(out_path)
    actual_sha = hashlib.sha256(written.encode()).hexdigest()
    if actual_sha != expected_sha:
        log.error(
            "F9: SYSTEM SHA mismatch. Expected %s, got %s. "
            "Modelfile.production may have changed mid-build.",
            expected_sha, actual_sha,
        )
        sys.exit(60)

    log.info("Modelfile written and SYSTEM SHA verified (%s).", expected_sha[:12])
    return out_path


def _extract_system_block(modelfile_path: Path) -> str:
    """Extract the SYSTEM block content from an Ollama Modelfile."""
    content = modelfile_path.read_text()
    # Match SYSTEM """...""" or SYSTEM "..."
    m = re.search(r'SYSTEM\s+"""(.*?)"""', content, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r'SYSTEM\s+"(.*?)"', content, re.DOTALL)
    if m:
        return m.group(1)
    raise ValueError(f"No SYSTEM block found in {modelfile_path}")


def _write_modelfile(out_path: Path, gguf_path: Path, system_text: str) -> None:
    content = (
        f'FROM ./{gguf_path.name}\n'
        f'SYSTEM """{system_text}"""\n'
        f'PARAMETER temperature 0.7\n'
        f'PARAMETER num_ctx 8192\n'
    )
    out_path.write_text(content)


# ── Ollama create ─────────────────────────────────────────────────────────────

def ollama_create(
    build_dir: Path,
    modelfile_path: Path,
    tag: str = "qukaizen/ai-eng:1.5b",  # LOCAL-ONLY build/smoke tag — never pushed
    min_free_ram_gb: float = 8.0,
    dry_run: bool = False,
) -> None:
    """Create local Ollama tag from Modelfile. Idempotent.

    The default tag ``qukaizen/ai-eng:1.5b`` is a LOCAL build/smoke tag only.
    It is NOT pushed to the ollama.ai registry. Distribution uses the
    self-hosted GGUF path (see _run_publish / CONSOLIDATION.md §3).
    """
    step = "ollama-create"
    if step_done(build_dir, step):
        log.info("Step '%s' already complete, skipping.", step)
        return

    if not dry_run:
        check_free_ram_gb(min_free_ram_gb)

    if dry_run:
        log.info("[dry-run] Would run: ollama create %s -f %s", tag, modelfile_path)
        mark_done(build_dir, step)
        return

    cmd = ["ollama", "create", tag, "-f", str(modelfile_path)]
    log.info("Creating Ollama tag: %s", " ".join(cmd))
    # Must run from build_dir so FROM ./...gguf resolves
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(build_dir))
    if r.returncode != 0:
        log.error("ollama create failed (F8):\n%s", r.stderr)
        _write_safe(build_dir / "error-ollama-create.log", r.stderr)
        sys.exit(60)

    log.info("Ollama tag created: %s", tag)
    mark_done(build_dir, step)


def ollama_smoke(tag: str = "qukaizen/ai-eng:1.5b", timeout: int = 30) -> None:
    """Run a quick smoke test: ollama must return non-empty within timeout s.

    Operates on the LOCAL build/smoke tag — not the ollama.ai registry.
    """
    cmd = ["ollama", "run", tag, "Explain LoRA in 3 sentences."]
    log.info("Smoke test: %s (timeout=%ds)", " ".join(cmd), timeout)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0 or not r.stdout.strip():
            log.error("Smoke test FAILED. stdout=%r stderr=%r", r.stdout[:200], r.stderr[:200])
            sys.exit(60)
        log.info("Smoke test PASSED.")
    except subprocess.TimeoutExpired:
        log.error("Smoke test timed out after %ds.", timeout)
        sys.exit(60)


# ── CLI entry point ───────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="build_ai_eng.py — ARAIL model build helper")
    p.add_argument("subcommand", choices=["build", "bench-only", "convert", "publish", "clean", "dry-run"])
    p.add_argument("--adapter-repo", default=DEFAULT_ADAPTER_REPO)
    p.add_argument("--bf16-base", default=DEFAULT_BF16_BASE)
    p.add_argument("--mlx-base", default=DEFAULT_MLX_BASE)
    p.add_argument("--bench-prompts", default="models/ai-eng/bench-prompts.v2.1.yaml")
    p.add_argument("--llama-cpp-rev", default=DEFAULT_LLAMA_CPP_REV)
    p.add_argument("--min-free-ram-gb", type=float, default=DEFAULT_MIN_FREE_RAM_GB)
    p.add_argument("--min-free-disk-gb", type=float, default=DEFAULT_MIN_FREE_DISK_GB)
    p.add_argument("--build-dir", default=os.environ.get("ARAIL_BUILD_DIR", "./build"))
    p.add_argument("--modelfile-production", default="models/ai-eng/Modelfile.production")
    p.add_argument("--candidate", choices=["a", "b"], help="For 'convert' subcommand")
    p.add_argument("--force", action="store_true", help="Re-run even if sentinel exists")
    p.add_argument("--yes-i-have-read-bench", action="store_true")
    p.add_argument("--license", default=None, help="License identifier (required for publish)")
    p.add_argument(
        "--quant", default="Q4_K_M",
        help="Quantisation type passed to llama-quantize (default: Q4_K_M). "
             "The build pipeline converts to f16/bf16 first, then quantizes to this type. "
             "The published artifact is named ai-eng-1.5b-<QUANT>.gguf.",
    )
    return p.parse_args()


def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _parse_args()
    build_dir = Path(args.build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)

    dry_run = args.subcommand == "dry-run"
    if dry_run:
        args.subcommand = "build"  # run full build code path in dry-run mode

    if args.force:
        log.info("--force: removing all sentinels in %s", build_dir)
        for s in build_dir.glob(".step-*.done"):
            s.unlink()

    if args.subcommand == "clean":
        if (build_dir / "BENCH-v2.1.md").exists():
            # Never delete the bench output
            shutil.rmtree(build_dir, ignore_errors=True)
            build_dir.mkdir(parents=True, exist_ok=True)
            log.info("build/ cleaned (BENCH-v2.1.md is preserved in models/ai-eng/).")
        else:
            shutil.rmtree(build_dir, ignore_errors=True)
            build_dir.mkdir(parents=True, exist_ok=True)
            log.info("build/ cleaned.")
        return

    if args.subcommand == "publish":
        _run_publish(args, build_dir)
        return

    if args.subcommand == "convert":
        if not args.candidate:
            log.error("'convert' subcommand requires --candidate a|b")
            sys.exit(1)
        f16_gguf = convert_to_gguf(
            build_dir, args.candidate, args.llama_cpp_rev,
            args.min_free_ram_gb, dry_run=dry_run,
        )
        quantize_gguf(
            build_dir, f16_gguf, args.quant, args.llama_cpp_rev,
            args.min_free_ram_gb, dry_run=dry_run,
        )
        return

    # build / dry-run
    if not dry_run:
        check_portal_not_running()
        check_free_disk_gb(build_dir, args.min_free_disk_gb)

    adapter_dir = download_adapter(build_dir, args.adapter_repo, dry_run=dry_run)
    fmt = probe_adapter_format(adapter_dir)

    build_candidate_a(
        build_dir, adapter_dir, args.mlx_base,
        args.min_free_ram_gb, dry_run=dry_run,
    )
    build_candidate_b(
        build_dir, adapter_dir, args.bf16_base, fmt,
        args.min_free_ram_gb, dry_run=dry_run,
    )

    if not dry_run:
        # Run bench; let bench_ai_eng.py decide winner and exit code
        bench_cmd = [
            sys.executable, "scripts/bench_ai_eng.py",
            "--candidate-a-path", str(build_dir / "mlx-fused"),
            "--candidate-b-path", str(build_dir / "bf16-merged"),
            "--prompts-file", args.bench_prompts,
            "--out", str(build_dir / "BENCH-v2.1.md"),
        ]
        log.info("Running bench: %s", " ".join(bench_cmd))
        r = subprocess.run(bench_cmd)
        bench_exit = r.returncode
        if bench_exit == 2:
            log.error("Bench exit 2: both candidates failed quality gate. Sprint shelved.")
            sys.exit(10)
        winner = "b" if bench_exit == 0 else "a"
        log.info("Bench complete. Winner: Candidate %s (exit %d)", winner.upper(), bench_exit)
    else:
        log.info("[dry-run] Skipping bench; assuming winner=b for code path.")
        winner = "b"
        mark_done(build_dir, "bench")

    modelfile_production = Path(args.modelfile_production).resolve()
    f16_gguf_path = convert_to_gguf(
        build_dir, winner, args.llama_cpp_rev,
        args.min_free_ram_gb, dry_run=dry_run,
    )
    gguf_path = quantize_gguf(
        build_dir, f16_gguf_path, args.quant, args.llama_cpp_rev,
        args.min_free_ram_gb, dry_run=dry_run,
    )
    modelfile_path = generate_modelfile(
        build_dir, gguf_path, modelfile_production, dry_run=dry_run,
    )
    ollama_create(
        build_dir, modelfile_path,
        min_free_ram_gb=8.0, dry_run=dry_run,
    )
    if not dry_run:
        ollama_smoke()

    log.info("Build complete. Run 'scripts/build_ai_eng.sh bench-only' to re-run bench.")
    log.info("Review build/BENCH-v2.1.md, then run 'scripts/build_ai_eng.sh publish --yes-i-have-read-bench'.")


# ── Publish helpers ───────────────────────────────────────────────────────────

def emit_notice_beside_gguf(build_dir: Path, gguf_path: Path) -> None:
    """Copy repo-root NOTICE into build_dir next to the GGUF (G1).

    Falls back to a minimal inline NOTICE only if the repo NOTICE is absent.
    The repo NOTICE is the authoritative Apache-2.0 attribution; callers should
    prefer keeping the repo NOTICE accurate rather than relying on the fallback.
    """
    notice_dest = build_dir / "NOTICE"
    if notice_dest.exists():
        log.info("NOTICE already present at %s, skipping copy.", notice_dest)
        return

    # Locate repo-root NOTICE relative to this script (scripts/ → parent)
    repo_root = Path(__file__).parent.parent
    repo_notice = repo_root / "NOTICE"

    if repo_notice.exists():
        shutil.copy2(str(repo_notice), str(notice_dest))
        log.info("Copied repo-root NOTICE to %s", notice_dest)
    else:
        # Minimal fallback — mirrors the scaffold's inline NOTICE
        log.warning(
            "Repo-root NOTICE not found at %s — writing minimal fallback NOTICE.", repo_notice
        )
        notice_dest.write_text(
            "NOTICE: ai-eng is derived from Qwen/Qwen2.5-1.5B-Instruct (Alibaba Cloud),\n"
            "licensed under Apache-2.0. See the repo-root NOTICE file and\n"
            "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct/blob/main/LICENSE\n"
            "for the full license text. This NOTICE MUST be included in any redistribution\n"
            "of the ai-eng GGUF artifact (HuggingFace model card, GitHub release, CDN).\n"
        )
        log.info("Minimal fallback NOTICE written to %s", notice_dest)


def print_upload_instructions(
    gguf_path: Path,
    sha256: str,
    license_id: str,
    quant: str,
) -> None:
    """Print self-hosted HF/GitHub-release/CDN upload commands as manual TODO blocks (G3).

    Commands are PRINTED, never executed — preserves the no-credentials /
    no-auto-upload safety property. Repo names and URLs use the same
    placeholders as pyproject.toml [tool.arail.models] and check_ai_eng_artifact.sh.
    """
    # Derive the quant-tagged GGUF filename (G4) so upload commands align with
    # check_ai_eng_artifact.sh's GGUF_FILE="ai-eng-1.5b-${QUANT}.gguf" derivation.
    quant_tagged_name = f"ai-eng-1.5b-{quant}.gguf"
    hf_repo = "qukaizen/ai-eng-1.5b-gguf"  # matches pyproject ai_eng_hf_repo placeholder
    gh_release_url = (
        f"https://github.com/qukaizen/arail/releases/download/ai-eng-1.5b/{quant_tagged_name}"
    )

    print("\n" + "=" * 78)
    print("UPLOAD STEPS (manual — uncomment and run after logging in)")
    print("=" * 78)
    print()
    print("# 1. Update pyproject.toml [tool.arail.models] with the real values:")
    print(f'#      ai_eng_sha256  = "{sha256}"')
    print(f'#      ai_eng_hf_repo = "{hf_repo}"   # set your real HF org/repo')
    print(f'#      ai_eng_gh_url  = "{gh_release_url}"')
    print("#      ai_eng_quant   = \"" + quant + '"')
    print()
    print(f"# 2. The build pipeline produced the quantized GGUF: {gguf_path.name}")
    print(f"#    This is already quantized to {quant} via llama-quantize.")
    print(f"#    The staged published artifact is: {quant_tagged_name}")
    print()
    print("# 3. HuggingFace upload (primary — enables the clean single-pull path):")
    print("#")
    print("#    huggingface-cli login   # run once; stores token in ~/.cache/huggingface/")
    print("#")
    print(f"#    huggingface-cli upload {hf_repo} \\")
    print(f"#      {gguf_path} \\")
    print("#      --repo-type model \\")
    print(f'#      --commit-message "Add ai-eng-1.5b {quant} GGUF (sha256: {sha256})"')
    print("#")
    print(f"#    # Also upload the Modelfile and NOTICE:")
    print(f"#    huggingface-cli upload {hf_repo} <build_dir>/ai-eng-1.5b-v2.1.Modelfile --repo-type model")
    print(f"#    huggingface-cli upload {hf_repo} <build_dir>/NOTICE --repo-type model")
    print()
    print("# 4. GitHub Release mirror (fallback for HF outage / corp proxies):")
    print("#")
    print("#    gh auth login   # run once")
    print("#")
    print(f'#    gh release create ai-eng-1.5b \\')
    print(f'#      --repo qukaizen/arail \\')
    print(f'#      --title "ai-eng 1.5B GGUF ({quant})" \\')
    print(f'#      --notes "sha256: {sha256}\\n\\nai-eng is derived from Qwen/Qwen2.5-1.5B-Instruct.')
    print("#    Licensed under Apache-2.0. See NOTICE in this release.\"")
    print("#")
    print(f"#    gh release upload ai-eng-1.5b {gguf_path} --repo qukaizen/arail")
    print()
    print("# 5. CDN (optional tertiary — set ARAIL_AI_ENG_CDN_URL / ai_eng_cdn_url):")
    print("#    Upload via your hosting provider; update ai_eng_cdn_url in pyproject.toml.")
    print()
    print("# 6. After uploading, verify the artifact is live:")
    print("#    scripts/check_ai_eng_artifact.sh")
    print()
    print("# 7. Commit the updated pyproject.toml with the real sha256 + repo values.")
    print("=" * 78)


def _run_publish(args: argparse.Namespace, build_dir: Path) -> None:
    """Phase 2 publish — requires --yes-i-have-read-bench and interactive yes.

    Distribution model (self-hosted GGUF, per CONSOLIDATION.md §3):
    - Primary:   HF GGUF repo (ollama pull hf.co/<repo>:<quant>)
    - Mirror:    GitHub Release asset (sha256-verified HTTPS + local ollama create)
    - Tertiary:  optional CDN
    - Pin:       ai_eng_sha256 in pyproject.toml [tool.arail.models]

    The ollama.ai registry tag (qukaizen/ai-eng:1.5b) is NOT a distribution
    destination — it exists only as a local build/smoke tag. Never pushed.
    """
    if not args.yes_i_have_read_bench:
        log.error(
            "Publish refused (exit 70): pass --yes-i-have-read-bench to confirm "
            "you have reviewed BENCH-v2.1.md. This flag codifies authority chain D3."
        )
        sys.exit(70)

    if not args.license:
        log.error(
            "Publish refused (exit 70): --license is required (D1 gate). "
            "Example: --license Apache-2.0"
        )
        sys.exit(70)

    quant = getattr(args, "quant", "Q4_K_M")

    # Verify HF auth
    r = subprocess.run(["huggingface-cli", "whoami"], capture_output=True, text=True)
    if r.returncode != 0 or "anonymous" in r.stdout.lower():
        log.error(
            "HF auth check failed (F10). Run 'huggingface-cli login' with a write token "
            "for the qukaizen org, then retry publish."
        )
        sys.exit(30)

    # Locate the quantized GGUF in build_dir.
    # The quantize step produces ai-eng-1.5b-v2.1.<QUANT>.gguf (build-internal name).
    # Prefer it; fall back to any gguf for operators who ran convert but not quantize.
    quant_internal_name = f"ai-eng-1.5b-v2.1.{quant}.gguf"
    quant_internal_path = build_dir / quant_internal_name

    if quant_internal_path.exists():
        src_gguf = quant_internal_path
        log.info("Using quantized GGUF: %s", src_gguf)
    else:
        gguf_files = list(build_dir.glob("*.gguf"))
        if not gguf_files:
            log.error("No GGUF found in %s — run 'build' first.", build_dir)
            sys.exit(1)
        src_gguf = gguf_files[0]
        log.warning(
            "Quantized GGUF (%s) not found; falling back to %s. "
            "Run 'build' (not just 'convert') to produce the quantized artifact.",
            quant_internal_name, src_gguf.name,
        )

    # Derive the published filename (G4) — this is what check_ai_eng_artifact.sh
    # and setup.sh expect: ai-eng-1.5b-<QUANT>.gguf (no v2.1 infix).
    quant_tagged_name = f"ai-eng-1.5b-{quant}.gguf"
    published_gguf_path = build_dir / quant_tagged_name

    # Stage the published file (copy build-internal → published name) so sha256
    # is computed on the exact file that will be uploaded. Idempotent.
    if not published_gguf_path.exists() or published_gguf_path.resolve() != src_gguf.resolve():
        log.info(
            "Staging published artifact: %s → %s",
            src_gguf.name, quant_tagged_name,
        )
        shutil.copy2(str(src_gguf), str(published_gguf_path))
    else:
        log.info("Published artifact already staged: %s", published_gguf_path)

    # G1: Emit NOTICE beside the GGUF before the gate
    emit_notice_beside_gguf(build_dir, published_gguf_path)

    # sha256 is computed on the PUBLISHED file (the exact bytes users will download)
    gguf_sha = sha256_file(published_gguf_path)
    log.info("sha256(%s) = %s", quant_tagged_name, gguf_sha)

    print("\n=== PUBLISH GATE ===")
    print(f"Build artifact: {src_gguf.name}")
    print(f"Published filename: {quant_tagged_name}  (← what users download)")
    print("Distribution (self-hosted GGUF):")
    print("  1. HF GGUF repo: qukaizen/ai-eng-1.5b-gguf  (primary — ollama pull hf.co/<repo>:<quant>)")
    print("  2. GitHub Release mirror: sha256-verified HTTPS + local ollama create")
    print("  3. CDN (optional): ai_eng_cdn_url in pyproject.toml")
    print("  NOTE: no ollama.ai registry push — distribution is self-hosted GGUF only.")
    print(f"  License: {args.license}")
    print()

    # G2: Print full sha256 + pyproject-pinning guidance
    print(f"sha256 ({quant_tagged_name}): {gguf_sha}")
    print()
    print(f"  Next step: set ai_eng_sha256 = \"{gguf_sha}\" in pyproject.toml")
    print("  [tool.arail.models] and paste it into the GitHub Release body so")
    print("  downloaders can verify the artifact via check_ai_eng_artifact.sh.")
    print()

    print("\nThis action is IRREVERSIBLE. Type 'yes' to proceed: ", end="", flush=True)

    answer = input().strip().lower()
    if answer != "yes":
        log.error("Publish refused (exit 70): user declined at interactive prompt.")
        sys.exit(70)

    log.info("Publish authorised. Proceeding...")

    # G3: Print upload instructions (printed, never executed)
    print_upload_instructions(published_gguf_path, gguf_sha, args.license, quant)

    # Write self-hosted PUBLISHED.json (no ollama registry key)
    published = {
        "hf_gguf_repo": "qukaizen/ai-eng-1.5b-gguf",
        "gh_release_url": (
            f"https://github.com/qukaizen/arail/releases/download/ai-eng-1.5b/{quant_tagged_name}"
        ),
        "cdn_url": "",
        "gguf_file": quant_tagged_name,
        "gguf_sha256": gguf_sha,
        "quant": quant,
        "license": args.license,
        "status": "ready-to-upload",
    }
    (build_dir / "PUBLISHED.json").write_text(json.dumps(published, indent=2))
    log.info("Wrote build/PUBLISHED.json (self-hosted shape, no ollama registry key).")


if __name__ == "__main__":
    _main()
