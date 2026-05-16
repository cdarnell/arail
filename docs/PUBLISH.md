---
title: Publishing Your Lab
category: Operating
order: 30
tags:
  - publish
  - networking
  - security
audience: operator
related:
  - PRIVACY
  - INSTALL
---
# Publishing Your Lab to the Public Internet

This guide covers what it takes to expose an ARAIL instance beyond
localhost — the way qukaizen.com does. Read every section before you
open a port to the world.

---

## 1. Prerequisites

Before publishing:

- You have run `./arailctl setup` and `./arailctl start` successfully on your
  server. The portal responds on `http://127.0.0.1:8080`.
- You have a domain name pointed at your server's public IP.
- You have a TLS certificate (Let's Encrypt via certbot or Caddy's
  automatic TLS is the easiest path).
- You have set `ARAIL_PASSWORD` in `.env` to a strong passphrase
  (not the placeholder `change-me`). The onboarding gate will block
  all surfaces until this is set.
- You are running on `LAB_TIER=max` if you want the Admin surface
  and the Production Readiness security scan.

---

## 2. Reverse proxy configuration

ARAIL must sit behind a reverse proxy for TLS termination. Two options
are provided: nginx and Caddy.

### nginx

```nginx
server {
    listen 443 ssl;
    server_name lab.example.com;

    ssl_certificate     /etc/letsencrypt/live/lab.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/lab.example.com/privkey.pem;

    # Disable proxy-level buffering so SSE streams (activity log,
    # live checks, security scan) reach the browser in real time.
    proxy_buffering off;
    proxy_cache off;

    location / {
        proxy_pass         http://127.0.0.1:8080;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # Long timeout for inference (local models can take minutes).
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;

        # Required for EventSource (SSE) — do not remove.
        proxy_http_version 1.1;
        proxy_set_header   Connection '';
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name lab.example.com;
    return 301 https://$host$request_uri;
}
```

**Note:** `X-Accel-Buffering: no` is already set by the server on SSE
endpoints. nginx honours this header only when `proxy_buffering off` is
also set at the `location` or `server` level — both are required.

### Caddy

```caddy
lab.example.com {
    reverse_proxy localhost:8080 {
        # Flush responses immediately so SSE works.
        flush_interval -1

        # Inference can take minutes; don't drop the connection.
        transport http {
            response_header_timeout 600s
            dial_timeout 10s
        }
    }
}
```

Caddy handles TLS automatically via Let's Encrypt. No separate
certbot step required.

---

## 3. Authentication

**The in-app `onboarding_gate` passphrase is a first line of defense,
not a substitute for a real authentication proxy.** Anyone who can
reach your portal URL can attempt to guess the passphrase.

**Recommended:** put the portal behind an auth proxy before exposing it.
Two options:

### Option A — Cloudflare Access (zero-trust, no self-hosted auth)

Cloudflare Access sits in front of your origin and enforces identity
before any request reaches nginx. See
[Cloudflare Access documentation](https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/)
for the current setup steps (Cloudflare's UI changes frequently;
linking their docs is more reliable than embedding screenshots here).

Key points:
- Create a Self-hosted Application in the Zero Trust dashboard.
- Set your application domain to `lab.example.com`.
- Add a policy requiring your own email address (or a list).
- Install the Cloudflare Tunnel (`cloudflared`) on your server to avoid
  opening any inbound port; the tunnel proxies traffic from Cloudflare
  to `localhost:8080`.

### Option B — HTTP Basic Auth at nginx (simpler, weaker)

```nginx
location / {
    auth_basic           "Lab access";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass           http://127.0.0.1:8080;
    # ... (rest of proxy_pass config from §2)
}
```

Generate a password file with `htpasswd -c /etc/nginx/.htpasswd yourname`.
This is easier than Cloudflare Access but weaker — credentials travel
in an HTTP header and must be protected by TLS.

---

