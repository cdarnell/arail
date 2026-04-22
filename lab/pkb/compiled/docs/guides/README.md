---
title: Readme
section: docs
tags: [guide]
aliases: [README]
source: README.md
generated: 2026-04-22T01:03:30Z
---
# OGLab

An AI lab that runs on your own machine.

You set a goal. Agents start working on it. They research, summarize, test, and write findings while you sleep. Nothing phones home unless you tell it to.

OGLab is a blueprint. Fork it. Keep what works. Replace what doesn't. There is no one right way to run a lab. See [BLUEPRINTS.md](BLUEPRINTS.md) for how blueprints work.

---

## 3-step Quickstart

```bash
# 1) Clone
git clone https://github.com/cdarnell/minimalist-blueprint.git oglab
cd oglab

# 2) Setup: detects hardware, installs deps, generates a passphrase,
#    captures your first research goal
./oglab setup

# 3) Start: portal, terminal, notebook, and IDE come online together
./oglab start
```

That's it. The dashboard opens at <http://127.0.0.1:8080>. Type your
goal, click **Run Research**, and the agents begin working on it
locally, privately, on your hardware.

**Works on:** macOS (Apple Silicon), Windows 10/11 (WSL2 + Ubuntu),
any Linux with Python ≥ 3.10. Per-platform prereqs below.

**First-time friendly.** Setup walks through 10 numbered checkpoints
(hardware, Python, passphrase, models, goal) and prints the
passphrase and next three steps when it's done. Nothing hidden in a file.

**Sharing this with friends, family, or a classroom?** See
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for the top five
first-run gotchas and [docs/PRIVACY.md](docs/PRIVACY.md) for what the
lab does and does not send over the network.

---

## Why OGLab

You tell it what you care about. It builds a lab around that.

A handful of simple Python agents come along for the ride: a researcher, a curator, an experiment tracker. They start working the moment the lab comes online. They explore. They test ideas. They write findings. You sleep, they don't.

Everything runs on your machine. No accounts, no API keys required, no telemetry leaving the box. As private as you need it to be.

---

## Key Features

### Airgapped by Default

The best security is digging a hole and taking your language model with you while cutting the internet cord.
Zero network calls out of the box. Your models run locally. Your data
stays local. The lab doesn't phone home, ping analytics, or reach for
the cloud unless you explicitly open the door.

### Hybrid mode does exist

Start with free tier options before you buy, try HuggingFace, OpenRouter, Nvidia.
Remember, you opt in. The default is silence on the wire.

### Host Out-of-Reach LLMs on Disk

OGLab ships **AeroLLM**, a Rust runtime with MLX and CUDA backends and
multi-threaded prefetched layer streaming off your SSD. A 70B model
that would need 40 GB of RAM runs in ~4 GB of RAM and 40 GB of disk.
Slow per-prompt, yes, but concurrent prompts share each layer pass,
so research and CoT batch workloads scale near-linearly in N.

The bootstrap scans your hardware for CPU, RAM, disk size, disk type
and attempts to auto-configure the basics. Got an NVMe drive with 80 GB free?
You qualify for deep research. The build manifest tells you exactly
what you qualify for.

```text
  ┌─── BUILD MANIFEST ──────────────────────────────────────────────┐
  │                                                                 │
  │  Tier:          ▶ deep                                          │
  │  Platform:      macos arm64 (mlx)                               │
  │  Disk:          400 GB free (NVMe SSD ✓)                        │
  │                                                                 │
  │  ┌─ ENGINES ─────────────────────────────────────────────┐      │
  │  │  ⚡ SLM (always on)   Phi-3.5-mini-instruct    ~2 GB  │      │
  │  │  🔬 Deep research     Qwen3-8B               ~16 GB │      │
  │  │     via AeroLLM · 4-bit · prefetched layer streaming  │      │
  │  └───────────────────────────────────────────────────────┘      │
  │                                                                 │
  │  Resources:     8 CPUs · 24 GB RAM · all services               │
  │  Cost tracking: cloud-equivalent savings + $0.13/kWh energy     │
  │  Research:      deep async (Qwen3-8B AeroLLM) + fast interactive│
  │                                                                 │
  └─────────────────────────────────────────────────────────────────┘
```

No menus. No tier selection. Discovery can determine 100% of what you get.

### Simulate Your Spend

