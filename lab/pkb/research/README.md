---
title: research/ — the lab's research recipe
section: research
tags: [meta, contract, program, prepare, train]
---

# The Research Recipe

Three files live here. Together they're the contract between you and
the lab's autoresearch loop.

| File              | Role                                          | Authored by                | Reset wipes? |
|-------------------|-----------------------------------------------|----------------------------|--------------|
| `program.md`      | **WHAT** to research — goal, hypotheses, knobs | System drafts → you edit   | yes          |
| `prepare.py`      | **HOW** to measure — the validation contract   | Hand-written, locked       | **no**       |
| `train.py`        | **HOW** to apply a variant — config or training | System scaffolds stub → you edit | yes      |

## How a goal turns into a recipe

1. You set a goal on the dashboard (or via `POST /api/goal`).
2. The lab parses your goal and immediately writes a first draft of
   `program.md` and a stub `train.py` — within a few seconds, you'll
   see `Drafted research program — review at …` in the activity feed.
3. You open `program.md` in the Knowledge tab and edit anything you
   disagree with: tighten the hypotheses, adjust success criteria,
   add or remove sources, override the candidate knobs.
4. You click **Run autoresearch** on the Autoresearch tab.
5. `autoresearch.py` reads the recipe, runs the experiments, and
   writes results back to `lab/data/aerollm-bench.jsonl` (or the MLX
   variant). Each variant lives on its own `autoresearch/<id>` git
   branch so you can review or revert.

## Why three files instead of one

- **`program.md` is for humans.** Markdown so you can read and edit
  comfortably; YAML frontmatter so the lab can parse the structured
  bits. The optional `## Knobs` fenced YAML block is the power-user
  extension point.
- **`prepare.py` is the substrate.** The agent isn't allowed to grade
  its own homework — if the loop wants a better number, it has to
  produce a better number, not redefine "good." Reset deliberately
  leaves this file alone.
- **`train.py` is the apply step.** Most goals only need config tuning
  (the stub is a no-op for that path), but the file exists so a goal
  that needs real training (LoRA, fine-tune, distillation) has an
  obvious place to live.

## Default sources — "LLMs on disk"

The shipped default sources (referenced in the program.md the system
drafts) point at the papers, repos, and specs that anchor the lab's
signature topic — running frontier models on laptop hardware. You can
swap these out for your own topic by editing the Sources section of
`program.md` directly.

When `LAB_MODE=hybrid` AND `ARAIL_AUTORESEARCH_FETCH_EXTRAS=1`, the
drafter will also fan out a few HTTP fetches to pull abstracts of
related work into the Sources section. Off by default — airgapped
mode is the secure default.

## Resetting

- `./arail reset program` — wipes `program.md` + `train.py` + any
  curated source fetches + the autoresearch schedule. Leaves
  `prepare.py` alone.
- `./arail reset all` — also wipes the recipe, plus everything else
  (env, lab.conf, .venv, lab/data/, lab/pkb/).

You can re-draft any time from the dashboard's "Lab knows" panel
(the **Re-draft** button). Re-draft uses `force: true`, so it
*will* clobber edits — only click it when you genuinely want a
fresh draft from the current goal.
