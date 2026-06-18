# ARCHITECTURE — World `model_hint` (READ + SUGGEST + 2B default-floor)

**Sprint:** 2026-06-14-world-model-hint
**Repo:** arail-verify (ARAIL) · branch `qukaizen/arail-world-model-hint`
**Mode:** DESIGN deliverable (owner reviews before build, given cross-repo + license gates)
**Author:** architect persona
**Inputs:** `VISION.md`; `src/arail/world_mount.py`; `src/arail/chat/__init__.py`;
`src/arail/portal/app.py`; `src/arail/chat/models_catalog.yaml`; `scripts/setup.sh`.

This document is precise enough to implement with **zero new decisions**. Where a
choice exists, it is made here and justified. Everything is labelled **BUILT-on**
(mirrors an existing, merged pattern) or **ROADMAP** (explicitly out of this sprint).

---

## 0. Scope & standing constraints

- **ARAIL repo ONLY.** ARAIL *reads* `model_hint`; the `qukaizen-dac` session
  *emits* it. ARAIL must not import DaC. The wire format (§1) is the contract DaC
  implements — defined here because ARAIL is the consumer and the consumer pins
  the shape it will tolerate.
- **Additive, seal-exempt, graceful.** `model.json` is NOT in the sealed
  manifest. Its absence, malformation, or unknown content **must never fail or
  block a mount**. This mirrors `capabilities.json` exactly (`world_mount.py`
  `_resolve_and_write_capabilities`, lines 684–731).
- **Portable-file boundary (Standing Rule 3).** The hint crosses the
  DaC→ARAIL boundary as one portable JSON file with a versioned schema string.
- **Suggest, never force.** No silent auto-download. No silent auto-switch.
  Every model fetch is consent-gated; every switch is one explicit tap and is
  reversible.
- **Two ship-gates are real, not footnotes:** (G1) the `qukaizen-dac` cross-repo
  handoff (the `model.json` field + the `qkz-project-aware-2b` artifact), and
  (G2) the **"Built with Gemma" disclosure**. The READ+SUGGEST path ships
  *independently* of both via the off-ramp in §10.

---

## 1. The `model_hint` bundle field — home + schema  *(CONTRACT for DaC)*

### 1.1 Decision: a NEW seal-exempt sibling file `model.json`

**Home:** `<bundle_dir>/model.json`, a new optional sibling, schema
`dac.world-model/v1`.

**Rejected alternatives:**
- *Stuff into `face.json`* — `face.json` is identity/branding text that may
  parameterize prompts through the Buddy WORLD FRAMING block (`world_mount.py`
  security-boundary docstring, lines 11–18). A model id is operational config,
  not framing text; mixing them widens the prompt-injection surface and couples
  an optional operational hint to a file that participates in slug-consistency
  checks. Reject.
