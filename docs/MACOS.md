# macOS — OGLab Setup

Apple Silicon Macs run inference natively via MLX — no cloud needed.

---

## Requirements

- macOS 13+ (Ventura or later)
- Apple Silicon (M1 / M2 / M3 / M4)
- ~8 GB free disk (for one 7B model)

## Setup

```bash
git clone https://github.com/cdarnell/minimalist-blueprint.git oglab
cd oglab
./setup.sh          # detects macOS + Apple Silicon → installs MLX
source .venv/bin/activate
python3 examples/peanut_farmer/run.py
```

`setup.sh` will:
1. Create a `.venv`
2. Install `mlx` + `mlx-lm`
3. Download `Mistral-7B-Instruct` (4-bit, ~4 GB)
4. Set `MODEL_BACKEND=mlx` in `.env`

## Intel Macs

Intel Macs don't support MLX. Use the CPU backend:

```bash
MODEL_BACKEND=cpu    # in .env
# setup.sh will install llama-cpp-python and prompt for a GGUF model
```

## Airgapped Mode

After the first `setup.sh` run (which downloads the model), everything
runs offline. `OGLAB_MODE=airgapped` is the default.
