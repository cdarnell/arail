# Architecture: DaC World SKILL.md → agent system prompt

**Date:** 2026-06-27
**Spec:** [SPRINT.md](./SPRINT.md) · plan `~/.claude/plans/quizzical-chasing-lovelace.md` · DaC contract qukaizen-dac `docs/adr/0004-dac-arail-mount-contract.md`
**Repo:** arail (Python), branch `qukaizen/arail-world-forge-doc` (see Branch)

## Restatement

DaC now emits a governed, sourced `SKILL.md` inside every WorldBundle (a pure projection of
gated terms — verified by reading `dist/bundles/art-history/SKILL.md` and the
`renderWorldSkill` source in `src/arail-export/skill.ts`). ARAIL's mount path is already fully
built: `mount()` verifies the seal, stages the 6 sealed files to `lab/pkb/sources/world-<slug>/`,
writes the `world-mount.json` pointer, and flips identity live via `effective_identity()`. Buddy
already gets a delimited **WORLD FRAMING** block from `face.json` (`_world_framing_block`), and
the Researcher already reframes intent to `"other"` with the World's `domain_framing`. **The one
remaining gap:** the mounted World's `SKILL.md` — its actual glossary of sourced terms — never
reaches `compose_system_context()`, so the agents adopt the World's *identity* but not its
*knowledge*. This sprint closes that gap: stage `SKILL.md` at mount time and load it into the
composed system prompt for both Buddy and Researcher, treating it as untrusted data on load.

## Assumptions

1. **DaC emits SKILL.md in the exact `skills_loader` shape.** Verified: `art-history/SKILL.md`
   has YAML frontmatter (`id: world-<slug>`, `name`, `domain: <slug>`, `version: "1.0.0"`,
   `when_to_use`/`when_not_to_use` dash lists) parseable by `parse_frontmatter`, and a body
   `strip_frontmatter` cleanly separates. ADR-0004 Decision 4 pins this contract with tests.
2. **SKILL.md is seal-EXEMPT in v1.** Verified: `manifest.files{}` for art-history lists only
   the 6 sealed files; `SKILL.md` is a sibling. `verify_seal` iterates the hardcoded
   `_BUNDLE_FILES` frozenset (`world_mount.py:351`), so a 7th `files{}` entry is silently
   ignored and `_stage_files` copies only the 6. **Therefore ARAIL cannot today detect a
   SKILL.md tampered after DaC emitted it** — this is the central security problem (§Security).
3. **DaC already applies sanitization** (`sanitizeBodyField` / `sanitizeFrontmatterScalar` in
   `skill.ts`): newline-collapse + leading-control-token neutralization. We assume this is
   correct but do NOT trust it on load (defense-in-depth) — a bundle can arrive from any path
   (`world mount <external-dir>`), possibly hand-edited or from an older/forked DaC.
4. **A World provides at most one SKILL.md.** One mounted World ⇒ one world-skill. (Multi-skill
   bundles are out of scope; v1 mounts one World at a time per `current_mount()`.)
5. **Eager loading stays.** `compose_system_context` concatenates all skills every call
   (scoping is Sprint 3). World SKILL.md bodies are small (term glossaries, a few KB) — the
   added prompt cost is acceptable for v1.
6. **face.json framing and SKILL.md are complementary, not duplicative.** face.json gives the
   short *domain framing* (who the lab is); SKILL.md gives the *term-level knowledge* (what it
   knows). Both can appear without redundancy (§Unmount/§Failure: duplicate-vs-framing).
7. **AGENT.md skill lists are author-owned.** We must not rewrite `buddy`/`researcher`
   `AGENT.md` `skills:` lists at mount time (that mutates user-authored, git-tracked PKB and
   risks drift/stale entries on unmount). The world-skill is injected *out of band* of AGENT.md.

## Data flow

