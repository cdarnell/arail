# Vision: Capability registry + on-device speech-to-text (STT) adapter

**Date:** 2026-06-13
**Product:** arail
**Wedge size:** one sprint
**Program:** DaC 2.0 × ARAIL — World-Driven Labs, Part 2 (capability/inheritance engine). Second half;
the world-mount identity layer shipped in PR #77 (see
`/Users/netsushi/ProJects/sprints/2026-06-13-integrate-dac-into-arail/ARCHITECTURE.md`, Phases 0–6).

---

## User

A named, concrete persona — and I am refusing to let it stay "any researcher."

**Primary (the wedge user):** A clinical-psychology grad student running ARAIL airgapped on a personal
MacBook (Apple Silicon, macOS) who has just mounted `world:psychology` (a DaC WorldBundle). She has a
4-minute spoken observation about a session she just ran — a hypothesis worth keeping — and she is
*sitting in front of her lab with no fast way to get the spoken thought into the knowledge base.* Today
she either (a) types it out, breaking the train of thought, or (b) records a voice memo in another app
that never reaches the lab's KB and is never indexed, never researched, never resurfaced. The voice
memo dies outside the lab.

**Honest generalization:** the wedge is NOT "psychology." Psychology is the *first World that declares
the need*; the value is **any-lab voice capture**. The moment relieved is identical for a field
ecologist dictating site notes, a maker narrating a build, or a physics tutor talking through a
derivation. The DaC framing matters because it is what makes STT arrive *as an inherited capability*
(the World declared `speech-to-text`; ARAIL provisioned it) rather than as a bespoke psychology feature.
We build the adapter ONCE; every World that declares the need inherits it. That is the actual product
claim being tested.

## Problem

The underlying pain is **capture friction at the speed of thought, inside an airgapped lab.** A spoken
observation is the cheapest, fastest form a research thought takes, and ARAIL today has no path for it.
The KB ingests files and typed notes; it does not ingest speech. So the most fluid input modality
is the one the lab cannot accept — and routing through any cloud transcription service violates the
airgapped default that is ARAIL's whole posture (`LAB_MODE=airgapped` blocks every cloud provider).

The deeper, program-level problem this sprint exists to solve: **DaC's "Worlds inherit capabilities"
claim is unproven on a live modality.** PR #77 proved a World can change what the lab *knows* (dictionary,
framing, theme) with zero domain code. It did NOT prove a World can change what the lab *can do*. Until
a declared `capabilities.json` id resolves to a real adapter that lights up real hardware, the
inheritance engine is a slide, not an engine. This sprint's job is to make it an engine — on exactly
one capability — without over-building for capabilities we haven't earned the right to build.

## Win condition

Falsifiable, pass/fail, testable on macOS / Apple Silicon. Restates PROGRAM win conditions 2 & 3 plus
an abstraction-proof.

**WC-A (inheritance, live modality) — the headline.** On a clean-ish Apple Silicon machine, a tester:
mounts a vendored test World whose `capabilities.json` declares `speech-to-text` → taps a mic affordance
→ speaks a ~30s memo → an on-device transcript lands as a **RAW note** in the World's KB
(`lab/pkb/research/` or inbox), gets indexed, and is searchable. PASS requires ALL of:
  1. Zero network egress during capture+transcribe (assert via `egress.py`/airgap guard; works under
     `LAB_MODE=airgapped`).
  2. Zero domain-specific ("psychology") strings in ARAIL source — `grep` is clean.
  3. The landed note is typed RAW/unsourced (user-captured observation), NOT gate-passed truth, and is
     NEVER injected into a system prompt as instructions. The DATA-not-instructions boundary holds.
  4. Transcript word error rate is *good enough to be useful*: on a scripted 30s clear-speech sample,
     ≥90% of content words correct, end-to-end latency (stop-talking → note-on-disk) **< 15s**. If
     Apple on-device cannot clear this bar, see disconfirming evidence — that is a real kill signal.

**WC-B (Linux-ready by construction).** A Linux backend could be added for EITHER seam (audio capture;
STT) **without touching** the World contract, the `capabilities.json` schema, the mount loader, or lab
logic. PASS = proven structurally now: each seam has an interface; macOS backend implements it; a Linux
backend is **registered as `unimplemented`** and selected-by-platform. Test: force-select the Linux
backend on macOS → it raises a clean, actionable `CapabilityUnavailable("speech-to-text: no backend for
linux")`, and NO World/loader/lab file imports an Apple symbol above the adapter interface (`grep` for
`AVFoundation`/`Speech`/`pyobjc` outside `capabilities/backends/macos/` is clean).

**WC-C (the registry is real, not a wrapper for one adapter).** A SECOND capability id —
`equation-ocr` — declared in a test bundle's `capabilities.json` resolves to **"declared, no adapter
installed → degrade gracefully"** with ZERO code changes (no new adapter, no edits): the mount surfaces
it as a known-but-unprovisioned capability, the lab keeps working, nothing crashes. If adding a second
*declared* id requires touching code, the abstraction is fake and we built a one-off with extra steps.

**WC-D (graceful absence).** A bundle with NO `capabilities.json` (BUNDLE-OPTIONAL) mounts exactly as
PR #77 mounts today — no regression, no new required file.

## Wedge

The minimum that proves capability-inheritance end-to-end on a live modality. Shippable in one sprint.

**IN (BUILT):**
- `src/arail/capabilities/` — the registry: `declared id → resolved adapter | declared-unimplemented |
  unknown`. Reads `capabilities.json` at mount (reuse the `world_mount.py` mount flow; `capabilities.json`
  is BUNDLE-OPTIONAL and handled absent).
- One capability-adapter **interface** per seam: (A) audio/mic capture, (B) speech-to-text. OS-specific
  code lives strictly BELOW these interfaces.
