from __future__ import annotations

from fastapi.testclient import TestClient


class _FakeBackend:
    model_name = "mlx-community/Qwen3-8B-4bit"


class _FakeRouter:
    backend_name = "mlx"
    _backend = _FakeBackend()


def _client(monkeypatch):
    import arail.portal.app as app_mod

    monkeypatch.setattr(app_mod, "_get_primary_router", lambda: _FakeRouter())
    return TestClient(app_mod.app), app_mod


def test_api_chat_models_exposes_compact_selector_payload(monkeypatch, tmp_path):
    client, app_mod = _client(monkeypatch)

    import arail.chat as chat_mod

    monkeypatch.setenv("ARAIL_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("COMPUTE_SOURCE", "my_machine")
    monkeypatch.setattr(app_mod, "_local_memory_snapshot", lambda: {
        "label": "Apple M5",
        "gpu_label": None,
        "total_gb": 24.0,
        "used_gb": 6.0,
        "free_gb": 18.0,
    })
    monkeypatch.setattr(chat_mod, "gallery_view", lambda: {
        "installed": [
            {
                "id": "mlx-community/Qwen3-8B-4bit",
                "runtime": "mlx",
                "size_gb": 7.8,
                "modified": "2026-04-27T10:00:00Z",
                "endpoint": None,
            }
        ],
        "catalog": [],
        "runtime_counts": {"mlx": 1},
    })

    r = client.get("/api/chat/models")

    assert r.status_code == 200
    body = r.json()

    assert body["provider"] == "my_machine"
    assert body["compact"]["label"] == "Model"
    assert body["compact"]["hosting_line"] == "Local (default) · Claude · NVIDIA · OpenRouter · HF"
    assert body["compact"]["compute_sources"][0]["inline_label"] == "Local (default)"
    assert body["compact"]["local_models"]["title"] == "Local Models"
    assert body["compact"]["local_models"]["items"][0]["label"] == "Qwen3-8B-4bit"
    assert body["compact"]["local_models"]["items"][0]["badge"] == "new"
    assert body["compact"]["local_models"]["items"][0]["fit"]["verdict"] == "Good"
    assert body["compact"]["local_models"]["headroom"] == "Detected: 24GB Apple M5 · Headroom: Good"
    assert body["onboarding"]["title"] == "Local Models — How to add"
    assert body["onboarding"]["folder"] == str(tmp_path / "models")
    assert str(tmp_path / "models") in body["onboarding"]["cli_example"]
    assert body["model_load"]["state"] == "ready"
    assert body["model_load"]["blocking"] is False


def test_api_chat_models_reports_streaming_actions_for_large_local_model(monkeypatch, tmp_path):
    client, app_mod = _client(monkeypatch)

    import arail.chat as chat_mod

    monkeypatch.setenv("ARAIL_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(app_mod, "_local_memory_snapshot", lambda: {
        "label": "Apple M5",
        "gpu_label": None,
        "total_gb": 24.0,
        "used_gb": 6.0,
        "free_gb": 18.0,
    })
    monkeypatch.setattr(chat_mod, "gallery_view", lambda: {
        "installed": [
            {
                "id": "Qwen3-30B-4bit",
                "runtime": "mlx",
                "size_gb": 22.0,
                "modified": "",
                "endpoint": None,
            }
        ],
        "catalog": [],
        "runtime_counts": {"mlx": 1},
    })

    r = client.get("/api/chat/models")

    assert r.status_code == 200
    body = r.json()

    fit = body["local_model_entries"][0]["fit"]
    assert fit["verdict"] == "Requires streaming"
    assert fit["actions"] == ["Enable streaming", "Select smaller model"]
    assert "Estimated model VRAM need: 22.0GB" in fit["limits"]


def test_chat_page_renders_compact_single_thread_shell():
    import arail.portal.app as app_mod

    client = TestClient(app_mod.app)
    r = client.get("/chat")

    assert r.status_code == 200
    assert "Responses" in r.text
    assert "Local Models — How to add" in r.text
    assert "Control Panel" in r.text
    assert "Preset Starters" in r.text
    assert "These are the starter lines inserted into the input" in r.text
    assert "Reset defaults" in r.text
    assert "You are a helpful assistant. Answer clearly and directly. If the request is unclear, ask one short clarifying question." in r.text
    assert ".chat-modal-backdrop[hidden]" in r.text
    assert "Terminal Pop Out" not in r.text


def test_chat_model_load_endpoints_prepare_and_report_state(monkeypatch):
    client, app_mod = _client(monkeypatch)

    r = client.post("/api/chat/model-load", json={
        "model": "mlx-community/Qwen3-8B-4bit",
        "runtime": "",
        "provider": "my_machine",
    })

    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "ready"
    assert body["blocking"] is False
    assert body["message"].endswith("ready")

    status = client.get("/api/chat/model-load")
    assert status.status_code == 200
    assert status.json()["state"] == "ready"

    canceled = client.post("/api/chat/model-load/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["state"] == "canceled"
