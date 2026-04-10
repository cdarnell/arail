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

## Two Modes

- **Airgapped** (default) — zero network calls. Local model, local data.
- **Hybrid** — local-first with optional cloud fallback (HuggingFace free tier, OpenRouter, Claude).

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
./bootstrap.sh
```

The bootstrap detects your Mac automatically:

```
━━━ 1/8  Detecting hardware
  Platform:    macos (arm64)
  CPUs:        10
  Memory:      32 GB
  Disk free:   400 GB
  Accelerator: mlx
```

It asks how much of your machine to dedicate, then installs everything:

```
? CPUs for the lab [8]:
? Memory for the lab (GB) [24]:
? Model size [medium]:

━━━ 3/8  System packages        ← brew install python git curl tmux cmake
━━━ 4/8  Python environment     ← venv + mlx + mlx-lm
━━━ 5/8  Lab services           ← portal, jupyter, ttyd, code-server
━━━ 6/8  AI model               ← MLX-quantized model download
━━━ 7/8  Configuration          ← .env + lab.conf
━━━ 8/8  Start script           ← ./start.sh

✓ Bootstrap complete!
```

Then:

```bash
source .venv/bin/activate
./start.sh
```

### Mac services

| Service | URL | What |
|---------|-----|------|
| **Dashboard** | http://127.0.0.1:8080 | Goal tracking, experiments, agents |
| **Terminal** | http://127.0.0.1:7681 | Shell in browser (ttyd) |
| **Notebook** | http://127.0.0.1:8888 | Jupyter Lab |
| **IDE** | http://127.0.0.1:8443 | VS Code in browser (code-server) |

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
━━━ 1/8  Detecting hardware
  Platform:    wsl (x86_64)
  CPUs:        16
  Memory:      64 GB
  Disk free:   200 GB
  Accelerator: cuda
  GPU:         NVIDIA RTX 4090 (24564 MB VRAM)
```

It asks resource allocation, then installs everything:

```
? CPUs for the lab [14]:
? Memory for the lab (GB) [48]:
? Model size [medium]:

━━━ 3/8  System packages        ← emerge -av python gcc cmake ...
━━━ 4/8  Python environment     ← venv + vllm + torch (CUDA)
━━━ 5/8  Lab services           ← portal, jupyter, ttyd, code-server
━━━ 6/8  AI model               ← CUDA-optimized model download
━━━ 7/8  Configuration          ← .env + lab.conf
━━━ 8/8  Start script           ← ./start.sh

✓ Bootstrap complete!
```

Then:

```bash
source .venv/bin/activate
./start.sh
```

Services are accessible from your Windows browser at the same URLs.

### Windows services

| Service | URL | What |
|---------|-----|------|
| **Dashboard** | http://127.0.0.1:8080 | Goal tracking, experiments, agents |
| **Terminal** | http://127.0.0.1:7681 | Shell in browser (ttyd) |
| **Notebook** | http://127.0.0.1:8888 | Jupyter Lab |
| **IDE** | http://127.0.0.1:8443 | VS Code in browser (code-server) |

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
