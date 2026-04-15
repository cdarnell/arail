---
title: oglab (shell)
section: docs
tags: [shell, script]
aliases: [oglab, oglab]
source: oglab
generated: 2026-04-15T01:06:26Z
---

# oglab (shell)

**Source:** `oglab`

## Overview

=============================================================================
oglab — unified entry point
Usage: ./oglab <command> [args]
setup    provision venv, deps, model, lab/ scaffolding (first-time setup)
start    launch portal + terminal + notebook + IDE
stop     stop running lab services
reset    wipe models/data/env/plugins (see: ./oglab reset help)
status   show what's running and where
doctor   validate the environment end-to-end
pkm      knowledge base ops: ingest | compile | browse
wiki     documentation-as-code: build | info | new <title>
help     show this message
=============================================================================

## Usage

```text
cat <<EOF

  $(printf '\033[1m')oglab$(printf '\033[0m') — local AI research lab

  Usage: ./oglab <command> [args]

  Commands:
    setup         provision everything (venv, deps, model, lab/ dirs)
    start         launch portal + terminal + notebook + IDE
    stop          stop running lab services
    status        show what's running
    doctor        validate the environment end-to-end
    reset [mode]  wipe state — models|data|plugins|env|full|destroy
    pkm <op>      ingest | compile | browse — knowledge base ops
    wiki <op>     build | info | new <title> — documentation-as-code
    help          this message

  Quick start:   ./oglab setup && ./oglab start

EOF
```

## Functions

- `die()`
- `say()`
- `usage()`
- `warn()`
