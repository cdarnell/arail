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
- Python 3.10 or newer (`brew install python@3.12` if needed)
- ~8 GB free disk for one 8B model

## Setup

```bash
git clone https://github.com/cdarnell/autoresearch-lab.git arail
cd arail
./arail setup       # detects macOS + Apple Silicon → installs MLX, captures your goal
./arail start       # launches portal + terminal + notebook + IDE
```

`./arail setup` will:

1. Create a `.venv` and `pip install -e ".[dev]"`
2. Install `mlx` + `mlx-lm`
3. Download `mlx-community/Qwen3-8B-4bit` (~4.3 GB)
4. Set `MODEL_BACKEND=mlx` in `.env`
5. Ask for your research goal and work windows, write them to `lab/data/goals/bootstrap_goal.json` and `.env`

Then `./arail start` brings up the dashboard at <http://127.0.0.1:8080> along with the in-browser terminal (ttyd), Jupyter Lab, and VS Code Server. The researcher agent auto-starts on your captured goal after a 5-minute courtesy delay (configurable via `LAB_STARTUP_DELAY_SEC`).

## Intel Macs

Intel Macs don't support MLX. Use the CPU backend:

```bash
MODEL_BACKEND=cpu    # in .env
# ./arail setup will install llama-cpp-python and prompt for a GGUF model
```

## Airgapped Mode

After the first `./arail setup` run (which downloads the model), everything runs offline. `ARAIL_MODE=airgapped` is the default.
