# Autoresearch AI Lab — Blueprint Master Prompt

> This file is the master prompt used to rebrand and restructure this
> repository into a shareable AI research lab blueprint. It's kept in-repo
> so future collaborators (human or agent) can see the intent behind the
> layout.

## Vision

A **simple, massively good blueprint** for friends and family to run their
own AI research lab locally. The default name is **Autoresearch AI Lab
(ARAIL)**, but any operator can rename their instance in one line of
`.env` — e.g. "Sam's AI Lab", "gentoofoo's ai lab", "PeanutLab". It is the
lab that belongs to whoever spins it up.

## Non-negotiables

1. **Educational first.** Every tab explains what is happening in plain
   English. A curious teenager should be able to learn something on day one.
2. **Two tiers — min or max.** Operators pick one and upgrade later. No
   middle-ground "med" to confuse the choice.
3. **Knowledge Base + Agents ship in `min`.** They're how research drives.
4. **Local-first, cloud-optional.** The Chat tab has a one-click pivot
   between "My Machine" and every major cloud vendor. A dedicated **Manage
   providers** modal handles save/test/list-models/remove per-vendor.
5. **Airgapped mode is the default and enforced.** `LAB_MODE=airgapped`
   blocks every cloud provider operation at the API layer — not just the
   UI. Operators flip `LAB_MODE=hybrid` in `.env` (explicit opt-in).
6. **Brand is display-only.** `LAB_NAME` rebrands every surface; internal
   Python identifiers (`arail`) stay stable so imports and tests don't break.
7. **No "OGLab" branding anywhere the operator sees it.** Not in the nav,
   README, CLI banner, activity log, wiki landing, or setup screen.

## Tier matrix

| Surface                             | min                  | max                 |
| ----------------------------------- | -------------------- | ------------------- |
| Dashboard                           | ✅                   | ✅                  |
| Chat (provider pivot + modal)       | ✅                   | ✅                  |
| Autoresearch                        | ✅                   | ✅                  |
| Knowledge Base (markdown + keyword) | ✅                   | ✅                  |
| Agents                              | ✅                   | ✅                  |
| Admin                               | —                    | ✅                  |
| Notebooks                           | —                    | ✅                  |
| LanceDB (semantic KB)               | —                    | ✅                  |
| AirLLM 70B default (Llama-3.1-70B)  | ✅                   | —                   |
| AirLLM 405B default (Llama-3.1-405B)| —                    | ✅                  |
| Anthropic SDK                       | —                    | ✅                  |
| LangChain / LangGraph               | —                    | ✅                  |
| Cloud catalogue (Claude/NVIDIA/…)   | partial (HTTP only)  | full (SDKs)         |

Upgrade with `./arail upgrade max`. Downgrade (`./arail upgrade min`)
only hides the tabs — doesn't uninstall packages.

## Chat provider pivot

The Chat tab shows a **Compute Source** radio row + a **⚙ Manage providers**
button that opens a modal.

Row options: **My Machine** · Claude · NVIDIA NIM · OpenRouter ·
HuggingFace · Custom endpoint.

Modal per provider: save token · test (pings `/models` with the saved key) ·
list models (shows the vendor catalogue) · remove · open vendor docs.

Tokens write to `lab/data/secrets.env` (`chmod 0600`, git-ignored). They
are never echoed back to the UI after saving and never logged.

### Airgapped enforcement

When `LAB_MODE=airgapped` (the default):

- `/api/providers/save` refuses with a friendly error.
- `/api/providers/active` refuses to switch to a cloud source.
- `/api/providers/test` refuses.
- `/api/providers/models` refuses.
- `/api/providers/status` reports `cloud_enabled: false` + an
  `airgapped_notice` string.
- The UI greys out cloud radios, shows a banner, and the modal shows the
  same banner instead of the provider cards.

Operators must explicitly set `LAB_MODE=hybrid` in `.env` and restart.

## Connectivity endpoints

- `GET  /api/providers/status` — lab mode, active provider, per-provider
  token presence, list of providers with labels + docs URLs.
- `POST /api/providers/save` — persist token (and optional endpoint for
  custom). Blocked in airgapped.
- `POST /api/providers/remove` — delete saved token. Works in both modes.
- `POST /api/providers/active` — switch compute source. Airgapped allows
  only `my_machine`.
- `POST /api/providers/test` — ping vendor, report auth status.
- `GET  /api/providers/models?provider=…` — enumerate vendor's catalogue
  (capped at 200 entries). Blocked in airgapped.

## Execution plan carried out

1. Package renamed `oglab` → `arail`. 129 tests pass.
2. CLI moved to `./arail` with `./qkz` symlink.
3. `brand.py` default → "Autoresearch AI Lab", rebrandable via `LAB_NAME`.
4. Two tiers in [pyproject.toml](pyproject.toml): `min`, `max`.
5. `_nav.html` reads `tier_surfaces` from [portal/app.py](src/arail/portal/app.py).
6. `setup.sh capture_tier` prompts two-choice; legacy `med` rolls to `max`.
7. `scripts/upgrade.sh` handles tier switching + persists to `.env`.
8. Chat's **Manage providers** modal + six `/api/providers/*` endpoints.
9. Airgapped mode blocks every cloud provider operation end-to-end.
10. README, INSTALL.md, AGENTS.md, BLUEPRINTS.md updated to match.

If an operator forks this later and wants to evolve it, this file tells the
story of why it looks the way it does.
