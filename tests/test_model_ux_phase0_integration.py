"""Phase 0 (display fidelity) — the "Persistence & Honesty" checkpoint,
display subset (implementation-order step 9).

Sprint: 2026-07-20-model-ux-unification
Architecture: sprints/2026-07-20-model-ux-unification/ARCHITECTURE.md

This is the "re-run the exact live in-browser test that surfaced the
lies this session" regression, done as a single realistic end-to-end
`GET /api/chat/models` payload assembled from the VISION.md scenario:
a 13.45 GB `gemma-4-26b-a4b` installed via Ollama on a machine with
7.1 GB free. Every gap the sprint set out to close is asserted against
ONE response, the way an operator would actually see it — not just
per-failure-mode in isolation (those live in the sibling
test_model_ux_phase0_*.py files).

If any of these regress, the wedge failed per ARCHITECTURE.md's Test
Strategy > Regression: "Re-run the exact live in-browser test... If any
of header / fake fit / blank telemetry / lying eject / lying Cancel
still shows — wedge failed, does not ship."
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))


class _FakeBackend:
    model_name = "gemma-4-26b-a4b:latest"


class _FakeRouter:
    backend_name = "ollama"
    _backend = _FakeBackend()


def test_gemma_26b_moe_installed_on_a_memory_tight_machine_is_never_lied_about(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import arail.portal.app as app_mod
    import arail.chat as chat_mod
    from arail.portal import model_warmth

    monkeypatch.setattr(app_mod, "_get_primary_router", lambda: _FakeRouter())
    monkeypatch.setenv("ARAIL_MODELS_DIR", str(tmp_path / "models"))

    # VISION.md's exact scenario: gemma-4-26b-a4b (13.45 GB on disk),
    # 7.1 GB free on the host.
    monkeypatch.setattr(app_mod, "_local_memory_snapshot", lambda: {
        "label": "Apple M5", "gpu_label": None,
        "total_gb": 24.0, "used_gb": 16.9, "free_gb": 7.1,
    })
    monkeypatch.setattr(chat_mod, "gallery_view", lambda: {
        "installed": [
            {
                "id": "gemma-4-26b-a4b:latest",
                "runtime": "ollama",
                "size_gb": 13.45,
                "modified": "2026-07-19T10:00:00Z",
                "endpoint": "http://127.0.0.1:11434/v1",
            }
        ],
        "catalog": [], "runtime_counts": {"ollama": 1},
    })
    monkeypatch.setattr(app_mod, "_ollama_ps_resident_ids", lambda: set())
    monkeypatch.setattr(app_mod, "_is_aerollm_installed", lambda: True)
    monkeypatch.setattr(model_warmth, "_tier1_resident", lambda: False)

    client = TestClient(app_mod.app)
    r = client.get("/api/chat/models")
    assert r.status_code == 200
    body = r.json()

    # F-BLANK / BLOCK-1: hardware lives in exactly one place.
    assert body["compact"]["hardware"]["free_gb"] == 7.1
    assert "hardware" not in body

    # F-FAKEFIT / F-MOEBASIS: a 13.45 GB model on a 7.1 GB-free machine is
    # never "Good", and the estimate is based on real disk size, not the
    # ~4B active-param figure.
    gemma = body["compact"]["local_models"]["items"][0]
    assert gemma["id"] == "gemma-4-26b-a4b:latest"
    assert gemma["fit"]["verdict"] != "Good"
    assert gemma["fit"]["verdict"] in ("Marginal", "Requires streaming", "Unknown")
    assert gemma["estimated_vram_gb"] >= 13.4, (
        "estimate must be based on the real 13.45 GB on-disk size (rounds "
        "to 13.4/13.5), never the ~4B active-param figure (A6/F-MOEBASIS)"
    )
    assert gemma["warm"] is False
    assert gemma["endpoint"] == "http://127.0.0.1:11434/v1"

    # F-DEADFIELD: backend_notice is gone (checked at the /api/chat send
    # layer in test_model_ux_phase0_wiring.py; here we confirm it never
    # leaked into the models payload either).
    assert "backend_notice" not in body

    # aeroLLM row: installed, cold (never claims resident, never streaming).
    aerollm = next(b for b in body["optional_backends"] if b["id"] == "aerollm")
    assert aerollm["resident"] is False
    assert aerollm["streamed"] is False


def test_deep_column_header_and_local_column_header_make_no_false_claim():
    """F-HEADER: the static markup itself (not response data) — the local
    column's "8B" ceiling and the deep column's "SSD (streamed)" claim are
    both gone, checked once more here as the final display-fidelity gate."""
    chat_html = os.path.join(
        _REPO_ROOT, "src", "arail", "portal", "templates", "chat.html"
    )
    with open(chat_html, "r", encoding="utf-8") as f:
        text = f.read()
    assert "(&le; 8B)" not in text
    assert "SSD (streamed)" not in text
    assert "backend_notice" not in text
    assert "src/arail/chat/gallery.py" not in text
