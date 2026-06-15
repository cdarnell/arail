"""test_llama_disclosure.py — F9: machine-verified Llama disclosure contract.

This test is a STOP-SHIP gate. It fails if any disclosure surface drifts:
  - Modelfile.default SYSTEM prompt
  - models_catalog.yaml entry
  - README.md
  - NOTICE file
  - licenses/ directory

The Llama 3.2 Community License requires that derived models and apps
disclose the base model. "Built with Llama" must appear in the product
surface and the model id must start with "llama-".

Do NOT remove or soften these assertions — they are the contract between
the engineering team and the license.
"""
from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).parent.parent

# Canonical paths
MODELFILE = REPO / "models" / "ai-eng" / "Modelfile.default"
CATALOG = REPO / "src" / "arail" / "chat" / "models_catalog.yaml"
README = REPO / "README.md"
NOTICE = REPO / "NOTICE"
LICENSES_DIR = REPO / "licenses"


def test_modelfile_default_exists():
    """Modelfile.default must exist — it is the disclosure anchor."""
    assert MODELFILE.exists(), (
        f"Missing {MODELFILE} — Llama persona-wrap Modelfile not found. "
        "This is a stop-ship disclosure failure."
    )


def test_modelfile_default_from_llama():
    """Modelfile.default must pull from a llama3.2 base (not a swap-in)."""
    text = MODELFILE.read_text()
    # FROM line must reference llama3.2
    from_lines = [ln for ln in text.splitlines() if ln.strip().upper().startswith("FROM")]
    assert from_lines, "Modelfile.default has no FROM line"
    from_model = from_lines[0].strip().split()[-1].lower()
    assert "llama3.2" in from_model or "llama-3.2" in from_model, (
        f"Modelfile.default FROM is '{from_model}', expected llama3.2:1b. "
        "Changing the base model requires a new disclosure review."
    )


def test_modelfile_default_system_contains_built_with_llama():
    """SYSTEM prompt must contain 'Built with Llama' — required disclosure."""
    text = MODELFILE.read_text()
    assert "Built with Llama" in text, (
        "Modelfile.default SYSTEM prompt does not contain 'Built with Llama'. "
        "This is a Llama 3.2 Community License disclosure violation. "
        "Stop-ship: do not merge until this is restored."
    )


def test_catalog_default_model_id_starts_with_llama():
    """The default model id in models_catalog.yaml must start with 'llama-'."""
    text = CATALOG.read_text()
    # Catalog uses YAML list format: "- id: llama-ai-eng" OR "  id: llama-ai-eng"
    # Match both list-entry style and plain mapping style.
    id_matches = re.findall(r"^\s*-?\s*id:\s*(\S+)", text, re.MULTILINE)
    assert id_matches, f"No 'id:' entries found in {CATALOG}"
    default_id = id_matches[0]  # first entry is the default model
    assert default_id.startswith("llama-"), (
        f"Default model id in catalog is '{default_id}', expected to start with 'llama-'. "
        "The Llama 3.2 license requires the model id to reflect its lineage."
    )


def test_catalog_contains_built_with_llama():
    """models_catalog.yaml must mention 'Built with Llama' for the llama-ai-eng entry."""
    text = CATALOG.read_text()
    assert "Built with Llama" in text, (
        "models_catalog.yaml does not contain 'Built with Llama'. "
        "The catalog description for llama-ai-eng must carry the disclosure phrase."
    )


def test_readme_contains_built_with_llama():
    """README.md must contain 'Built with Llama' — user-facing disclosure."""
    text = README.read_text()
    assert "Built with Llama" in text, (
        "README.md does not contain 'Built with Llama'. "
        "The Llama 3.2 Community License requires visible disclosure in the project README."
    )


def test_notice_references_llama_license():
    """NOTICE must reference the Llama 3.2 Community License."""
    assert NOTICE.exists(), f"NOTICE file missing at {NOTICE}"
    text = NOTICE.read_text()
    assert "Llama 3.2 Community License" in text, (
        "NOTICE does not reference 'Llama 3.2 Community License'. "
        "Third-party attribution is required."
    )


def test_notice_references_aup():
    """NOTICE must reference the Llama 3.2 Acceptable Use Policy."""
    text = NOTICE.read_text()
    assert "Acceptable Use Policy" in text or "use-policy" in text, (
        "NOTICE does not reference the Llama 3.2 Acceptable Use Policy (AUP). "
        "The AUP reference is required alongside the license."
    )


def test_licenses_dir_has_llama_community_license():
    """licenses/ must contain the Llama 3.2 Community License text."""
    license_file = LICENSES_DIR / "LLAMA-3.2-COMMUNITY-LICENSE.txt"
    assert license_file.exists(), (
        f"Missing {license_file}. "
        "The Llama 3.2 Community License text must be bundled in licenses/. "
        "Stop-ship: redistribution without the license text violates the license."
    )
    # Must have non-trivial content
    content = license_file.read_text().strip()
    assert len(content) > 100, (
        f"{license_file} appears empty or truncated. "
        "The full license text must be present."
    )


def test_licenses_dir_has_llama_aup():
    """licenses/ must contain the Llama 3.2 Acceptable Use Policy text."""
    aup_file = LICENSES_DIR / "LLAMA-3.2-ACCEPTABLE-USE-POLICY.txt"
    assert aup_file.exists(), (
        f"Missing {aup_file}. "
        "The Llama 3.2 AUP must be bundled in licenses/. "
        "Stop-ship: redistribution without the AUP violates the license."
    )
    content = aup_file.read_text().strip()
    assert len(content) > 100, (
        f"{aup_file} appears empty or truncated. "
        "The full AUP text must be present."
    )
