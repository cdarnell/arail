# Shipped Worlds (the catalog)

Every directory in here is a sealed **`dac.world-bundle/v1`** — the objective
knowledge dataset a lab studies: terms, categories, an association graph, and
a matching look. Whatever lives in this folder *is* the World catalog: the
portal's picker, the welcome flow, and `./arailctl world list` all scan it
directly.

## Provenance — where these come from

The default bundles (`ai`, `qukaizen`) are authored and sealed upstream in the
sibling **qukaizen-dac** repo — the offline curation press — and their exported
bytes are **vendored into this repo and committed to git**.

That means the coupling is by vendoring, not by fetching:

- **Single-repo install, guaranteed.** Downloading ARAIL gives you every World
  dependency. qukaizen-dac is dev-time only — it is never fetched, never a
  submodule, never imported at runtime.
- **Airgapped-friendly by construction.** An airgapped lab's fundamental
  domain terms come from these in-box bundles; the research material is
  whatever you drop into the Knowledge Base.

| Bundle | Display name | Terms | Provenance tier | Source |
|--------|--------------|-------|-----------------|--------|
| `ai` | AI & Machine Learning | 331 | sourced | qukaizen-dac export |
| `qukaizen` | QuKaiZen | 32 | sourced | qukaizen-dac export |

Three more example bundles live in `examples/worlds/` (same format, same
provenance) — import them from the Worlds page when you want them.

## Integrity

Each bundle's `manifest.json` pins a sha256 for the six sealed files
(`terms/spec/roster/face/agenda/drift-report`) plus a `world_sha256` over
`terms.json`. Verify anytime:

```bash
./arailctl world verify-shipped            # the catalog
./arailctl world verify-shipped --examples # + examples/worlds/
```

Setup runs this automatically (step 11) and the portal re-checks at startup —
both shout, neither bricks the lab: a broken bundle is simply omitted from the
picker until restored.

## Editing rules

- **Never hand-edit the six sealed files** — that breaks the seal and the
  bundle refuses to mount. Restore with `git checkout -- lab/worlds/<slug>`.
- Term edits made **through the portal** are fine — they re-seal properly via
  `world_forge.reseal_bundle`.
- Official upstream updates arrive as whole-bundle replacements from the
  qukaizen-dac export pipeline; this README lives outside the bundle dirs so
  re-exports never conflict with it.
- Worlds you forge in-lab are sealed by ARAIL's own `world_forge` and need no
  upstream at all.

> Naming note: new user-facing copy standardizes on **"Documentation as Code
> (DaC)"** (as the shipped `qukaizen` World defines it). qukaizen-dac's own
> CLAUDE.md still says "Declarative-as-Code" — reconcile upstream at the next
> reseal.
