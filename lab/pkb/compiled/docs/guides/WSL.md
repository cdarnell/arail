---
title: Wsl
section: docs
tags: [guide]
aliases: [WSL]
source: docs/WSL.md
generated: 2026-04-15T11:48:11Z
---
# Windows WSL — OGLab Setup

Run OGLab on Windows via WSL2 with Nvidia GPU passthrough.

---

## 1. Prerequisites (Windows Side)

- Windows 10 build 21H2+ or Windows 11
- Nvidia GPU driver **525.x or newer** installed on Windows (not inside WSL)
- WSL2 enabled

## 2. Install WSL2

```powershell
# PowerShell (admin)
wsl --install -d Ubuntu-24.04
wsl --set-version Ubuntu-24.04 2
```

## 3. Verify GPU Inside WSL

```bash
nvidia-smi     # should show your GPU
```

If `nvidia-smi` fails, update your **Windows** Nvidia driver. Do **not** install nvidia-drivers inside WSL — it uses the host driver.

## 4. Install Dependencies

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git build-essential
```

## 5. OGLab Setup

```bash
git clone https://github.com/cdarnell/minimalist-blueprint.git oglab
cd oglab
./oglab setup       # detects WSL + CUDA automatically, captures your goal
./oglab start       # launches portal + terminal + notebook + IDE
```

`./oglab setup` provisions the venv, installs vLLM + PyTorch with CUDA, downloads a starter model, and captures your research goal and work windows. `./oglab start` brings up the dashboard at <http://127.0.0.1:8080> — reachable from your Windows browser at the same address — plus the in-browser terminal (ttyd), Jupyter Lab, and VS Code Server. The researcher agent auto-starts on your captured goal after a 5-minute courtesy delay.

## 6. Airgapped Mode

Once models are downloaded, disconnect from the network. OGLab runs fully offline with `OGLAB_MODE=airgapped` (the default).
