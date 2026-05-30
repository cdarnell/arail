"""QA guards for the 2026-05-30 model-hosting-reframe sprint.

Allocation (arail): 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression.
The setup-ladder shell tests live in tests/setup_ladder/. This file covers the
Python/static surfaces: the deep-model sentinel, qwen-hiding regression guard,
NOTICE attribution, packaging-script security, Buddy (ai-eng) resolution.

OOM-SAFETY: no model is loaded; backend guards are asserted to RAISE before
any load. No network. No subprocess that downloads.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SENTINEL = "__TODO_DEEP_MODEL__"


# ===========================================================================
# DEEP-MODEL SENTINEL (security / OOM-safety)
# ===========================================================================

def test_sentinel_is_not_a_resolvable_model_id():
    """The sentinel must look like a placeholder, never a real org/model id."""
    assert SENTINEL.startswith("__") and SENTINEL.endswith("__")
    assert "/" not in SENTINEL, "a real HF id has an org/ prefix; sentinel must not"
    assert ":" not in SENTINEL, "a real ollama tag has a :tag; sentinel must not"


def test_airllm_worker_raises_on_sentinel_before_any_load(monkeypatch):
    """airllm_worker._load_model must raise (no download/load) when the deep
    model resolves to the sentinel.

    OOM-SAFETY: we set AIRLLM_MODEL to the sentinel string explicitly (the
    documented 'unconfigured' state). The guard must trip BEFORE any
    AutoModel.from_pretrained call. We also patch the airllm import so that
    if the guard ever regressed, the test fails loudly instead of loading a
    real 70B (matching the workspace OOM memory note)."""
    monkeypatch.setenv("AIRLLM_MODEL", SENTINEL)
    import types
    fake_airllm = types.ModuleType("airllm")

    class _Boom:
        @staticmethod
        def from_pretrained(*a, **k):  # pragma: no cover - must never run
            raise AssertionError(
                "GUARD REGRESSION: AutoModel.from_pretrained was called with "
                "the sentinel still active — a real model would have loaded."
            )

    fake_airllm.AutoModel = _Boom
    monkeypatch.setitem(sys.modules, "airllm", fake_airllm)
    from arail.router import airllm_worker
    with pytest.raises(RuntimeError, match="[Dd]eep model is not configured"):
        airllm_worker._load_model()


def test_backends_raises_on_sentinel_before_any_load(monkeypatch):
    """backends deep backend must raise on the sentinel default."""
    monkeypatch.delenv("AIRLLM_MODEL", raising=False)
    from arail.router import backends
    # Find the AirLLM backend class and instantiate enough to hit the guard.
    # The guard lives in __init__ (reads AIRLLM_MODEL, raises on sentinel).
    src = (REPO_ROOT / "src/arail/router/backends.py").read_text()
    assert 'os.getenv("AIRLLM_MODEL"' in src
    assert f'_sentinel = "{SENTINEL}"' in src
    # Behavioral: the guard raises. Locate the class and trigger __init__.
    classes = [getattr(backends, n) for n in dir(backends)
               if isinstance(getattr(backends, n), type)]
    raised = False
    for cls in classes:
        srcfile = getattr(cls, "__module__", "")
        if "backends" not in srcfile:
            continue
        try:
            cls()
        except RuntimeError as e:
            if "not configured" in str(e).lower():
                raised = True
                break
        except Exception:
            continue
    assert raised, "a backend must RuntimeError 'not configured' on the sentinel"


def test_no_deep_default_resolves_to_a_real_weight():
    """REGRESSION GUARD: fail if anyone wires a real 70B/405B/llama default
    back into the deep-model defaults. Locks the sentinel in place."""
    files = [
        "pyproject.toml",
        "scripts/setup.sh",
        "src/arail/router/backends.py",
        "src/arail/router/airllm_worker.py",
        "src/arail/portal/app.py",
        "src/arail/chat/models_catalog.yaml",
    ]
    # Only flag a heavy id used as a DEFAULT (env getenv default, assignment,
    # or default_model wiring) — not benign comment/docstring mentions.
    default_ctx = re.compile(
        r"""(?ix)
        (?:
          getenv\(\s*["']AIRLLM_MODEL["']\s*,\s*["'][^"']*Llama-3\.1-(?:70B|405B)
        | (?:AIRLLM_MODEL[_A-Z]*|default_model)\s*[:=]\s*["'][^"']*Llama-3\.1-(?:70B|405B)
        )
        """
    )
    for f in files:
        text = (REPO_ROOT / f).read_text()
        m = default_ctx.search(text)
        assert not m, f"{f} reintroduces a heavy deep MODEL DEFAULT: {m.group(0)!r}"


def test_app_default_model_is_sentinel():
    """The optional-backend default_model wiring stays on the sentinel."""
    text = (REPO_ROOT / "src/arail/portal/app.py").read_text()
    assert f'"default_model": "{SENTINEL}"' in text


# ===========================================================================
# QWEN-HIDING REGRESSION GUARD (security / attribution)
# ===========================================================================

# The ONLY places "qwen" (ai-eng lineage) may appear user-facing:
#   - the single Modelfile.preview FROM line (class-c base ref, WC#3-permitted)
#   - license/attribution files (NOTICE, LICENSE) and operator config
#   - the preview-net plumbing (Modelfile.preview, pyproject ai_eng_preview)
# Standalone qwen *catalog rows* and internal build/bench recipes are OUT OF
# SCOPE (architecture §Part 3). This guard locks the ai-eng-identity surfaces.

USER_FACING_AI_ENG_SURFACES = [
    "README.md",
    "CLAUDE.md",
    "src/arail/portal/templates/tuning.html",
]


def _ai_eng_section_has_qwen(text: str) -> list[str]:
    """Return offending lines that mention qwen NEAR an ai-eng mention."""
    offending = []
    for line in text.splitlines():
        low = line.lower()
        if "qwen" in low and ("ai-eng" in low or "ai engineer" in low):
            offending.append(line.strip())
    return offending


def test_no_qwen_in_ai_eng_identity_lines():
    """No line ties ai-eng to qwen in user-facing README/CLAUDE/tuning copy."""
    for f in USER_FACING_AI_ENG_SURFACES:
        text = (REPO_ROOT / f).read_text()
        bad = _ai_eng_section_has_qwen(text)
        assert not bad, f"{f}: ai-eng lineage leaks qwen: {bad}"


def test_catalog_ai_eng_description_has_no_qwen():
    """The ai-eng catalog entry description must not mention qwen lineage."""
    text = (REPO_ROOT / "src/arail/chat/models_catalog.yaml").read_text()
    # Extract the ai-eng:latest block (up to the next top-level list item).
    m = re.search(r"^- id: ai-eng:latest\b.*?(?=^- id:|\Z)", text,
                  re.MULTILINE | re.DOTALL)
    assert m, "ai-eng:latest catalog entry not found"
    block = m.group(0)
    assert "qwen" not in block.lower(), (
        f"ai-eng catalog entry leaks qwen lineage:\n{block}"
    )


def test_modelfile_preview_is_the_only_user_facing_qwen_FROM():
    """The lone permitted qwen reference is Modelfile.preview's FROM line."""
    mf = (REPO_ROOT / "models/ai-eng/Modelfile.preview").read_text()
    assert re.search(r"^FROM\s+qwen2\.5:7b\s*$", mf, re.MULTILINE), (
        "Modelfile.preview must retain its FROM qwen2.5:7b base line"
    )
    # And its SYSTEM prompt must NOT self-describe as qwen.
    sys_block = mf.lower()
    # The persona must still be ai-eng, not a qwen self-description.
    assert "ai-eng" in sys_block
    # qwen appears only on the FROM line, nowhere in the SYSTEM narrative.
    non_from = "\n".join(ln for ln in mf.splitlines()
                         if not ln.strip().lower().startswith("from"))
    assert "qwen" not in non_from.lower(), (
        "qwen may only appear on the FROM line, not in the SYSTEM persona"
    )


# ===========================================================================
# NOTICE / ATTRIBUTION (security)
# ===========================================================================

def test_notice_exists_and_names_qwen_base_and_license():
    notice = (REPO_ROOT / "NOTICE").read_text()
    assert "Qwen2.5-3B-Instruct" in notice
    assert "Qwen Research License" in notice, "must name the (non-Apache) license"
    assert "huggingface.co/Qwen/Qwen2.5-3B-Instruct" in notice, "upstream URL"
    assert "NOT Apache-2.0" in notice, "must flag the license is not Apache-2.0"


def test_notice_states_redistribution_attribution_requirement():
    """Architecture: NOTICE must state HF-card + GitHub-release carry it too."""
    notice = (REPO_ROOT / "NOTICE").read_text().lower()
    assert "model card" in notice
    assert "release" in notice
    assert "redistribut" in notice


def test_license_points_to_notice():
    lic = (REPO_ROOT / "LICENSE").read_text().lower()
    assert "notice" in lic, "LICENSE must point to NOTICE for bundled model licenses"


# ===========================================================================
# PACKAGING-SCRIPT SECURITY
# ===========================================================================

def test_package_script_embeds_no_credentials():
    script = (REPO_ROOT / "scripts/package_ai_eng.sh").read_text()
    # No hardcoded tokens.
    assert not re.search(r"hf_[A-Za-z0-9]{20,}", script), "looks like an HF token"
    assert not re.search(r"ghp_[A-Za-z0-9]{20,}", script), "looks like a GitHub PAT"
    assert not re.search(r"(?i)(api[_-]?key|secret|password)\s*=\s*['\"][^'\"]{8,}",
                         script), "embedded credential literal"
    # Login is a manual step, not baked in.
    assert "huggingface-cli login" in script
    assert "gh auth login" in script


def test_package_script_exits_nonzero_on_missing_inputs(tmp_path):
    """Missing --base-dir/--lora-dir → prints manual steps, exits nonzero,
    performs NO download."""
    r = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/package_ai_eng.sh")],
        capture_output=True, text=True, timeout=30,
        cwd=str(tmp_path),
    )
    assert r.returncode != 0, "must fail when required inputs are missing"
    assert "Manual steps" in (r.stdout + r.stderr)
    # It must not have invented or fetched weights.
    assert "huggingface-cli download" in (r.stdout + r.stderr), (
        "should DOCUMENT the manual download, not perform it"
    )


def test_package_script_weight_download_is_only_documentation():
    """`huggingface-cli download` of the base weights must appear ONLY inside a
    documentation heredoc / comment — never as an executable command the
    script runs on the user's behalf (it must not fetch arbitrary weights)."""
    script = (REPO_ROOT / "scripts/package_ai_eng.sh").read_text()
    in_heredoc = False
    heredoc_tag = None
    offending = []
    for ln in script.splitlines():
        s = ln.strip()
        # Track heredoc bodies (cat <<'TAG' ... TAG). Anything inside is text.
        if not in_heredoc:
            m = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", ln)
            if m:
                in_heredoc = True
                heredoc_tag = m.group(1)
                continue
        else:
            if s == heredoc_tag:
                in_heredoc = False
                heredoc_tag = None
            continue  # inside heredoc → documentation, allowed
        if s.startswith("#"):
            continue  # comment → allowed
        if "huggingface-cli download" in s:
            offending.append(ln)
    assert not offending, (
        f"package script EXECUTES a weight download (must be doc-only): {offending}"
    )


def test_package_script_passes_bash_syntax():
    r = subprocess.run(["bash", "-n", str(REPO_ROOT / "scripts/package_ai_eng.sh")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_check_artifact_script_passes_bash_syntax():
    r = subprocess.run(["bash", "-n", str(REPO_ROOT / "scripts/check_ai_eng_artifact.sh")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_setup_sh_passes_bash_syntax():
    r = subprocess.run(["bash", "-n", str(REPO_ROOT / "scripts/setup.sh")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ===========================================================================
# SUPPLY-CHAIN: digest gate exists and gates the create
# ===========================================================================

def test_setup_mirror_create_is_gated_behind_sha256_check():
    """The ollama-create-from-gguf must be reachable only after a sha256 match
    and only when the digest is not the placeholder (static assertion that the
    fail-closed structure is present in source)."""
    src = (REPO_ROOT / "scripts/setup.sh").read_text()
    # Fail-closed on placeholder.
    assert '"$_sha256" == "__PLACEHOLDER_SHA256__"' in src
    # sha mismatch path discards the file and skips create.
    assert "sha256 mismatch" in src.lower()
    # The create happens via a generated Modelfile only inside _install_from_gguf.
    assert "_install_from_gguf" in src


def test_check_artifact_uses_head_not_blob_download():
    """check_ai_eng_artifact.sh probes with HEAD (-I), never downloads the blob."""
    src = (REPO_ROOT / "scripts/check_ai_eng_artifact.sh").read_text()
    assert "-I" in src, "must use HEAD probes"
    assert "-o /dev/null" in src, "must discard any body"


# ===========================================================================
# BUDDY — ai-eng is Buddy's brain; the id must still resolve post-rename
# ===========================================================================

def test_resilient_chat_default_returns_installed_ai_eng(monkeypatch):
    """_resilient_chat_default('ai-eng:latest') returns it when installed.

    NOTE: the function does a local `from arail.chat import
    detect_installed_models`, so we patch the source module, not the alias."""
    monkeypatch.setenv("LAB_MODE", "airgapped")
    import arail.chat as chat_mod
    monkeypatch.setattr(chat_mod, "detect_installed_models",
                        lambda: [{"id": "ai-eng:latest"}], raising=False)
    from arail.portal import app as portal_app
    assert portal_app._resilient_chat_default("ai-eng:latest") == "ai-eng:latest"


def test_resilient_chat_default_aliases_legacy_ai_engineer(monkeypatch):
    """If only legacy ai-engineer:latest is installed, the ai-eng-family regex
    still resolves Buddy's brain (no broken reference after the rename)."""
    monkeypatch.setenv("LAB_MODE", "airgapped")
    import arail.chat as chat_mod
    monkeypatch.setattr(chat_mod, "detect_installed_models",
                        lambda: [{"id": "ai-engineer:latest"}], raising=False)
    from arail.portal import app as portal_app
    assert portal_app._resilient_chat_default("ai-eng:latest") == "ai-engineer:latest"


def test_no_reference_to_removed_modelfile_production_tag():
    """Buddy plumbing must not point at a now-removed Modelfile.production tag
    or the dead ollama.ai qukaizen/ai-eng:3b tag for the default install."""
    # The catalog install command must be the self-hosted hf.co pull, not the
    # dead ollama.ai tag.
    cat = (REPO_ROOT / "src/arail/chat/models_catalog.yaml").read_text()
    m = re.search(r"^- id: ai-eng:latest\b.*?(?=^- id:|\Z)", cat,
                  re.MULTILINE | re.DOTALL)
    block = m.group(0)
    assert "hf.co/" in block, "ai-eng install must be the self-hosted hf.co pull"
    assert "qukaizen/ai-eng:3b" not in block, "dead ollama.ai tag must be gone"


def test_modelfile_preview_persona_is_ai_eng():
    """Buddy behavior unchanged: the preview Modelfile still yields the ai-eng
    persona (asserted on text, no model load — OOM-safe)."""
    mf = (REPO_ROOT / "models/ai-eng/Modelfile.preview").read_text()
    assert "ai-eng" in mf
    assert "AI engineering expert" in mf or "AI engineer" in mf.lower()


# ===========================================================================
# REGRESSION: honest framing — no 'frontier-scale' in rewritten surfaces
# ===========================================================================

@pytest.mark.parametrize("f", [
    "README.md", "CLAUDE.md",
    "src/arail/portal/templates/tuning.html", "pyproject.toml",
])
def test_no_frontier_scale_in_rewritten_surfaces(f):
    text = (REPO_ROOT / f).read_text()
    assert not re.search(r"frontier-scale", text, re.IGNORECASE), (
        f"{f} still contains 'frontier-scale' marketing"
    )


def test_pyproject_self_hosted_keys_are_placeholder_marked():
    text = (REPO_ROOT / "pyproject.toml").read_text()
    assert 'ai_eng_sha256' in text
    assert "__PLACEHOLDER_SHA256__" in text, "sha must ship as a placeholder"
    assert "ai_eng_hf_repo" in text
    assert 'ai_eng_preview' in text and "qwen2.5:7b" in text, (
        "preview base key must remain (operator config)"
    )


def test_check_artifact_returns_nonzero_today(tmp_path):
    """Documents the 2b deferral: the artifact is not uploaded, so the probe
    must report NOT LIVE (nonzero). It flips to 0 once the GGUF is live.

    OOM/network-safe: we force placeholder repo + a curl shim that always
    fails, so no real network call leaves the box."""
    binp = tmp_path / "bin"; binp.mkdir()
    curl = binp / "curl"
    curl.write_text("#!/usr/bin/env bash\nexit 22\n")
    curl.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{binp}:{env['PATH']}"
    r = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/check_ai_eng_artifact.sh")],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert r.returncode != 0, "probe must report NOT LIVE while artifact unuploaded"
    assert "NOT LIVE" in (r.stdout + r.stderr)