Every inference the lab runs gets priced two ways:

- **Cloud equivalent**: what that same call would cost on a commercial
  API (GPT-4-class pricing, Claude pricing, per-million-token rates).
- **Actual energy**: real watts × real time × your electricity rate
  (default $0.13/kWh, national average).

The dashboard shows a running total. Over weeks of research, you watch
the gap widen. Hundreds of dollars in cloud-equivalent work, pennies
in electricity. That's the point.

### Organically Growing Toward Your Goal

State a goal at bootstrap, or change it any time from the dashboard.
The lab doesn't just store it. It *works on it*.

A **researcher agent** plans experiments, runs them, analyzes results,
and writes reports. A **curator agent** finds and vets sources. An
**experiment tracker** logs every hypothesis, observation, and outcome.

You come back the next morning and there's a research report waiting.
The progress bar moved. New experiments ran. New findings landed.

The lab is alive. It grows toward what you asked for.

### Structured (PKB) Knowledge Base

Everything the lab discovers lives in `lab/pkb/`, your personal
knowledge base folder. Drop raw material in `inbox/`, run
`./oglab pkb ingest`, and it gets sorted into `sources/`. The
agents write research findings, experiment logs, and recommendations
to `agents/`. Your notes go in `notes/`. Run `./oglab pkb compile` to
build a searchable index across everything.

The dashboard has a **Knowledge** page: browse by section, search
full-text across all files, view any document. The agents build knowledge
in their area; you build knowledge in yours. The compile step merges
them together into polished reports.

#### Documentation as code: the wiki layer

On top of the PKB tree, OGLab runs a **self-curating wiki** at
<http://127.0.0.1:8080/wiki>. It renders every markdown file with
`[[wikilinks]]`, backlinks, tags, and frontmatter; ships a
force-directed knowledge graph at `/wiki/graph`; and **auto-generates
wiki pages from the repo's own source**: every Python module via
`ast` (no runtime imports), every shell script's header comment,
every compose overlay, every hand-written guide, and the
`.env.example` reference. Write a better docstring, rebuild, get
better docs. Auto-generated pages live under
`lab/pkb/compiled/docs/` so they never touch your notes, and the
markdown is fully Obsidian-compatible. See [docs/wiki.md](docs/wiki.md)
for the full user guide.

---

## What you get after `./oglab start`

Four services come online on localhost. Everything binds to `127.0.0.1`
by default. Nothing is reachable from the network unless you change that
in `lab.conf`.

| Service | URL | What |
| --------- | ----- | ------ |
| **Dashboard** | <http://127.0.0.1:8080> | Goal tracking, cost savings, experiments, agents |
| **Terminal** | <http://127.0.0.1:7681> | Shell in browser (ttyd) |
| **Notebook** | <http://127.0.0.1:8888> | Jupyter Lab (classic option, swap for Marimo below) |
| **IDE** | <http://127.0.0.1:8443> | VS Code in browser (code-server). Passphrase from setup unlocks it |

Run `./oglab help` any time to see every subcommand (`setup`, `start`,
`stop`, `restart`, `doctor`, `logs`, `reset`, `pkb`, `wiki`).

### Curate insight: optional add-ons

Two docker-compose overlays let you curate what the lab (or your agents) pulls in, without coupling to the host-native services above. Both bind to `127.0.0.1` by default.

| Add-on | URL | What |
| --------- | ----- | ------ |
| **Marimo** | <http://127.0.0.1:2718> | Reactive Python notebooks. Notebooks are plain `.py` files in [lab/notebooks/](lab/notebooks/). |
| **Open Notebook** | <http://127.0.0.1:8502> | Self-hosted NotebookLM alternative. Ingest PDFs/video/audio, chat with sources, generate podcasts. REST API on `:5055`. |

```bash
# Marimo: the "experiment" surface
docker compose -f compose/marimo.yml up -d

# Open Notebook: the "curate" surface (needs OPEN_NOTEBOOK_ENCRYPTION_KEY in .env)
docker compose -f compose/open-notebook.yml up -d
```

Both reach host-side LM Studio / Ollama at `host.docker.internal`, so they inherit your existing local model stack with no double-inference cost. Prefer classic Jupyter? It's still wired into `./oglab start` on `:8888`. Use whichever surface fits the task.

## Two Modes