```
DaC export-bundle.mts                ARAIL mount path (BUILT, extended here)
─────────────────────                ──────────────────────────────────────
renderWorldSkill()                   mount(bundle_dir)
  → SKILL.md (sanitized,               1. load_bundle + verify_seal + compat + categories
    seal-exempt sibling)               2. _stage_files → lab/pkb/sources/world-<slug>/
        │                                   ├─ copies the 6 SEALED files  (BUILT)
        ▼                                   └─ NEW: copy SKILL.md if present (best-effort)
  dist/bundles/<slug>/SKILL.md        3. _index_staged (best-effort)
        │   (mount/swap)              4. _write_record (world-mount.json pointer)  ← LAST
        └───────────────────────────►5. adopt_into_catalog / capabilities / model sidecars

Agent prompt assembly (per LLM call, hot-reloaded)
──────────────────────────────────────────────────
load_agent_skills("buddy"|"researcher")           AGENT.md skills (observe-lab, …)
        +  NEW: load_world_skill()  ──reads──►  current_mount().staged_dir/SKILL.md
                  │                                │
                  │                                ▼
                  │                         load_skill_from_path()  →  Skill
                  │                                │  body = containment(strip_frontmatter)
                  ▼                                ▼
        compose_system_context([*agent_skills, world_skill])
                  │
                  ▼
   Buddy._compose_prompt  /  Researcher._get_system_context
        base voice/intent + WORLD FRAMING (face) + Procedural knowledge (skills+world)
```

Nothing-mounted: `current_mount()` returns None → `load_world_skill()` returns None → the
skill list is unchanged → agents fall back to the default AI/ML world exactly as today.

## Interface contracts

### Chosen wire — **Option (b): `skills_loader` loads the mounted World's SKILL.md at compose time, plus stage it at mount time.**

Rejected (a) (register `world-<slug>` into AGENT.md `skills:`): mutates user-authored, git-tracked
`AGENT.md`, needs cleanup on unmount/swap (stale-entry risk), and couples the world-skill lifecycle
to file edits rather than the single `current_mount()` switch. Rejected (c) (a separate injection
layer parallel to WORLD FRAMING): duplicates the `compose_system_context` machinery and gives the
local model a *different* container for the same kind of content (procedural knowledge), defeating
the H2-per-skill separation the composer was built for. **Option (b)** reuses the built path with
the least new surface: one mount-time copy + one read keyed off `current_mount()` (the same switch
identity/face/capabilities already read), so unmount/swap behavior is automatic and AGENT.md is
never touched. Staging at mount (rather than reading from `bundle_dir` at compose time) keeps reads
inside the PKB jail and survives an external/unmounted `bundle_dir` moving.

#### `world_mount.py` — extend `_stage_files` (and the staged-file constant)

```python
# New module constant — staged but NOT sealed, NOT in _BUNDLE_FILES.
_WORLD_SKILL_NAME = "SKILL.md"

def _stage_files(bundle: Bundle, pkb_root: Path) -> Path:
    # ... existing copy of the 6 _BUNDLE_FILES into staging_dir ...
    # NEW (additive, best-effort, after the 6-file loop, before the atomic swap):
    src_skill = bundle.bundle_dir / _WORLD_SKILL_NAME
    if src_skill.exists():
        try:
            shutil.copy2(src_skill, staging_dir / _WORLD_SKILL_NAME)
        except Exception as e:
            _log.warning("world_mount: SKILL.md stage failed (continuing): %s", e)
    # ... unchanged atomic .staging → world-<slug> swap ...
```

- **Promises:** if the bundle has a readable `SKILL.md`, the staged dir contains a byte-identical
  copy. If absent or unreadable, mount succeeds unchanged (no SKILL.md staged).
