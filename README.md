# OGLab — AI Lab Blueprint

A shareable blueprint for building your own AI research lab.
Local-first. Airgapped by default. Your models, your data, your hardware.

**Not a product. A blueprint you fork, customize, and own.**

---

## Why OGLab

You tell it what you care about. It builds a lab around that.

Small agents — a researcher, a curator, an experiment tracker — start
working toward your goal the moment the lab comes online. They explore,
they test hypotheses, they write findings. You sleep; they don't.

Everything runs on your machine. No accounts. No API keys required.
No telemetry. No one watching.

---

## Key Features

### Airgapped by Default

Zero network calls out of the box. Your models run locally. Your data
stays local. The lab doesn't phone home, ping analytics, or reach for
the cloud unless you explicitly open the door.

Hybrid mode exists — HuggingFace free tier, OpenRouter, Claude — but
you opt in. The default is silence on the wire.

### Host Out-of-Reach LLMs on Disk

Most people can't run a 70-billion-parameter model. Not enough RAM.
OGLab ships **AirLLM** — it loads models layer by layer from your SSD,
one slice at a time. A 70B model that would need 40 GB of RAM runs in
4 GB. Slow, yes. But it runs. And it's *yours*.

The bootstrap scans your hardware — CPU, RAM, disk size, disk type —
and auto-configures everything. Got an NVMe drive with 80 GB free?
You qualify for deep research. The build manifest tells you exactly
what you're getting:

```
  ┌─── BUILD MANIFEST ──────────────────────────────────────────────┐
  │                                                                 │
  │  Tier:          ▶ deep                                          │
  │  Platform:      macos arm64 (mlx)                               │
  │  Disk:          400 GB free (NVMe SSD ✓)                        │
  │                                                                 │
  │  ┌─ ENGINES ─────────────────────────────────────────────┐      │
  │  │  ⚡ SLM (always on)   Phi-3.5-mini-instruct    ~2 GB  │      │
  │  │  🔬 Deep research     Qwen3-8B               ~16 GB │      │
  │  │     via AirLLM · 4-bit · layer-by-layer from disk     │      │
  │  └───────────────────────────────────────────────────────┘      │
  │                                                                 │
  │  Resources:     8 CPUs · 24 GB RAM · all services               │
  │  Cost tracking: cloud-equivalent savings + $0.13/kWh energy     │
  │  Research:      deep async (Qwen3-8B AirLLM) + fast interactive │
  │                                                                 │
  └─────────────────────────────────────────────────────────────────┘
```

No menus. No tier selection. Discovery determines 100% of what you get.

### Simulate Your Spend

Every inference the lab runs gets priced two ways:

- **Cloud equivalent** — what that same call would cost on a commercial
  API (GPT-4-class pricing, Claude pricing, per-million-token rates).
- **Actual energy** — real watts × real time × your electricity rate
  (default $0.13/kWh, national average).

The dashboard shows a running total. Over weeks of research, you watch
the gap widen — hundreds of dollars in cloud-equivalent work, pennies
in electricity. That's the point.

### Organically Growing Toward Your Goal

State a goal at bootstrap — or change it any time from the dashboard.
The lab doesn't just store it. It *works on it*.

A **researcher agent** plans experiments, runs them, analyzes results,
and writes reports. A **curator agent** finds and vets sources. An
**experiment tracker** logs every hypothesis, observation, and outcome.

You come back the next morning and there's a research report waiting.
The progress bar moved. New experiments ran. New findings landed.

The lab is alive. It grows toward what you asked for.

### Structured Knowledge Base

Everything the lab discovers lives in `lab/pkm/` — your personal
knowledge management folder. Drop raw material in `inbox/`, run
`./oglab pkm ingest`, and it gets sorted into `sources/`. The AI
agents write research findings, experiment logs, and recommendations
to `agents/`. Your notes go in `notes/`. Run `./oglab pkm compile` to
build a searchable index across everything.

The dashboard has a **Knowledge** page — browse by section, search
full-text across all files, view any document. The AI builds knowledge
in its area; you build knowledge in yours. The compile step merges
them together into polished reports.

---

## Quick Start

```bash
git clone https://github.com/cdarnell/minimalist-blueprint.git oglab
cd oglab
./oglab setup && ./oglab start
```

One entry point. `./oglab setup` detects your hardware, installs
dependencies, downloads your model, and scaffolds `lab/`. `./oglab
start` brings up all four services. Run `./oglab help` for the rest.

Four services come online:

| Service | URL | What |
|---------|-----|------|
| **Dashboard** | http://127.0.0.1:8080 | Goal tracking, cost savings, experiments, agents |
| **Terminal** | http://127.0.0.1:7681 | Shell in browser (ttyd) |
| **Notebook** | http://127.0.0.1:8888 | Jupyter Lab |
| **IDE** | http://127.0.0.1:8443 | VS Code in browser (code-server) |

## Two Modes

- **Airgapped** (default) — zero network calls. Local model, local data.
- **Hybrid** — local-first with optional cloud fallback (HuggingFace free tier, OpenRouter, Claude).

---

## Three Tiers of Inference

The lab always keeps a small, fast model in RAM (Phi-3.5-mini, ~2 GB).
That handles interactive work — goal parsing, quick questions, observations.

Anything heavier goes elsewhere:

| Tier | What fires | When |
|------|-----------|------|
| **SLM** (always on) | Phi-3.5-mini in RAM | Instant — every fast task |
| **AirLLM** (deep) | 70B model from disk, layer by layer | Research planning, analysis, reports |
| **Cloud** (opt-in) | HuggingFace / OpenRouter / Claude | When you choose to open the door |

The researcher agent uses both: fast SLM for observations and quick
reasoning, deep AirLLM for the heavy thinking. You don't configure
this — the dual router handles it.

---

# Section 1 — Mac (Apple Silicon)

> Native Metal acceleration via MLX. No VM, no Docker, no fuss.

### What you get

| Component | How it works on Mac |
|-----------|-------------------|
| **GPU** | Apple Metal via MLX — native, no drivers to install |
| **Model router** | `MODEL_BACKEND=mlx` (auto-detected) |
| **Packages** | Homebrew + pip in a venv |
| **OS** | Your existing macOS — nothing to replace |

### Quick start

```bash
git clone https://github.com/cdarnell/minimalist-blueprint.git oglab
cd oglab
./oglab setup
```

The setup detects your Mac automatically:

```
━━━ 1/10  Detecting hardware
  Platform:    macos (arm64)
  CPUs:        10
  Memory:      32 GB
  Disk free:   400 GB
  Accelerator: mlx
```

It computes your build profile, shows the manifest, and asks one question — your research goal:

```
━━━ 2/10  Computing build profile
━━━ 3/10  Build manifest

  ┌─── BUILD MANIFEST ────────────────────────────────────────────┐
  │  Tier:          ▶ deep                                        │
  │  Platform:      macos arm64 (mlx)                             │
  │  Engines:       ⚡ Phi-3.5-mini + 🔬 Llama-3.1-70B (AirLLM)  │
  │  Cost tracking: cloud-equivalent + $0.13/kWh                  │
  └───────────────────────────────────────────────────────────────┘

  ? Build this lab? [Y]:

━━━ 4/10  System packages        ← brew install python git curl tmux cmake
━━━ 5/10  Python environment     ← venv + mlx + mlx-lm + airllm
━━━ 6/10  Lab services           ← portal, jupyter, ttyd, code-server
━━━ 7/10  AI models              ← SLM (Phi-3.5-mini) + deep (70B)
━━━ 8/10  Configuration          ← .env + lab.conf

  ? What do you want to research?

━━━ 9/10  Finalizing              ← ./oglab start

✓ Bootstrap complete!
```

Then:

```bash
./oglab start
```

### Mac inference options

MLX is the default and best choice for Apple Silicon.  Alternatives:

| Option | `.env` setting | Notes |
|--------|---------------|-------|
| **MLX** (default) | `MODEL_BACKEND=mlx` | Native Metal, fastest on Mac |
| **LM Studio** | `MODEL_BACKEND=openai_compat`<br>`MODEL_API_BASE=http://localhost:1234/v1` | GUI app, download models with one click |
| **Ollama** | `MODEL_BACKEND=openai_compat`<br>`MODEL_API_BASE=http://localhost:11434/v1` | CLI-first, `ollama run mistral` |
| **CPU fallback** | `MODEL_BACKEND=cpu` | llama.cpp, slower but works on Intel Macs too |

### Mac notes

- No Gentoo needed on Mac — MLX runs natively on macOS.
- GPU passthrough to a VM doesn't work on Apple Silicon. Don't try.
- If you want Gentoo for the experience, run it in UTM (QEMU) for
  dev/orchestration — but GPU work stays on the macOS host via MLX.

---

# Section 2 — Windows (WSL2 + Gentoo)

> Nvidia GPU passthrough into a Gentoo Linux environment via WSL2.

### What you get