- **Airgapped** (default): zero network calls. Local model, local data.
- **Hybrid**: local-first with optional cloud fallback. Start on free tiers (**NVIDIA NIM** at `build.nvidia.com` for free credits on Llama 3.3 / Nemotron / DeepSeek-R1, **HuggingFace Inference**, **OpenRouter**) and graduate to paid tiers (Claude, OpenAI, Groq) once you know what your spend actually looks like.

---

## Platform Support

OGLab is **platform-neutral by design**. The model router ([src/oglab/router/backends.py](src/oglab/router/backends.py)) has one class per accelerator (MLX / CUDA / CPU / AeroLLM / OpenAI-compat / HuggingFace / OpenRouter / Claude), auto-detected from hardware, swappable via a single `.env` line. The Python code and the portal never ask what OS they're on.

The only thing that actually differs per platform is the package manager in [`./oglab setup`](scripts/setup.sh), and that's where the recommendations below matter.

| Platform | Recommended path | Why |
| --- | --- | --- |
| **macOS (Apple Silicon)** | Native + MLX | **Blessed path.** Unified memory means a base-model M-series with 32 GB can run a 70B model via AeroLLM's MLX-backed prefetched layer streaming that would otherwise need a ~48 GB discrete GPU. MLX is Apple's first-party Metal framework. No drivers, no VM, no CUDA toolkit. |
| **Windows (any GPU)** | WSL2 Ubuntu + CUDA | Nvidia ships full CUDA-in-WSL2 support (`/dev/dxg` bridge, Windows driver ≥ 525.x). `wsl --install` gets you Ubuntu in one command. This gets you real Linux userspace on Windows hardware without dual-booting. |
| **Linux (native)** | Your distro, your rules | The blueprint runs on any Linux with Python 3.10+ and a supported backend. Our [`setup.sh`](scripts/setup.sh) knows Homebrew, apt, and emerge. If you're on Arch/Fedora/NixOS/whatever, the fastest path is to **"vibe integrate"**: point an agent at [docs/LINUX.md](docs/LINUX.md) and `setup.sh` and let it port the 20 lines of package-manager calls. See [docs/LINUX.md](docs/LINUX.md) for the recipe. |

**Intel Mac / no GPU / curious?** CPU fallback via llama.cpp works everywhere. Set `MODEL_BACKEND=cpu` and expect slower tokens/sec but full functionality.

---

## Work Windows: don't burn the GPU while you're using the lab

OGLab's scheduler splits the day into **active** and **heavy** windows so the lab stays responsive while you're engaged and hammers the hardware while you're away. The researcher agent checks the current window on every tick and picks its weight accordingly.

| Window | Default | What fires | Why |
| --- | --- | --- | --- |
| **☀ Active** | `08:00-22:00` | SLM only. Observations, planning, note synthesis, PKB compile | Lab stays responsive for interactive use |
| **🌙 Heavy** | `22:00-08:00` | AeroLLM experiments, deep synthesis, full report generation | GPU hammering while you sleep |
| **◦ Idle** | any gap | Queued work drains | Catch-up |

On boot, the researcher applies a **5-minute courtesy delay** before its first tick so the UI loads clean. Override with `LAB_STARTUP_DELAY_SEC=0` for instant start, or click "Run now" in the dashboard.

**Soft kill switch.** The dashboard has a **Halt jobs** button (or `POST /api/jobs/halt`) that cancels every running agent task *without* taking the portal down. Resume with one click. Use this when you want to reclaim the GPU for interactive work without restarting the lab.

Configure in `.env`:

```bash
LAB_ACTIVE_HOURS=08:00-22:00   # light work window
LAB_HEAVY_HOURS=22:00-08:00    # heavy GPU burn window (24h local)
LAB_STARTUP_DELAY_SEC=300      # courtesy delay before first tick (seconds)
```

Or answer the two questions at the end of `./oglab setup` and they'll be written for you.

---

## Three Tiers of Inference

The lab always keeps a small, fast model in RAM (Phi-3.5-mini, ~2 GB).
That handles interactive work: goal parsing, quick questions, observations.

Anything heavier goes elsewhere:

