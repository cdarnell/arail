---
title: Linux Setup
category: Getting Started
order: 3
tags:
  - linux
  - setup
  - install
audience: operator
related:
  - INSTALL
  - TROUBLESHOOTING
---
# Linux — Bring Your Own Distro

Arail is distro-neutral. The Python package, the portal, the agents,
and the model router don't care what installed CUDA or what version of
Python you're running — they just need `python >= 3.10` and a working
venv.

The only OS-aware code lives in [`scripts/setup.sh`](../scripts/setup.sh),
and specifically in the `install_core_deps` and `install_accel_deps`
functions. Out of the box those know:

| Distro family | Package manager | Status |
| --- | --- | --- |
| macOS | Homebrew | blessed path |
| Debian / Ubuntu (incl. WSL2) | `apt` | blessed path |
| Gentoo | `emerge` | supported, notes below |
| Arch | `pacman` | worked example below |
| Fedora | `dnf` | worked example below |
| openSUSE / NixOS / Alpine / … | whatever | **port it with an agent** (see [AGENTS.md](../AGENTS.md)) |

If `./arailctl setup` doesn't recognize your distro, you have two options:
either port the setup script yourself (~20 lines), or hand the
blueprint to an agent and let it do it for you.

If you're adapting Arail to a person's machine rather than adding distro
support, see [vibe-integrate.md](vibe-integrate.md).

## The agent-port approach

The idea: you already have a local model running the lab (or a cloud
agent — this works with any coding assistant). Point it at the two
files it needs and ask it to add a branch for your package manager.

Here's a prompt that gets it done reliably:

> I'm porting [arail](https://github.com/qukaizen/arail)
> to **\<your distro\>**. Look at `scripts/setup.sh` — specifically the
> `detect_platform`, `install_core_deps`, and `install_accel_deps`
> functions. Add a new branch for \<your distro\> that installs the
> equivalent of the apt packages (`python3 python3-venv build-essential
> cmake git curl`) and, if an Nvidia GPU is present, CUDA toolkit + cuDNN.
> Preserve the existing macOS / apt / emerge branches. Keep it under 30
> lines.

That's the whole port. The agent reads the file, writes a patch, you
review it, commit it. Upstream a PR if you want the blueprint to learn
a new distro permanently.

## Worked example — Arch Linux

Here's what an Arch port looks like (concrete enough to copy-paste, short
enough to read in one sitting):

```bash
# scripts/setup.sh — inside install_core_deps()
elif [[ "$PLATFORM" == "arch" ]]; then
    info "Installing core packages via pacman…"
    sudo pacman -S --needed --noconfirm \
        python python-pip python-virtualenv \
        base-devel cmake git curl
fi

# scripts/setup.sh — inside install_accel_deps()
elif [[ "$PLATFORM" == "arch" && "$ACCEL" == "cuda" ]]; then
    info "Installing CUDA via pacman…"
    sudo pacman -S --needed --noconfirm cuda cudnn
    # pip install torch with the CUDA wheel matching your toolkit
    pip install -q torch --index-url https://download.pytorch.org/whl/cu121
fi

# scripts/setup.sh — inside detect_platform()
elif [[ -f /etc/arch-release ]]; then
    PLATFORM=arch
fi
```

That's it. After those three stanzas, `./arailctl setup` on Arch behaves
identically to Ubuntu or macOS — it creates the venv, installs the
Python package, downloads a model, captures your goal, and hands off
to `./arailctl start`.

## Worked example — Fedora Workstation

Fedora 39+ ships Python 3.12 and has solid Nvidia support via rpmfusion.
High-impact because of the student demographic on Fedora Workstation /
AI Boxes.

```bash
# scripts/setup.sh — inside detect_platform()
elif [[ -f /etc/fedora-release ]]; then
    PLATFORM=fedora

# scripts/setup.sh — inside install_services()
fedora)
    if command -v dnf &>/dev/null; then
        info "Installing ttyd via dnf…"
        sudo dnf install -y ttyd 2>&1 | tail -3 || \
            warn "ttyd install failed — /terminal will show install help."
    fi
    ;;

# scripts/setup.sh — inside install_accel_deps()
# The cuda branch already handles Fedora once CUDA is installed via rpmfusion.
# If CUDA isn't present, the user falls back to the cpu branch automatically.
```

Prerequisites a Fedora user handles themselves (setup won't do it):

```bash
# Enable rpmfusion for proprietary drivers (Nvidia only)
sudo dnf install -y \
    https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm \
    https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm

# Nvidia driver + CUDA
sudo dnf install -y akmod-nvidia xorg-x11-drv-nvidia-cuda

# Reboot, then verify
nvidia-smi
```

After that, `./arailctl setup` detects CUDA automatically and uses the
existing cuda branch. The Fedora-specific work is just the three-line
port above.

## Gentoo notes

Gentoo is supported directly in `setup.sh`, but you typically do a bit
more system prep yourself than on Ubuntu or macOS.

Base packages:

```bash
emerge -av dev-lang/python dev-python/pip dev-python/virtualenv
emerge -av sys-devel/gcc sys-devel/make dev-build/cmake git curl
```

If you're running Nvidia CUDA:

```bash
echo "x11-drivers/nvidia-drivers NVIDIA-r2" >> /etc/portage/package.license/nvidia
echo 'dev-util/nvidia-cuda-toolkit -profiler' >> /etc/portage/package.use/cuda

emerge -av x11-drivers/nvidia-drivers dev-util/nvidia-cuda-toolkit
modprobe nvidia
nvidia-smi
```

For the Python side inside the Arail venv:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
python3 -c "import torch; print(torch.cuda.is_available())"
```

OpenRC / service notes:

- [scripts/gentoo-bootstrap.sh](../scripts/gentoo-bootstrap.sh) includes a working service file for the portal.
- Keep the portal bound to `127.0.0.1:8080` unless you put real auth and TLS in front of it.
- Typical Portage flags for ML hosts: `USE="cuda opencl python"` and `PYTHON_TARGETS="python3_12"`.
- Kernel basics: enable DRM, disable Nouveau if using the proprietary Nvidia driver, and verify the matching kernel module is loaded.

## What if my distro has no Nvidia support at all?

CPU fallback via llama.cpp works on literally any Linux with a working
C++ toolchain:

```bash
# In your .env
MODEL_BACKEND=cpu
MODEL_NAME=Qwen/Qwen3-8B-GGUF
```

The Python package for that is `llama-cpp-python`, installed by
`pip install -e .[cpu]`. No CUDA, no drivers, no kernel modules — just
slower tokens per second.

## If you're on ROCm (AMD GPU)

ROCm isn't in the blessed path, but the router's CUDA backend will
honor `HIP_VISIBLE_DEVICES` if you've set up `rocm-device-libs`,
`hip-python`, and a PyTorch ROCm wheel. Expect to do some per-distro
plumbing — `arch4edu` has decent ROCm packages, Ubuntu's
`rocm-hip-runtime` works on 22.04+, and Fedora has `rocm-hip`. The
blueprint doesn't test this path, but the code will happily use it.

## Headless servers

If you're running this on a box without a graphical shell (a home lab,
a VPS, a dedicated research machine), skip the auto-open browser step:

```bash
ARAIL_NO_BROWSER=1 ./arailctl start
```

Bind to all interfaces instead of localhost by editing `lab.conf`:

```text
BIND_ADDR=0.0.0.0
```

Then hit it from another machine at `http://<server-ip>:8080`.

## Reporting back

If you port the blueprint to a new distro and it works, open a PR with
your additions to `scripts/setup.sh` and a one-line entry in the table
above. That's how the blueprint grows without forking.
