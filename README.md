# ARAIL — Autoresearch AI Labs
**A rail gun for AI.**

ARAIL is a blueprint, not a product. Clone it, pick a tier, and you have a
local AI research bench with some visibility. RAG'd up chat tab that can connect
to your machine or any cloud vendor, an agent-driven knowledge base, and a
loop that runs experiments while you sleep.

<img width="852" height="639" alt="Screenshot 2026-05-01 at 8 01 48 PM" src="https://github.com/user-attachments/assets/17a0eb3a-2160-4c5f-b980-2289a75424b0" />

<img width="1398" height="783" alt="Screenshot 2026-05-01 at 8 08 10 PM" src="https://github.com/user-attachments/assets/c6eeff47-975f-4ed9-bf0b-13080e8d76a7" />



>
>
> *A learn-by-doing AI research lab for friends, family, and the curious.*
> Default name is **Autoresearch AI Lab**. Rename it to whatever you want in one
> line of `.env` — "Sam's AI Lab", "gentoofoo's ai lab", "PeanutLab". It's
> your lab.


---

## Quick start

```bash
git clone https://github.com/cdarnell/autoresearch-lab.git
cd autoresearch-lab
./arail setup      # pick a tier, install deps, download a starter model
./arail start      # open http://127.0.0.1:8080
```

Three keystrokes: `./arail setup`, `./arail start`, and a browser. (If you
prefer a shorter alias, `./qkz` is symlinked to `./arail`.)

---

## Pick a tier

Two tiers. Pick one; upgrade later.

| Tier  | What you get                                                                                                            | Good for                                         |
| ----- | ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| `min` | Dashboard · Chat · Autoresearch · Knowledge Base · Agents · LanceDB vectors · **AirLLM 70B** (Llama-3.1-70B)           | The everyday lab. Real models on small hardware. |
| `max` | + Admin · Docs · Notebooks · **AirLLM 405B** (Llama-3.1-405B) · Anthropic SDK · LangChain · full cloud SDKs             | Frontier-scale local inference, full bench.      |

Upgrade any time:

```bash
./arail upgrade max
```

Knowledge Base and Agents are part of `min` on purpose — research needs
memory to work. Both tiers ship with the embedded LanceDB-backed KB; `max`
adds the heavier operator surfaces and orchestration extras.

External providers (Claude, NVIDIA NIM, OpenRouter, HuggingFace) are
reachable in both tiers via plain HTTP — `max` just adds the official SDKs
and LangChain/LangGraph for heavier orchestration. **Airgapped mode is the
default: agents cannot collect information from the public internet.**
Local services on this machine and your private network (loopback,
RFC1918, link-local) stay reachable so a LAN GPU box keeps working. Flip
`LAB_MODE=hybrid` in `.env` to allow agent fetches to cloud vendors.

See [docs/INSTALL.md](docs/INSTALL.md) for the long walkthrough.

---

## The main surfaces

### 📊 Dashboard *(every tier)*

The lab's home screen. Shows what the agents are doing, your current goal,
the simulated cloud cost of today's work, and an activity stream so nothing
happens out of view.

### 💬 Chat — with a Compute Source pivot *(every tier)*

The Chat tab is built for crappy machines and beefy ones alike. A
**Compute Source** row at the top lets you choose in one click:

- **My Machine** — runs the model locally (MLX on Apple Silicon, CUDA on
  NVIDIA GPUs, llama.cpp on CPU-only boxes). No key needed.
- **Claude** — Anthropic's API.
- **NVIDIA NIM** — free credits at build.nvidia.com.
- **OpenRouter** — paid catalogue of hosted open-weight models.
- **HuggingFace** — the HF Inference API.
- **Custom endpoint** — any OpenAI-compatible URL (LM Studio, Ollama,
  your own vLLM server).

