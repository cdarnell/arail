---
title: "Build-time teacher"
tags: [world-ai, qukaizen]
aliases: [build-time-teacher]
---

[BUILT] Frontier model used only during corpus authoring — never at runtime.

[BUILT] The build-time teacher is the frontier LLM (e.g., Claude) used during World authoring and corpus compilation. It assists in drafting definitions, sourcing verification, and knowledge synthesis — but it is never deployed as a runtime component. The pattern is: frontier model as authoring teacher → compiled World → baked SLM as runtime. This ensures the high cost of frontier inference is paid once, at build time, not per query. BUILT: this is the live authoring method for every World including this one.

**Example:** Claude Sonnet 4.6 authored and sourced the ml-engineering World terms (build-time teacher); the eventual runtime is the baked 7B specialist, not Claude.

## Related

- [[teacher-student-training]]
- [[the-bake]]
- [[aerollm-runtime]]

Source: QuKaiZen CLAUDE.md ('the frontier model is the build-time teacher, never the runtime'); QuKaiZen VISION.md
