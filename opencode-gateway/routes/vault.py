from fastapi import APIRouter, HTTPException, Request
import os
import json
import time
import requests

router = APIRouter()


@router.post("/api/vault/store-token")
async def store_token(body: dict):
    token = body.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="missing token")

    vault_addr = os.getenv("VAULT_ADDR")
    vault_token = os.getenv("VAULT_TOKEN")
    secret_path = os.getenv("VAULT_SECRET_PATH", "secret/data/gentoofoo/tokens")

    payload = {"data": {"token": token, "ts": int(time.time())}}
    if vault_addr and vault_token:
        url = vault_addr.rstrip("/") + "/v1/" + secret_path.lstrip("/")
        headers = {"X-Vault-Token": vault_token}
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=10)
            if r.status_code not in (200, 204):
                raise HTTPException(status_code=502, detail=f"vault error: {r.status_code} {r.text}")
            return {"status": "ok", "stored": "vault"}
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=str(e))

    # fallback: write to local data path
    try:
        os.makedirs("/data", exist_ok=True)
        path = "/data/vault_tokens.json"
        existing = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        existing.append({"token": token, "ts": int(time.time())})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f)
        return {"status": "ok", "stored": "file", "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/runbook/goal")
async def store_goal(body: dict):
    goal = body.get("goal")
    if not goal:
        raise HTTPException(status_code=400, detail="missing goal")

    vault_addr = os.getenv("VAULT_ADDR")
    vault_token = os.getenv("VAULT_TOKEN")
    secret_path = os.getenv("VAULT_SECRET_PATH", "secret/data/gentoofoo/runbook_goal")

    payload = {"data": {"goal": goal, "ts": int(time.time())}}
    if vault_addr and vault_token:
        url = vault_addr.rstrip("/") + "/v1/" + secret_path.lstrip("/")
        headers = {"X-Vault-Token": vault_token}
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=10)
            if r.status_code not in (200, 204):
                raise HTTPException(status_code=502, detail=f"vault error: {r.status_code} {r.text}")
            return {"status": "ok", "stored": "vault"}
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=str(e))

    # fallback: write to local file for ephemeral persistence
    try:
        os.makedirs("/data", exist_ok=True)
        path = "/data/runbook_goal.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"goal": goal, "ts": int(time.time())}, f)
        return {"status": "ok", "stored": "file", "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _check_url(url: str, timeout: float = 3.0) -> dict:
    try:
        r = requests.head(url, timeout=timeout)
        return {"ok": True, "status_code": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/api/validate")
async def validate_system():
    """Run quick health and security checks and return results."""
    results = {"health": {}, "security": {}}

    # Vault health
    vault_addr = os.getenv("VAULT_ADDR")
    vault_token = os.getenv("VAULT_TOKEN")
    if vault_addr:
        health = _check_url(vault_addr.rstrip('/') + '/v1/sys/health')
        results['health']['vault'] = health
        results['security']['vault_token_present'] = bool(vault_token)
    else:
        results['health']['vault'] = {"ok": False, "error": "VAULT_ADDR not set"}
        results['security']['vault_token_present'] = False

    # LM Studio / orchestration
    lm = os.getenv('LM_STUDIO_URL') or os.getenv('LM_STUDIO_URL'.upper()) or os.getenv('LM_STUDIO_URL')
    if lm:
        results['health']['lmstudio'] = _check_url(lm)
    else:
        results['health']['lmstudio'] = {"ok": False, "error": 'LM_STUDIO_URL not set'}

    # File system writable (fallback storage)
    try:
        test_path = '/data/health_check.tmp'
        os.makedirs('/data', exist_ok=True)
        with open(test_path, 'w') as f:
            f.write('ok')
        os.remove(test_path)
        results['health']['data_writable'] = {"ok": True}
    except Exception as e:
        results['health']['data_writable'] = {"ok": False, "error": str(e)}

    # Security posture quick checks (zero-trust basics)
    #  - Is CORS wide open? (we added permissive CORS for local UI; recommend locking in prod)
    results['security']['cors_permissive'] = True
    #  - Is webhook secret set?
    results['security']['lmstudio_webhook_secret_set'] = bool(os.getenv('LM_STUDIO_WEBHOOK_SECRET'))
    #  - Are Vault settings configured?
    results['security']['vault_configured'] = bool(vault_addr and vault_token)

    return results
