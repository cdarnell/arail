# OGLab — AI Lab Blueprint

A shareable blueprint for building your own AI research lab.
Local-first. Airgapped by default. Your models, your data, your hardware.

**Not a product. A blueprint you fork, customize, and own.**

---

## What This Is

You state a goal. The lab helps you break it down, find data, run
experiments, and track results — all powered by a local LLM running on
your own machine.

```
"I want to grow the best peanuts in Georgia"
        ↓
  Goal Parser → structured objectives
        ↓
  Experiment Tracker → hypothesis → test → results
        ↓
  Your open notebook of findings
```

Works for farming, ML research, cooking, business — any domain.

## Platforms

| Platform | Accelerator | How |
|----------|-------------|-----|
| **Gentoo Linux** | Nvidia CUDA / AMD ROCm / CPU | Full compile-from-source stack |
| **macOS (Apple Silicon)** | MLX | Native Metal acceleration |
| **Windows** | Nvidia via WSL2 | GPU passthrough to Linux |
| **Any Linux** | CUDA / CPU | Standard pip install |

### GPU abstraction

GPU drivers vary wildly across platforms — CUDA on Linux, Metal/MLX on
Mac, the WSL2 `/dev/dxg` bridge on Windows.  **The model router
abstracts all of this.**  Your code calls `router.complete()` and the
router dispatches to whatever accelerator is available on the host.
Gentoo serves as the lab environment and orchestration layer; it does
not need to own the GPU driver on every platform.

```
Mac host  ──→  MLX (native Metal, no VM needed)
WSL2      ──→  CUDA via Windows GPU bridge
Linux box ──→  CUDA / ROCm via Gentoo portage
Any host  ──→  Local inference server (LM Studio / Ollama / DeployLM)
Any host  ──→  CPU fallback (llama.cpp)
Any host  ──→  External API (free tier, bring your own token)
```

One codebase, zero `if platform ==` branches in user code.

### Local inference servers

Don't want to wire up raw CUDA or MLX? Point the router at a local
inference server instead.  These run on your GPU and expose an
OpenAI-compatible API on localhost:

