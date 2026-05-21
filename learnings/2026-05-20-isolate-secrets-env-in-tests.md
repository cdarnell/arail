# When a test hits a secrets-writing endpoint, isolate secrets.env with a fixture

**Date:** 2026-05-20
**Tags:** [arail, build, qa, security, infra, pitfall]
**Source:** Sprint 2026-05-18-provider-aware-chat-dropdown (QA finding QA-1)

## Action shape

When a test POSTs to an endpoint that persists to `lab/data/secrets.env` (e.g. `/api/chat/default`, `/api/chat/models/set-ctx`), do **wrap it in the `isolated_secrets` fixture** (monkeypatch the secrets path to `tmp_path` AND restore `os.environ` on teardown) instead of letting it write to the default path, because the test will otherwise clobber the developer's *real* saved provider tokens and leak env vars into the rest of the suite — silently, and irreversibly.

## Context

The L4 "chat-wide default" tests (`test_chat_default.py`) POSTed to `/api/chat/default` without redirecting the secrets path. The endpoint did exactly what it does in production: wrote `COMPUTE_SOURCE` + `ARAIL_CHAT_DEFAULT_MODEL` to `lab/data/secrets.env` and set `os.environ`. Running the suite **destroyed the real `secrets.env`** (any saved provider tokens gone) and leaked `COMPUTE_SOURCE` into the process, which was the actual mechanism behind the "env-leak pollution" other tests showed under a full run. QA reproduced it deterministically, restored the file to its pre-QA state, and flagged QA-1. The fix added an `isolated_secrets` fixture to `tests/conftest.py` and applied it to every secrets-writing test; `secrets.env` MD5 is now stable across runs.

Note: `monkeypatch` of the path alone is insufficient — the endpoint also writes `os.environ` directly, which monkeypatch won't undo. The fixture needs explicit `os.environ` save/restore in teardown.

## Why this matters

This violated the CLAUDE.md secrets-hygiene contract ("tokens live in `lab/data/secrets.env` … never mutated by tests") and would have re-fired on every CI run and every contributor's machine, quietly wiping their tokens. It's the kind of defect that erodes trust in the test suite itself — "running the tests broke my setup." Cheap to prevent (one fixture), expensive and confusing to diagnose after the fact. Any new endpoint that writes secrets/env should ship its tests with the fixture from line one.

## Related learnings

- [2026-05-05-allow-egress-task-scope.md](2026-05-05-allow-egress-task-scope.md) — the other secrets/egress-hygiene subtlety in ARAIL; same family of "the lab runs on others' machines, don't let test/runtime code widen the blast radius."
- [2026-05-20-reachability-tests-for-new-classes.md](2026-05-20-reachability-tests-for-new-classes.md) — the other pitfall from this same sprint (caught in review, not QA).
