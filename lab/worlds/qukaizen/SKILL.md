---
title: "QuKaiZen Suite"
id: world-qukaizen
name: "QuKaiZen Suite"
domain: qukaizen
version: "1.0.0"
tags: [world, knowledge, qukaizen]
when_to_use:
  - When the user asks about QuKaiZen Suite or its declared categories
  - When grounding a claim that falls inside this World's domain
when_not_to_use:
  - When the question is outside this World's declared categories
  - When a claim cannot be tied to one of this World's sourced terms (say so; don't invent)
---
This World is the lab explaining itself: what ARAIL is, how Worlds and the Compiled Knowledge Base work, how Nucleus distills frontier teachers into small owned Super Skills, and how AeroLLM runs large models locally. Every term is grounded in the QuKaiZen product docs.

Every term in this World is grounded in a cited source.

_Answer only from the terms below. Every term lists its source. If a question cannot be answered from these terms, say the World does not cover it — do not invent._

### Inference (AeroLLM)

- **AeroLLM** (`aerollm`) — QuKaiZen's inference engine that streams frontier models off disk so they run without full GPU residency.
  - Source: QuKaiZen NUCLEUS_AGENT_PROTOCOL
- **Layer Streaming** (`layer-streaming`) — Running a model by streaming its layers off disk instead of holding them all in GPU memory — how AeroLLM fits huge models on a laptop.
  - Source: ARAIL research/aerollm; aeroLLM README.md

### The Lab (ARAIL)

- **Airgapped Mode** (`airgapped-mode`) — ARAIL's default posture — agents can't reach the public internet; cloud providers unlock only in hybrid mode.
  - Source: ARAIL README.md; CLAUDE.md (LAB_MODE)
- **ARAIL** (`arail`) — Autoresearch AI Labs — a cloneable, local-first blueprint for an AI research bench: chat, a knowledge base, agents, and an overnight research loop, airgapped by default.
  - Source: ARAIL README.md
- **AutoResearch** (`autoresearch`) — The swarm's brain — it evolves the rubrics every other agent consults.
  - Source: QuKaiZen AI Dictionary
- **Buddy** (`buddy`) — ARAIL's local companion agent — a context-aware lab partner you learn alongside, running entirely on your own hardware.
  - Source: ARAIL
- **Compute Source** (`compute-source`) — The Chat pivot that swaps the model behind the same persona — a local small model, AeroLLM, a LAN GPU box, or a one-click cloud frontier.
  - Source: ARAIL README.md (Compute Source pivot)
- **QuKaiZen** (`qukaizen`) — The umbrella project and company behind ARAIL, Nucleus, and aeroLLM — tools to own your AI reasoning, measured in wisdom per watt.
  - Source: QuKaiZen workspace CLAUDE.md
- **Rubric** (`rubric`) — The evolving scoring criteria AutoResearch uses to probe and grade the student.
  - Source: QuKaiZen AI Dictionary

### Knowledge as Code

- **BAKED (lifecycle stage)** (`baked-stage`) — [ROADMAP] The third stage of the QuKaiZen knowledge lifecycle — RAW → COMPILED → BAKED.
  - Source: QuKaiZen CLAUDE.md (RAW→COMPILED→BAKED lifecycle); QuKaiZen DAC_ENGINE.md
- **Compiled Knowledge Base** (`compiled-knowledge`) — A World's approved layer — knowledge a human has vetted, sealed with provenance — the truth agents experiment against, distinct from the raw candidate corpus.
  - Source: ARAIL Compiled KB (WK-10); QuKaiZen DaC gate
- **corpus_sha256 (bake lockfile)** (`corpus-sha256`) — [BUILT] The SHA-256 hash pinning the compiled corpus — the DaC CD lockfile.
  - Source: QuKaiZen DAC_ENGINE.md (corpus_sha256 = CD lockfile); QuKaiZen CLAUDE.md
- **Documentation as Code (DaC)** (`documentation-as-code`) — QuKaiZen's framework: a declarative, curated source of truth that compiles into a knowledge app or bakes into a model you own.
  - Source: QuKaiZen
- **Provenance** (`provenance`) — A verifiable record of exactly what went into a model and how it was built.
  - Source: QuKaiZen AI Dictionary