The **⚙ Manage providers** button opens a modal where you save each key,
**test** it (the lab pings the vendor's `/models` endpoint), **list** the
available models, or **remove** the token. Tokens persist to
`lab/data/secrets.env` with `chmod 0600` and are git-ignored. Tokens are
never echoed back to the UI after saving and never printed to logs.

**Airgapped guard.** By default `LAB_MODE=airgapped`. Agent-originated
outbound calls through `requests` and `urllib` are denied unless the
destination resolves to loopback, RFC1918, or link-local. Denials raise
`EgressBlocked` and append one line to `lab/data/egress.jsonl` for audit.
The Compute Source row shows a banner, cloud radios grey out, and the
save/test/models endpoints refuse. Click the **Airgapped** badge in the
nav to see the operational definition and the most recent blocks.

**Toggling LAB_MODE from the UI.** When the lab is bound to loopback
(the default, `BIND_ADDR=127.0.0.1`), the Network Policy modal shows a
toggle button. Click it, read the confirmation copy, wait 3 seconds for
the confirm button to enable, then click **Confirm**. The portal rewrites
`.env` atomically and updates the running process immediately — no
restart needed. Each toggle appends one line to
`lab/data/airgap_audit.jsonl` (chmod 0600). The toggle is disabled when
the portal is bound to a non-loopback address (`BIND_ADDR=0.0.0.0`, for
example) — in that case the modal shows a static note to edit `.env`
directly, because a UI toggle on a LAN-exposed portal would be a
CSRF attack surface.

### 🔬 Autoresearch *(every tier)*

Tell the lab a measurable goal — *"make our chat responses land under 400 ms
on my MacBook"* — and it runs an experiment loop: propose a change, measure,
compare against the baseline, write up what it learned. You watch from the
dashboard and steer when the direction drifts.

### 📚 Knowledge Base *(every tier)*

The lab's long-term memory. Agents ingest papers, notes, web pages, and
your uploaded PDFs into a LanceDB vector index. Searchable from Chat and
Autoresearch — the answers you get start referring back to your own
materials. Ingest with `./arail pkb ingest <file>`.

### 🤖 Agents *(every tier)*

Three built-in personalities:

- **Pip** — your lab buddy. Observes, nudges, writes warm two-line summaries.
- **SRE** — the crash watcher. Surfaces recurring errors so you don't miss a
  broken loop.
- **Researcher** — the engine behind Autoresearch. Reads goals, writes code,
  runs experiments, commits the winners.

Use the Agent Forge, or add `lab/pkb/agents/<id>/AGENT.md` plus
`lab/pkb/agents/<id>/<id>.py`; the loader discovers them on start.

### 🛠 Admin *(max)*

System health, plugin manager, tier status, diagnostics. It's where the lab
admits what's broken.

### 📖 Docs *(max)*

Curated operator docs rendered inside the lab. Use it for setup notes,
agent architecture, design specs, and the platform-porting manifest without
leaving the local UI.

---

## What "local-first" means

By default `LAB_MODE=airgapped` — agents in the lab cannot collect
information from the public internet. Calls to loopback and your private
network still work, so a LAN GPU box (Ollama, vLLM, an aerollm node)
keeps inferring without changes. Cloud-provider APIs are blocked at the
HTTP layer. The dashboard's **Airgapped** badge is clickable — it shows
what is and isn't enforced, the recent blocks, and the known gaps
(`httpx`, raw sockets, subprocess `curl`) the Python-level guard
doesn't cover. The threat model is well-meaning agent code, not an
adversary on this host — for that, run a host firewall.

Flip to `hybrid` and cloud vendors become fallbacks when the local model
isn't enough. The Chat tab makes this explicit: you see which provider is
active, and you can pivot back with a click.

---

## Make it yours

Edit `.env`:

```bash
LAB_NAME="Sam's AI Lab"
LAB_TAGLINE="Our family AI bench"
```

Restart, and every banner, nav logo, activity line, and wiki landing page
now says "Sam's AI Lab". The Python package stays named `arail` internally
so imports don't break — only the display rebrands.

---

## Where to read next

- [docs/INSTALL.md](docs/INSTALL.md) — tier choice, platform setup, upgrades.
- [docs/PUBLISH.md](docs/PUBLISH.md) — publishing your lab to the public internet (nginx/Caddy, Cloudflare Access, hardening checklist).
- [docs/MACOS.md](docs/MACOS.md) — Apple Silicon specifics (MLX).
- [docs/LINUX.md](docs/LINUX.md) — Linux + CUDA.
- [docs/WSL.md](docs/WSL.md) — Windows via WSL2 with GPU passthrough.
- [docs/PRIVACY.md](docs/PRIVACY.md) — exactly what data leaves the box.
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — first-run gotchas.
- [docs/agents-explained.md](docs/agents-explained.md) — the quick tour of Pip, SRE, Researcher, and custom agents.
- [docs/agents.md](docs/agents.md) — the agent architecture and loader contract.
- [AGENTS.md](AGENTS.md) — the platform-porting manifest for coding agents.
- [BLUEPRINTS.md](BLUEPRINTS.md) — how this repo thinks of itself as a blueprint.
- [CONTRIBUTING.md](CONTRIBUTING.md) — contribute back upstream.
- [SECURITY.md](SECURITY.md) — threat model, how to report issues.

---

## Philosophy

ARAIL exists because AI research shouldn't feel like a closed club. If you
have a computer and curiosity, you can run your own experiments, curate
your own knowledge, and talk to real frontier models — on terms you
understand, with code you can read.

Every tab teaches something. Every loop you run leaves notes behind. That's
the lab.

— start with `./arail setup`.

## License

MIT. See [LICENSE](LICENSE).
