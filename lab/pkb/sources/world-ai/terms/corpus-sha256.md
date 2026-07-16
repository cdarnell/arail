---
title: "corpus_sha256 (bake lockfile)"
tags: [world-ai, qukaizen]
aliases: [corpus-sha256]
---

[BUILT] The SHA-256 hash pinning the compiled corpus — the DaC CD lockfile.

[BUILT] corpus_sha256 is the SHA-256 hash of the compiled terms.json (or bake corpus bundle) stamped by bake-corpus.mts. It serves as the Content-Delivery lockfile for the bake pipeline: any downstream consumer (Nucleus training run, model version tag) pins this hash to guarantee it is training on the exact same compiled corpus. Analogous to a package.lock — the corpus is reproducible and auditable. BUILT: bake-corpus.mts produces and writes this hash today.

**Example:** bake-corpus.mts writes corpus_sha256: 'a3f7...' to the manifest; the Nucleus training config pins this hash so the exact corpus can be recovered from git.

## Related

- [[the-bake]]
- [[nucleus-bake-engine]]
- [[baked-stage]]

Source: QuKaiZen DAC_ENGINE.md (corpus_sha256 = CD lockfile); QuKaiZen CLAUDE.md
