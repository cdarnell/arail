# Arail Troubleshooting

First-run bumps and their fixes. Runs top-to-bottom in rough order of
how often they hit first-timers. If the answer isn't here, check the
setup log at `setup.log` (created by `./arail setup`, kept next to the
repo root) and open an issue with the last 30 lines.

## `./arail setup` didn't prompt me for a passphrase

Your shell is non-interactive. Most common causes:

- Running via a pipe: `curl ... | bash`, `cat answers | ./arail setup`.
- IDE task runner without a PTY (some VS Code tasks, CI agents).
- An old `.env` from a pre-unified-password release that already has
  `ARAIL_PASSWORD=` set.

Fix — re-run from a real terminal:

```bash
./arail setup
```

Force interactive even when stdin looks piped:

```bash
ARAIL_NONINTERACTIVE=0 ./arail setup < /dev/tty
```

Rotate a passphrase that's already set — the prompt now asks whether
to keep or rotate it; answer `new`.

## Dashboard won't open / "connection refused" on :8080

Port 8080 is already in use by something else.

```bash
# macOS / Linux
lsof -iTCP:8080 -sTCP:LISTEN -P -n

# Change the port, then restart
# Edit lab.conf and set PORTAL_PORT=8090 (or whatever's free)
./arail restart
```

## IDE at :8443 rejects my passphrase

The passphrase in `.env` diverged from `lab.conf` (usually from an
older setup run that only wrote one of the two). `./arail setup` now
resyncs them automatically via its `validate_env` step — re-run:

```bash
./arail setup
```

When it asks about the existing passphrase, answer `new` if you want
to rotate, or accept the default to keep it. Both files will match
when setup finishes.

## `pip install` fails on Python 3.13

Arail tests against Python 3.10-3.12. Install 3.11 via your platform's
package manager, nuke the venv, and re-run:

```bash
# macOS
brew install python@3.11

# Ubuntu / Debian
sudo apt install python3.11 python3.11-venv

# Then
rm -rf .venv
./arail setup
```

## Apple Silicon: MLX install fails

Update Xcode command-line tools — MLX wheels need a recent clang:

```bash
xcode-select --install
```

Then retry `./arail setup`. If you're on macOS 12 (Monterey) or older,
MLX isn't available — use `MODEL_BACKEND=cpu` instead.

## WSL: `nvidia-smi` works but CUDA install fails

You installed the Linux Nvidia driver inside WSL. Remove it — WSL gets
CUDA through the Windows-side driver only, projected in via `/dev/dxg`:

```bash
# Inside WSL
sudo apt purge 'nvidia-*'
sudo apt autoremove

# On Windows (PowerShell)
# Install the Nvidia Game Ready / Studio driver from nvidia.com.
# Version >= 525.x is required.
```

Restart WSL (`wsl --shutdown` from PowerShell) and retry.

## WSL1 instead of WSL2

Arail needs WSL2. Check your version:

```powershell
# PowerShell
wsl -l -v
```

If the `VERSION` column says `1`, upgrade:

```powershell
wsl --set-version Ubuntu 2
```

## Model download stalls at 0%

Hugging Face rate-limits anonymous downloads. Either wait and retry, or
authenticate:

```bash
# Get a read-only token at https://huggingface.co/settings/tokens
# Add to .env:
echo "HUGGING_FACE_HUB_TOKEN=hf_xxxxxxxxxx" >> .env

# Re-run the model step only
ARAIL_SKIP_MODEL_DOWNLOAD=0 ./arail setup
```

Skip the download entirely and bring your own model later:

```bash
ARAIL_SKIP_MODEL_DOWNLOAD=1 ./arail setup
```

## `ollama pull qwen3:8b` is taking forever

It's a ~5 GB download. Skip it and pull later:

```bash
ARAIL_SKIP_OLLAMA=1 ./arail setup
# then, when you're ready:
ollama pull qwen3:8b
```

## Setup finished but `./arail doctor` says something's missing

`doctor` imports the Python package and checks that optional binaries
(ttyd, code-server, jupyter) are on PATH. Re-run setup — it's
idempotent — or install the missing binary manually per your platform:

```bash
# macOS
brew install ttyd jupyter

# Ubuntu
sudo apt install ttyd
pip install jupyter
```

## I want to start over from scratch

```bash
./arail reset full     # nukes lab/, .venv, .env, lab.conf
./arail setup
```

For only specific state:

```bash
./arail reset models   # remove downloaded models only
./arail reset data     # remove PKB + experiments, keep models + env
./arail reset env      # reset .env + lab.conf, keep everything else
```

## Running on a locked-down school computer (no sudo, no admin)

A `--user-only` mode is on the roadmap. Meanwhile:

- Install Python 3.11 via `pyenv` (no root needed) or have IT install it.
- Set `ARAIL_SKIP_OLLAMA=1` so setup doesn't try to `brew install ollama`.
- Skip `ttyd` and `code-server` — the dashboard, knowledge base, and
  researcher all run without them. Use your system terminal and any
  text editor for the parts that need it.
- `MODEL_BACKEND=cpu` works on any hardware without root.

Open an issue if you hit a specific blocker — school deployment is a
priority and every report shapes the roadmap.
