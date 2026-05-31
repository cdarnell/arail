# CLAUDE.md — ARAIL

> Orientation file for Claude sessions working on this repo. Read this
> first; it's the fastest way to ground yourself in what ARAIL is, how
> it relates to the sibling repos, and what the conventions are. The
> human-facing entry point is `README.md`; the platform-porting manifest
> for external coding agents is `AGENTS.md` (different intent).

## What ARAIL is, in one paragraph

ARAIL — Autoresearch AI Labs — is a local-first AI research lab
blueprint. Clone the repo, run `./arailctl setup && ./arailctl start`, pick a
tier, and you have a dashboard, a chat tab with a Compute Source pivot
(local MLX/CUDA/llama.cpp or any cloud vendor), an autoresearch loop
that runs experiments while you're away, an agent-driven knowledge base
backed by LanceDB, and three built-in agents (Buddy, SRE, Researcher).
Default mode is `airgapped`; flip to `hybrid` and cloud providers
become fallbacks. ARAIL is positioned as a blueprint, not a product:
users are expected to fork, rename, and adapt.

## Where ARAIL sits in this workspace

ARAIL is the umbrella project. Two sibling repos in `~/ProJects` hang
off it:

- **aerollm** (`~/ProJects/aerollm`) — Streaming inference runtime, a
  product of ARAIL. Origin lives here in `research/aerollm/` (00 through
  04 design docs) before it was extracted to its own repo. As of v1.0.0,
  AeroLLM is the deep-mode backend for the `maximus` tier. CUDA hosts
  fall back to AirLLM with a notice until AeroLLM's CUDA backend ships.
  The README's Compute Source pivot in the Chat tab is the surface where
  alternative backends slot in. See `aerollm/CLAUDE.md` for runtime
  internals.
- **qukaizen-nucleus** (`~/ProJects/qukaizen-nucleus`) — Nucleus, the
  Super Skill Distillation Pipeline. Independent today (its own pipeline, its own
  CLI also called `qkz`), but a planned future consumer of aeroLLM for
  teacher inference. The shared `qkz` name is convergent: in this repo
  `./qkz` is symlinked to `./arailctl` as a shorthand alias; in qukaizen
  `qkz` is a Rust CLI binary. They're not the same program.

ARAIL is where the user's research **happens** — the lab. aeroLLM is
the inference substrate the lab will run on. qukaizen is a separate
research effort that also needs that substrate.

## Two tiers, two surfaces, one CLI

The product is intentionally simple at the entry point. Two tiers
(renamed in v1.0.0 — legacy `min`/`max` env values are still accepted
with a deprecation warning for one release):