## 4. Environment and secrets hardening

```bash
# Verify the passphrase is set and not a placeholder
grep ARAIL_PASSWORD lab/data/secrets.env

# Lock down the secrets file
chmod 0600 lab/data/secrets.env

# Lock down the root .env
chmod 0600 .env

# Confirm the lab is not in airgapped mode if you want cloud providers
grep LAB_MODE .env      # should be "hybrid" if you want cloud SDKs

# Confirm the tier
grep LAB_TIER .env      # "max" for Admin + Security surface
```

**Never commit `.env` or `lab/data/secrets.env` to a public repository.**
Both are in `.gitignore` by default. Check with `git status` before
pushing.

Provider tokens (Claude, OpenRouter, NVIDIA, Hugging Face) are stored
in `lab/data/secrets.env`, `chmod 0600`, and never echoed back by the
API. Do not move them into a world-readable location.

---

## 5. Admin surface: lock it down

The Admin surface (`/admin`) is tier-gated (`LAB_TIER=max` only) and
sits behind the same `onboarding_gate` passphrase. If you are using
Cloudflare Access, the entire origin is protected and `/admin` is
covered automatically.

**Warning:** the Admin surface exposes system health, logs, plugin
management, and the security scan. Do not expose it to untrusted users.
If you share the lab with friends/family, consider running two
instances: one `min` for users, one `max` for yourself.

---

## 6. Performance tuning for a shared instance

ARAIL's inference semaphore (`ARAIL_INFERENCE_CONCURRENCY`) limits
concurrent local-model calls. The default is 1 (one inference at a
time) because most consumer GPUs/CPUs cannot run parallel inference
without thrashing.

```bash
# In .env — increase only if your hardware supports it
ARAIL_INFERENCE_CONCURRENCY=1   # default; safe for any hardware
```

The `Admin → Production Readiness → Performance` card shows real-time
queue depth, in-flight count, and p50/p95 latency per label. Use it
to confirm the semaphore is working before inviting users.

**Reverse proxy timeout:** set `proxy_read_timeout 600s` (nginx) or
the equivalent for your proxy. Local inference can take 3–5 minutes
on consumer hardware. The default nginx timeout (60 s) will kill the
connection mid-response.

---

## 7. Security scan

Run a CVE scan before going public:

1. Upgrade to `max` tier: `./arailctl upgrade max` (installs `pip-audit`).
2. Open `Admin → Production Readiness → Security → Run scan now`.
3. Review findings. Any **Critical** or **High** severity issues should
   be patched before going live.

Enable the auto-scan toggle in the Security card to run a fresh scan
on every restart (hybrid mode only — it calls PyPI to resolve the
vulnerability database).

The SRE agent watches `lab/data/security/last_scan.json` and alerts
you in the activity feed if a scan is stale (>24h) or if new Critical/
High findings appear.

---

## 8. Ongoing operations

| Task | Command |
|---|---|
| Update all components | `./arailctl update` |
| Check component health | `./arailctl doctor` |
| View activity log | `./arailctl logs` |
| Restart portal | `./arailctl restart` |
| Run security scan (CLI) | `pip-audit -f json` |
| Rebuild knowledge base | `./arailctl pkb compile` |
| Prune stale cache files | Admin → Production Readiness → Cleanup |

**Backups:** `lab/data/` holds your secrets, goals, and activity log.
Back it up separately from the repo. `lab/pkb/` holds your knowledge
base. Both are git-ignored by default; use your own backup strategy
(e.g. `rsync`, `rclone`, or a nightly cron).

---

## 9. Sharing the lab with others

ARAIL is designed as a personal lab. Sharing with friends/family is
supported but carries responsibility:

- Every user who can reach the portal can read the activity log, chat
  history, and goals unless you add per-user isolation (not built-in).
- Cloud provider tokens in `lab/data/secrets.env` are available to
  all users of the portal. Treat them as shared credentials.