| Component | How it works on Windows |
|-----------|------------------------|
| **GPU** | Nvidia CUDA via WSL2 `/dev/dxg` bridge — Windows driver, Linux userspace |
| **Model router** | `MODEL_BACKEND=cuda` (auto-detected) |
| **Packages** | Gentoo Portage (`emerge`) — compile from source |
| **OS** | Gentoo Linux running inside WSL2 |

### Prerequisites

1. **Windows 10 (21H2+) or Windows 11**
2. **WSL2 enabled** — `wsl --install` from PowerShell (admin)
3. **Nvidia GPU driver** installed on Windows (≥ 525.x) — this is the
   *Windows* driver, not a Linux driver. WSL2 projects it into Linux
   automatically.

### Install Gentoo in WSL2

```powershell
# PowerShell (admin)
# Download a Gentoo stage3 tarball and import it:
wsl --import Gentoo C:\Gentoo C:\Downloads\stage3-amd64-*.tar.xz
wsl -d Gentoo
```

Or use an existing Gentoo WSL image from the community.

### Default user

Once inside Gentoo WSL:

| | |
|---|---|
| **User** | `gentoofoo` |
| **Password** | `gentoofoo` |
| **Sudo** | Full access (passwordless) |
| **Home** | `/home/gentoofoo` |

> **Change your password on first login:**
> ```bash
> passwd
> ```

### Quick start (inside WSL2 Gentoo)

```bash
git clone https://github.com/cdarnell/minimalist-blueprint.git oglab
cd oglab
./bootstrap.sh
```

The bootstrap detects WSL + Nvidia automatically:

```
━━━ 1/10  Detecting hardware
  Platform:    wsl (x86_64)
  CPUs:        16
  Memory:      64 GB
  Disk free:   200 GB
  Accelerator: cuda
  GPU:         NVIDIA RTX 4090 (24564 MB VRAM)

━━━ 2/10  Computing build profile
━━━ 3/10  Build manifest         ← tier, engines, resources
━━━ 4/10  System packages        ← emerge -av python gcc cmake ...
━━━ 5/10  Python environment     ← venv + vllm + torch (CUDA)
━━━ 6/10  Lab services           ← portal, jupyter, ttyd, code-server
━━━ 7/10  AI models              ← SLM + tier-appropriate model
━━━ 8/10  Configuration          ← .env + lab.conf
         ? What do you want to research?
━━━ 9/10  Finalizing              ← ./oglab start

✓ Bootstrap complete!
```

Then:

```bash
./oglab start
```

Services are accessible from your Windows browser at the same URLs.

### Gentoo package management

Gentoo uses `emerge` (Portage) instead of `apt`.  It compiles from source:

```bash
# Search
emerge --search numpy

# Install
sudo emerge -av dev-python/numpy

# Update everything
sudo emerge --update --deep --newuse @world

# Remove
sudo emerge --depclean dev-python/numpy
```

USE flags let you compile with exactly the features you need:

```bash
# Enable CUDA + Python bindings for OpenCV
echo "dev-libs/opencv cuda python" | sudo tee -a /etc/portage/package.use/oglab
sudo emerge -av dev-libs/opencv
```

Common lab packages:

```bash
sudo emerge -av dev-python/numpy dev-python/scipy dev-python/pandas
sudo emerge -av dev-util/nvidia-cuda-toolkit    # CUDA
sudo emerge -av app-misc/tmux net-misc/curl app-editors/vim
```

### Windows inference options

| Option | `.env` setting | Notes |
|--------|---------------|-------|
| **CUDA / vLLM** (default) | `MODEL_BACKEND=cuda` | Direct GPU, fastest |
| **LM Studio** (on Windows host) | `MODEL_BACKEND=openai_compat`<br>`MODEL_API_BASE=http://host.docker.internal:1234/v1` | Run LM Studio on Windows, call from WSL |
| **Ollama** (in WSL) | `MODEL_BACKEND=openai_compat`<br>`MODEL_API_BASE=http://localhost:11434/v1` | Runs inside WSL with CUDA |
| **CPU fallback** | `MODEL_BACKEND=cpu` | llama.cpp, no GPU needed |

### Windows notes

- The Nvidia driver is installed on **Windows only**. WSL2 bridges it
  via `/dev/dxg`. Do NOT install nvidia-drivers inside Gentoo WSL.
- AMD ROCm on WSL2 is experimental. Stick with Nvidia for now.
- WSL2 uses Microsoft's kernel, not a Gentoo kernel. That's fine — the
  GPU bridge requires it.
