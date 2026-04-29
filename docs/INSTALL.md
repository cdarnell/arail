# Install Guide — Autoresearch AI Lab

A friendly walkthrough. If you've never run a Python app from a terminal
before, this is for you.

If you're adapting Arail for someone else's machine or translating the same lab
between machines, pair this guide with [vibe-integrate.md](vibe-integrate.md).
That companion explains how to keep the setup path the same while tuning the
first-run choices to the target hardware.

---

## 0. What you need

- **macOS**, **Linux**, or **Windows + WSL2**. Native Windows shells are not
  supported by `./arail setup`.
- ~8 GB free disk for the `min` tier, ~60 GB for the `max` tier.
- Git, a terminal, and a browser.

`./arail setup` bootstraps everything else for you. If Homebrew, Python
3.11, or Node.js are missing, it'll prompt once and then install them via
your platform's package manager. Pass `ARAIL_NONINTERACTIVE=1` (the
agent-driven flag) to skip every prompt, or `ARAIL_AUTO_INSTALL=0` to
fall back to the old "tell me what to install, I'll do it myself"
behavior.

---

## 1. Clone and enter the repo

```bash
git clone https://github.com/cdarnell/autoresearch-lab.git
cd autoresearch-lab
```

---

## 2. Decide on a tier

Two tiers. You can change your mind later with `./arail upgrade max`.

### 🟢 `min` — the everyday lab

- **Tabs**: Dashboard, Chat, Autoresearch, Knowledge Base, Agents.
- **Packages**: core lab + embedded **LanceDB** recall + **AirLLM** for
  deep layer-streaming inference.
- **Default deep model**: `meta-llama/Llama-3.1-70B`. AirLLM streams
  layer-by-layer from disk, so a 70B fits even on a small machine —
  it'll be slow (tokens-per-minute), but the model itself is the real
  thing.
- **Memory**: KB ships with embedded semantic recall out of the box. You get
  the same knowledge surface in `min`; `max` is about heavier operator tools,
  not a different memory backend.
- **External providers**: Claude / NVIDIA / OpenRouter / HuggingFace are
  still reachable in `min` — they go over plain HTTP. The only thing `max`
  adds here is the official SDKs for heavier orchestration.
- **Good for**: a first taste; an older laptop; the blueprint you hand to a
  friend who wants to learn.

### 🔴 `max` — the full bench

- **Tabs**: everything in `min` + Admin + Docs + Notebooks.
- **Adds**:
  - `jupyterlab` — browser notebooks.
  - `anthropic` SDK — first-class Claude integration.
  - `langchain` + `langgraph` — for operators who want to compose agents
    with the community ecosystem on top of the built-ins.
  - **AirLLM with a 405B default** (`meta-llama/Llama-3.1-405B`) —
    AirLLM was literally designed around this case ("8 GB VRAM runs
    405B"). Frontier open-weight inference on whatever hardware you
    happen to have.
  - Hardware-specific extras (MLX, CUDA, or CPU) install automatically
    based on what `./arail setup` detects.
- **Good for**: real experiments, frontier models, the full kitchen sink.

> **Heads up — Llama is gated.** Both 70B and 405B require accepting the
> Hugging Face license and authenticating with `huggingface-cli login` (or
> `HF_TOKEN`). Setup leaves the weights download to you — the model
> registry is several hundred GB and you should pick when to pay that bill.

---

## 3. Run `./arail setup`

```bash
./arail setup
```

This walks you through 10 steps:

1. Detect your platform (macOS / Linux / WSL2) and accelerator (MLX / CUDA / CPU).
2. Install OS packages if needed (brew, apt, dnf, pacman, emerge).
3. Create a Python venv and install deps **for the tier you pick**.
4. Name your lab. Default is *Autoresearch AI Lab* — rename to taste.
5. Pick a passphrase (protects the in-browser IDE and notebook encryption).
6. Write `.env` with your choices.
7. Scaffold the knowledge base directory.
8. Download a starter model (~5 GB for Qwen3-8B).
9. Capture a research goal.
10. Verify with a smoke test.

Everything is idempotent — re-run any time without fear.

---

## 4. Start the lab

```bash
./arail start
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). You're in.

---

## 5. Upgrade later

When you're ready for more:

```bash
./arail upgrade max     # bumps AirLLM default 70B → 405B + adds notebook/cloud orchestration extras
./arail restart         # pick up the new nav
```

`./arail upgrade min` is a downgrade — it doesn't uninstall packages, it
just hides the extra tabs. Hit `upgrade max` any time to get them back.

---

## 6. Connect an outside model (Chat → Manage providers)

The Chat tab is where every operator — `min` or `max` — configures outside
model vendors.

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

`./arail restart` and every banner, title, log line, and wiki landing page
now says "Sam's AI Lab".

---

## 8. Troubleshooting

```bash
./arail doctor          # end-to-end validation
./arail status          # what's running, on which ports
./arail logs            # live activity tail
./arail reset help      # ways to wipe state if something went very wrong
```

See [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common first-run gotchas.

---

## 9. The `qkz` alias

If typing `./arail` gets old, there's a symlink at `./qkz` that does the same
thing. Or alias it in your shell:

```bash
alias qkz='./arail'     # then: qkz setup, qkz start, qkz restart
```

Happy researching.
