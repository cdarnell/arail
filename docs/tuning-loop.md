# Autoresearch Tuning Loop — `/tuning`

The `/tuning` page is the single-pane view for measuring and
improving OGLab's 1 TB research model. It ties three things
together:

1. A **bench runner** that times the model, records every run as
   JSONL, and tags each record with the git SHA that produced it.
2. A **tuning config** (`config/tuning.yml`) that is the complete
   surface area an autoresearch agent is allowed to modify.
3. An **autoresearch loop** that enumerates known-safe variants,
   runs the bench for each, and commits the winners on dedicated
   `autoresearch/<id>` branches.

The whole module sits under `src/oglab/experiments/` and is
wired into the portal at `/tuning`.

## The model under test

Exactly one "research model" is tuned at a time. It must be a
model whose weights are ≥ 1 TB on disk — this is the whole
premise of the loop. The default is DeepSeek-R1 (671B MoE, FP16 ≈
1.3 TB). Swap it by editing `config/tuning.yml`:

```yaml
research_model:
  name: "meta-llama/Meta-Llama-3.1-405B"
  precision: "fp32"
  expected_disk_gb: 1620
  family: "dense"
  ...
```

Small models (Qwen3-0.6B, Phi-3.5-mini, etc.) are listed
separately under `small_models` for the fast/draft paths. They
are not tuned by this loop.

## Safety rails

The loop makes commits. That means every safety rail here is
load-bearing.

- **Working tree must be clean.** The loop aborts with a clear
  error if `git status --porcelain` returns anything. Commit or
  stash first.
- **`OGLAB_AUTORESEARCH_ENABLED` env var required.** Without it,
  the `/api/tuning/autoresearch/start` endpoint returns a 200
  with `{ok: false, error: ...}`. Belt + braces so an accidental
  click can't make commits.
- **Only two files are ever writable by the loop.** Enforced in
  `git_ops.ALLOWED_WRITABLE_FILES`:
  - `config/tuning.yml`
  - `lab/data/airllm-bench.jsonl`
  If the agent somehow proposes a different edit, `commit_experiment`
  raises `GitSafetyError` before anything is staged.
- **Schema validator rejects off-schema knob values.** Each knob
  in `tuning.yml` declares a type and bounds/choices. Candidates
  that propose invalid values are skipped as errors without
  touching git.
- **Variants never touch main.** Each variant runs on its own
  `autoresearch/<timestamp>-<slug>` branch. Losing variants are
  left on-branch for human inspection; winners are committed with
  a structured message, still on their branch — human reviews &
  cherry-picks.
- **No pushes, no force, no rebases.** This module never shells
  out to any git operation that rewrites history or sends anything
  over the network.

## Interpreting the page

- **Baseline** — the frozen reference measurement on the commit
  captured by the "Capture baseline" action. Sets the denominator
  for Δ%.
- **Champion** — the best `decode_tok_per_sec` observed across
  all runs in `airllm-bench.jsonl`, with a link to its commit.
- **Throughput over time** — sparkline of every successful run's
  `decode_tok_per_sec`, ordered by timestamp. Winning commits
  lift the line visibly.
- **Variants table** — the results of the most recent loop. A
  "win" row is committed; "loss" and "error" rows are left on
  branch for inspection.
- **Bench history table** — full detail from JSONL, newest first.

## The candidate list

`autoresearch.CANDIDATES` is a hand-curated list of 8 variants
mirroring the sections of `docs/airllm-fork-guide.md`. Adding a
new candidate requires two edits:

1. `config/tuning.yml` — if the variant needs a new knob or a new
   allowed `choices` value.
2. `src/oglab/experiments/autoresearch.py` — add an entry to
   `CANDIDATES`.

Two-file discipline keeps the search space from expanding behind
the maintainer's back. Agents that propose variants at runtime
must pass them via the `candidates` parameter; they cannot extend
`CANDIDATES` in-place.

## Extending with fork-level optimizations

The stock AirLLM package only honors two of our knobs at runtime
(`AIRLLM_COMPRESSION` and `AIRLLM_MAX_LENGTH`). The other four —
`prefetch_enabled`, `prefetch_lookahead`, `expert_cache_size_mb`,
and `airllm_package` — exist to support an AirLLM fork (see
`docs/airllm-fork-guide.md`). The workflow is:

1. Fork and modify AirLLM to read the new env vars (e.g.
   `AIRLLM_PREFETCH_LOOKAHEAD`).
2. Add the fork's pip target to `airllm_package.schema.choices`
   in `config/tuning.yml`.
3. Update `bench._apply_knob_env` to translate the new knobs to
   the env vars the fork reads.
4. Let the loop run. Now your fork is under experimental control.

## Tests

`tests/test_experiments.py` covers the safety-critical parts:

- Knob validator rejects off-schema values (string choices, int
  bounds, bool type).
- `ALLOWED_WRITABLE_FILES` stays small.
- YAML round-trips preserve schema.
- `config/tuning.yml` in the repo always has a ≥ 1 TB
  research_model and every knob's current value passes its own
  schema.
- The loop refuses to run without the env flag.
- Invalid candidates get skipped as errors instead of partially
  applied.

101 tests pass (88 existing + 13 new). Run with:

```bash
./oglab test   # or: pytest tests/
```
