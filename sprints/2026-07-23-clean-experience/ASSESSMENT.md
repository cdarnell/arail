# ARAIL Platform Assessment — 2026-07-23

**How this was produced:** a nine-dimension read-only multi-agent sweep of this repo
(model-building, DaC/KB/agents data flow, auto-checks, onboarding UX, portal surfaces,
docs drift, security posture, agent runtime quality, autoresearch loop), followed by a
synthesis pass that spot-verified the highest-stakes claims against source before writing.
Raw per-dimension reports live in [`reports/`](reports/); the merged critique is
[`reports/synthesis.md`](reports/synthesis.md). Every file:line anchor cited below was
verified on disk at commit time. Owner decisions taken from this assessment are recorded
in `SPRINT.md`; the remediation spec is `ARCHITECTURE.md`.

## Executive verdict

ARAIL is two products wearing one skin. Underneath is a genuinely thoughtful local-first
scaffold — a fail-closed knowledge gate that actually holds (`src/arail/compiled_kb.py`),
honest planning-trace provenance (`researcher.py:1208-1246`), crash-resumable research
runs, airgapped-by-default egress enforcement that is load-bearing and correct, and a
fully token-migrated design system. On top sits a marketing-grade surface that repeatedly
promises more than the code delivers. The gap between those two layers is precisely where
the owner "feels something is missing."

### 1. Model building is unmet and actively obscured (the owner's flagship desire)

Five mutually-conflated "model" surfaces, only one automated:

1. The default "AI Engineer" (`llama-ai-eng`) is a two-line system-prompt wrap over
   `llama3.2:1b` — built by setup, not model building.
2. The `/build` tab — the only surface saying "Build, distill, and register models" — is a
   thin HTTP client hard-depending on the separate `qukaizen-nucleus` repo (orchestrator
   :8000, synthesizer :8005, trainer :8006) which ARAIL's setup never installs; a fresh
   clone shows "nucleus down" and 502s (`build_api.py:163-169`).
3. The World-corpus path can train but emits **no seal** (`build_api.py:377-381`), and
   compaction does not exist anywhere in `src/` — the bake→seal→compact `RETAIN` stage is
   paper (see `sprints/2026-07-22-distill-now/VISION.md`).
4. The one genuine distillation pipeline (`scripts/build_ai_eng.sh`) is CLI-only, dormant
   behind placeholder HF repos, and never surfaced in the portal.
5. `/tuning` is inference-throughput tuning of a ≥1TB model — not weight training — one
   nav-click away with no explainer.

Artifacts scatter across 5+ locations (Ollama store, `lab/models/`, repo `build/`,
`models/graduated/`, the sibling nucleus configs tree) with no user-facing doc; and
`docs/build-and-finetune-plan.md` (37KB) describes a model subsystem (`src/arail/models/`,
`src/arail/jobs/`, `scripts/arail-model`) that does not exist on disk.

### 2. Research output is theater presented as substance

The Researcher's "experiments" are timed `asyncio.sleep` loops (`researcher.py:923-965`);
analysis asks the LLM to invent a metrics JSON, and with no model emits identical
hardcoded constants — `improvement_rate 0.15 / confidence_score 0.72 / data_points 24 /
success=True` — for every experiment (`researcher.py:1325-1331`, confirmed on disk), then
writes them into the KB and report as if measured, with no "simulated" label. For a
platform whose purpose is to teach research hygiene, this is the single worst violation
of "educate the user."

### 3. The KB/DaC layer is the strongest part — buttoned up only for Tier-1

One human-gated write path (`/api/pkb/promote` is the sole `compiled_kb.approve` caller),
sha256 drift discipline, terms-as-data-never-prompted, sealed/verified World bundles.
But: the entire documented Tier-2 "user understanding" fact store (fact distillation,
`recall_user_facts`, `lab/pkb/understanding/`) has **zero implementation**; conversation
`meta.json` titles leak into the ungated searchable index (`pkb.py:376,391-404`);
`ARAIL_CONVERSATIONS_DIR` can silently defeat wipe-PKB-wipes-memory
(`chat/conversations.py:43-48` vs `reset.sh:202`); and the egress-consent story is
decorative — Buddy silently puts the user's private goal text into a live HuggingFace URL
query in hybrid mode (`_builtin_buddy.py:948-951`, confirmed), and `browser.py` claims
"consent-gated" but never consults the consent store.

### 4. Boot friction is real and precisely diagnosed

The shell start path is clean; the FastAPI startup event is not: a synchronous LLM
subprocess with a 60s timeout (`app.py:888`), a potentially heavy LanceDB rebuild
(`app.py:992`), and a Neo4j connect (`app.py:813`) all run before first byte. At runtime
the model-registry health thread re-probes Ollama every 60s emitting "MODEL TIER DOWN"
with **no off-switch** (`registry/health.py:254-269`), and `/api/admin/components` shells
out to `pip list` on every Admin page load, ungated (`app.py:4754-4853`). Silencing what
can be silenced requires ~7 env vars; three offenders have no gate at all.

### 5. "Inviting for friends and family" is undercut by disconnected onboarding

The polished 3-step welcome wizard is dead on the main path (CLI setup satisfies its
gate); the dashboard "read this first" banner points at a stale runbook; the single most
important first action has five different names across surfaces (no "Run Research" button
exists); and the default first goal a non-expert accepts by pressing Enter is an
expert-hostile AirLLM-70B KV-cache sweep about a backend that isn't installed. On the
hand-off front: the dashboard has no authentication at all post-onboarding, the plugin
installer git-clones + pip-installs arbitrary repos ungated, tier is nav-visibility rather
than an access boundary, and the passphrase is written world-readable and embedded in the
Marimo iframe URL.

### 6. Docs drift ahead of the code

CLAUDE.md self-reports 114 commits / 2026-04-28 (real: 644 / 2026-07-22) and omits
Worlds/DaC entirely; Docs-tier is wrong in README/CLAUDE/INSTALL; `.env.example`
advertises a default model that never shipped; legacy `min/med/max` naming survives in six
files; `standards-compliance.md` anchors are ~2,500 lines stale. (Bright spot: the Llama
disclosure chain is fully compliant, and the Gemma gate is correctly dormant.)

## The through-line

ARAIL has built the hard, honest primitives (gate, trace, airgap, resume) but wrapped
them in aspirational copy, dead-on-arrival flows, and unlabeled simulation. The owner
senses something missing because the platform *claims* to be an intuitive model-building
playground while the model-building lives in another repo, the research is fabricated,
and the friendly wizard never runs. Buttoning up means making the surface tell the truth
and closing the last mile on the primitives that already work — which is exactly what
this sprint's ARCHITECTURE.md does.