- *Stuff into `manifest.json`* — `manifest.json` is the **sealed** root
  (it carries `world_sha256` + `files{}` and drives `verify_seal`). Adding a hint
  there would either make the hint seal-bound (violates "seal-exempt, additive,
  graceful absence") or require carving an exemption inside the sealed file.
  Reject.
- *Extend `capabilities.json`* — different concern (host capabilities vs.
  recommended brain) with a different registry resolver. Overloading it couples
  two independent roadmaps. Reject.

**Why a dedicated sibling wins:** it is the *exact* shape of the merged
`capabilities.json` precedent — a seal-EXEMPT, OPTIONAL sibling resolved
best-effort to a DATA_DIR sidecar on mount. It inherits the entire
graceful-absence + graceful-malformation contract for free, and it keeps the
hint legible and independently versioned. This is the cleanest mirror; **recommend it.**

### 1.2 Schema `dac.world-model/v1`

```jsonc
{
  "schema": "dac.world-model/v1",        // REQUIRED. Exact string. Unknown → treat as absent (logged).
  "recommended": {                        // REQUIRED object.
    "id": "qkz-project-aware-2b",         // REQUIRED. An ollama model:tag OR a catalog `id`.
                                          //   Resolution maps this to a catalog entry by exact `id` match.
    "family": "gemma",                    // OPTIONAL advisory (catalog is source of truth when matched).
    "size_gb": 1.6,                       // OPTIONAL advisory display only (catalog wins when matched).
    "good_at": ["physics", "math", "reasoning"],  // OPTIONAL advisory chips.
    "rationale": "Tuned for physics derivations; far stronger than a 1B on technical domains."
                                          // OPTIONAL human string. CAP 280 chars on read. DATA, never prompt-injected.
  },
  "fallback": [                           // OPTIONAL ordered chain of alternative ids (same id semantics).
    "gemma3:4b",
    "qwen3:4b"
  ]
}
```

**Field rules ARAIL enforces on read (defensive, since DaC is a separate repo):**
- `schema` missing or != `"dac.world-model/v1"` → **treat the whole file as absent**
  (resolution state `none`, log at WARNING). Forward-compat: a future `…/v2`
  is ignored gracefully, never errors.
- `recommended.id` missing/empty/non-string → `none` + logged.
- `id` is validated against a conservative allowlist regex
  **`^[A-Za-z0-9][A-Za-z0-9._:/-]{0,128}$`** before any catalog lookup. This is
  a defense-in-depth guard: the id is only ever compared against catalog `id`s
  and rendered as text — it is **never** shell-interpolated by ARAIL (install is
  user-initiated through the existing picker path). A failing id → `none` + logged.
- `rationale` truncated to 280 chars; it is DATA (rendered in a template-escaped
  banner) and must NEVER enter a model prompt — same boundary as `terms.json`.
- `fallback[]` entries each validated by the same id regex; invalid entries
  dropped silently; the chain is advisory and only consulted if `recommended`
  resolves to `recommended_unknown` (see §2.2).
- Everything OPTIONAL except `schema` + `recommended.id`. A World without
  `model.json` behaves **exactly as today**.

> **CONTRACT NOTE for the qukaizen-dac session:** emit `model.json` as a sibling,
> do NOT list it in `manifest.files{}` (keeping it seal-exempt). `recommended.id`
> SHOULD equal the catalog `id` of the target (`qkz-project-aware-2b` for the
> Physics World). If you emit a raw `ollama model:tag` that is not a catalog `id`,
> ARAIL resolves it to `recommended_unknown` (advisory-only; no one-tap install).
> The clean path is: catalog `id`.

---

## 2. ARAIL read + resolve (mount path)  *(BUILT-on the capabilities precedent)*

### 2.1 Decision: a NEW dedicated sidecar `world-model.json`

Mirror `world-capabilities.json` rather than extending it. Rationale: same as
§1.1 — independent concern, independent lifecycle, independent reader. Reusing
the capabilities sidecar would force two resolvers to share one payload and one
corruption-blast-radius. A dedicated sidecar keeps `current_capabilities()`
untouched and gives us a symmetric `current_model_hint()` reader.

**New constants / paths** (in `world_mount.py`):
```python
MODEL_SIDECAR_NAME = "world-model.json"          # in DATA_DIR, alongside world-capabilities.json
# bundle sibling read from: <bundle_dir>/model.json
```

### 2.2 Resolution states (mirror capabilities `available` / `declared_unavailable`)

Resolution runs at mount/swap time and persists the result to the sidecar. The
state is computed by joining `recommended.id` against the live catalog
(`arail.chat.load_catalog()`) and the live installed set
(`arail.chat.detect_installed_models()`):

| State | Condition | UI consequence |
|---|---|---|
| `recommended_installed` | id matches a catalog entry AND id ∈ installed ids | one-tap **switch** (no download) |
| `recommended_available` | id matches a catalog entry, NOT installed | consent-gated **install + switch** (size shown) |
| `recommended_unknown` | id present + valid, but NOT in catalog (after also trying `fallback[]`) | **advisory only** — show rationale, no one-tap action |
| `none` | no `model.json`, or malformed, or `recommended.id` invalid | nothing rendered (today's behavior) |

`fallback[]` handling: if `recommended` is `recommended_unknown`, walk
`fallback[]` in order; the first entry that resolves to
`recommended_installed`/`recommended_available` is promoted to the surfaced
suggestion (recording `promoted_from_fallback: true`). If none resolve, the
state stays `recommended_unknown` against the original `recommended.id`.

> **Catalog/installed coupling caveat (flag for builder & QA):** resolution reads
> the catalog (cheap, file) and the installed set (network calls to Ollama/MLX with
> 1.5s timeouts, `chat/__init__.py`). Per the capabilities precedent this runs
> best-effort inside mount and **must never block or fail the mount**. To keep
> mount latency bounded and robust, resolution stores the **raw recommendation +
> a catalog-only resolution** at mount time, and re-derives the live
> installed/available distinction at **read time** in the portal (§3.2). I.e. the
> sidecar records "what the World wants + whether it's a known catalog model";
> the volatile "is it installed right now" check happens on the gallery request,
> not on the mount hot-path. This avoids a hung Ollama slowing a mount and avoids
> a stale "available" persisting after the user installs the model.

### 2.3 Sidecar payload (`DATA_DIR/world-model.json`)

```jsonc
{
  "world": "physics",
  "resolved_at": "2026-06-15T12:00:00+00:00",
  "recommended": {                        // normalized + validated copy of bundle model.json.recommended
    "id": "qkz-project-aware-2b",
    "family": "gemma",
    "size_gb": 1.6,
    "good_at": ["physics", "math"],
    "rationale": "…(≤280 chars)…"
  },
  "fallback": ["gemma3:4b", "qwen3:4b"],
  "catalog_state": "in_catalog",          // in_catalog | not_in_catalog  (cheap mount-time check ONLY)
  "model_hint_error": null                // string when malformed; mirrors capabilities_error
}
```

The volatile `installed` distinction is NOT stored here (see §2.2 caveat).

### 2.4 New functions in `world_mount.py` (mirroring the capabilities trio)

```python
def current_model_hint(data_dir: Path | None = None) -> Optional[Dict[str, Any]]:
    """Read DATA_DIR/world-model.json. Mirrors current_capabilities():
    returns the dict or None if absent/unreadable. Never raises."""

def _resolve_and_write_model_hint(bundle_dir: Path, slug: str, data_dir: Path) -> None:
    """Best-effort: read bundle_dir/model.json (seal-exempt, OPTIONAL),
    validate schema+id, do the CHEAP catalog-membership check, persist sidecar
    atomically (temp + os.replace). Any failure → logged, NEVER fails mount.
    Three cases mirror capabilities: absent (no sidecar written OR sidecar with
    recommended=None), malformed (model_hint_error recorded), valid."""

def _remove_model_hint_sidecar(data_dir: Path) -> None:
    """Unlink DATA_DIR/world-model.json. Mirrors _remove_capabilities_sidecar."""
```

> **Absent-file decision:** when `model.json` is absent, write NO sidecar (cheaper
> + cleaner than a null sidecar), matching the "absent → none" path. `unmount`
> still calls `_remove_model_hint_sidecar` unconditionally (idempotent
> `unlink(missing_ok=True)`).

### 2.5 Wiring into the existing mount lifecycle

Three call sites, each guarded by `try/except` that only logs (never raises),
**after** the pointer is written — identical placement to the capabilities calls:

- `mount()` — add `_resolve_and_write_model_hint(bundle_dir, bundle.slug, dd)`
  immediately after the existing `_resolve_and_write_capabilities(...)` block
  (`world_mount.py` ~lines 874–878).
- `swap()` — same, after the capabilities call (~lines 966–970).
- `unmount()` — add `_remove_model_hint_sidecar(dd)` immediately after the
  existing `_remove_capabilities_sidecar(dd)` (~line 901).

No change to `verify_seal`, `_BUNDLE_FILES`, `check_compat`, `check_categories`,
`load_bundle`, or `MountRecord` — `model.json` stays entirely outside the sealed,
gated path.

---

## 3. Suggest, don't force — the wedge UX  *(BUILT-on the chat gallery seam)*

### 3.1 Where it renders — decision: the **Chat tab Compute Source / model picker**, via the gallery payload

Grounded seam: the chat page builds a `gallery` payload at
`portal/app.py` ~line 7078 from `arail.chat.gallery_view()`; the front-end stores
it as `State.gallery` (`chat.html` ~line 3464) and renders the model picker
(`#model-picker`, `chat.html` ~lines 1505, 2174–2179, 3012). This is the
**existing model picker** the VISION requires ("through the existing chat model
picker"). It is the right surface because the suggestion is *about which model
generates words* — the exact thing this picker controls — and it is where the
user already goes to switch models.

**Rejected:** a dashboard toast or a mount-time modal. A modal at mount time
would (a) block/interrupt the mount-celebration moment and (b) risk reading as
"forced". A dismissible banner co-located with the picker keeps the user in
control and in context. (A *non-blocking* mount toast that merely deep-links to
the picker banner is acceptable polish but is **ROADMAP**, not required for the
wedge.)

### 3.2 Payload extension — additive field on the gallery view

Extend `arail.chat.gallery_view()` to attach a `model_hint` block, computed by
joining the sidecar recommendation against the *live* installed set already
computed in that function (so the volatile install state is fresh — §2.2 caveat):

```python
# in gallery_view(), after installed_ids is known:
from arail.world_mount import current_model_hint
hint = current_model_hint()                  # None if no World / no hint
model_hint_block = _resolve_hint_for_gallery(hint, installed_ids, catalog_by_id)
# returns None, or:
# { "state": "recommended_installed" | "recommended_available" | "recommended_unknown",
#   "id": "...", "name": "...", "size_gb": 1.6, "good_at": [...],
#   "rationale": "...", "world": "physics",
#   "catalog_entry": {...} | None,           # for one-tap install/switch wiring
#   "promoted_from_fallback": false }
return { "installed": ..., "catalog": ..., "runtime_counts": ..., "model_hint": model_hint_block }
```

`_resolve_hint_for_gallery` lives in `arail/chat/__init__.py` (it needs the
catalog + installed set already in scope there). It is pure + total (returns
`None` on any inconsistency). The existing `gallery_view()` error-fallback dict
(`app.py` ~7081) gains `"model_hint": None`.

### 3.3 Front-end banner (in `chat.html`)

When `State.gallery.model_hint` is non-null, render a **dismissible banner**
anchored above the picker:

- **`recommended_installed`** — *"This World recommends **{name}** for {good_at} — switch?"*
  → primary button **Switch** triggers the **existing** COMPUTE_SOURCE/active-model
  selection path (the same code a manual pick of an installed model runs — no new
  switch mechanism). Secondary: **Dismiss**.
- **`recommended_available`** — *"This World recommends **{name}** ({size_gb} GB) for {good_at} — install & switch?"*
  → primary **Install ~{size_gb} GB** runs the **existing** consent-gated install
  path the gallery already uses for "available" catalog cards (pull → then switch).
  Size is always shown (VISION win-condition 2). Secondary: **Dismiss**.
- **`recommended_unknown`** — *"This World recommends `{id}` ({rationale}). It isn't
  in your catalog — pick it manually if you have it."* Advisory only; **no**
  action button; **Dismiss** only.

`rationale` is rendered through the template's standard HTML-escaping (it is DATA).

### 3.4 Dismissal semantics (respect user choice — VISION win-condition 4 / risk 3)

- Dismiss is **per-mount, client-side**, keyed by `world` slug +
  `recommended.id` in `localStorage` (e.g. `arail.modelHintDismissed.<world>.<id>`).
  Once dismissed for that (world,id), the banner does not re-appear for that
  mount. A *new* World (different slug) or a *changed* recommendation re-surfaces.
- The suggestion is **never sticky-override**: if the user has already selected a
  model (manually or previously), the banner is informational and the current
  model is unchanged until they tap **Switch**. ARAIL never changes the active
  model as a side effect of mount.

### 3.5 Airgapped grace (VISION failure mode)

`recommended_available` in `LAB_MODE=airgapped`: the **Install** action depends on
the install path's existing airgapped posture. For an **Ollama pull** (the
`qkz-project-aware-2b` / local-model case) the pull is from the local Ollama
daemon's registry and is the *same* action a manual gallery install runs — so the
banner uses exactly that path and inherits its behavior. If that path is
unavailable offline, the banner degrades to advisory text: *"Recommended model
**{name}** isn't installed and the lab is airgapped — install it when you're
online, then switch."* No queue is built this sprint (ROADMAP); we **inform**, we
never silently fail or block.

---

## 4. Default-generalist swap — the floor  *(SPLIT: ARAIL-side BUILT, weights ROADMAP/external)*

### 4.1 The hard external dependency (flag — do NOT assume weights exist)

The `qkz-project-aware-2b` (Gemma 2B) **weights + its Ollama Modelfile live in the
parallel `qukaizen-dac`/other session.** This ARAIL change DEPENDS on that landing.
**Do not assume the artifact exists.** Until it lands and is reachable by
`ollama pull`/`ollama create`, the default **stays `llama-ai-eng`** (the safe
interim, §4.4).

### 4.2 Catalog entry (ARAIL-side, BUILT — but tier-gated to interim)

Add one row to `models_catalog.yaml`, ordered at the top (recommended models
first, per the file's ordering comment), as the new default-generalist:

```yaml
- id: qkz-project-aware-2b
  name: Project-Aware 2B
  family: gemma
  size_gb: 1.6                 # advisory; align to the actual artifact when it lands
  released: 2026-06
  source: ollama
  good_at: [chat, reasoning, generalist, math]
  description: "Generalist assistant — built with Gemma (Gemma-2-2B class).
               ARAIL's default local brain: stronger floor than a 1B on
               technical domains, still fits 16 GB. Built with Gemma."
  install: "ollama pull <gemma-2b-handle>  # then: ollama create qkz-project-aware-2b -f models/ai-eng/Modelfile.gemma"
  tier: recommended
```

> The `install` handle + the `Modelfile.gemma` name are **placeholders pinned by
> the DaC handoff** (G1). The catalog row may land *ahead* of the weights as a
> browse-able entry, but it must NOT be wired as the setup default until §4.3's
> gate is satisfied. Until then `llama-ai-eng` remains `tier: recommended` and the
> de-facto default; the Gemma row can sit as `tier: optional` if the owner wants
> it visible-but-not-default in the interim.

### 4.3 `scripts/setup.sh` default-install swap (ARAIL-side, BUILT behind a gate)

Today the minimalist default path (`setup.sh` lines 938–953) does
`ollama pull llama3.2:1b` → `ollama create llama-ai-eng -f Modelfile.default`,
and idempotency checks the ai-eng family (lines 803–814).

The swap, gated on the artifact existing:
1. Introduce `MODEL_NAME` default = `qkz-project-aware-2b` (parallel to the
   existing `AEROLLM_MODEL_ID` etc. block, and overridable from
   `pyproject.toml [tool.arail.models]` via `load_pyproject_metadata`).
2. The default install path pulls the Gemma handle → `ollama create
   qkz-project-aware-2b -f models/ai-eng/Modelfile.gemma`, with the **identical
   `_arail_timeout` + idempotency + offline-fallback ladder** the Llama path uses.
3. **Interim safety (REQUIRED):** if the Gemma handle is still a placeholder
   (sentinel, mirroring `__TODO_DEEP_MODEL__`), the default install path
   **falls back to the existing `llama-ai-eng` Llama path unchanged** and logs a
   one-line notice. A fresh clone is never left with no model. This is the
   `AIRLLM_MODEL_ID="__TODO_DEEP_MODEL__"` sentinel pattern (`setup.sh` lines 86–88)
   applied to the default model.
4. The `ollama_default_enabled()` gating (lines 47–62) is unaffected — Gemma is
   still an Ollama model, so minimalist still needs Ollama. Do NOT revert that.

### 4.4 Safe interim summary

| Artifact state | Setup default | Catalog |
|---|---|---|
| Gemma handle = sentinel (not landed) | `llama-ai-eng` (unchanged) | Gemma row present as `optional` (browse-only) |
| Gemma handle pinned + reachable + **disclosure done (G2)** | `qkz-project-aware-2b` | Gemma row `recommended`, top of list |

The swap flips **only** when both the artifact is reachable AND the §5 disclosure
gate is green.

---

## 5. Gemma "Built with Gemma" disclosure — SHIP-GATE (G2)

Parallel to the Llama exception (CLAUDE.md "Llama disclosure exception";
`licenses/LLAMA-3.2-COMMUNITY-LICENSE.txt`, `LLAMA-3.2-ACCEPTABLE-USE-POLICY.txt`;
`NOTICE`; "Built with Llama" in README/catalog/persona). The Gemma default
introduces Gemma Terms of Use obligations. **This is a ship-blocker on §4.3, not
a footnote.**

**Disclosure checklist (all REQUIRED before the default swap lands):**
1. **Name convention** — the model id begins with / clearly carries the base
   lineage. `qkz-project-aware-2b`'s catalog name + description MUST state
   **"Built with Gemma"** (the Llama rule's "name begins with base" is satisfied
   in spirit by an explicit, prominent "Built with Gemma" since the QuKaiZen
   product name is the persona wrapper — match whatever the Gemma Terms require;
   if Gemma Terms mandate a name prefix, prefix it). **Pin the exact requirement
   from the Gemma Terms during build — do not guess.**
2. **In-app attribution** — "Built with Gemma" shown wherever "Built with Llama"
   is shown today: README tier table, `models_catalog.yaml` description (already in
   §4.2), and the persona system prompt in `models/ai-eng/Modelfile.gemma`.
3. **License/AUP bundled** — add the **Gemma Terms of Use** and the
   **Gemma Prohibited Use Policy** to `licenses/` (parallel to the two Llama files),
   and reference them from `NOTICE`.
4. **Distribution-of-terms** — if Gemma Terms require passing the Terms to
   downstream recipients (they do for Gemma), ensure the bundled copy + NOTICE
   reference satisfies it for ARAIL's "blueprint you fork" distribution model.
5. **No hide-the-base** — unlike the Apache-2.0 Qwen deep lineage (which CLAUDE.md
   permits hiding), Gemma's terms REQUIRE disclosure. Treat Gemma like Llama: base
   is disclosed, never hidden.

> **The QA gate (per arail product gating, "security 20% / setup 30%"):** the
> disclosure checklist is verified as a test artifact (§9, T7). If any item is
> unmet, the default swap **does not ship**; the wedge falls back to
> mounted-hint-READ-only (§10 off-ramp), which carries no new license obligation.

---

## 6. Failure modes / grace (consolidated)

| Condition | Behavior | Mechanism |
|---|---|---|
| `model.json` absent | exactly today; no banner | no sidecar; `current_model_hint()→None` |
| `model.json` malformed / bad schema | exactly today; logged WARNING; no banner | `model_hint_error` recorded, `recommended=None` |
| `recommended.id` not in catalog | advisory banner, no one-tap (after fallback tried) | state `recommended_unknown` |
| recommended model not installed | consent-gated install+switch, size shown | state `recommended_available` |
| airgapped + not installed | advisory "install when online", never blocks | §3.5 |
| user already chose a model | current model unchanged; banner is suggestion only | §3.4; ARAIL never auto-switches |
| user dismissed | banner suppressed for that (world,id) for the mount | localStorage key §3.4 |
| Ollama hung / unreachable during resolve | mount unaffected; install-state derived at read with 1.5s timeout | §2.2 caveat; resolution is best-effort |
| **Mount itself** | **NEVER fails on any of the above** | all hint logic is post-pointer, try/except-logged |

---

## 7. Cross-repo contract — explicit deliverable (G1)

**What the `qukaizen-dac` session must implement (ARAIL designs, does not edit):**
1. Emit `<bundle_dir>/model.json` conforming to `dac.world-model/v1` (§1.2).
2. Do NOT add `model.json` to `manifest.files{}` (keep it seal-exempt).
3. Prefer `recommended.id` == a catalog `id` (clean one-tap path); a raw
   `ollama model:tag` degrades to advisory-only on the ARAIL side.
4. Ship the `qkz-project-aware-2b` weights + an Ollama Modelfile such that
   `ollama pull <handle> && ollama create qkz-project-aware-2b -f Modelfile.gemma`
   succeeds, and hand ARAIL the **exact pull handle + Modelfile** for §4.2/§4.3.
5. Provide the precise **Gemma Terms + Prohibited Use Policy** text/links for §5.

**Handoff is coordinated in `SPRINT.md`.** ARAIL's READ side + the fixture-based
tests (§9/§10) proceed *now*, independent of DaC timing.

---

## 8. Build order (numbered) with the pre-Gemma off-ramp

**Phase A — READ + SUGGEST (ships independently; no external dependency):**
1. `world_mount.py`: add `MODEL_SIDECAR_NAME`, `current_model_hint()`,
   `_resolve_and_write_model_hint()`, `_remove_model_hint_sidecar()` (mirror the
   capabilities trio). Wire into `mount`/`swap`/`unmount` (§2.5). Pure + best-effort.
2. `chat/__init__.py`: add `_resolve_hint_for_gallery()`; extend `gallery_view()`
   to attach `model_hint` (§3.2). Add `"model_hint": None` to the `app.py` fallback dict.
3. `chat.html`: render the dismissible banner above the picker; wire **Switch** to
   the existing active-model selection path and **Install** to the existing
   consent-gated gallery install path; dismissal localStorage (§3.3–3.4).
4. Vendor a **fixture WorldBundle** carrying a valid `model.json` (a
   `recommended_available` and a `recommended_installed` variant) under the test
   tree for end-to-end verification *without DaC*.
5. Tests T1–T6 (§9).

> **OFF-RAMP:** after Phase A, the wedge's central hypothesis (a World declares its
> brain; one tap improves the answer) is fully testable against the fixture bundle,
> with **zero** dependency on the Gemma artifact or the disclosure. Phase A is a
> shippable increment.

**Phase B — DEFAULT-FLOOR swap (gated on G1 artifact + G2 disclosure):**
6. `models_catalog.yaml`: add the `qkz-project-aware-2b` row (§4.2), initially
   `optional` (browse-only) until the gate is green.
7. `licenses/` + `NOTICE` + README + `Modelfile.gemma`: complete the **Gemma
   disclosure checklist** (§5). **Gate G2.**
8. `scripts/setup.sh`: introduce `MODEL_NAME`, swap the default install path with
   the **sentinel-fallback to `llama-ai-eng`** (§4.3). **Gate G1** (real handle).
9. Flip the Gemma row to `tier: recommended`, top of list.
10. Tests T7–T9 (§9).

Phase B lands only when both gates are green; otherwise the product ships Phase A
plus the unchanged `llama-ai-eng` default.

---

## 9. Test strategy (arail QA allocation: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression)

Tests live alongside existing `world_mount` / `chat` tests. The fixture bundle
(build step 4) is the spine.

| # | Type | Test |
|---|---|---|
| T1 | regression | Mount a bundle with **no** `model.json` → mount succeeds, no sidecar written, `current_model_hint()→None`, gallery `model_hint` is `None`. (Proves "behaves exactly as today.") |
| T2 | security/edge | `model.json` with bad schema / missing `recommended.id` / `id` failing the regex / oversized `rationale` → mount succeeds, `model_hint_error` recorded, no crash, `rationale` capped, no banner. |
| T3 | happy | `recommended_installed` fixture → gallery `model_hint.state == recommended_installed`; banner offers Switch; Switch uses the existing select path (no new switch code reachable). |
| T4 | setup/happy | `recommended_available` fixture → state correct; size_gb surfaced; **no auto-download occurs** (assert the install path is only invoked on explicit action). |
| T5 | edge | `recommended_unknown` (+ `fallback` that does/doesn't resolve) → advisory-only; fallback promotion logic (`promoted_from_fallback`) correct. |
| T6 | regression | `unmount` removes `world-model.json`; `swap` re-resolves to the new World's hint; dismissal is per-(world,id). |
| T7 | security (G2) | **Disclosure gate:** assert `licenses/` contains Gemma Terms + Prohibited Use Policy, `NOTICE` references them, catalog description + README + Modelfile carry "Built with Gemma". This test **must pass before the default swap ships.** |
| T8 | setup (G1) | With Gemma handle = sentinel, `setup.sh` default path falls back to `llama-ai-eng` (fresh clone never model-less). With handle pinned, default installs `qkz-project-aware-2b`. (Drive via the non-interactive setup harness / a unit around the model-select branch.) |
| T9 | regression | `ollama_default_enabled()` unchanged: minimalist on Apple Silicon still installs the default (no F1 regression). |

Security focus (the 20%): the `id`/`fallback`/`rationale` validation (T2) and the
disclosure gate (T7) are the load-bearing security/license tests — `model_hint` is
attacker-influenced data crossing a repo boundary onto someone else's machine.

---

## 10. Summary for the owner (the five asks)

- **`model.json` schema + home:** new seal-exempt sibling `<bundle_dir>/model.json`,
  schema `dac.world-model/v1` (§1). Cleanest mirror of `capabilities.json`;
  rejected face/manifest/capabilities homes with reasons.
- **Sidecar + resolution:** new dedicated `DATA_DIR/world-model.json` + a
  `current_model_hint()` reader mirroring the capabilities trio; four states
  (`recommended_installed`/`recommended_available`/`recommended_unknown`/`none`);
  volatile install-state derived at read time so a hung Ollama never slows a mount
  (§2).
- **Suggest-UX seam:** the **existing chat model picker**, via an additive
  `model_hint` block on the `gallery_view()` payload (`app.py` ~7078 → `chat.html`
  `State.gallery`), rendered as a **dismissible, per-mount banner** with one-tap
  Switch (installed) / consent-gated Install+Switch (available, size shown) /
  advisory (unknown). No silent download, no silent switch, never blocks (§3).
- **Default-swap plan + external dependency + disclosure gate:** catalog row +
  `setup.sh` `MODEL_NAME` swap with a **sentinel-fallback to `llama-ai-eng`** until
  the **`qkz-project-aware-2b` weights land from `qukaizen-dac` (G1)**; the swap is
  **blocked on the "Built with Gemma" disclosure checklist (G2)** — Gemma Terms +
  Prohibited Use Policy bundled in `licenses/`, NOTICE + README + Modelfile
  attribution (§4–§5).
- **Build order + pre-Gemma off-ramp:** Phase A (READ+SUGGEST) ships and is fully
  tested against a vendored fixture bundle with **zero** dependency on the Gemma
  artifact or disclosure; Phase B (default floor) lands only when both gates are
  green (§8).
