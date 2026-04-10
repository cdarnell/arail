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

## Two Modes

- **Airgapped** (default) — zero network calls. Local model, local data. Flip a switch after setup.
- **Hybrid** — local-first with optional cloud fallback (HuggingFace free tier, OpenRouter, Claude).

---

## Quick Start

```bash
git clone https://github.com/cdarnell/minimalist-blueprint.git oglab
cd oglab
./setup.sh                    # detects your OS + GPU, installs everything
source .venv/bin/activate
python3 examples/peanut_farmer/run.py
```

`setup.sh` will:
1. Detect your platform (Gentoo / macOS / WSL / Linux)
2. Create a Python venv
3. Install the right accelerator (MLX, CUDA, or CPU fallback)
4. Download a starter model
5. Write your `.env`

**Platform-specific guides:** [Gentoo](docs/GENTOO.md) · [macOS](docs/MACOS.md) · [WSL/Windows](docs/WSL.md)

---

## Project Structure

```
oglab/
├── oglab/                    # Python package
│   ├── router/               # Model router (MLX / CUDA / CPU / cloud)
│   │   ├── backends.py       # All backend implementations
│   │   └── core.py           # ModelRouter class
│   └── skills/               # Pluggable lab skills
│       ├── goal_parser/      # Natural language → structured goals
│       └── experiment_tracker/# Hypothesis → test → results
│
├── examples/
│   └── peanut_farmer/        # Complete working example
│
├── platform/                 # Platform-specific configs (Gentoo ebuilds, etc.)
├── scripts/                  # Utility scripts
├── docs/                     # Setup guides per platform
│   ├── GENTOO.md
│   ├── MACOS.md
│   └── WSL.md
│
├── setup.sh                  # One-command setup
├── .env.example              # Configuration template
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