- **Requires:** nothing beyond a parsed `Bundle`. Must NOT be added to `_BUNDLE_FILES` (that
  would make `verify_seal` demand a hash it can't find and break every existing 6-file bundle).
- **Bad input:** unreadable/oversized SKILL.md → logged, skipped; mount proceeds.
- `_adopt_into_catalog` already copies *all* files in the bundle dir (`for f in src.iterdir()`),
  so the adopted catalog copy includes SKILL.md automatically — no change needed there.

#### `skills_loader.py` — two additive functions, plus a containment pass

```python
# Caps — refuse to inject an oversized world-skill (DoS / prompt-bloat guard).
_MAX_WORLD_SKILL_BYTES = 64 * 1024          # whole-file read cap
_MAX_WORLD_SKILL_BODY_CHARS = 24 * 1024     # body cap after strip_frontmatter

def load_skill_from_path(path: Path, skill_id: str) -> Optional[Skill]:
    """Load a Skill from an explicit SKILL.md path (not the skills/ dir).
    Returns None when missing/oversized/unreadable. Applies on-load containment
    to the body (treats SKILL.md as untrusted DATA — see _contain_skill_body)."""

def load_world_skill(pkb_root: Path | None = None,
                     data_dir: Path | None = None) -> Optional[Skill]:
    """Load the mounted World's SKILL.md as a Skill, or None when nothing is
    mounted / no SKILL.md staged. Keyed off current_mount().staged_dir so it
    tracks mount/unmount/swap with no extra state. Never raises."""
```

- **`load_world_skill` promises:** returns a `Skill` whose `id == f"world-{record.world}"`,
  `body` is the contained markdown body, **only** when `current_mount()` is non-None AND
  `<staged_dir>/SKILL.md` exists and is within caps. Otherwise `None`.
- **Requires:** `current_mount()` resolves the live pointer (same call identity already uses).
- **Bad input:** missing → `None` (graceful no-op); oversized → `None` + warning; malformed
  frontmatter → `parse_frontmatter` already returns `{}` and `load_skill` tolerates it, so we
  still get a body-only skill (name falls back to `world-<slug>`); unreadable → `None`.

```python
_BODY_CONTROL_RE = re.compile(r"^([#\->`])")   # mirror skill.ts BODY_CONTROL_RE

def _contain_skill_body(body: str) -> str:
    """Defense-in-depth: re-apply DaC's containment in Python so a SKILL.md
    tampered AFTER DaC emitted it cannot forge prompt structure.
    Per physical line: collapse is unnecessary (we keep line structure for
    readability), but any line whose first non-space char is a markdown control
    token at column 0 that would forge a NEW top-level section (e.g. '# WORLD
    FRAMING', '---' frontmatter fences, or our own '# Procedural knowledge'
    header) is neutralized with a zero-width non-joiner (U+200C) prefix.
    Deterministic; mirrors skill.ts sanitizeBodyField at the line granularity
    ARAIL injects."""
