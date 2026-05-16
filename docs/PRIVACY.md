---
title: Privacy Model
category: Operating
order: 5
tags:
  - privacy
  - security
  - airgap
audience: beginner
related:
  - INSTALL
  - api-conventions
---
# Arail Privacy Model

Arail is designed to run **entirely on your machine**. This document is
the honest, specific version of "no telemetry": what the lab never
sends over the network, what it sends only when you opt into hybrid
mode, and what the optional third-party components do on their own.

Read this before donating the blueprint to a school or sharing it with
someone whose privacy posture matters.

## What the lab itself never sends

No component of Arail (portal, researcher, curator, experiment tracker,
goal parser, wiki, PKB) phones home.

- No telemetry pings.
- No crash reports.
- No "anonymous usage stats" toggle hidden in settings.
- No analytics SDKs (Sentry, PostHog, Amplitude, Mixpanel, GA — grep
  the repo; they're not there).
- No update checks against a central server. `./arailctl update` pulls
  from the git remote you configured, nothing else.

The portal binds to `127.0.0.1` by default. If you want it on the LAN
or exposed to the internet, you have to edit `lab.conf` (`BIND_ADDR`)
yourself.

## What airgapped mode enforces

`LAB_MODE=airgapped` (the default) blocks agent-originated calls
through `requests` and `urllib.request` to anything that isn't:

- Loopback: `127.0.0.0/8`, `::1`, `localhost`
- RFC1918: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
- Link-local: `169.254.0.0/16`, `fe80::/10`

The destination's hostname is resolved to an IP via the system
resolver and the IP is checked against those ranges (so a public
domain re-pointed at `127.0.0.1` is treated as local — that's a
known DNS-trust limit). Denials raise `EgressBlocked` (a
`RuntimeError` subclass) and append one structured line to
`lab/data/egress.jsonl`.

### Known gaps — what the Python-level guard does NOT catch

The guard wraps `requests` and `urllib.request`. It does NOT wrap:

- `httpx` — used by the open-notebook integration and the
  knowledge-canvas client, both for `localhost` only in this tree.
- `aiohttp` — not used in tree today.
- Raw sockets (`socket.socket()`) — wrapping these would break
  loopback connection paths underneath the wrapped libraries.
- Subprocess shells — `subprocess.run(["curl", ...])` and
  `os.system("curl ...")` go straight to the OS network stack.

These are documented gaps for the v1 guard. The threat model is
well-meaning agent code that uses standard libraries; it is not
an adversary on the host. For host-level enforcement, run a
firewall (`pf` on macOS, `iptables`/`ufw` on Linux).

### One opt-in network exemption — `BUDDY_EGRESS_PROBE`

Setting `BUDDY_EGRESS_PROBE=1` enables one outbound TCP connect to
`1.1.1.1:443` with a 1-second timeout. No payload, no DNS, no HTTP.
The probe exists so the airgap modal can show the honest disclosure
"your host has internet, but the lab refuses to use it." It is the
only audited exemption to the airgapped rule and is off by default.

## What hybrid mode sends

`LAB_MODE=hybrid` (opt-in) lets agent calls reach the public internet
via the same `requests`/`urllib` clients. The egress audit log still
records every outbound call (`reason: "hybrid"`) so the user can
inspect what was sent. Per-domain consent prompts (curator, browser)
remain in force on top of the guard.

## Toggling LAB_MODE from the UI

When the portal is bound to loopback (`BIND_ADDR=127.0.0.1`, the
default), the **Network Policy** modal (click the Airgapped/Hybrid
badge in the nav bar) includes a toggle button. The protocol is
deliberately two-step: click the button, read the consequence copy,
wait 3 seconds for the confirm button to enable, then click **Confirm**.

On confirm the portal:
1. Rewrites `.env` atomically (temp file + `os.replace`; original is
   untouched if anything fails mid-write).
2. Updates `os.environ["LAB_MODE"]` so the change takes effect
   immediately — no restart needed.
3. Appends one audit line to `lab/data/airgap_audit.jsonl` (chmod 0600,
   never echoed in any response body).

**Bind-address gate.** The toggle is refused with a 403 if `BIND_ADDR`
is not `127.0.0.1`, `::1`, or `localhost`. A portal bound to a LAN
interface could be toggled by any peer on the same network (CSRF). If
you run with `BIND_ADDR=0.0.0.0`, the modal shows a static note: edit
`.env` directly and restart to change the mode.

## Third-party components — what they do independently

Setup installs a handful of optional tools. Each has its own network
posture you should audit for your use case.

### Ollama

Setup may install Ollama (Homebrew on Mac) and pull `qwen3:8b` (~5 GB).
Ollama, as of current releases:

- Pings Ollama's update server at startup to check for new versions.
- Downloads models from `ollama.com` / its mirror when `ollama pull`
  runs.
- Does not send prompts or completions anywhere.

Disable the update ping by setting `OLLAMA_UPDATE_CHECK=false` in
Ollama's environment, or running with the `--noupdate` flag if your
version supports it. Skip Ollama entirely during setup:

```bash
ARAIL_SKIP_OLLAMA=1 ./arailctl setup
```

### agent-browser

Installed via `npm install -g agent-browser`. Runs Playwright under
the hood and executes actions inside a headless Chromium. Network
activity is exactly whatever the pages it visits would do in a normal
browser — plus any telemetry Playwright itself emits on first run
(Chromium download, etc.).

Skip agent-browser if Node/npm isn't on PATH during setup — it's
optional and the lab works without it (you lose the `Knowledge → web
research` capability and nothing else).

### Open Notebook

Docker-compose overlay (`compose/open-notebook.yml`). A self-hosted
NotebookLM alternative — ingests PDFs, audio, video and chats with
them. Everything is local, but:

- The image is pulled from Docker Hub on first run.
- If you configure it to use a cloud model provider, that provider
  sees your queries and source snippets.
- Point it at local Ollama or LM Studio (`MODEL_API_BASE`) to keep
  conversations on-device.

### code-server

VS Code in browser. Binds to `127.0.0.1:8443` behind the unified
passphrase. Respects VS Code's telemetry settings; setup passes
`--disable-telemetry` when launching it.

### jupyter

Classic Jupyter Lab. No telemetry by default; binds to `127.0.0.1`.

## Loopback trust boundary

`127.0.0.1` (the default `BIND_ADDR`) is the lab's security perimeter.
Any process or user that can reach the portal on loopback already has full
host privileges — they could read `lab/data/secrets.env`, inspect the
filesystem, and execute the same shell commands Buddy and the Researcher
agents can. The portal itself has **no authentication layer**: anyone who
reaches `127.0.0.1:8080` is treated as "the user" by every API endpoint,
including the airgap toggle and the opencode subprocess controls.

This is an explicit design choice for a single-user workstation: adding
username/password auth would be friction for the primary use case and
provide only marginal security when the threat is already on the host. If
you need to share the lab, put it behind an auth proxy (nginx + basic auth,
Tailscale, etc.) and ensure `BIND_ADDR` is **not** `0.0.0.0` unless that
proxy is in front.

The CSRF defences on `/api/airgap/toggle` (Origin check, Sec-Fetch-Site
check) exist to prevent a malicious web page from pivoting through the
user's browser to flip the airgap mode — they are browser-level defences,
not a substitute for host isolation.

## A note on schools / shared lab machines

Arail's threat model assumes a single-user workstation. If you're
putting this on a shared computer:

- The passphrase in `.env` and `lab.conf` is readable by anyone with
  a shell on the machine.
- The portal has no user accounts. Anyone who reaches `127.0.0.1:8080`
  is "the user" as far as the agents are concerned.
- Put the machine behind an auth proxy (nginx + basic auth, Tailscale,
  etc.) before exposing it beyond localhost.

For a classroom where each student has their own login, run Arail
under each user account. The `.venv`, `.env`, `lab/`, and
`~/.config/code-server/config.yaml` are all per-user — the blueprint
handles multi-user naturally as long as no two students share a
Unix account.

## opencode Workbench (max-tier only)

opencode is an external binary (MIT, by SST) that runs as a subprocess
of the portal when you start it from the Workbench tab. Its privacy
posture differs from the rest of the lab:

**What the lab controls:**

- opencode is spawned with `--hostname 127.0.0.1` — it binds loopback
  only, not accessible from the network.
- The lab generates `lab/.opencode/opencode.json` (in a git-ignored
  directory, mode 0700) at each start. The file contains model and
  provider configuration; it **never embeds API keys or tokens in
  plaintext**. Cloud API keys reach opencode via subprocess environment
  variables only (the same approach the Chat tab uses).
- `OPENCODE_DISABLE_AUTOUPDATE=true` is set so opencode does not phone
  home to check for updates.
- `OPENCODE_LOG_LEVEL=WARN` limits log verbosity; opencode logs are
  captured in `lab/logs/opencode.log` (git-ignored, max 10 MB).
- The opencode iframe src is `http://127.0.0.1:<port>/` — no credentials
  are embedded in the URL.

**What opencode does on its own:**

opencode is a third-party binary — its network behaviour outside the
lab-controlled configuration is outside our audit scope. By default
the lab sets `OPENCODE_DISABLE_AUTOUPDATE=true` and
`OPENCODE_DISABLE_MODELS_FETCH=true` is available as an env override
if you want to additionally block model-list fetches from opencode's
configured providers.

Read the [opencode source](https://github.com/sst/opencode) and its
docs for its own privacy posture. The binary is open source and
auditable.

## Auditing claims yourself

Everything above is verifiable with `grep` — no need to trust this doc:

```bash
# Find every network call in the Python code
grep -rn "httpx\|requests\.\|urllib\.request\|aiohttp" src/arail/

# Confirm no analytics SDKs
grep -rn "sentry\|posthog\|amplitude\|mixpanel\|google-analytics" .

# See what a given backend actually hits
grep -rn "MODEL_API_BASE\|api_base" src/arail/router/
```

If an audit turns up something that doesn't match this doc, that's a
privacy bug — file an issue.
