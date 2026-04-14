# Contributing to OGLab

Thanks for being here. OGLab is a blueprint, not a product — it's meant to be forked, vibe-integrated, and re-shaped for your own platform. Contributions that strengthen the blueprint itself are welcome.

## Design principles

Read these before sending a PR. If your change fights one of them, we'll probably push back.

1. **Local-first by default.** Everything works with no network. Cloud backends are opt-in, behind `OGLAB_MODE=hybrid`, behind per-domain consent.
2. **Platform-neutral code, platform-specific setup.** The Python code never asks what OS it's on. The accelerator class (`MLX` / `CUDA` / `CPU` / etc.) is selected by one env var. Platform differences live in `scripts/setup.sh`.
3. **No external agent frameworks.** The researcher, curator, and consent store are ~800 lines of stdlib Python. LangChain, LangGraph, AutoGen, CrewAI, etc. bring cloud-first assumptions and heavy abstractions that don't fit the blueprint. If you want multi-agent orchestration, write it as a new `oglab.agents.<name>` module that consumes `ModelRouter` the same way `ResearcherAgent` does.
4. **One class per accelerator.** The router ([src/oglab/router/backends.py](src/oglab/router/backends.py)) has one backend per hardware/API family. New cloud APIs that speak OpenAI's `/v1/chat/completions` protocol should reuse `OpenAICompatBackend` with a different `MODEL_API_BASE`, not get their own class.
5. **No speculative abstractions.** Three similar lines is better than a premature helper. Don't add config for hypothetical future requirements.
6. **No features that can't be explained in a paragraph.** If your change needs a wiki page to justify, it's probably not a fit.

## Development loop

```bash
git clone <your-fork>
cd oglab
./oglab setup    # creates .venv, installs deps, generates OGLAB_PASSWORD
./oglab start    # launches portal, terminal, notebook, IDE
```

Edit code, reload the portal (uvicorn auto-reloads if you run it directly), iterate. When you're done:

```bash
./oglab doctor        # import + smoke test
python -m pytest      # if you added tests (there aren't many yet — help wanted)
```

## Pull request checklist

- [ ] The change fits one of the design principles above.
- [ ] No new secrets, API keys, or absolute local paths in tracked files.
- [ ] No new unauthenticated mutating endpoints on the portal.
- [ ] `./oglab doctor` passes on your machine.
- [ ] If you touched `scripts/setup.sh`, you ran it on a clean checkout and it completed without prompting for anything it shouldn't.
- [ ] If you added a new env var, it's documented in `.env.example`.
- [ ] If you added a dependency, it's justified in the PR description (we prefer stdlib).
- [ ] The commit message explains the *why*, not just the *what*. We use conventional prefixes (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`) loosely.

## Reporting security issues

See [SECURITY.md](SECURITY.md). **Do not** open a public issue for security reports.

## Code of conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Short version: be kind, assume good faith, don't be a jerk.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE) that covers the project.
