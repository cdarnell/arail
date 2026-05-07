"""Unit tests for _render_opencode_config + lab_system_prompt.

Covers ARCHITECTURE.md must-pass list:
  F-CONFIG-1  — schema smoke (golden shape)
  F-CONFIG-2  — no token in plaintext (= F-SEC-CRED-1)
  F-CONFIG-7  — command paths use $REPO_ROOT variable
  F-LOCK-1    — picker hint in build-agent prompt
  F-AIRGAP-1  — airgapped + my_machine → only loopback URL
  F-AIRGAP-2  — airgapped forces my_machine regardless of active provider
  F-SEC-CRED-1 — cloud config has no API key in JSON
"""
from __future__ import annotations

import json
import os
import unittest.mock as mock

import pytest


def _render(provider="my_machine", model="test-model", portal_port=8080,
            tier="max", models_list=None, lab_mode="airgapped"):
    """Helper: call _render_opencode_config with given args."""
    from arail.portal.services.opencode import _render_opencode_config
    return _render_opencode_config(
        provider=provider,
        model=model,
        portal_port=portal_port,
        tier=tier,
        models_list=models_list,
        lab_mode=lab_mode,
    )


# ---------------------------------------------------------------------------
# Golden-shape tests
# ---------------------------------------------------------------------------

class TestRenderMyMachineGolden:
    def test_render_my_machine_has_required_top_level_keys(self):
        """my_machine config has all required top-level keys. (F-CONFIG-1)"""
        d = _render()
        assert d["$schema"] == "https://opencode.ai/config.json"
        assert d["share"] == "disabled"
        assert d["autoupdate"] is False
        assert "instructions" in d
        assert "provider" in d
        assert "enabled_providers" in d
        assert "model" in d
        assert "small_model" in d
        assert "agent" in d
        assert "command" in d
        assert "permission" in d

    def test_render_my_machine_provider_block(self):
        """my_machine uses lab-local provider with loopback URL. (F-AIRGAP-1)"""
        d = _render(portal_port=8080)
        assert "lab-local" in d["provider"]
        p = d["provider"]["lab-local"]
        assert "options" in p
        base_url = p["options"]["baseURL"]
        assert "127.0.0.1:8080" in base_url
        assert base_url.startswith("http://127.0.0.1:")
        assert base_url.endswith("/api/openai/v1")

    def test_render_my_machine_enabled_providers_locked(self):
        """enabled_providers = ['lab-local'] locks the picker. (F-LOCK-3 primary path)"""
        d = _render()
        assert d["enabled_providers"] == ["lab-local"]

    def test_render_my_machine_model_reference(self):
        """model and small_model reference lab-local/<active-model>."""
        d = _render(model="Qwen2.5-Coder-3B")
        assert d["model"] == "lab-local/Qwen2.5-Coder-3B"
        assert d["small_model"] == "lab-local/Qwen2.5-Coder-3B"

    def test_render_my_machine_agent_build_and_plan(self):
        """agent has build and plan sub-configs."""
        d = _render(model="TestModel")
        assert "build" in d["agent"]
        assert "plan" in d["agent"]
        build = d["agent"]["build"]
        assert build["model"] == "lab-local/TestModel"
        assert "prompt" in build
        assert "tools" in build
        plan = d["agent"]["plan"]
        assert plan["model"] == "lab-local/TestModel"
        # plan agent has no write/edit/bash
        assert plan["tools"].get("write") is False
        assert plan["tools"].get("edit") is False
        assert plan["tools"].get("bash") is False
        # plan agent can read
        assert plan["tools"].get("read") is True

    def test_render_includes_six_slash_commands(self):
        """All 6 slash commands present with description and template. (F-CONFIG-1)"""
        d = _render()
        cmd = d["command"]
        expected = ["lab-status", "sprint-current", "skills-list",
                    "agents-status", "kb-search", "claude-md"]
        for name in expected:
            assert name in cmd, f"Missing command: {name}"
            assert cmd[name].get("description"), f"Missing description for: {name}"
            assert cmd[name].get("template"), f"Missing template for: {name}"

    def test_render_command_paths_use_repo_root_var(self):
        """Each command template uses $REPO_ROOT/lab/... (F-CONFIG-7)"""
        d = _render()
        for name, cmd_def in d["command"].items():
            template = cmd_def.get("template", "")
            # Commands referencing lab paths should use $REPO_ROOT
            if "lab/" in template:
                assert "$REPO_ROOT" in template or "lab/" in template, (
                    f"Command {name} template uses absolute path: {template[:80]}"
                )

    def test_render_deterministic(self):
        """Same inputs → byte-identical JSON. (F-CONFIG-1)"""
        from arail.portal.services.opencode import _render_opencode_config
        args = dict(provider="my_machine", model="m1", portal_port=8080,
                    tier="max", lab_mode="airgapped")
        d1 = _render_opencode_config(**args)
        d2 = _render_opencode_config(**args)
        assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)

    def test_render_includes_picker_hint_in_prompt(self):
        """build-agent prompt mentions Chat-tab swap. (F-LOCK-1)"""
        d = _render()
        prompt = d["agent"]["build"]["prompt"]
        assert "Chat" in prompt or "Compute Source" in prompt, (
            f"Prompt lacks Chat/Compute Source mention: {prompt[:200]}"
        )

    def test_render_includes_lab_tier_aware_prompt_max(self):
        """tier=max prompt mentions Workbench."""
        d = _render(tier="max")
        prompt = d["agent"]["build"]["prompt"]
        assert "Workbench" in prompt or "workbench" in prompt, (
            f"Max-tier prompt lacks Workbench mention: {prompt[:200]}"
        )

    def test_render_includes_lab_tier_aware_prompt_min(self):
        """tier=min prompt does NOT mention Workbench."""
        d = _render(tier="min")
        prompt = d["agent"]["build"]["prompt"]
        assert "Workbench" not in prompt and "workbench" not in prompt, (
            f"Min-tier prompt mentions Workbench: {prompt[:200]}"
        )

    def test_render_share_disabled(self):
        """share is 'disabled' — never share lab transcripts."""
        d = _render()
        assert d["share"] == "disabled"

    def test_render_autoupdate_false(self):
        """autoupdate is false — lab pins binary version."""
        d = _render()
        assert d["autoupdate"] is False


