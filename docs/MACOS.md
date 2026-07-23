---
title: macOS Setup
category: Getting Started
order: 2
tags:
  - macos
  - setup
  - install
  - apple-silicon
audience: beginner
related:
  - INSTALL
  - TROUBLESHOOTING
---
# macOS — Arail Setup

Apple Silicon Macs run inference natively via MLX — no cloud needed.

If you're setting Arail up for another Apple Silicon machine, pair this page
with [vibe-integrate.md](vibe-integrate.md). The command surface stays the same;
the integration work is choosing the right starter tier and model for that
specific Mac's RAM, disk, and role.

---

## Requirements

- macOS 13+ (Ventura or later)
- Apple Silicon (M1 / M2 / M3 / M4)
- ~8 GB free disk for one 8B model

`./arailctl setup` bootstraps Homebrew and `python@3.11` for you on first
run — both with a one-line prompt — so you don't need either installed
ahead of time. Set `ARAIL_NONINTERACTIVE=1` to skip the prompts.

## Setup

```bash
git clone https://github.com/qukaizen/arail.git arail
cd arail
./arailctl setup       # detects macOS + Apple Silicon → installs MLX, captures your goal
./arailctl start       # launches portal + terminal + notebook + IDE
```

`./arailctl setup` will:

1. Create a `.venv` and `pip install -e ".[dev]"` (plus `mlx` + `mlx-lm` on Apple Silicon)
2. Install Ollama (if missing) as the local model runtime
3. Pull `llama3.2:1b` (~0.9 GB) and wrap it with the AI-engineer persona as `llama-ai-eng` — the only model that auto-installs (Built with Llama; see [NOTICE](../NOTICE))
4. Ask for your research goal and work windows, write them to `lab/data/goals/bootstrap_goal.json` and `.env`

Then `./arailctl start` brings up the dashboard at <http://127.0.0.1:8080> along with the in-browser terminal (ttyd), Jupyter Lab, and VS Code Server. Your captured goal is **staged** on the dashboard — research does not start on its own; open the Autoresearch page and press **Approve & Run** when you're ready. (The lab boots quiet by design: no model/version probes or background warmers unless you opt in with `ARAIL_AUTOCHECKS=1`. Run `./arailctl doctor` any time for an explicit checkup.)

## Intel Macs

Intel Macs don't support MLX. Use the CPU backend:

```bash
MODEL_BACKEND=cpu    # in .env
# ./arailctl setup will install llama-cpp-python and prompt for a GGUF model
```

## Airgapped Mode

After the first `./arailctl setup` run (which downloads the model), everything runs offline. `ARAIL_MODE=airgapped` is the default.