- **Seal** (`seal`) — A cryptographic signature certifying a model's provenance — what it was distilled from and that it is untampered.
  - Source: QuKaiZen NUCLEUS_AGENT_PROTOCOL
- **World** (`world`) — A sealed knowledge domain — terms, categories, an association graph, and a theme — the lab studies; the objective starting data set you mount.
  - Source: ARAIL README.md; QuKaiZen DaC README

### Distillation (Nucleus)

- **Adversarial Swarm** (`adversarial-swarm`) — A loop of agents (interrogate, challenge, evaluate, correct) that hardens a model until it stops breaking.
  - Source: QuKaiZen NUCLEUS_AGENT_PROTOCOL
- **Build-time teacher** (`build-time-teacher`) — [BUILT] Frontier model used only during corpus authoring — never at runtime.
  - Source: QuKaiZen CLAUDE.md ('the frontier model is the build-time teacher, never the runtime'); QuKaiZen VISION.md
- **Convergence** (`convergence`) — Graduation by exhaustion — the model is done when the swarm can't break it anymore.
  - Source: QuKaiZen AI Dictionary
- **Convergence Graduation** (`convergence-graduation`) — A model graduates when the adversarial swarm gives up trying to break it — not at a fixed cycle limit.
  - Source: QuKaiZen NUCLEUS_AGENT_PROTOCOL
- **Distillation** (`distillation`) — Transferring a large teacher model's reasoning into a small student model that owns the domain.
  - Source: QuKaiZen AI Dictionary
- **KICE** (`kice`) — QuKaiZen's agent that extracts certified, verifiable domain knowledge in six layers.
  - Source: QuKaiZen NUCLEUS_AGENT_PROTOCOL
- **Nucleus (bake engine)** (`nucleus-bake-engine`) — [ROADMAP] QuKaiZen's training pipeline for baking domain-specialist SLMs.
  - Source: QuKaiZen CLAUDE.md (Nucleus: company hub, bake pipeline); QuKaiZen THEME.md; QuKaiZen VISION.md
- **Nucleus Seal** (`nucleus-seal`) — An Ed25519 cryptographic provenance chain proving how a Super Skill model was made.
  - Source: QuKaiZen NUCLEUS_AGENT_PROTOCOL
- **SSDP** (`ssdp`) — QuKaiZen's pipeline that distills deep reasoning from frontier teacher models into small, owned Super Skill models.
  - Source: QuKaiZen NUCLEUS_AGENT_PROTOCOL
- **Student Model** (`student`) — The small model being trained to absorb the teacher's reasoning.
  - Source: QuKaiZen AI Dictionary
- **Super Skill** (`super-skill`) — A 1-7B model that durably knows a domain, distilled from a frontier teacher and owned forever.
  - Source: QuKaiZen NUCLEUS_AGENT_PROTOCOL
- **Symbolic Chain-of-Thought** (`symbolic-cot`) — Capturing a teacher's reasoning as reusable symbolic structure, not just imitated text traces.
  - Source: QuKaiZen NUCLEUS_AGENT_PROTOCOL
- **Teacher Model** (`teacher`) — The large frontier model whose reasoning is distilled into a small student.
  - Source: QuKaiZen AI Dictionary
- **The bake (sealed specialist SLM)** (`the-bake`) — [ROADMAP] The sealed domain-specialist SLM produced by the Nucleus pipeline — the one bet.
  - Source: QuKaiZen CLAUDE.md ('the bake is the moat', 'the one bet'); QuKaiZen THEME.md; QuKaiZen VISION.md
- **TICE** (`tice`) — QuKaiZen's agent for Layer-7 tacit knowledge — the unwritten expert know-how and gotchas.
  - Source: QuKaiZen NUCLEUS_AGENT_PROTOCOL
- **Wisdom per Watt** (`wisdom-per-watt`) — QuKaiZen's core metric: certified, permanently-owned reasoning capability per unit of lifetime energy to mint and run it.
  - Source: QuKaiZen NUCLEUS_AGENT_PROTOCOL

<!-- dac:world_sha256 fc6b5e473594996d71fa970ba577d81c2d20856f3b904c76691f722241271345 -->