```

  Concretely `_contain_skill_body` must, at minimum: (1) strip any residual `---` YAML fence
  lines (the body should already be frontmatter-free, but a forged second fence is neutralized);
  (2) neutralize a line that exactly forges ARAIL's own structural delimiters
  (`# WORLD FRAMING`, `# END WORLD FRAMING`, `# Procedural knowledge`, `Observation:`,
  `<NAME>'s one-sentence note:`) so a tampered body cannot impersonate the prompt scaffold;
  (3) leave ordinary `### Category` / `- **term**` lines intact (they are the legitimate
  glossary shape and live *under* the skill's own H2, so they cannot escape the section).

#### Buddy — `_builtin_buddy.py::_compose_prompt`

```python
skills = _host.load_agent_skills("buddy")
world_skill = _host_load_world_skill()        # NEW (via host seam, best-effort)
all_skills = skills + ([world_skill] if world_skill else [])
skill_ctx = _host.compose_skill_context(all_skills)
```

- The `BuddyHost` Protocol gains `load_world_skill(self) -> Optional[Any]` with `ArailHost`
  wiring `from arail.skills_loader import load_world_skill` in a try/except (returns None on any
  failure — matches the existing host-method style). The mock host in tests returns None by
  default, so Buddy's existing tests are unaffected.
- **face WORLD FRAMING stays** (`_world_framing_block` unchanged). Order in the prompt:
  base voice → WORLD FRAMING (face: short identity framing) → dream → Procedural knowledge
  (agent skills + world glossary) → Observation. No duplication: framing is the 2-line "who",
  the world-skill is the term glossary "what" — different sections, different content.

#### Researcher — `researcher.py::_get_system_context`

```python
from arail.skills_loader import load_agent_skills, compose_system_context, load_world_skill
skills = load_agent_skills("researcher")
ws = load_world_skill()
if ws: skills = skills + [ws]
skill_ctx = compose_system_context(skills)
```

- Stays inside the existing `try/except → skill_ctx=""` failsoft block, so a loader error never
  breaks research. Researcher already gets the World's `domain_framing` via `effective_identity`
  in the `intent == "other"` base; the world-skill adds the *term glossary* the base lacks.

### Postconditions (acceptance)

With art-history mounted, the string of a known art-history term body (e.g. `Ballets Russes`)
appears in `compose_system_context(...)` for both agents; with nothing mounted, neither agent's
composed context contains a world-skill section and behavior matches today's tests.

## Security decision (seal-exempt SKILL.md)

**v1 posture: defense-in-depth on load NOW (ARAIL-owned) + seal-promotion as the durable
cross-repo follow-up (does not block this sprint).** Rationale: ADR-0004 Decision 2 already
established that promoting `SKILL.md` to `manifest.files{}` is *cosmetic* until ARAIL's
`verify_seal` iterates `files{}` generically — DaC hashing it changes nothing on the consumer
side. ARAIL therefore cannot depend on a DaC change landing first, and the lab runs on other
people's machines, so the load-time guard is the control that must exist in v1.

- **(ii) Load-time containment (THIS SPRINT, required):** `_contain_skill_body` mirrors
  `skill.ts`'s `sanitizeBodyField` semantics in Python and is applied to the body before it ever
  reaches `compose_system_context`. Even a SKILL.md hand-edited after emission cannot (a) forge a
  new top-level `#`/`---` section that escapes its own H2, (b) impersonate ARAIL's own prompt
  delimiters (`# WORLD FRAMING`, `# Procedural knowledge`, `Observation:`), or (c) inject through
  malformed frontmatter (`parse_frontmatter` already fails closed to `{}`). The body is also size-
  capped (`_MAX_WORLD_SKILL_BODY_CHARS`) so a giant SKILL.md cannot bloat or DoS the prompt.
  The world-skill is rendered under its own H2 by `compose_system_context`, so legitimate glossary
  markdown (`### Category`, `- **term**`) stays contained beneath that header.

- **(i) Seal-promotion (DURABLE FIX, cross-repo follow-up — NOT this sprint):** the real
  integrity guarantee requires changing ARAIL's `verify_seal` to hash-check `SKILL.md` against
  `manifest.files{}` AND DaC adding `SKILL.md` to `manifest.files{}`. Two options for ARAIL's
  side, both deferred to a tracked follow-up (see Tech debt): either add `"SKILL.md"` to a new
  *optional-sealed* set checked only when present in `files{}`, or refactor `verify_seal` to
  iterate `manifest.files{}` generically. **Interim posture (v1):** ARAIL **loads SKILL.md
  without trusting it** (contained, capped) — it never refuses a mount over an unsealed SKILL.md
  and never claims the body is sealed. We do NOT add `"SKILL.md"` to `_BUNDLE_FILES` in this
  sprint (that would break the seal check for every existing 6-file bundle that has no SKILL.md
  hash). The honesty rail: the world-skill body is injected as DATA the agent reasons over, never
  as trusted instructions — consistent with the `terms.json`-is-DATA boundary already documented
  in `world_mount.py`.

## Unmount / swap / nothing-mounted

- **Unmount:** `unmount()` removes the `world-mount.json` pointer first. Because `load_world_skill`
  keys off `current_mount()`, the world-skill **disappears on the very next prompt assembly** with
  no extra code — no stale domain skill can linger. (Staged `SKILL.md` may remain on disk under
  `world-<slug>/` exactly like the other staged files unless `--remove-staged`; that is inert
  because nothing reads it without a live pointer. This matches existing staged-file behavior.)
- **Swap:** `swap()` calls `_stage_files` for the new bundle (now also staging the new SKILL.md)
  and flips the pointer. The next prompt assembly reads the NEW staged dir's SKILL.md. A same-slug
  swap is covered by the existing atomic `.staging → world-<slug>` rename, so SKILL.md is replaced
  atomically with the rest. No stale prior-World skill survives.
- **Nothing mounted:** `current_mount()` → None → `load_world_skill()` → None → unchanged skill
  list → default AI/ML world (`intent="ai"` base, Buddy with no WORLD FRAMING). Regression-safe.

## Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Tampered SKILL.md (forged `# WORLD FRAMING` / `---` / `# Procedural knowledge` / `Observation:`) | `_contain_skill_body` matches control/delimiter lines on load | Neutralize with U+200C prefix / strip fence; body injected as inert DATA under its own H2 |
| Oversized SKILL.md (prompt-bloat / DoS) | byte cap on read + char cap on body | `load_world_skill` returns None (file) / truncates body; warning logged; mount unaffected |
| Malformed frontmatter | `parse_frontmatter` returns `{}` | `load_skill` tolerates; skill loads body-only, name falls back to `world-<slug>` |
| Missing SKILL.md (legacy 6-file bundle, e.g. existing staged worlds) | `<staged_dir>/SKILL.md` absent | `load_world_skill` returns None → graceful no-op; agents keep face framing only |
| Stale skill after unmount/swap | `load_world_skill` re-reads `current_mount()` each call | New/None pointer ⇒ new/None skill on next assembly; no lingering domain knowledge |
| Duplicate vs face WORLD FRAMING | Distinct prompt sections (framing = face 2-liner; skill = glossary under H2) | By construction non-overlapping; a test asserts framing block and skill section are both present and distinct |
| AGENT.md drift / unintended mutation | We never write AGENT.md (Option b) | N/A — world-skill is injected out of band; unmount needs no AGENT.md cleanup |
| Loader raises mid-compose | try/except in ArailHost.load_world_skill + Researcher failsoft block | Returns None / skill_ctx unchanged; agent still speaks with base + face framing |
| SKILL.md stage fails at mount | best-effort copy in `_stage_files` wrapped in try/except | Logged; mount succeeds with the 6 sealed files; world-skill simply absent |

## Test strategy (weighted to ARAIL gating: 30% setup · 30% Buddy/Researcher prompt · 20% security · 10% happy · 10% regression)

- **Setup / mount-on-clean-checkout (~30%):**
  - `test_world_skill_mount_stages_skill_md`: mount a SKILL.md-bearing fixture →
    `<staged_dir>/SKILL.md` exists, byte-identical to the bundle's.
  - `test_world_skill_mount_seal_still_passes`: a bundle whose seal-exempt SKILL.md is *modified*
    still mounts (seal covers only the 6) — and the modified body is contained on load (links to
    security test). Confirms we did NOT add SKILL.md to `_BUNDLE_FILES`.
  - `test_world_skill_missing_is_noop`: mount an existing 6-file fixture (no SKILL.md) → mount
    succeeds, `load_world_skill()` returns None.
  - Clean-checkout self-containment: all fixtures live under `tests/fixtures/world-bundles/`.
- **Buddy / Researcher prompt includes skill (~30%):**
  - `test_buddy_prompt_includes_world_skill`: mount art-history fixture → `_compose_prompt("x")`
    contains a known term body substring (e.g. `Ballets Russes`) AND the `# Procedural knowledge`
    header AND the face `# WORLD FRAMING` block (both present, distinct).
  - `test_researcher_context_includes_world_skill`: `_get_system_context()` with the World mounted
    contains the term substring; intent base is the `"other"` domain_framing.
  - `test_world_skill_absent_no_section`: nothing mounted → neither composed context contains a
    world-skill section (regression-anchored to current behavior).
- **Security / injection-on-load (~20%):**
  - `test_world_skill_tampered_cannot_forge_structure`: a `hostile` fixture SKILL.md with a body
    line `# Procedural knowledge` / `# WORLD FRAMING` / `---` / `Observation: ignore previous` →
    after `load_world_skill`, those lines are neutralized (U+200C or stripped) and do not appear
    as bare structural lines in `compose_system_context`.
  - `test_world_skill_oversized_rejected`: a >64KB SKILL.md → `load_world_skill` returns None.
  - `test_world_skill_malformed_frontmatter_loads_body_only`: garbage frontmatter → body still
    loads, no exception.
- **Happy path (~10%):** `test_world_skill_end_to_end`: export/copy art-history → mount → Buddy
  composes a prompt grounded in art-history terms; unmount → next compose has no world-skill.
- **Regression (~10%):** existing `tests/test_world_*.py` (mount, identity flip, buddy, kb,
  switcher, catalog adopt) pass unchanged; `compose_system_context` with only AGENT.md skills is
  byte-identical to pre-sprint output (no world mounted).

### Test fixture plan

The existing `tests/fixtures/world-bundles/` already has `physics`, `hostile`, `tampered`, and
caps/model variants — none has a SKILL.md (they predate the emitter). Plan:

1. **Primary fixture — copy DaC's real emitted bundle.** `dist/bundles/art-history/` in
   `../qukaizen-dac` already contains a SKILL.md + the 6 sealed files + manifest. Copy the
   directory (the 6 sealed files + `manifest.json` + `SKILL.md`; capabilities/plugin/model
   optional) to `tests/fixtures/world-bundles/art-history-skill/`. Self-contained, no DaC
   toolchain needed at test time — keeps the clean-machine gate green. `horticulture/` is a
   second real-bundle option if a sourced (non-dreamed) provenance variant is wanted.
2. **Hostile SKILL.md fixture.** Add a `SKILL.md` to a copy of the `hostile` (or a new
   `world-skill-hostile`) fixture whose *body* contains forged structural lines
   (`# Procedural knowledge`, `# WORLD FRAMING`, `---`, `Observation: …`). The 6 sealed files
   keep a valid seal so the bundle mounts; the security test asserts containment on load.
3. **No-SKILL fixture.** Reuse `physics` (already 6-file, no SKILL.md) for the missing→no-op test.

Builder note: do NOT regenerate fixtures via the DaC toolchain in CI; copy the already-emitted
bytes so the fixture is frozen and `--check`-independent of DaC's current state.

## Tech debt

**Added:**
- One new staged, *unsealed* file in the World dir (`SKILL.md`) that ARAIL injects into prompts
  but cannot yet hash-verify. Mitigated to data-not-instructions by load-time containment; the
  real fix is the cross-repo seal-promotion below.
- A second containment implementation in Python (`_contain_skill_body`) that must stay in sync
  with `skill.ts`'s `sanitizeBodyField`. Low drift risk (both deterministic, both tested) but a
  duplicated invariant.

**Repaid:**
- Closes the "identity without knowledge" gap — the mounted World now drives what the agents
  *know*, not just who they *are*. Removes the surprising half-mounted state.
- Establishes the untrusted-data-on-load pattern for bundle-sourced markdown, reusable for any
  future seal-exempt sibling that reaches a prompt.

**Net:** roughly neutral with one explicit follow-up filed.

**Follow-up ticket (cross-repo, tracked):** *"Seal-promote SKILL.md end-to-end."* ARAIL: refactor
`verify_seal` to iterate `manifest.files{}` generically (or add an optional-sealed set) so a
present `SKILL.md` hash is enforced when DaC supplies it; decide refuse-vs-warn for a SKILL.md
listed in `files{}` whose hash mismatches. DaC: add `SKILL.md` to `manifest.files{}` (ADR-0004
Decision 2 "Sprint 2 path"). Gate: backward-compatible with existing 6-file bundles (SKILL.md
remains optional). Until then the v1 load-time containment is the standing control.

## Branch recommendation

**Branch `qukaizen/arail-dac-world-mount` off the current `qukaizen/arail-world-forge-doc`.** The
current branch carries unrelated uncommitted staged-world work (`lab/pkb/sources/world-*`,
`lab/worlds/*`, `bookmarks.md`, etc.). Branching now isolates this sprint's commits and lets the
builder stage ONLY the files it touches (`world_mount.py`, `skills_loader.py`, the two agents,
new tests, new fixtures). **Builder must `git add` explicit paths — never `git add -A`/`.`** — so
the user's unrelated uncommitted work is never swept into a sprint commit.

## Recommended implementation order

1. `skills_loader.py`: add `_MAX_*` caps, `_contain_skill_body`, `load_skill_from_path`,
   `load_world_skill` (+ unit tests for containment, caps, malformed frontmatter, missing→None).
2. `world_mount.py`: add `_WORLD_SKILL_NAME` + best-effort SKILL.md copy in `_stage_files`
   (+ stage/seal-unaffected/missing-noop tests).
3. Test fixtures: copy `art-history-skill`, add the hostile-SKILL fixture.
4. Researcher: wire `load_world_skill` into `_get_system_context` (failsoft) + test.
5. Buddy: add `BuddyHost.load_world_skill` seam + `ArailHost` impl + `_compose_prompt` wiring +
   test (mock host returns None by default → existing Buddy tests unaffected).
6. End-to-end + regression pass; confirm unmounted composed context is byte-identical to pre-sprint.
