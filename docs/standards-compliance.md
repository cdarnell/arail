# arail — QKZ-PRODUCT-SPEC compliance report

*Status: initial audit · Spec version: 1.0.0 · Audit date: 2026-05-09*

## Conformance summary
- MUST-pass: 8
- MUST-fail: 6
- SHOULD-pass: 5
- SHOULD-fail: 4

arail is the cleanest of the four products audited — strong identity discipline, exemplary security architecture (airgap), durable structured activity log. Principal gaps are HTTP API conventions (versioning, RFC 7807, `X-Request-ID`, pagination, readiness probe) and Prometheus metric prefix.

## Per-section findings

### §1 HTTP API conventions
**Status: PARTIAL**

#### §1.1 Required endpoints

| Endpoint | Status | Evidence |
|---|---|---|
| `GET /health` | PARTIAL | [src/arail/portal/app.py:5976-5993](src/arail/portal/app.py#L5976-L5993); returns `{status, service, version, uptime_seconds, lab_mode}` — **missing `timestamp` (RFC 3339)** |
| `GET /ready` | **FAIL** | Not implemented; `/api/system/health` is detailed diagnostics, not readiness |
| `GET /metrics` | PASS | Prometheus text at [src/arail/portal/app.py:5996-6009](src/arail/portal/app.py#L5996-L6009) |
| `GET /api-docs` | PASS | FastAPI Swagger at `/api/docs` ([app.py:138](src/arail/portal/app.py#L138)) |
| `GET /openapi.json` | PASS | FastAPI auto-provides |
| `GET /version` | **FAIL** | Not implemented |

#### §1.2 Versioned namespace
- **MUST-fail.** All endpoints unversioned (`/api/providers/status`, `/api/chat`, `/api/goal`, etc., 80+ routes). Evidence: `grep -oP '@app\.(get|post|put|patch|delete)\("[^"]+' src/arail/portal/app.py | sort -u`.

#### §1.3 Resource naming
- ✓ Plural lowercase nouns for collections (`/api/agents`, `/api/providers`, `/api/goals`).
- ✓ Some k8s-style: `/api/agents/{id}/loadout`.
- ✗ Verb endpoints: `POST /api/providers/test` (acceptable as MAY when idempotent).
- ✓ No `/apply` with file-path arguments. RCE check PASS.

#### §1.4 Error envelope
- **MUST-fail.** No RFC 7807. Errors are ad-hoc JSON: `{"error": "lab_not_onboarded", "detail": "..."}` ([app.py:180-182](src/arail/portal/app.py#L180-L182)).

#### §1.5 Headers and correlation
- **MUST-fail.** No `X-Request-ID` middleware (only consent-request IDs internally).
- **SHOULD-fail.** No W3C `Traceparent`/`Tracestate`.
- **SHOULD-fail.** No `X-QKZ-Product` response header.

#### §1.6 Pagination
- **MUST-fail.** List endpoints (`/api/agents/list`, `/api/agents/prompts`) use plain `limit` without cursor or `next_cursor`. Evidence: [app.py:2561](src/arail/portal/app.py#L2561).

#### §1.7 Auth
- ✓ Bearer token used for cloud providers ([app.py:1107](src/arail/portal/app.py#L1107)).
- ✓ Tokens never in query strings or logs ([app.py:954-1042](src/arail/portal/app.py#L954-L1042); `chmod 0600` on secrets file).
- **MUST-fail.** Routes not deny-by-default — passphrase gate covers HTML routes; JSON API routes pass through after passphrase without per-route auth.

### §2 Configuration
**Status: PARTIAL**

- **SHOULD-fail §2.1.** Env-var driven, no TOML config files. Acceptable for a local-first lab; document as exception.
- **MUST-fail §2.2.** No Pydantic validation. [src/arail/config.py:36](src/arail/config.py#L36) uses plain `os.getenv()` with hardcoded defaults; invalid values silently fall back.
- ✓ Env vars documented in README.md and `.env.example`.
- **MUST-fail §2.3.** Naming uses `ARAIL_*` and `LAB_*`, not `QKZ_ARAIL_*`. Evidence: 80+ env vars without `QKZ_` prefix.

### §3 Logging
**Status: PARTIAL**

- **MUST-fail §3.1.** No structured JSON to stdout. Operational record is the activity log only.
- ✓ Activity log is structured JSON JSONL ([src/arail/activity.py:50-82](src/arail/activity.py#L50-L82)) with `ts`, `source`, `message`, `level`, `data`.
- ✗ Activity log missing `product` and `version` fields.
- ✓ No `print()` calls in hot paths.
- ✓ Tokens never logged ([app.py:1043](src/arail/portal/app.py#L1043) logs `"Saved provider token for {provider}"` without value).

### §4 Observability
**Status: PARTIAL**

- **MUST-fail §4.1.** Metrics use `arail_*` prefix not `qkz_arail_*`. Evidence: [src/arail/portal/app.py:5881-5970](src/arail/portal/app.py#L5881-L5970).
- ✓ Counters end in `_total`.
- ✓ Low-cardinality labels (no `request_id`, no `user_id`).
- **SHOULD-fail §4.2.** No OpenTelemetry.
- **MUST-fail §4.3.** No `/ready`.

### §5 Identity & naming
**Status: COMPLIANT**

| Artifact | Status |
|---|---|
| Repo dir `arail` | ✓ |
| `pyproject.toml` `name = "arail"` ([pyproject.toml:7](pyproject.toml#L7)) | ✓ |
| FastAPI title (customizable, default `_BRAND.name`) | ACCEPTABLE — blueprint design |
| Slug format | ✓ |
| Metric prefix `arail_*` | needs `qkz_` prefix migration |
| Log `product` field | not emitted (gap) |

Identity is the strongest of the four products. Customizable title is intentional (blueprint design).

### §6 Security defaults
**Status: COMPLIANT**

- ✓ Loopback-only by default; threat model in [SECURITY.md](SECURITY.md).
- ✓ No server-local file paths in API requests.
- ⚠ One token-in-URL pattern at [app.py:1568](src/arail/portal/app.py#L1568) (`?access_token={password}` in marimo URL). Operator-set password, not a true secret, but violates the spirit of §1.7.
- ⚠ Per-route auth not enforced after passphrase gate — acceptable for single-user lab.
- ✓ **EXEMPLARY**: [src/arail/airgap.py:1-152](src/arail/airgap.py#L1-L152) is a model implementation for §6 egress control. `lab_mode()` defaults to `airgapped`, fail-closed semantics, audit-safe error metadata. **This should be cited in QKZ-PRODUCT-SPEC §6 as the reference implementation.**

### §7 Documentation
**Status: PARTIAL**

- ✓ `README.md` (9400+ words).
- **MUST-fail.** No `docs/architecture.md`.
- **MUST-fail.** No `docs/standards-compliance.md` (this document).
- ✓ `SECURITY.md` — comprehensive threat model.
- ✓ 30+ docs in `docs/` (INDEX.md, INSTALL.md, PRIVACY.md, agents.md, design.md, etc.).

### §8 Repo layout
**Status: PARTIAL**

- ✓ `README.md`, `CLAUDE.md`, `SECURITY.md`, `pyproject.toml`.
- **MISSING:** `configs/` with sample TOML files.
- ✓ Substantial `docs/` tree.
- ✓ `src/arail/` with 80+ modules.
- ✓ `tests/` (80+ test files).
- ✓ `sprints/` per workspace CLAUDE.md.

## Strengths to preserve

1. **`airgap.py`** — exemplary egress guard. Cite in spec §6 as reference implementation.
2. **`activity.py`** — durable JSONL log pattern, async-safe SSE fan-out. Pattern is sound; just needs stdout export and `product`/`version` fields added.
3. **`SECURITY.md`** — clear threat model with in-scope/out-of-scope and disclosure window.
4. **Identity discipline** — slug consistent across most artifacts.
5. **Token handling** — `chmod 0600` secrets file, never echoed.
6. **Prometheus metric structure** — proper text format, low-cardinality labels.

## Top remediation priorities

### Critical (MUST-fail)

1. **Implement `/ready`** — distinct from `/health`; 503 when not onboarded or dependencies offline.
2. **Add `timestamp` to `/health` response** — RFC 3339.
3. **RFC 7807 error envelope** — middleware + exception handler.
4. **`X-Request-ID` middleware** — UUID v4 generation, echo, propagate to activity log.
5. **`/version` endpoint** — `{product, version, commit}`.
6. **`/api/v1/` versioned namespace** — migrate 80+ routes; backward-compat alias for one minor release.

### High (MUST-fail, can document exception)

7. **Cursor-based pagination** on list endpoints (~10+ affected).
8. **Env var migration** — `ARAIL_*`/`LAB_*` → `QKZ_ARAIL_*`. Backward-compat aliases.
9. **Metric prefix** — `arail_*` → `qkz_arail_*` in [src/arail/portal/app.py:5847+](src/arail/portal/app.py#L5847).
10. **Activity log: add `product` / `version` fields** at [src/arail/activity.py:50-82](src/arail/activity.py#L50-L82).

### Medium (SHOULD-fail)

11. **Pydantic schema validation** — replace `os.getenv()` calls with `BaseSettings`.
12. **`docs/architecture.md`** — lift from existing docs into one architectural narrative.
13. **`configs/sample-lab.toml`** — even if env-driven, ship a sample for spec compliance.
14. **Export activity log to stdout JSON** — orchestrator-friendly.
15. **Fix token-in-URL** at [app.py:1568](src/arail/portal/app.py#L1568) — use bearer header instead.

## Acceptable exceptions (proposed)

- **§2.1 TOML format** — env-driven config is intentional for local-first single-user lab; document as exception.
- **§4.2 OpenTelemetry** — single-process; not applicable. Activity log is the audit trail.
- **§3.1 stdout JSON logs** — activity log is the durable record; stdout export is a SHOULD upgrade, not a MUST blocker for this product.
- **§1.7 per-route auth** — single-user passphrase model. Document explicitly.

These exceptions need architect signoff per spec §9.

## Reference

- Spec: [QKZ-PRODUCT-SPEC.md](../../QKZ-PRODUCT-SPEC.md)
- Workspace summary: [QKZ-COMPLIANCE-SUMMARY.md](../../QKZ-COMPLIANCE-SUMMARY.md)