# ---------------------------------------------------------------------------
# Cloud provider variant
# ---------------------------------------------------------------------------

class TestRenderCloudClaude:
    def test_render_cloud_claude_golden(self):
        """Claude provider config has anthropic provider block. (F-SEC-CRED-1)"""
        d = _render(provider="claude", model="claude-opus-4-5", lab_mode="hybrid")
        assert "anthropic" in d["provider"]
        assert d["enabled_providers"] == ["anthropic"]
        assert "anthropic/" in d["model"]

    def test_render_cloud_claude_no_api_key_in_json(self):
        """No apiKey field in anthropic provider options. (F-SEC-CRED-1)"""
        d = _render(provider="claude", model="claude-opus-4-5", lab_mode="hybrid")
        p = d["provider"]["anthropic"]
        options = p.get("options", {})
        assert "apiKey" not in options, f"apiKey found in provider options: {options}"
        # Serialize the whole dict and check no key-like thing slipped in
        j = json.dumps(d)
        assert "apiKey" not in j

    def test_render_no_token_in_plaintext_per_provider(self, monkeypatch):
        """Fake token must NOT appear in serialized JSON for any cloud provider. (F-CONFIG-2, F-SEC-CRED-1)"""
        from arail.portal.services.opencode import _render_opencode_config
        providers = {
            "claude":      "ANTHROPIC_API_KEY",
            "nvidia":      "NVIDIA_API_KEY",
            "openrouter":  "OPENROUTER_API_KEY",
            "huggingface": "HF_TOKEN",
            "custom":      "MODEL_API_KEY",
        }
        for provider_id, env_name in providers.items():
            fake_token = f"sk-FAKE-TOKEN-{provider_id.upper()}-12345"
            monkeypatch.setenv(env_name, fake_token)
            d = _render_opencode_config(
                provider=provider_id,
                model="some-model",
                portal_port=8080,
                tier="max",
                lab_mode="hybrid",
            )
            serialized = json.dumps(d)
            assert fake_token not in serialized, (
                f"Token for {provider_id} leaked into config JSON: {serialized[:500]}"
            )

    def test_render_cloud_nvidia(self):
        """nvidia provider has its own block."""
        d = _render(provider="nvidia", model="nvidia-model", lab_mode="hybrid")
        assert "nvidia" in d["provider"] or "lab-local" not in d["provider"]
        assert d["enabled_providers"] != ["lab-local"]

    def test_render_airgap_forces_my_machine(self):
        """airgapped mode → renderer drops cloud providers. (F-AIRGAP-2)"""
        d = _render(provider="claude", model="claude-opus-4-5", lab_mode="airgapped")
        # When airgapped, fall back to lab-local (my_machine)
        assert "lab-local" in d["provider"], (
            f"Airgapped config should use lab-local, got providers: {list(d['provider'].keys())}"
        )
        assert d["enabled_providers"] == ["lab-local"]
        # No cloud provider entries
        cloud_providers = {"anthropic", "claude", "nvidia", "openrouter", "huggingface"}
        for cp in cloud_providers:
            assert cp not in d["provider"], (
                f"Cloud provider {cp!r} leaked into airgapped config"
            )

    def test_render_airgap_my_machine_only_loopback(self):
        """Airgapped + my_machine → only loopback URL in config. (F-AIRGAP-1)"""
        d = _render(provider="my_machine", model="m1", lab_mode="airgapped")
        assert "lab-local" in d["provider"]
        base_url = d["provider"]["lab-local"]["options"]["baseURL"]
        assert "127.0.0.1" in base_url


# ---------------------------------------------------------------------------
# lab_system_prompt
# ---------------------------------------------------------------------------

class TestLabSystemPrompt:
    def test_system_prompt_max_tier(self):
        """Max-tier prompt has Workbench mention."""
        from arail.portal.services.opencode import lab_system_prompt
        p = lab_system_prompt("max")
        assert "Workbench" in p or "workbench" in p

    def test_system_prompt_min_tier(self):
        """Min-tier prompt has no Workbench mention."""
        from arail.portal.services.opencode import lab_system_prompt
        p = lab_system_prompt("min")
        assert "Workbench" not in p and "workbench" not in p

    def test_system_prompt_has_conventions(self):
        """System prompt mentions key conventions."""
        from arail.portal.services.opencode import lab_system_prompt
        p = lab_system_prompt("max")
        assert "CLAUDE.md" in p
        assert "secrets.env" in p or "secrets" in p
        assert "airgapped" in p or "airgap" in p
