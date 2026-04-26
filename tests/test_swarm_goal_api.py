from __future__ import annotations

from fastapi.testclient import TestClient


def test_swarm_goal_preview_and_confirm_flow(monkeypatch, tmp_path):
    import arail.goals as goals_mod
    import arail.portal.app as app_mod

    monkeypatch.setattr(goals_mod, "GOALS_DIR", tmp_path / "goals")
    monkeypatch.setattr(goals_mod, "CURRENT_FILE", goals_mod.GOALS_DIR / "current.json")
    monkeypatch.setattr(goals_mod, "PREVIEW_FILE", goals_mod.GOALS_DIR / "preview.json")
    monkeypatch.setattr(goals_mod, "HISTORY_DIR", goals_mod.GOALS_DIR / "history")
    app_mod.goal_store = goals_mod.GoalStore()

    def fake_parse(goal_text: str):
        return {
            "goal": goal_text,
            "domain": "general",
            "primary_objective": goal_text,
            "sub_objectives": ["Choose routing", "Choose lodging"],
            "success_metrics": {},
            "timeline": "late September",
            "constraints": [],
            "resources_needed": [],
        }

    starts: list[dict] = []

    monkeypatch.setattr(app_mod.parser, "parse", fake_parse)
    monkeypatch.setattr(app_mod.parser, "parse_offline", fake_parse)
    monkeypatch.setattr(app_mod.researcher, "_status", "idle", raising=False)
    monkeypatch.setattr(app_mod.researcher, "start", lambda parsed: starts.append(parsed))

    client = TestClient(app_mod.app)

    preview_resp = client.post(
        "/api/goal/preview",
        json={
            "goal": "Plan a family trip to Hokkaido Japan with flights, lodging, and rail routes.",
            "scale": "balanced",
        },
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert preview["status"] == "preview"
    assert preview["swarm"]["goal_archetype"] == "travel"

    confirm_resp = client.post(
        "/api/goal/confirm",
        json={
            "auto_start": True,
            "auto_draft": False,
            "mission_brief": "Bias toward fewer hotel changes.",
            "operator_notes": "Keep kid transit friction low.",
            "enabled_workers": ["scout", "seasonality", "routing", "lodging"],
        },
    )
    assert confirm_resp.status_code == 200
    record = confirm_resp.json()
    assert record["goal_mode"] == "swarm"
    assert record["source"] == "preview"
    assert record["swarm"]["status"] == "confirmed"
    assert record["swarm"]["mission_brief"] == "Bias toward fewer hotel changes."
    assert record["swarm"]["operator_notes"] == "Keep kid transit friction low."
    assert starts
    assert starts[0]["swarm_plan"]["status"] == "confirmed"

    preview_after = client.get("/api/goal/preview")
    assert preview_after.status_code == 200
    assert preview_after.json() is None


def test_clear_swarm_goal_preview(monkeypatch, tmp_path):
    import arail.goals as goals_mod
    import arail.portal.app as app_mod

    monkeypatch.setattr(goals_mod, "GOALS_DIR", tmp_path / "goals")
    monkeypatch.setattr(goals_mod, "CURRENT_FILE", goals_mod.GOALS_DIR / "current.json")
    monkeypatch.setattr(goals_mod, "PREVIEW_FILE", goals_mod.GOALS_DIR / "preview.json")
    monkeypatch.setattr(goals_mod, "HISTORY_DIR", goals_mod.GOALS_DIR / "history")
    app_mod.goal_store = goals_mod.GoalStore()

    monkeypatch.setattr(
        app_mod.parser,
        "parse",
        lambda text: {
            "goal": text,
            "domain": "general",
            "primary_objective": text,
            "sub_objectives": [],
            "success_metrics": {},
            "timeline": "unspecified",
            "constraints": [],
            "resources_needed": [],
        },
    )
    monkeypatch.setattr(app_mod.parser, "parse_offline", app_mod.parser.parse)

    client = TestClient(app_mod.app)
    client.post("/api/goal/preview", json={"goal": "Compare local inference stacks"})

    clear_resp = client.delete("/api/goal/preview")
    assert clear_resp.status_code == 200
    assert clear_resp.json()["ok"] is True
    assert client.get("/api/goal/preview").json() is None