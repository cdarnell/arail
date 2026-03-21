import os
import json
from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_store_token_fallback(tmp_path, monkeypatch):
    # ensure no VAULT_* env
    monkeypatch.delenv('VAULT_ADDR', raising=False)
    monkeypatch.delenv('VAULT_TOKEN', raising=False)
    # make sure /data points to tmp_path
    monkeypatch.setenv('PYTHONPATH', str(tmp_path))
    data_dir = tmp_path / 'data'
    monkeypatch.setenv('DATA_DIR', str(data_dir))

    # Use route and ensure fallback writes file
    res = client.post('/api/vault/store-token', json={'token': 'sometoken'})
    assert res.status_code == 200
    body = res.json()
    assert body['status'] == 'ok'
    assert body['stored'] in ('file', 'vault')


def test_store_goal(tmp_path, monkeypatch):
    monkeypatch.delenv('VAULT_ADDR', raising=False)
    monkeypatch.delenv('VAULT_TOKEN', raising=False)
    res = client.post('/api/runbook/goal', json={'goal': 'Be an AI champion'})
    assert res.status_code == 200
    body = res.json()
    assert body['status'] == 'ok'


def test_validate_endpoint(monkeypatch):
    # Clear env to simulate minimal setup
    monkeypatch.delenv('VAULT_ADDR', raising=False)
    monkeypatch.delenv('VAULT_TOKEN', raising=False)
    resp = client.get('/api/validate')
    assert resp.status_code == 200
    data = resp.json()
    assert 'health' in data and 'security' in data
