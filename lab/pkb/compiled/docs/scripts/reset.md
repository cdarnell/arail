---
title: reset.sh (shell)
section: docs
tags: [shell, script]
aliases: [reset, reset.sh]
source: scripts/reset.sh
generated: 2026-04-15T17:33:38Z
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
    echo "  Usage: ./oglab reset [mode] [--yes]"
    echo ""
    echo "  Modes:"
    echo "    models    Remove downloaded models only"
    echo "    data      Remove experiments and data"
    echo "    plugins   Remove installed plugins"
    echo "    env       Remove .venv, .env, lab.conf"
    echo "    full      Complete wipe (everything except source code)"
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
- `reset_plugins()`
- `stop_services()`
- `usage()`
- `warn()`