- You're running a real Gentoo userspace. `emerge`, USE flags, and
  everything else works normally.

---

# Shared — Both Platforms

Everything below applies identically on Mac and Windows.  Your code
never sees the platform difference — the model router abstracts it.

```
Mac host  ──→  MLX (native Metal)
WSL2      ──→  CUDA via Windows GPU bridge
Either    ──→  AirLLM (70B from disk, layer-by-layer)
Either    ──→  LM Studio / Ollama / DeployLM (OpenAI-compat API)
Either    ──→  External API (free tier, bring your own token)
Either    ──→  CPU fallback (llama.cpp)
```

One codebase, zero `if platform ==` branches.

Edit `lab.conf` to change ports or resource limits.
Edit `.env` to change model backend or API keys.

---

## Project Structure

```
oglab/
├── oglab                     # ← unified CLI: setup | start | stop | reset | pkm | doctor
├── src/oglab/                # Python package
│   ├── router/               # Model router (MLX / CUDA / CPU / AirLLM / cloud)
│   ├── skills/               # goal_parser, experiment_tracker
│   ├── agents/               # consent, curator, researcher
│   ├── plugins/              # Plugin manager (GitHub → install)
│   ├── portal/               # FastAPI dashboard (app.py + templates/ + static/)
│   ├── pkm.py                # Knowledge base engine
│   ├── costs.py              # CostTracker
│   ├── activity.py           # Event bus (SSE streaming)
│   ├── goals.py              # Goal persistence
│   └── config.py             # Central runtime paths + env loader
│
├── lab/                      # runtime state (gitignored, created by setup)
│   ├── data/                 # activity.jsonl, goals/, consent/, experiments/
│   ├── models/               # downloaded model weights
│   └── pkm/                  # knowledge base — inbox, sources, agents, notes, compiled
│
├── scripts/                  # delegates for ./oglab
│   ├── setup.sh              # provision venv + deps + model + lab/
│   ├── start.sh              # launch portal + terminal + notebook + IDE
│   ├── reset.sh              # wipe models/data/env/plugins
│   ├── pkm-{ingest,compile,browse}
│   └── gentoo-bootstrap.sh
│
├── docs/                     # MACOS.md, WSL.md, GENTOO.md, vibe-integrate.md
├── examples/peanut_farmer/   # Complete working example
│
├── pyproject.toml            # Single source of truth for deps (src layout)
├── .env.example              # Configuration template
└── README.md
```

## How the Router Works

One interface. Any backend. Switch by changing `.env`.

```python
from oglab.router import ModelRouter

router = ModelRouter()                    # reads MODEL_BACKEND from .env
response = router.complete("Explain crop rotation in one paragraph.")
print(response.text)
```

| Backend | Env value | Needs | Cost |
|---------|-----------|-------|------|
| MLX (Mac) | `mlx` | Apple Silicon | Free |
| CUDA (Nvidia) | `cuda` | Nvidia GPU + vLLM | Free |
| CPU (llama.cpp) | `cpu` | Any machine | Free |
| **LM Studio / Ollama / DeployLM** | `openai_compat` | Local server running | Free |
| HuggingFace | `huggingface` | API key | Free tier |
| OpenRouter | `openrouter` | API key | Free tier |
| Claude | `claude` | API key | Paid |

## Adding Your Own Domain

```python
from oglab.skills.goal_parser import GoalParser
from oglab.skills.experiment_tracker import ExperimentTracker

# Parse your goal (works offline with parse_offline)
parser = GoalParser()
goal = parser.parse_offline("I want to master French pastry")

# Track experiments
tracker = ExperimentTracker()
exp = tracker.create(
    hypothesis="Laminated dough needs exactly 27 folds",
    methodology="Bake 3 batches with different fold counts",
    variables={"treatment": "fold_count", "control": "27_folds"},
    metrics=["flakiness", "rise_height", "taste_score"],
)
tracker.start(exp["id"])
tracker.observe(exp["id"], "24 folds produced good layers but less rise")
tracker.complete(
    exp["id"],
    results={"best_folds": 27, "rise_improvement": "15%"},
    conclusion="27 folds confirmed optimal",
    success=True,
)
```

## Sharing

Share this repo link:
```
https://github.com/cdarnell/minimalist-blueprint
```

Tell people:
> Fork it. Run `./oglab setup`. Set your goal. The lab handles the rest.

For non-technical family: the example runs a complete demo with zero
configuration beyond `./oglab setup`.

## License

MIT — use it, change it, share it.
