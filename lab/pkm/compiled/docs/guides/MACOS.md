---
title: Macos
section: docs
tags: [guide]
aliases: [MACOS]
source: docs/MACOS.md
generated: 2026-04-15T00:51:55Z
---
# macOS — OGLab Setup

Apple Silicon Macs run inference natively via MLX — no cloud needed.

---

## Requirements

- macOS 13+ (Ventura or later)
- Apple Silicon (M1 / M2 / M3 / M4)
- Python 3.10 or newer (`brew install python@3.12` if needed)
- ~8 GB free disk for one 8B model

## Setup

```bash
git clone https://github.com/cdarnell/minimalist-blueprint.git oglab
cd oglab
./oglab setup       # detects macOS + Apple Silicon → installs MLX, captures your goal
./oglab start       # launches portal + terminal + notebook + IDE
```

`./oglab setup` will:

1. Create a `.venv` and `pip install -e ".[dev]"`
2. Install `mlx` + `mlx-lm`
3. Download `mlx-community/Qwen3-8B-4bit` (~4.3 GB)
4. Set `MODEL_BACKEND=mlx` in `.env`
5. Ask for your research goal and work windows, write them to `lab/data/goals/bootstrap_goal.json` and `.env`

Then `./oglab start` brings up the dashboard at <http://127.0.0.1:8080> along with the in-browser terminal (ttyd), Jupyter Lab, and VS Code Server. The researcher agent auto-starts on your captured goal after a 5-minute courtesy delay (configurable via `LAB_STARTUP_DELAY_SEC`).

## Intel Macs

Intel Macs don't support MLX. Use the CPU backend:

```bash
MODEL_BACKEND=cpu    # in .env
# ./oglab setup will install llama-cpp-python and prompt for a GGUF model
```

## Airgapped Mode

After the first `./oglab setup` run (which downloads the model), everything runs offline. `OGLAB_MODE=airgapped` is the default.