| Tier | What fires | When |
| ------ | ----------- | ------ |
| **SLM** (always on) | Phi-3.5-mini in RAM | Instant. Every fast task |
| **AeroLLM** (deep) | 70B+ model from disk via prefetched layer streaming | Research planning, analysis, reports |
| **Cloud** (opt-in) | HuggingFace / OpenRouter / Claude | When you choose to open the door |

The researcher agent uses both: fast SLM for observations and quick
reasoning, deep AeroLLM for the heavy thinking. You don't configure
this. The dual router handles it.

---

## macOS: Apple Silicon

> Native Metal acceleration via MLX. No VM, no Docker, no fuss.

### What you get on Mac

| Component | How it works on Mac |
| ----------- | ------------------- |
| **GPU** | Apple Metal via MLX. Native, no drivers to install |
| **Model router** | `MODEL_BACKEND=mlx` (auto-detected) |
| **Packages** | Homebrew + pip in a venv |
| **OS** | Your existing macOS. Nothing to replace |

### Quick start on Mac

```bash
git clone https://github.com/cdarnell/minimalist-blueprint.git oglab
cd oglab
./oglab setup
```

The setup detects your Mac automatically:

```text
━━━ 1/10  Detecting hardware
  Platform:    macos (arm64)
  CPUs:        10
  Memory:      32 GB
  Disk free:   400 GB
  Accelerator: mlx
```

It computes your build profile, shows the manifest, and asks one question: your research goal.

```text
━━━ 2/10  Computing build profile
━━━ 3/10  Build manifest

  ┌─── BUILD MANIFEST ────────────────────────────────────────────┐
  │  Tier:          ▶ deep                                        │
  │  Platform:      macos arm64 (mlx)                             │
  │  Engines:       ⚡ Phi-3.5-mini + 🔬 Llama-3.1-70B (AeroLLM) │
  │  Cost tracking: cloud-equivalent + $0.13/kWh                  │
  └───────────────────────────────────────────────────────────────┘

  ? Build this lab? [Y]:

━━━ 4/10  System packages        ← brew install python git curl tmux cmake
━━━ 5/10  Python environment     ← venv + mlx + mlx-lm + aerollm
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

MLX is the default and top choice for Apple Silicon.

On Apple Silicon, `./oglab setup` now favors native MLX / `mlx-lm` and
does not auto-install Ollama unless you explicitly opt in with
`OGLAB_ENABLE_OLLAMA=1`.

| Option | `.env` setting | Notes |
| -------- | --------------- | ------- |
| **MLX** (default) | `MODEL_BACKEND=mlx` | Native Metal, fastest on Mac |
| **LM Studio** | `MODEL_BACKEND=openai_compat`<br>`MODEL_API_BASE=http://localhost:1234/v1` | GUI app, download models with one click |
| **Ollama** (optional) | `MODEL_BACKEND=openai_compat`<br>`MODEL_API_BASE=http://localhost:11434/v1` | CLI-first, useful when you specifically want a local OpenAI-compatible API |
| **CPU fallback** | `MODEL_BACKEND=cpu` | llama.cpp, slower but works on Intel Macs too |

### Mac notes

- No Gentoo Linux needed on Mac. MLX runs natively on macOS.
- GPU passthrough to a VM doesn't work on Apple Silicon. Don't try.
- If you must run Linux, run it in UTM (QEMU) for
  dev/orchestration. GPU work stays on the macOS host via MLX.

---

## Windows: WSL2 + Ubuntu + CUDA

> Real Linux userspace on your Windows machine, with full Nvidia GPU
> passthrough. No dual-boot, no VM GPU drama.

### What you get on Windows

| Component | How it works on Windows |
| --- | --- |
| **GPU** | Nvidia CUDA via WSL2 `/dev/dxg` bridge. Windows driver, Linux userspace |
| **Model router** | `MODEL_BACKEND=cuda` (auto-detected) |
| **Packages** | `apt` (Ubuntu default). Fast, predictable |
| **OS** | Ubuntu 22.04 LTS or 24.04 LTS running inside WSL2 |

### Prerequisites

1. **Windows 10 (21H2+) or Windows 11**
2. **Nvidia GPU driver** installed on Windows (≥ 525.x). This is the
   *Windows* driver, not a Linux driver. WSL2 projects it into Linux
   automatically. Do **not** install `nvidia-drivers` inside WSL.

### Install WSL2 + Ubuntu

```powershell
# PowerShell (admin): installs WSL2 and Ubuntu in one step
wsl --install
```

