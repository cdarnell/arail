# AGENTS.md — Vibe App Integration manifest

This file tells an AI coding agent everything it needs to **port Autoresearch
AI Lab (ARAIL) to a new platform, package manager, or shell** without reading
the whole codebase. If you're a human trying to do the same port by hand,
[docs/LINUX.md](docs/LINUX.md) is the long-form version.

> Looking for the *user-facing* agents (Pip, SRE, Researcher)? See the
> README's "Agents" section or [docs/agents.md](docs/agents.md).

The goal: a user on a distro we don't support yet can hand their
agent this file + `scripts/setup.sh` + one sentence ("port this to
Fedora") and get a working setup with the same UX our blessed paths
have.

## What ARAIL is, in two sentences

A local-first AI lab blueprint. Users clone the repo, run
`./arail setup && ./arail start`, pick a tier (min / med / max), and
get a dashboard + chat + autoresearch running on their own hardware
with their own models.

## The three entry points a port must implement

Every platform port lives in **one file**: [scripts/setup.sh](scripts/setup.sh).
You extend three `case` statements, nothing else.

### 1. Platform detection — `detect_platform()` (setup.sh:33)

Add a branch that sets two variables based on what's available:

- `PLATFORM` — freeform identifier (`fedora`, `arch`, `nixos`, …).
- `ACCEL` — one of `mlx`, `cuda`, `cpu` (fallback).

Example — adding Fedora:

```bash
elif [[ -f /etc/fedora-release ]]; then
    PLATFORM="fedora"
    # Same GPU detection as the generic Linux branch
```

### 2. System packages — `install_services()` (setup.sh:134)

Four binaries setup tries to install. Each has a per-platform branch.
Port the package-manager calls, preserving the `tail -3` log trimming
and the `command -v X &>/dev/null` idempotency guards:

| Binary | Why we install it | Notes |
|---|---|---|
| `ttyd` | Browser terminal at `/terminal` | Optional — portal shows install help if missing |
| `tmux` | Persistence across iframe reloads | Optional — scrollback loss if missing |
| `ollama` | Local LLM server on port 11434 | Optional — `ARAIL_SKIP_OLLAMA=1` to skip |
| `agent-browser` | Web research agent | npm global — same on every platform |

Fedora example:

```bash
fedora)
    if command -v dnf &>/dev/null; then
        info "Installing ttyd via dnf…"
        sudo dnf install -y ttyd 2>&1 | tail -3 || warn "ttyd install failed."
    fi
    ;;
```

### 3. Accelerator deps — `install_accel_deps()` (setup.sh:110)

Three branches today (`mlx`, `cuda`, `cpu`). Only port this if your
platform introduces a genuinely new accelerator (ROCm, Habana, etc.).
Most Linux distros fall back to `cuda` or `cpu` and need no change.

## Contract the port must preserve

1. **Idempotent.** Re-running `./arail setup` on a half-finished run
   must pick up cleanly. Every install step checks `command -v X`
   first. Never fail hard on an optional binary — `warn` and continue.
2. **Numbered banners.** Every major section prints
   `step "N/10  Title"` at the top. Don't add more sections than
   we have — extend within the existing 10 checkpoints.
3. **No sudo without warning.** If your branch needs root, say so
   via `info` before the `sudo` call. Don't silently prompt in the
   middle of a 90-second pip install where the prompt gets lost.
4. **No `error` for optional deps.** If ttyd fails to install, the
   portal's terminal tab shows install help and the rest of the lab
   still works. Only hard-fail on Python, pip, and the venv creation.
5. **Logs go to `setup.log`.** Redirect verbose pkg-manager output
   with `2>>"$log"` and print the last 20 lines on failure via
   `tail -n 20 "$log" | sed 's/^/    /' >&2`.

## How to test a port

```bash
# Fresh VM of your target distro
git clone https://github.com/cdarnell/autoresearch-lab.git arail
cd arail

# Non-interactive mode confirms the whole pipeline works without human input
ARAIL_NONINTERACTIVE=1 ./arail setup

# Environment validator — catches stale .env, missing keys, passphrase drift
./arail doctor

# End-to-end — portal should come up with agents running
./arail start

# Visit http://127.0.0.1:8080 — type a goal, click Run Research,
# confirm the research activity log lights up.
```

Done means all five steps succeed on a fresh VM with no manual
intervention. If you had to `apt install X` before `./arail setup`
worked, add `X` to `install_services()` so the next user doesn't.

## Files your port should NOT touch

- `src/arail/` — the Python code has no OS-specific branches. It
  shouldn't grow any.
- `compose/*.yml` — Docker overlays are platform-neutral.
- `.env.example` — `./arail setup` writes values at runtime; don't
  hardcode platform-specific defaults here.
- `lab.conf` — regenerated on every setup.

## When to write a new doc vs. extend setup.sh

- **Extending setup.sh** is the right call for 95% of ports.
- **Write a `docs/<PLATFORM>.md`** only when your platform needs
  prerequisites that can't be auto-installed (kernel flags, BIOS
  settings, proprietary driver downloads). See
   [docs/LINUX.md](docs/LINUX.md) for the template.

## Pull-request checklist for a port

- [ ] `detect_platform` has a branch that sets `PLATFORM` and `ACCEL`.
- [ ] `install_services` has a branch for each of ttyd, tmux, ollama.
- [ ] `ARAIL_NONINTERACTIVE=1 ./arail setup` completes on a fresh VM.
- [ ] `./arail doctor` returns OK.
- [ ] `./arail start` launches, dashboard reaches `/` without errors.
- [ ] `README.md` Platform Support table has a row for your distro.
- [ ] If the port needs a pre-requisite the script can't auto-install,
      `docs/<YOUR_PLATFORM>.md` documents it.

## For humans reading this

If you're not an AI agent and you got here by accident: this manifest
is what we hand to coding agents (Claude, Cursor, etc.) when asking
them to port ARAIL to new platforms. You can use it the same way —
point your favorite LLM at `scripts/setup.sh` and this file, ask it
to add a Fedora branch, and it'll give you a working patch in one
shot. That's the "vibe integrate" flow.

See [docs/vibe-integrate.md](docs/vibe-integrate.md) for the prompt
template.
