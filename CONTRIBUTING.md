---
title: Contributing to Arail
category: Reference
order: 95
tags:
  - contributing
  - reference
  - community
audience: architect
related:
  - BLUEPRINTS
  - SECURITY
---
# Contributing to Arail

Thanks for being here. Arail is a blueprint, not a product — it's meant to be forked, vibe-integrated, and re-shaped for your own platform. Contributions that strengthen the blueprint itself are welcome.

## Design principles

Read these before sending a PR. If your change fights one of them, we'll probably push back.

1. **Local-first by default.** Everything works with no network. Cloud backends are opt-in, behind `ARAIL_MODE=hybrid`, behind per-domain consent.
2. **Platform-neutral code, platform-specific setup.** The Python code never asks what OS it's on. The accelerator class (`MLX` / `CUDA` / `CPU` / etc.) is selected by one env var. Platform differences live in `scripts/setup.sh`.
3. **No external agent frameworks.** The researcher, curator, and consent store are ~800 lines of stdlib Python. LangChain, LangGraph, AutoGen, CrewAI, etc. bring cloud-first assumptions and heavy abstractions that don't fit the blueprint. If you want multi-agent orchestration, write it as a new `arail.agents.<name>` module that consumes `ModelRouter` the same way `ResearcherAgent` does.
4. **One class per accelerator.** The router ([src/arail/router/backends.py](src/arail/router/backends.py)) has one backend per hardware/API family. New cloud APIs that speak OpenAI's `/v1/chat/completions` protocol should reuse `OpenAICompatBackend` with a different `MODEL_API_BASE`, not get their own class.
5. **No speculative abstractions.** Three similar lines is better than a premature helper. Don't add config for hypothetical future requirements.
6. **No features that can't be explained in a paragraph.** If your change needs a wiki page to justify, it's probably not a fit.
7. **Package metadata lives in `pyproject.toml`.** Dependency versions, optional extras, and package install sources belong there. `scripts/setup.sh` may choose which extras to install, but it should not become a second source of truth for package specs.

## Your docstrings become wiki pages

Arail's wiki compiler ([src/arail/docgen.py](src/arail/docgen.py)) scans the repo on every rebuild and turns each Python module, shell script, compose overlay, and guide into a page under `lab/pkb/compiled/docs/`. The page content comes from:

- **Python** — the module-level docstring + each public class/function's docstring, extracted via `ast` (no runtime import, so optional deps don't block the scan).
- **Shell** — the header comment block + `usage()` body + top-level function names.
- **Compose YAML** — first comment block + service/image/ports summary.
- **Guides** — copied verbatim if frontmatter exists, enriched if it doesn't.

So **any time you add or change a Python module, shell script, or compose overlay, write the docstring/header comment first**. It lands in the wiki automatically the next time someone clicks Rebuild on `/wiki` or runs `./arailctl wiki build`. Good docs become discoverable without any extra curation work. See [docs/wiki.md](docs/wiki.md) for the wiki user guide.

## Development loop

```bash
git clone <your-fork>
cd arail
./arailctl setup    # creates .venv, installs deps, generates ARAIL_PASSWORD
./arailctl start    # launches portal, terminal, notebook, IDE
```

Edit code, reload the portal (uvicorn auto-reloads if you run it directly), iterate. When you're done:

```bash
./arailctl doctor        # import + smoke test
python -m pytest      # if you added tests (there aren't many yet — help wanted)
```

## Pull request checklist

- [ ] The change fits one of the design principles above.
- [ ] No new secrets, API keys, or absolute local paths in tracked files.
- [ ] No new unauthenticated mutating endpoints on the portal.
- [ ] `./arailctl doctor` passes on your machine.
- [ ] If you touched `scripts/setup.sh`, you ran it on a clean checkout and it completed without prompting for anything it shouldn't.
- [ ] If you added a new env var, it's documented in `.env.example`.
- [ ] If you added or changed a dependency, `pyproject.toml` is the source of truth and the PR explains why it belongs.
- [ ] The commit message explains the *why*, not just the *what*. We use conventional prefixes (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`) loosely.

## Porting to new distros

Arail's "vibe integrate" flow lets you hand the blueprint to a coding
agent and get a port for a new platform in one shot. See
[AGENTS.md](AGENTS.md) for the agent-facing manifest (three entry
points, test recipe, contract to preserve) and [docs/LINUX.md](docs/LINUX.md)
for the long-form guide with Arch and Fedora worked examples.

If you want to upstream a port, the PR checklist is in
[AGENTS.md](AGENTS.md#pull-request-checklist-for-a-port).

## Reporting security issues

See [SECURITY.md](SECURITY.md). **Do not** open a public issue for security reports.

## Code of conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Short version: be kind, assume good faith, don't be a jerk.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE) that covers the project.