| Tier         | What's in it                                                                                                                 |
|--------------|------------------------------------------------------------------------------------------------------------------------------|
| `minimalist` | Dashboard · Chat · Autoresearch · Knowledge Base · Agents · LanceDB vectors · **ai-eng** (1.5B-parameter Opus-4.7-derived AI engineering expert from QuKaiZen's Nucleus pipeline) — the everyday lab |
| `maximus`    | + Admin · Docs · Notebooks · **AeroLLM** deep-mode runtime · Anthropic SDK · LangChain · full cloud SDKs — the full local bench, cloud frontier one click away |

Tier upgrade is a single `./arailctl upgrade maximus` away; downgrade
likewise. Knowledge Base and Agents are part of `minimalist`
deliberately — research without memory is a non-starter.

**v1.0.0 default model:** `ai-eng` is the only model that auto-installs
during setup. Setup pulls the self-hosted ai-eng GGUF (HuggingFace primary
via `ollama pull hf.co/...`, GitHub Release mirror as fallback) with digest
verification; falls back to a preview base until the GGUF is uploaded. The
chat catalog (`src/arail/chat/models_catalog.yaml`) keeps ~20 other models
as a browse-and-pull gallery — nothing else ships pre-installed. AirLLM is
opt-in via `ARAIL_INSTALL_AIRLLM=1`.

The CLI is `./arailctl` (also reachable via `./qkz`). The main verbs:

- `./arailctl setup` — pick a tier, install deps, download a starter model.
- `./arailctl start` — open `http://127.0.0.1:8080`.
- `./arailctl upgrade {minimalist|maximus}` — change tier.
- `./arailctl pkb ingest <file>` — push a doc into the LanceDB-backed KB.
- `./arailctl benchmark_models` (alias `aerollm`) — local model benchmark.

`scripts/setup.sh` is the platform-porting surface. `AGENTS.md` is the
manifest for external coding agents that want to add a new platform
branch.

## The five surfaces in the portal

`src/arail/portal/` is the Flask app that renders the lab. The five
surfaces a user sees are described in `README.md` § "The main surfaces"
and (more deeply) `docs/agents-explained.md`:

1. **Dashboard** — what the agents are doing, current goal, simulated
   cloud cost, activity stream.
2. **Chat** — Compute Source pivot (My Machine / Claude / NIM /
   OpenRouter / HF / Custom endpoint); ⚙ Manage providers modal for
   key save / test / list / remove. Tokens persist to
   `lab/data/secrets.env` `chmod 0600`, git-ignored, never echoed back.
3. **Autoresearch** — measurable-goal experiment loop; the Researcher
   agent is the engine.
4. **Knowledge Base** — LanceDB vector index over papers, notes,
   uploaded PDFs.
5. **Agents** — Buddy (lab partner), SRE (crash watcher), Researcher
   (autoresearch engine). User-defined agents drop into
   `lab/pkb/agents/<id>/` with `AGENT.md` + `<id>.py`.

`max` adds **Admin** (system health, plugin manager, diagnostics) and
**Docs** (curated operator docs rendered inside the lab).

## Repo layout (orientation)

The top of the tree is dense; the parts that matter:

| Path                          | What's there                                                                       |
|-------------------------------|------------------------------------------------------------------------------------|
| `arail` (file)                | Main shell entry point — `./arailctl setup`, `./arailctl start`, etc.                    |
| `qkz` → `arail` (symlink)     | Shorthand alias                                                                    |
| `scripts/setup.sh`            | Platform-detect → service install → model download. `AGENTS.md` is the porting doc |
| `src/arail/`                  | Python package (portal app, agents, knowledge base, pipelines)                     |
| `src/arail/portal/`           | Flask app + templates (dashboard, chat, agents, knowledge, tuning, research)       |
| `lab/`                        | Runtime state — `lab/pkb/` is the agent-facing knowledge base, `lab/data/` is secrets, `lab/models/` is downloaded weights. All git-ignored except contracts |
| `blueprints/`                 | Four reference blueprints: `autoresearch`, `client-followup`, `inbox-triager`, `status-digest` |
| `core/knowledge-canvas/`      | The Knowledge Canvas frontend (TS/React)                                           |
| `compose/open-notebook/`      | Surreal-backed notebook integration (the surrealdb log file in git history is from here) |
| `research/aerollm/`           | **Five-doc design study where aeroLLM started.** Read these to understand aeroLLM's origin: `00-product-vision.md`, `01-pipeline-map.md`, `02-batching-strategy.md`, `03-parallel-work.md`, `04-measurement-log.md` |
| `research/speculative-decoding/` | Spec-decode research (now realised in `aerollm-speculative`)                    |
| `examples/peanut_farmer/`     | A canonical "PeanutLab" example of forking + renaming the lab                      |
| `docs/`                       | INSTALL, MACOS, LINUX, WSL, PRIVACY, TROUBLESHOOTING, agents architecture          |
| `BLUEPRINTS.md`               | How this repo thinks of itself as a blueprint, not a product                       |
| `ROADMAP.md`                  | Forward plan                                                                       |
| `design.md`                   | Design philosophy; complements README                                              |
| `pyproject.toml`              | Python package metadata. Internal package name stays `arail`; only the display rebrands |

## Current state

114 commits, latest 2026-04-28. Recent work has been on the portal
experience (Chat Studio rebuild, Knowledge Canvas iframe loading, live
checks modal, design system rollout) plus the cross-repo workflow
(branch names like `cdarnell/qukaizen/suspicious-napier-54a283` show
that there's tooling that auto-generates qukaizen-style branches even
in this repo). The `arailctl benchmark_models` CLI was added recently as
the local benchmarking entry point — useful when comparing AirLLM (today)
against aeroLLM (when it lands).

The code is more mature than aeroLLM's (it predates the extraction);
treat the portal and the agent loader as stable surfaces, the
autoresearch loop and the knowledge-base ingest paths as the moving
parts.

## Conventions worth knowing

- **License: MIT.** (Different from aeroLLM's Apache-2.0.)
- **Local-first by default.** `LAB_MODE=airgapped` blocks every cloud
  provider. The Compute Source row in Chat shows a banner; the
  save/test/models endpoints refuse. `LAB_MODE=hybrid` opens the door.
  Don't relax this default.
- **Internal package name stays `arail`.** Display name (LAB_NAME,
  LAB_TAGLINE) is rebrand-able via `.env`. Imports must not break when
  someone calls their lab "PeanutLab".
- **Compute Source pivot is the integration seam.** When aeroLLM lands
  HTTP bindings, it slots in as a new Compute Source option — same UX,
  no UI changes. Don't bake AirLLM into the surface; bake "local
  inference backend" with AirLLM as one implementation.
- **Tokens to `lab/data/secrets.env` `chmod 0600`, git-ignored, never
  echoed back, never logged.** This rule shows up in the README; it
  shows up in the code; treat any drift from it as a bug.
- **Agent loader contract.** New agents go in
  `lab/pkb/agents/<id>/AGENT.md` + `lab/pkb/agents/<id>/<id>.py`. The
  loader discovers them on start. Don't shortcut by editing the
  built-in agents.
- **`.gitignore` is comprehensive** (`models/`, `lab/models/`,
  `node_modules/`, `__pycache__/`, runtime state under `lab/pkb/`).
  The 47M `.git/` history bloat is from a single 42M PDF and
  accidentally-committed `node_modules/` before the ignore rules
  caught them; current state is clean. Don't try to clean history
  without coordinating — the user has decided to leave it.
- **The `qkz` symlink** in this repo points at `./arailctl`. It is **not**
  the qukaizen-nucleus Rust CLI; that lives in `~/ProJects/qukaizen-nucleus/qkz/`.
  Don't confuse the two.

## Where to start when you pick a task

1. **Skim this file**, then `README.md`, then `BLUEPRINTS.md` and
   `design.md` for philosophy.
2. **For a portal change**: `src/arail/portal/app.py` is the Flask
   entry; templates in `src/arail/portal/templates/`; static assets
   in `src/arail/portal/static/`.
3. **For an agent change**: `docs/agents.md` has the loader contract.
   `lab/pkb/agents/<id>/` is where agents live. The three built-ins
   (Buddy, SRE, Researcher) are reference implementations.
4. **For setup / port work**: `scripts/setup.sh` is the only file you
   need to touch. `AGENTS.md` walks an external agent through what each
   `case` statement does and what to add.
5. **For aeroLLM context**: `research/aerollm/00-product-vision.md`
   through `04-measurement-log.md` are the design docs. The actual
   runtime is `~/ProJects/aerollm`.
6. **Knowledge Base ingest**: easiest path is the portal —
   `/knowledge` has folder-reveal buttons (`lab/pkb/inbox` for docs,
   `lab/models` for model weights), full-page drag-drop, and a
   per-file post-upload toast with `[Open]` / `[Reveal]` links. CLI
   equivalent is `./arailctl pkb ingest <file>`. Wiki + embedded graph
   auto-refresh on a "Wiki rebuilt" SSE event from
   `wiki.schedule_rebuild()`; the reveal endpoint is
   `POST /api/system/reveal` with whitelisted slots
   (`inbox`/`models`/`pkb_root`/`sources`/`compiled`). LanceDB
   index lives at `lab/pkb/.wiki-cache/lancedb/`.

## Files to read first

In rough priority order:

- `README.md` — user-facing project orientation; tier descriptions; surfaces.
- `BLUEPRINTS.md` — philosophy: ARAIL is a blueprint, not a product.
- `design.md` — design choices (3 KB, dense).
- `docs/agents.md` — agent architecture and loader contract.
- `AGENTS.md` — external-agent porting manifest. (Different from
  Claude-onboarding; keep separate.)
- `research/aerollm/README.md` — the bridge to the aeroLLM repo.
- `ROADMAP.md` — forward plan; check before proposing significant changes.

## What this file is not

This is a Claude-orientation doc. `AGENTS.md` is the *external coding
agent* porting manifest — different audience, different scope. The
README is for users. CLAUDE.md is for me.
