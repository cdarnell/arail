---
title: Install Guide
description: "A friendly walkthrough for getting the lab running on your machine — no prior experience needed."
category: Getting Started
order: 1
tags:
  - install
  - setup
  - getting-started
audience: beginner
related:
  - MACOS
  - LINUX
  - WSL
  - TROUBLESHOOTING
---
# Install Guide — Autoresearch AI Lab

> **See also:** [The lab, end-to-end](the-lab.md) — the 12-minute runbook
> tour of every surface. Read it after you finish setup (or first, if
> you want to know what you're installing).

A friendly walkthrough. If you've never run a Python app from a terminal
before, this is for you.

If you're adapting Arail for someone else's machine or translating the same lab
between machines, pair this guide with [vibe-integrate.md](vibe-integrate.md).
That companion explains how to keep the setup path the same while tuning the
first-run choices to the target hardware.

---

## 0. What you need

- **macOS**, **Linux**, or **Windows + WSL2**. Native Windows shells are not
  supported by `./arailctl setup`.
- ~8 GB free disk for the `minimalist` tier, ~60 GB for the `maximus` tier.
- Git, a terminal, and a browser.

`./arailctl setup` bootstraps everything else for you. If Homebrew, Python
3.11, or Node.js are missing, it'll prompt once and then install them via
your platform's package manager. Pass `ARAIL_NONINTERACTIVE=1` (the
agent-driven flag) to skip every prompt, or `ARAIL_AUTO_INSTALL=0` to
fall back to the old "tell me what to install, I'll do it myself"
behavior.

---

## 1. Clone and enter the repo

```bash
git clone https://github.com/qukaizen/arail.git
cd arail
```

---

## 2. Decide on a tier

Two tiers. You can change your mind later with `./arailctl upgrade maximus`.

Legacy `min`/`max` tier names are accepted with a deprecation warning
(compat shim removed in v1.1.0).

### 🟢 `minimalist` — the everyday lab

- **Tabs**: Dashboard, Chat, Autoresearch, Knowledge Base, Agents, Docs.
- **Packages**: core lab + embedded **LanceDB** recall. No heavyweight
  deep backend installed by default.
- **Default model**: `ai-eng` — a 3B-parameter Opus-4.7-derived AI
  engineering expert from QuKaiZen's Project Nucleus. Served via Ollama.
  This is the only model that auto-installs. The chat catalog lists ~20
  other models you can browse and pull on demand.
- **Memory**: KB ships with embedded semantic recall out of the box.
  You get the same knowledge surface in `minimalist`; `maximus` is
  about heavier operator tools, not a different memory backend.
- **External providers**: Claude / NVIDIA / OpenRouter / HuggingFace are
  still reachable in `minimalist` — they go over plain HTTP. The only
  thing `maximus` adds here is the official SDKs for heavier
  orchestration.
- **Good for**: a first taste; an older laptop; the blueprint you hand
  to a friend who wants to learn.

### 🔴 `maximus` — the full bench

- **Tabs**: everything in `minimalist` + Admin + Docs + Notebooks +
  Tuning + Plugins.
- **Adds**:
  - `jupyterlab` — browser notebooks.
  - `anthropic` SDK — first-class Claude integration.
  - `langchain` + `langgraph` — for operators who want to compose agents
    with the community ecosystem on top of the built-ins.
  - **AeroLLM** — Arail's own Rust streaming runtime, the deep-mode
    backend. Apple Silicon: native. CUDA hosts: fall back to AirLLM with
    a notice until AeroLLM CUDA ships (set `ARAIL_FORCE_AEROLLM=1` to
    disable fallback).
  - Hardware-specific extras (MLX, CUDA, or CPU) install automatically
    based on what `./arailctl setup` detects.
- **Good for**: real experiments, frontier models when you pull them
  yourself from the catalog, the full kitchen sink.

> **Heads up — AirLLM is opt-in.** v1.0.0 removed AirLLM from the
> default install path. Power users on CUDA/Linux who want
> layer-streaming 405B inference can enable it with
> `ARAIL_INSTALL_AIRLLM=1 ./arailctl setup`. Llama weights are gated on
> Hugging Face and require `huggingface-cli login` (or `HF_TOKEN`).

