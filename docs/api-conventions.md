---
title: ARAIL API Conventions
description: "Reference for all /api/* endpoints: response shapes, error codes, streaming rules, and airgap gating."
category: Reference
order: 10
tags:
  - api
  - reference
  - conventions
audience: operator
related:
  - agents-explained
  - agents
buddy_prompt: "Show me how the API is shaped so I can wire up my own tooling against this lab."
---
# ARAIL API Conventions

**Scope:** All new `/api/*` endpoints added in sprint `2026-05-14-platform-foundation`
and forward. Pre-existing endpoints are listed in the "Known drift" section below;
they are not fixed here — fixing them is a separate backlog item.

---

## 1. Response format

All API endpoints return `application/json`. No XML, no plain-text except where
explicitly noted (e.g. Server-Sent Event streams use `text/event-stream`).

## 2. Key naming

All JSON keys are `snake_case`. No `camelCase`, no kebab-case in key names.

## 3. Error envelope

When an endpoint returns a non-2xx status code, the response body MUST be:

```json
{
  "error": "<machine_readable_slug>",
  "message": "<human_readable_sentence>"
}
```

`error` is lowercase, underscore-separated (e.g. `not_implemented`, `invalid_query`,
`not_found`). `message` is a plain English sentence suitable for display.

Example — bad query parameter:

```json
{
  "error": "invalid_query",
  "message": "Unknown format 'xml'. Supported formats: json."
}
```

Example — reserved-but-not-implemented feature:

```json
{
  "error": "not_implemented",
  "message": "Prometheus format is reserved for a future release."
}
```

## 4. Status code rules

| Situation | Status |
|---|---|
| Success | 200 |
| Created (POST that creates a resource) | 201 |
| Redirect (permanent or temporary) | 301 / 302 |
| Bad request or invalid query param | 400 |
| Unauthorized | 401 |
| Not found | 404 |
| Not implemented | 501 |
| Unhandled server error | 500 |

Unknown query parameters are **silently ignored** (forward-compatibility).

## 5. Schema versioning

Endpoints that return structured data intended to be scripted against MUST include
either:

- `"version": "<string>"` — for endpoints returning system info (e.g. `/api/system/health`)
- `"schema_version": <int>` — for metrics/time-series shapes (e.g. `/api/system/metrics`)

Incrementing `schema_version` signals a breaking shape change. Additive changes
(new keys) are not breaking and do not require a version bump.

## 6. URL path naming

- Paths are `kebab-case` segments: `/api/system/health`, `/api/skills/packs`.
- No `/api/v1/` prefix. Version is surfaced in the response body (`schema_version`),
  not the URL.
- Sub-resources use `/` nesting: `/api/skills/{skill_id}`.

## 7. Counter persistence

In-process counters (e.g. `http_requests_total` on `/api/system/metrics`) reset to
zero on portal restart. This is a documented v1 limitation. Persistent metrics
(Prometheus remote-write, OpenTelemetry) are a future item.

## 8. Loopback-only, no auth on system endpoints

`/api/system/health` and `/api/system/metrics` are anonymous on loopback
(`BIND_ADDR=127.0.0.1` default). Operators who expose the portal on a non-loopback
address should add a reverse-proxy auth layer.

---

## Known drift (pre-existing endpoints that do not conform)

The following pre-existing endpoints deviate from the conventions above.
They are listed here for visibility; fixing them is deferred to avoid scope creep.

| Endpoint | Deviation | Backlog |
|---|---|---|
| `POST /api/system/mode` | Returns `{"ok": false, "error": "..."}` — `error` is a top-level field but no `message` key | Add `message` on next touch |
| `GET /api/system/health` | Returns `service_checks` list with camelCase-adjacent mixed naming inside check dicts (`check_id`, `name`, `ok`, `detail` — these are snake_case, OK; but no `schema_version`) | Add `version` field (done in this sprint) |
| `POST /api/skills/{skill_id}` | Returns `{"saved": true}` — no `error`/`message` envelope on failure; returns 200 on some error paths | Harden on next touch |
| `GET /api/agents/loadouts` | Returns `{"loadouts": {...}}` — wrapper key deviates from flat style; acceptable since it's a collection | Low-priority |
| Various `POST /api/agent/*` | Some return bare strings or inconsistent shapes | Audit pass deferred |