| Server | Best for | GPU support |
|--------|----------|-------------|
| [LM Studio](https://lmstudio.ai) | Desktop GUI, one-click models | CUDA, Metal, Vulkan |
| [Ollama](https://ollama.com) | CLI-first, `ollama run` simplicity | CUDA, Metal |
| [DeployLM](https://deploylm.com) | Production serving, multi-model | CUDA |

Set `MODEL_BACKEND=openai_compat` and `MODEL_API_BASE=http://localhost:1234/v1`
in your `.env`.  The router talks to it like any other backend.

## Two Modes

- **Airgapped** (default) — zero network calls. Local model, local data. Flip a switch after setup.
- **Hybrid** — local-first with optional cloud fallback (HuggingFace free tier, OpenRouter, Claude).

---

## The Operating System — Gentoo Linux

OGLab runs on Gentoo.  Not because it's trendy — because it gives you
full control over every package compiled on your machine.  No black-box
binaries, no distro opinions about what you can install.

### Why Gentoo

- **Portage** compiles packages from source with your USE flags.  You
  decide what's linked, what's stripped, what GPU support is baked in.
- Rolling release — always current, no version-upgrade cliffs.
- Minimal base.  You install only what the lab needs.

### Default user

The lab ships with a single user pre-configured:

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

### Package management

Gentoo uses `emerge` (Portage).  Standard Linux package operations all work:

```bash
# Search for a package
emerge --search numpy

# Install a package
sudo emerge -av dev-python/numpy

# Update everything
sudo emerge --update --deep --newuse @world

# Remove a package
sudo emerge --depclean dev-python/numpy

# Check installed packages
qlist -Iv
```

USE flags let you compile exactly what you need:

```bash
# See USE flags for a package
equery uses dev-libs/opencv

# Set flags in /etc/portage/package.use
echo "dev-libs/opencv cuda python" | sudo tee -a /etc/portage/package.use/oglab
sudo emerge -av dev-libs/opencv    # rebuilds with CUDA + Python bindings
```

### Common lab packages

```bash
# Python ML stack
sudo emerge -av dev-python/numpy dev-python/scipy dev-python/pandas

# CUDA toolkit (if you have an Nvidia GPU)
sudo emerge -av dev-util/nvidia-cuda-toolkit

# System tools
sudo emerge -av app-misc/tmux net-misc/curl app-editors/vim
```

Everything is a normal Linux system.  `apt` doesn't exist — `emerge`
replaces it.  If you know `apt install foo`, the Gentoo equivalent is
`emerge -av foo` (search first with `emerge -s foo`).

---

## Quick Start

```bash
git clone https://github.com/cdarnell/minimalist-blueprint.git oglab
cd oglab
./bootstrap.sh
```

The bootstrap walks you through everything:

```
━━━ 1/8  Detecting hardware
  Platform:    gentoo (x86_64)
  CPUs:        16
  Memory:      64 GB
  Disk free:   200 GB
  Accelerator: cuda
  GPU:         NVIDIA RTX 4090 (24564 MB VRAM)

━━━ 2/8  Resource allocation
  Your machine has 16 CPUs, 64 GB RAM, 200 GB disk free.
  How much should the lab use?
? CPUs for the lab [14]:
? Memory for the lab (GB) [48]:
? Model size [medium]:

━━━ 3/8  System packages        ← emerge / apt / brew
━━━ 4/8  Python environment     ← venv + pip
━━━ 5/8  Lab services           ← portal, jupyter, ttyd, code-server
━━━ 6/8  AI model               ← download based on your GPU + size choice
━━━ 7/8  Configuration          ← .env + lab.conf
━━━ 8/8  Start script           ← generates ./start.sh

✓ Bootstrap complete!
```

Then launch everything:

```bash
source .venv/bin/activate
./start.sh
```

Four services come up:

| Service | URL | What |
|---------|-----|------|
| **Dashboard** | http://127.0.0.1:8080 | Goal tracking, experiments, agents, activity feed |
| **Terminal** | http://127.0.0.1:7681 | Full shell in browser (ttyd) |
| **Notebook** | http://127.0.0.1:8888 | Jupyter Lab |
| **IDE** | http://127.0.0.1:8443 | VS Code in browser (code-server, always free) |

Edit `lab.conf` to change ports or resource limits.
Edit `.env` to change model backend or API keys.

**Platform-specific guides:** [Gentoo](docs/GENTOO.md) · [macOS](docs/MACOS.md) · [WSL/Windows](docs/WSL.md)

---

## Project Structure

```
oglab/
├── oglab/                    # Python package
│   ├── router/               # Model router (MLX / CUDA / CPU / cloud)
│   │   ├── backends.py       # All backend implementations
│   │   └── core.py           # ModelRouter class
│   ├── skills/               # Pluggable lab skills
│   │   ├── goal_parser/      # Natural language → structured goals
│   │   └── experiment_tracker/# Hypothesis → test → results
│   ├── agents/               # Autonomous agents
│   │   ├── consent.py        # Network consent / allowlist
│   │   ├── curator.py        # Source curation
│   │   └── researcher.py     # Background auto-research agent
│   ├── plugins/              # Plugin manager (GitHub → install)
│   ├── activity.py           # Event bus (SSE streaming)
│   └── goals.py              # Goal persistence + history
│
├── portal/                   # Web dashboard (FastAPI + htmx)
│   ├── app.py                # Routes (30 endpoints)
│   ├── static/style.css      # 1337 design system
│   └── templates/            # dashboard, plugins, terminal, notebook
│
├── examples/
│   └── peanut_farmer/        # Complete working example
│
├── platform/                 # Platform-specific configs
├── docs/                     # Setup guides per platform
│
├── bootstrap.sh              # ← One-command full setup
├── start.sh                  # ← Generated: starts all services
├── lab.conf                  # ← Generated: resource allocation + ports
├── .env                      # ← Generated: model backend + API keys
├── pyproject.toml            # Python package definition
└── requirements.txt          # Core dependencies
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
> Fork it. Run `./setup.sh`. Set your goal. The lab handles the rest.

For non-technical family: the example runs a complete demo with zero
configuration beyond `./setup.sh`.

## License

MIT — use it, change it, share it.
