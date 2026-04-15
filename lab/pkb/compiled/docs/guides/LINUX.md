---
title: Linux
section: docs
tags: [guide]
aliases: [LINUX]
source: docs/LINUX.md
generated: 2026-04-15T11:48:11Z
---
# Linux — Bring Your Own Distro

OGLab is distro-neutral. The Python package, the portal, the agents,
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
| Gentoo | `emerge` | supported, see [GENTOO.md](GENTOO.md) |
| Arch / Fedora / openSUSE / NixOS / Alpine / … | whatever | **vibe-integrate it** |

If `./oglab setup` doesn't recognize your distro, you have two options:
either port the setup script yourself (~20 lines), or hand the
blueprint to an agent and let it do it for you.

## The vibe-integrate approach

The idea: you already have a local model running the lab (or a cloud
agent — this works with any coding assistant). Point it at the two
files it needs and ask it to add a branch for your package manager.

Here's a prompt that gets it done reliably:

> I'm porting [oglab](https://github.com/cdarnell/minimalist-blueprint)
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

That's it. After those three stanzas, `./oglab setup` on Arch behaves
identically to Ubuntu or macOS — it creates the venv, installs the
Python package, downloads a model, captures your goal, and hands off
to `./oglab start`.

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
OGLAB_NO_BROWSER=1 ./oglab start
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
