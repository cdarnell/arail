# AGENTS.md — Vibe App Integration manifest

This file tells an AI coding agent everything it needs to **port Autoresearch
AI Lab (ARAIL) to a new platform, package manager, or shell** without reading
the whole codebase. If you're a human trying to do the same port by hand,
[docs/LINUX.md](docs/LINUX.md) is the long-form version.

> Looking for the *user-facing* agents (Buddy, SRE, Researcher)? See the
> README's "Agents" section or [docs/agents.md](docs/agents.md).

The goal: a user on a distro we don't support yet can hand their
agent this file + `scripts/setup.sh` + one sentence ("port this to
Fedora") and get a working setup with the same UX our blessed paths
have.

## What ARAIL is, in two sentences

A local-first AI lab blueprint. Users clone the repo, run
`./arailctl setup && ./arailctl start`, pick a tier (minimalist / maximus), and
get a dashboard + chat + autoresearch running on their own hardware
with their own models.

## The four entry points a port must implement

Every platform port lives in **one file**: [scripts/setup.sh](scripts/setup.sh).
You extend four `case` statements, nothing else.

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

### 4. Python bootstrap — `install_python_for_platform()`

When the user's box has no Python 3.10+ on PATH, setup auto-installs
`python@3.11` via the platform package manager rather than telling
the user to come back. Add a branch that installs Python via your
distro's manager, e.g.:

```bash
opensuse)
    check_sudo
    info "Installing python3.11 via zypper…"
    sudo zypper install -y python311 python311-devel >>"$log" 2>&1 \
        || error "zypper install python311 failed — see setup.log."
    ;;
```

After your branch returns, `ensure_python` re-probes PATH for
`python3.12 / python3.11 / python3.10 / python3` and uses the first
one that satisfies `>=3.10`. So your job is simply: install something
in that candidate set.

The same auto-install policy applies to Homebrew (`ensure_brew`, macOS
only) and Node.js (`ensure_node`, agent-browser dependency). Both
honor `ARAIL_NONINTERACTIVE=1` (silent install) and
`ARAIL_AUTO_INSTALL=0` (refuse to install, fall back to old "install
this manually" behavior).

## Contract the port must preserve

1. **Idempotent.** Re-running `./arailctl setup` on a half-finished run
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
git clone https://github.com/qukaizen/arail.git arail
cd arail

# Non-interactive mode confirms the whole pipeline works without human input
ARAIL_NONINTERACTIVE=1 ./arailctl setup

# Environment validator — catches stale .env, missing keys, passphrase drift
./arailctl doctor

# End-to-end — portal should come up with agents running
./arailctl start

# Visit http://127.0.0.1:8080 — open Autoresearch, Set Research Goal, press Run,
# confirm the research activity log lights up.
```

Done means all five steps succeed on a fresh VM with no manual
intervention. If you had to `apt install X` before `./arailctl setup`
worked, add `X` to `install_services()` so the next user doesn't.

## Files your port should NOT touch

- `src/arail/` — the Python code has no OS-specific branches. It
  shouldn't grow any.
- `compose/*.yml` — Docker overlays are platform-neutral.
- `.env.example` — `./arailctl setup` writes values at runtime; don't
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
- [ ] `ARAIL_NONINTERACTIVE=1 ./arailctl setup` completes on a fresh VM.
- [ ] `./arailctl doctor` returns OK.
- [ ] `./arailctl start` launches, dashboard reaches `/` without errors.
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
