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
- No update checks against a central server. `./arail update` pulls
  from the git remote you configured, nothing else.

The portal binds to `127.0.0.1` by default. If you want it on the LAN
or exposed to the internet, you have to edit `lab.conf` (`BIND_ADDR`)
yourself.

## What hybrid mode sends

`ARAIL_MODE=hybrid` (opt-in, airgapped by default) permits the
researcher and browser agents to make outbound calls — but only to
domains you explicitly approve via the consent store. Every new domain
triggers an approval prompt in the dashboard, and the approval is
persisted so you're not asked twice.

Which domains get asked for depends on which backends and features you
use:

- **Model provider APIs** when you set `MODEL_BACKEND` to `openai_compat`,
  `huggingface`, `openrouter`, `claude`: calls go to the host you
  configured (`MODEL_API_BASE`). These are standard API calls with the
  key you supplied.
- **Web research agent** (`agent-browser`): only when you type a goal
  that asks the lab to browse, and only to domains you approve.
- **Hugging Face model downloads**: when setup pulls the starter model
  or when you manually request one.

Everything else stays local.

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
ARAIL_SKIP_OLLAMA=1 ./arail setup
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