Reboot when prompted, then launch **Ubuntu** from the Start menu and
set your username/password. That's it. You're in a real Linux shell
with GPU access.

### Quick start (inside Ubuntu WSL)

```bash
git clone https://github.com/cdarnell/minimalist-blueprint.git oglab
cd oglab
./oglab setup && ./oglab start
```

The setup detects WSL + Nvidia automatically:

```text
━━━ 1/10  Detecting hardware
  Platform:    wsl (x86_64)
  CPUs:        16
  Memory:      64 GB
  Disk free:   200 GB
  Accelerator: cuda
  GPU:         NVIDIA RTX 4090 (24564 MB VRAM)

━━━ 2/10  Computing build profile
━━━ 3/10  Build manifest         ← tier, engines, resources
━━━ 4/10  System packages        ← apt install python3 git build-essential cmake ...
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

### Windows inference options

| Option | `.env` setting | Notes |
| -------- | --------------- | ------- |
| **CUDA / vLLM** (default) | `MODEL_BACKEND=cuda` | Direct GPU, fastest |
| **LM Studio** (on Windows host) | `MODEL_BACKEND=openai_compat`<br>`MODEL_API_BASE=http://host.docker.internal:1234/v1` | Run LM Studio on Windows, call from WSL |
| **Ollama** (in WSL) | `MODEL_BACKEND=openai_compat`<br>`MODEL_API_BASE=http://localhost:11434/v1` | Runs inside WSL with CUDA |
| **CPU fallback** | `MODEL_BACKEND=cpu` | llama.cpp, no GPU needed |

### Windows notes

- The Nvidia driver is installed on **Windows only**. WSL2 bridges it
  via `/dev/dxg`. Do NOT install `nvidia-drivers` inside WSL.
- AMD ROCm on WSL2 is experimental. Stick with Nvidia for now.
- Prefer **Ubuntu 22.04 / 24.04 LTS**. It's what Nvidia tests against
  and what `./oglab setup` expects for apt package names.
