---
title: reset.sh (shell)
section: docs
tags: [shell, script]
aliases: [reset, reset.sh]
source: scripts/reset.sh
generated: 2026-05-16T03:56:19Z
---

# reset.sh (shell)

**Source:** `scripts/reset.sh`

## Overview

=============================================================================
${LAB_NAME} Reset — Clean wipe / selective reset
=============================================================================

## Usage

```text
echo ""
    echo -e "  ${BOLD}${LAB_NAME} Reset${RESET}"
    echo ""
    echo "  Usage: ./arailctl reset [mode] [--yes]"
    echo ""
    echo "  Modes:"
    echo "    models    Remove downloaded models only"
    echo "    data      Remove experiments and data"
    echo "    pkb       Remove the knowledge base (all notes, uploads,"
    echo "              agent findings, seed packs). Re-seeds on next start."
    echo "    pkb-seeds Remove only the seeded starter primers; keep your notes."
    echo "    program   Remove the auto-drafted research recipe (program.md,"
    echo "              train.py, curated source fetches). Keeps prepare.py."
    echo "    skills    Remove installed skill packs from lab/pkb/skills/."
    echo "              User-authored skills + AGENT.md loadouts stay put."
    echo "    plugins   Remove installed plugins"
    echo "    env       Remove .venv, .env, lab.conf"
    echo "    full      Complete wipe — keeps the knowledge base safe."
    echo "              Chain with 'pkb' if you truly want everything gone."
    echo "    destroy   Delete the entire local lab copy and app data"
    echo "    stop      Just stop running services"
    echo ""
    echo "  If no mode given, interactive menu is shown."
    echo ""
```

## Functions

- `confirm_and_run()`
- `destroy_lab()`
- `error()`
- `full_wipe()`
- `info()`
- `interactive_menu()`
- `report_size()`
- `reset_data()`
- `reset_env()`
- `reset_models()`
- `reset_pkb()`
- `reset_pkb_seeds()`
- `reset_plugins()`
- `reset_program()`
- `reset_skills()`
- `stop_services()`
- `usage()`
- `warn()`