- macOS backend, on-device: mic capture (AVFoundation/CoreAudio + TCC permission) → Apple Speech
  framework on-device recognition → text.
- Linux backend for both seams **registered as `unimplemented`** (selected by platform; raises clean).
- Mount-reads-capabilities path wired into the existing flow; RAW-note landing via the existing
  `pkb_index` (`schedule_upsert(path, pkb_root=…)`) filing seam — same path the world-mount sprint used.
- A minimal mic affordance (one button + state; "tap, speak, stop" → toast that note landed). Not a
  designed UI.
- Vendored test fixtures in `arail/tests/`: a bundle declaring `speech-to-text`; a bundle additionally
  declaring `equation-ocr` (WC-C); a bundle with no `capabilities.json` (WC-D). Same vendoring pattern as
  the physics bundle (`tests/fixtures/world-bundles/…`). **No qukaizen-dac edits.**

**OUT (ROADMAP — explicitly deferred):**
- `equation-ocr` *implementation* (only its declared-but-unprovisioned resolution is in scope — WC-C).
- vision-image-classify, pdf-table-extract, any other modality.
- Cloud STT of any kind. Non-negotiable: violates airgapped posture.
- Real-time / streaming live-transcription-as-you-speak if it costs more than batch (record → stop →
  transcribe is fine for v1; streaming is a polish item).
- Speaker diarization, punctuation models, multi-language, long-form (>~5 min) audio.
- A polished mic UI, waveform viz, editing-before-save. v1 lands the raw transcript; the user edits it
  as a normal KB note afterward.
- Auto-promotion of a transcript out of RAW into sourced/gate-passed truth. RAW stays RAW.
- The Linux backend *working*. Registered-unimplemented only (that is the point of WC-B).

## Disconfirming evidence

Pre-committed kill/defer signals. If we hit these, we do not rationalize.

1. **Quality/latency floor missed.** If Apple Speech on-device cannot clear WC-A.4 (≥90% content words,
   <15s) on clear scripted speech across 5 tries, the modality is not useful and we **defer** STT (the
   registry may still ship if WC-C/D hold) — we do NOT paper over it with cloud.
2. **Python→Apple-Speech access is too costly.** If neither pyobjc nor a *small* (<~150 line)
   Swift/Obj-C helper binary gets us on-device recognition inside one sprint — i.e. it turns into a
   build-system / signing / framework-linking swamp — **defer**; the cost has exceeded the wedge.
3. **Mic permission UX is too painful on a clean machine.** ARAIL gating weights setup-on-clean-machine
   heavily (30%). If TCC mic permission cannot be obtained gracefully from ARAIL's process context
   (e.g. headless/Flask-server/portal context can't trigger or inherit the prompt, or the failure mode
   is a silent hang rather than an actionable message), and there's no clean fix in-sprint, **defer** —
   a capability that bricks on first use on a clean machine fails the product, not just the feature.
4. **The abstraction is over-engineering.** If WC-C cannot be met cheaply — i.e. making the registry
   genuinely handle a second declared id costs as much as a second adapter — then the "registry" is a
   premature abstraction over N=1. In that case **ship STT as a direct adapter behind the seam
   interfaces (WC-B still holds) and DROP the registry** until a real second adapter justifies it.
   Inheritance is proven by the seam + RAW landing; the registry is only worth it if it's cheap.
5. **Nobody captures twice.** Post-ship behavioral signal: if the wedge user (or our own dogfood) records
   a voice memo once and never returns for a second capture within two weeks, the friction it removed
   wasn't real friction. Shelve further capture work.

## Displacement

What saying yes costs — and it is not "nothing."

- **Within ARAIL:** this sprint consumes the slot that would otherwise advance the *content* side of
  World-Driven Labs (Phase 7 goal/curriculum feed, additional World adapters) or core lab surfaces
  (Chat Studio, autoresearch loop, AeroLLM compute-source integration). Concretely: the goal/curriculum
  feed that turns a mounted World into a *curriculum* gets pushed.
- **Across QuKaiZen's three products:** time on ARAIL STT is time not on **aerollm** (frontier-scale
  inference) and **qukaizen-nucleus** (strategy/pipeline). aerollm's CUDA-backend gap and Nucleus work
  both wait. This is a deliberate bet that *proving the inheritance engine on a live modality* is the
  higher-leverage demo right now, because it is the load-bearing claim of the whole DaC × ARAIL program.
- **What it replaces for the user:** manual note typing (the slow path), cloud transcription apps (the
  airgap-violating path), and — most importantly — it forecloses the tempting **bespoke per-World hack**
  (a psychology-specific transcribe button hardwired into ARAIL). The whole sprint exists to make that
  hack illegal by construction.

## Recommended next step

**PROCEED to /architect with this as the spec — with a structural caveat.**

Justification: this is the load-bearing, falsifiable proof of DaC's central claim (Worlds inherit
*capabilities*, not just knowledge), it is scoped to one sprint, the seams already exist in
`world_mount.py` + `pkb_index`, and the airgapped/RAW-note constraints are sharp and testable.

The caveat the architect must resolve **before the builder starts**, because it gates whether half the
sprint exists: pick the Python→Apple-Speech access mechanism (pyobjc vs. a small Swift/Obj-C helper) and
prove the TCC mic-permission flow works from ARAIL's actual process context **on day one** as a spike. If
that spike fails, disconfirming-evidence items 2 and 3 fire and we defer the STT *backend* while
potentially still landing the registry + seams (WC-B/C/D). The architect should also pre-commit on
disconfirming item 4: define the registry so WC-C is cheap, or explicitly drop the registry to a direct
adapter. Do not let "we'll figure out the Apple-Speech binding during the sprint" stand — that decision is
made before the sprint, not during it.