---

## 3. Run `./arailctl setup`

```bash
./arailctl setup
```

This walks you through 10 steps:

1. Detect your platform (macOS / Linux / WSL2) and accelerator (MLX / CUDA / CPU).
2. Install OS packages if needed (brew, apt, dnf, pacman, emerge).
3. Create a Python venv and install deps **for the tier you pick**.
4. Name your lab. Default is *Autoresearch AI Lab* — rename to taste.
5. Pick a passphrase (protects the in-browser IDE and notebook encryption).
6. Write `.env` with your choices.
7. Scaffold the knowledge base directory.
8. Pull the ai-eng model (~5 GB — qwen2.5:7b preview base + AI Engineer
   persona Modelfile, or `qukaizen/ai-eng:3b` once QuKaiZen publishes it).
9. Capture a research goal.
10. Verify with a smoke test.

Everything is idempotent — re-run any time without fear.

---

## 4. Start the lab

```bash
./arailctl start
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). You're in.

---

## 5. Upgrade later

When you're ready for more:

```bash
./arailctl upgrade maximus     # installs AeroLLM + adds notebook/cloud orchestration extras
./arailctl restart             # pick up the new nav
```

`./arailctl upgrade minimalist` is a downgrade — it doesn't uninstall
packages, it just hides the extra tabs. Hit `upgrade maximus` any time
to get them back. Legacy `min`/`max` tier names still work via a
one-release compat shim (removed in v1.1.0).

---

## 6. Connect an outside model (Chat → Manage providers)

The Chat tab is where every operator — `minimalist` or `maximus` —
configures outside model vendors.

1. First: in `.env`, set `LAB_MODE=hybrid` and restart. This is the airgapped
   guard — by default the lab refuses every cloud provider operation
   (save, test, switch) until you explicitly opt in.
2. Open Chat. Click **⚙ Manage providers**.
3. For each vendor you want to use — Claude, NVIDIA NIM, OpenRouter,
   HuggingFace, or a custom OpenAI-compatible endpoint — paste the API key
   and click **Save**. The key writes to `lab/data/secrets.env` with
   `chmod 0600` (readable only by you, git-ignored).
4. Click **Test** to verify — the lab pings the vendor's `/models` endpoint
   with the saved token and reports OK or the error.
5. Click **List models** to see the vendor's current model catalogue. Handy
   for typing the exact model ID into your Autoresearch goal.
6. **Remove** deletes the saved token; the vendor goes back to "no token".
7. Close the modal. On the Chat tab, pick the provider from the
   **Compute Source** row and send a message.

Tokens are never echoed back to the UI after saving and never logged. If
you prefer managing keys in `.env` directly, the relevant vars are
`ANTHROPIC_API_KEY`, `NVIDIA_API_KEY`, `OPENROUTER_API_KEY`, `HF_TOKEN`,
and `MODEL_API_BASE` — `secrets.env` just keeps them out of `.env` so
they don't mix with non-sensitive config.

---

## 7. Rename your lab

The whole point of the blueprint. Edit `.env`:

```bash
LAB_NAME="Sam's AI Lab"
LAB_SHORT_NAME="sams-lab"
LAB_TAGLINE="Our family AI bench"
```

`./arailctl restart` and every banner, title, log line, and wiki landing page
now says "Sam's AI Lab".

---

## 8. Troubleshooting

```bash
./arailctl doctor          # end-to-end validation
./arailctl status          # what's running, on which ports
./arailctl logs            # live activity tail
./arailctl reset help      # ways to wipe state if something went very wrong
```

See [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common first-run gotchas.

---

## 9. The `qkz` alias

If typing `./arailctl` gets old, there's a symlink at `./qkz` that does the same
thing. Or alias it in your shell:

```bash
alias qkz='./arailctl'  # then: qkz setup, qkz start, qkz restart
```

Happy researching.
