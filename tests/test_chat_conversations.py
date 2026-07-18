"""Chat conversations: PKB-contract store, orphan sweep, API, stream hooks."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from arail.chat.conversations import ConversationStore


@pytest.fixture
def store(monkeypatch, tmp_path):
    root = tmp_path / "pkb" / "conversations"
    monkeypatch.setenv("ARAIL_CONVERSATIONS_DIR", str(root))
    return ConversationStore()


def test_roundtrip(store):
    meta = store.create("physics chat")
    cid = meta["conversation_id"]
    tid = store.start_turn(cid, "what is entropy?", model="m1", backend="b1")
    store.complete_turn(cid, tid, "disorder, roughly", tokens_used=12,
                        latency_ms=80.0)

    folded = store.fold(cid)
    assert folded["skipped_lines"] == 0
    msgs = folded["messages"]
    assert msgs[0] == {"role": "user", "content": "what is entropy?"}
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "disorder, roughly"
    assert msgs[1]["model"] == "m1"

    listed = store.list()
    assert listed[0]["title"] == "physics chat"
    assert listed[0]["turns"] == 1


def test_jsonl_never_json_invariant(store):
    """A .json transcript would be vector-indexed into the wiki (pinned)."""
    meta = store.create()
    cid = meta["conversation_id"]
    store.start_turn(cid, "hi")
    files = list((store.root / cid).iterdir())
    json_files = [f.name for f in files if f.suffix == ".json"]
    assert json_files == ["meta.json"]           # meta.json only, ever
    assert any(f.name == "transcript.jsonl" for f in files)


def test_orphan_sweep_idempotent(store):
    cid = store.create()["conversation_id"]
    store.start_turn(cid, "will be interrupted")   # no terminal event
    assert store.sweep_orphans() == 1
    folded = store.fold(cid)
    assert folded["messages"][0]["content"] == "will be interrupted"
    assert folded["turns"][0]["status"] == "interrupted"
    assert store.sweep_orphans() == 0              # second sweep: no-op


def test_torn_last_line_skipped(store):
    cid = store.create()["conversation_id"]
    tid = store.start_turn(cid, "hello")
    store.complete_turn(cid, tid, "world")
    with open(store._transcript(cid), "a") as f:
        f.write('{"v":1,"type":"turn.started","turn_id":"t_torn"')  # torn
    folded = store.fold(cid)
    assert folded["skipped_lines"] == 1
    assert len(folded["messages"]) == 2            # log intact


def test_delete_forgets_forever(store):
    cid = store.create()["conversation_id"]
    store.start_turn(cid, "secret")
    assert store.delete(cid) is True
    assert not (store.root / cid).exists()
    assert store.get_meta(cid) is None


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ARAIL_CONVERSATIONS_DIR",
                       str(tmp_path / "pkb" / "conversations"))
    import arail.portal.app as app_mod
    with TestClient(app_mod.app) as c:
        yield c, app_mod


def test_api_roundtrip(client):
    c, _ = client
    meta = c.post("/api/chat/conversations", json={"title": "t1"}).json()
    cid = meta["conversation_id"]
    assert c.get("/api/chat/conversations").json()["conversations"][0][
        "conversation_id"] == cid
    c.patch(f"/api/chat/conversations/{cid}", json={"title": "renamed"})
    got = c.get(f"/api/chat/conversations/{cid}").json()
    assert got["meta"]["title"] == "renamed"
    assert c.delete(f"/api/chat/conversations/{cid}").status_code == 200
    assert c.get(f"/api/chat/conversations/{cid}").status_code == 404


def test_stream_with_conversation_id_persists(client, monkeypatch):
    c, app_mod = client

    async def _fake_stream(**kwargs):
        yield {"type": "start", "backend": "fake", "model": "m"}
        yield {"type": "delta", "delta": "hel"}
        yield {"type": "delta", "delta": "lo"}
        yield {"type": "final", "reply": "hello", "tokens_used": 2}

    monkeypatch.setattr(app_mod, "_run_chat_completion_stream",
                        lambda **kw: _fake_stream(**kw))

    cid = c.post("/api/chat/conversations", json={}).json()["conversation_id"]
    r = c.post("/api/chat/stream", json={"message": "hi",
                                         "conversation_id": cid})
    assert r.status_code == 200
    folded = c.get(f"/api/chat/conversations/{cid}").json()
    assert [m["content"] for m in folded["messages"]] == ["hi", "hello"]
    assert folded["turns"][0]["status"] == "completed"


def test_stream_without_conversation_id_persists_nothing(client, monkeypatch,
                                                         tmp_path):
    c, app_mod = client

    async def _fake_stream(**kwargs):
        yield {"type": "final", "reply": "ok"}

    monkeypatch.setattr(app_mod, "_run_chat_completion_stream",
                        lambda **kw: _fake_stream(**kw))
    r = c.post("/api/chat/stream", json={"message": "warm ping"})
    assert r.status_code == 200
    root = tmp_path / "pkb" / "conversations"
    assert not root.exists() or not any(root.iterdir())


def test_stream_failure_records_partial(client, monkeypatch):
    c, app_mod = client

    async def _fake_stream(**kwargs):
        yield {"type": "delta", "delta": "par"}
        yield {"type": "final", "reply": "", "error": "backend died"}

    monkeypatch.setattr(app_mod, "_run_chat_completion_stream",
                        lambda **kw: _fake_stream(**kw))
    cid = c.post("/api/chat/conversations", json={}).json()["conversation_id"]
    c.post("/api/chat/stream", json={"message": "hi", "conversation_id": cid})
    folded = c.get(f"/api/chat/conversations/{cid}").json()
    turn = folded["turns"][0]
    assert turn["status"] == "failed"
    assert turn["partial"] == "par"