- Other distros (Debian, Arch-WSL, Gentoo-WSL) work too, but you're in
  the [native Linux](#section-3--linux-native-bring-your-own-distro)
  path below, and `setup.sh` won't know your package names automatically.

---

## Linux: Native (Bring Your Own Distro)

> The blueprint is distro-neutral. The only 20 lines that care about
> your OS are the package-manager calls in [`scripts/setup.sh`](scripts/setup.sh).

### What you get on Linux

| Component | How it works on Linux |
| --- | --- |
| **GPU** | CUDA (Nvidia) or CPU fallback (llama.cpp). ROCm is experimental. |
| **Model router** | `MODEL_BACKEND=cuda` or `cpu` (auto-detected) |
| **Packages** | Whatever your distro uses. `apt`, `dnf`, `pacman`, `emerge`, `nix` |
| **OS** | Any Linux with Python ≥ 3.10 |

### The vibe-integrate approach

`./oglab setup` has branches for macOS (Homebrew), Debian/Ubuntu (apt),
and Gentoo (emerge). If you're on Arch, Fedora, NixOS, Alpine, or
anything else, the fastest path is to **point an agent at the blueprint
and let it port the setup script to your distro**:

```bash
# 1. Clone
git clone https://github.com/cdarnell/minimalist-blueprint.git oglab
cd oglab

# 2. Try setup: it'll tell you what's missing
./oglab setup
```

When `setup.sh` doesn't recognize your distro, hand your agent the
two files it needs ([scripts/setup.sh](scripts/setup.sh) and
[docs/LINUX.md](docs/LINUX.md)) and ask it to add a branch for your
package manager. The rest of the blueprint (the Python package, the
portal, the router, the agents) doesn't care what installed CUDA.

Because OGLab is small and coherent by design, this port is usually a
single function in `setup.sh` plus a one-line entry in a case
statement. See [docs/LINUX.md](docs/LINUX.md) for the recipe and a
worked example (Arch Linux).

### Linux notes

- **Gentoo users**: [scripts/gentoo-bootstrap.sh](scripts/gentoo-bootstrap.sh)
  provides OpenRC service files and USE-flag suggestions.
- **Nvidia**: install the CUDA toolkit via your distro (don't mix
  pip-installed CUDA with system CUDA). Kernel modules must match
  the driver version.
- **ROCm**: AMD GPUs work in theory via `rocBLAS` + `hip-python`; not
  in the blessed path, but the router has a CUDA backend that will
  fall through to ROCm if `HIP_VISIBLE_DEVICES` is set.
- **Headless servers**: pass `OGLAB_NO_BROWSER=1 ./oglab start` to
  skip the auto-open step.

---

## Shared: All Platforms

Everything below applies identically on every platform. Your code
never sees the platform difference. The model router abstracts it.

```text
Mac host     ──→  MLX (native Metal)
WSL2         ──→  CUDA via Windows GPU bridge
Linux native ──→  CUDA (Nvidia) / ROCm (AMD, experimental) / CPU
Any platform ──→  AeroLLM (70B+ from disk, prefetched layer streaming)
Any platform ──→  LM Studio / Ollama / DeployLM (OpenAI-compat API)
Any platform ──→  External API (free tier, bring your own token)
Any platform ──→  CPU fallback (llama.cpp)
```

One codebase, zero `if platform ==` branches.

Edit `lab.conf` to change ports or resource limits.
Edit `.env` to change model backend or API keys.

---

## Project Structure

```text
oglab/
├── oglab                     # ← unified CLI: setup | start | stop | reset | pkb | doctor
├── src/oglab/                # Python package
│   ├── router/               # Model router (MLX / CUDA / CPU / AeroLLM / cloud)
│   ├── skills/               # goal_parser, experiment_tracker
│   ├── agents/               # consent, curator, researcher
│   ├── plugins/              # Plugin manager (GitHub → install)
│   ├── portal/               # FastAPI dashboard (app.py + templates/ + static/)
│   ├── pkb.py                # Knowledge base engine
│   ├── costs.py              # CostTracker
│   ├── activity.py           # Event bus (SSE streaming)
│   ├── goals.py              # Goal persistence
│   └── config.py             # Central runtime paths + env loader
│
├── lab/                      # runtime state (gitignored, created by setup)
│   ├── data/                 # activity.jsonl, goals/, consent/, experiments/
│   ├── models/               # downloaded model weights
│   └── pkb/                  # knowledge base: inbox, sources, agents, notes, compiled
│
├── scripts/                  # delegates for ./oglab
│   ├── setup.sh              # provision venv + deps + model + lab/
│   ├── start.sh              # launch portal + terminal + notebook + IDE
│   ├── reset.sh              # wipe models/data/env/plugins
│   ├── pkb-{ingest,compile,browse}
│   └── gentoo-bootstrap.sh
│
├── docs/                     # MACOS.md, WSL.md, LINUX.md, vibe-integrate.md
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
| --------- | ----------- | ------- | ------ |
| MLX (Mac) | `mlx` | Apple Silicon | Free |
| CUDA (Nvidia) | `cuda` | Nvidia GPU + vLLM | Free |
| CPU (llama.cpp) | `cpu` | Any machine | Free |
| **LM Studio / Ollama / DeployLM** | `openai_compat` | Local server running | Free |
| **NVIDIA NIM** (build.nvidia.com) | `openai_compat` | `nvapi-…` key | **Free credits** |
| HuggingFace | `huggingface` | API key | Free tier |
| OpenRouter | `openrouter` | API key | Free tier |
| Claude | `claude` | API key | Paid |

**NVIDIA NIM setup**, the "test the waters" path. Sign up at [build.nvidia.com](https://build.nvidia.com), grab an `nvapi-…` key, then in `.env`:

```bash
MODEL_BACKEND=openai_compat
MODEL_API_BASE=https://integrate.api.nvidia.com/v1
MODEL_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MODEL_NAME=meta/llama-3.3-70b-instruct
```

That's it. You're running Llama 3.3 70B (or Nemotron, DeepSeek-R1, etc.) through the same router that talks to your local MLX/CUDA stack. Swap `MODEL_NAME` to browse. Because NIM speaks OpenAI's protocol, no dedicated backend class is needed. The generic `openai_compat` path handles it.

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
```text
https://github.com/cdarnell/minimalist-blueprint
```

Tell people:
> Fork it. Run `./oglab setup`. Set your goal. The lab handles the rest.

For non-technical family: the example runs a complete demo with zero
configuration beyond `./oglab setup`.

## License

MIT. Use it, change it, share it.
