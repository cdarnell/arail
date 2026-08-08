# Build log: Tier 1.2 as a measurement — nomic vs `hash_embedding`

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at `3987f71`
**Started:** 2026-08-08

**Scope of this invocation: W0–W5 only.** W6–W10 (conditional integration) are
gated on the number produced by W4/W5 and are explicitly not attempted here.

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| W0 | `src/arail/dbspec/embed.py` | `_assert_local(base)` airgapped-egress guard on `_post` | `tests/dbspec/test_embed_airgapped.py` | pending |
| W1 | `scripts/eval/retrieval_ab.py`, `eval/retrieval/corpus_manifest.json`, `.gitignore` | Read-only harness skeleton: `--dump-corpus`, workdir-safety assert (exit 2), corpus manifest emitter (H2) | manual `--dump-corpus` run + workdir-guard unit test | pending |
| W2 | `eval/retrieval/queries.yaml`, `eval/retrieval/exact_tokens.yaml`, `eval/retrieval/pii_deny.txt`, `tests/eval/test_retrieval_fixture.py` | Hand-authored fixtures (F1/F2), read from `--dump-corpus` output only, before any measurement exists | `tests/eval/test_retrieval_fixture.py` (schema, verbatim-quote lint, PII lint, overlap-stratum floor) | pending |
| W3 | `scripts/eval/retrieval_ab.py` | Complete harness: hash arm, nomic arm, recall@5/MRR@10/rank-1/strata/bootstrap CI/latency, `results.json` + RESULTS markdown emitter | `tests/eval/test_retrieval_ab.py` (stub embedder, no Ollama) | pending |
| W4 | `eval/retrieval/results.json`, `sprints/.../RESULTS.md` | Run the harness against the live `lab/` corpus with real Ollama; publish the number | n/a (this is the measurement) | pending |
| W5 | `sprints/.../BUILD_LOG.md`, possibly `docs/adr/0004-hash-embeddings-are-a-measured-choice.md` | Evaluate against the 15pp/zero-rank-1-loss gate; write the verdict; if FAIL, write the ADR and stop | n/a | pending |

Order follows ARCHITECTURE.md "Recommended implementation order" §1–6 exactly.

## Execution

(filled in as steps land)

## Architect feedback required

(empty unless the architect's plan needs revision mid-build)

## Final state

(numbers, verdict, test counts — filled in at W5)
