---
title: gentoo-bootstrap.sh (shell)
section: docs
tags: [shell, script]
aliases: [gentoo-bootstrap, gentoo-bootstrap.sh]
source: scripts/gentoo-bootstrap.sh
generated: 2026-04-25T04:17:15Z
---

# gentoo-bootstrap.sh (shell)

**Source:** `scripts/gentoo-bootstrap.sh`

## Overview

!/usr/bin/env bash
=============================================================================
Arail — Gentoo System Bootstrap

Run this ONCE on a fresh Gentoo install to compile the full AI lab stack:
- Python + ML libraries
- WezTerm (terminal)
- ttyd (terminal-in-browser)
- Jupyter
- Avahi (mDNS for arail.local)
- Nvidia/CUDA (if GPU present)
- FastAPI portal dependencies

Usage:  sudo ./platform/gentoo-bootstrap.sh
=============================================================================

## Functions

- `depend()`
- `error()`
- `info()`
- `warn()`