- The Admin surface gives full system control. Do not share the
  passphrase with anyone you would not give `sudo` to.

For a shared public instance, the recommended model is:

1. **Cloudflare Access** (§3) for identity — each invited user has
   their own Cloudflare identity; you control the policy.
2. **Min tier** for users; max tier for the operator on a separate
   port or separate instance.
3. **No cloud tokens** in the shared instance — use `LAB_MODE=airgapped`
   and local inference only.

If you publish your own fork and want to mention it, please keep the
`ARAIL` credit line in the footer or README. The license is MIT — you
can do almost anything with it, but attribution is appreciated.

---

## 10. Observability endpoints

ARAIL exposes two industry-standard probes that work with any orchestrator or
monitoring stack.

### `GET /health` (alias `GET /healthz`)

**Liveness probe.** Returns 200 with a small JSON body while the process can
dispatch requests:

```json
{
  "status": "ok",
  "service": "arail",
  "version": "0.1.0",
  "uptime_seconds": 3724.1,
  "lab_mode": "airgapped"
}
```

Use this with nginx `upstream` health checks, Kubernetes liveness probes, or
Cloudflare Health Checks. This endpoint checks **only** that the process is
alive — it does not test the LLM backend, storage, or any external service.
For a full readiness check, use `/api/system/health`.

Both endpoints bypass the onboarding gate and require no authentication.

### `GET /metrics`

**Prometheus text-format exposition.** Returns `text/plain; version=0.0.4;
charset=utf-8` with standard `# HELP / # TYPE / name{labels} value` lines.

Metrics emitted:

| Metric | Type | Description |
|---|---|---|
| `arail_build_info{version,python}` | gauge | Static build metadata |
| `arail_uptime_seconds` | gauge | Seconds since process start |
| `arail_lab_mode` | gauge | 1 = hybrid, 0 = airgapped |
| `arail_inference_capacity` | gauge | Semaphore slots |
| `arail_inference_in_flight` | gauge | Active inference requests |
| `arail_inference_pending` | gauge | Waiting for a slot |
| `arail_inference_completed_5m` | gauge | Completions in last 5 min |
| `arail_inference_in_flight_by_label{label}` | gauge | Per-call-site in-flight count |
| `arail_inference_completed_total_by_label{label}` | counter | Per-label monotonic completions |
| `arail_inference_wait_p50_ms{label}` | gauge | P50 queue wait per label |
| `arail_inference_run_p50_ms{label}` | gauge | P50 run duration per label |
| `arail_security_last_scan_age_seconds` | gauge | Age of last pip-audit run; -1 if never |
| `arail_security_findings{severity}` | gauge | Aggregate counts by severity (critical/high/medium/low) |

Security note: `/metrics` emits **aggregate counts only** — no package names,
no version strings, no individual CVE IDs appear in the output (OBS1). The
full finding list is available at `/api/admin/security/status` (authenticated,
operator-only).

### Restricting `/metrics` at the reverse-proxy layer (OBS7)

`/metrics` is unauthenticated by design so that Prometheus can scrape it
without credential management. You **must** restrict it to internal traffic
at the reverse proxy. nginx example:

```nginx
location /metrics {
    # Allow only the Prometheus scraper and localhost.
    allow 127.0.0.1;
    allow ::1;
    # Replace with your Prometheus server IP if remote:
    # allow 10.0.1.42;
    deny all;
    proxy_pass http://127.0.0.1:8080;
}
```

Cloudflare Access alternative: add a Service Auth policy on `/metrics` that
only accepts your Prometheus scraper's service token.

Note on multi-worker deployments: ARAIL runs single-worker uvicorn by default.
If you scale to multiple workers, each worker reports its own uptime (from its
own process start). Prometheus will see one time-series per worker in that
case — this is expected behaviour.

---

*Questions? Open an issue at the upstream repo or check
[docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) first.*
