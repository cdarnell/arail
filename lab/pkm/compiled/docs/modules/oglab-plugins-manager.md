---
title: manager module
section: docs
tags: [python, module]
aliases: [manager, manager.py]
source: src/oglab/plugins/manager.py
generated: 2026-04-15T00:51:55Z
---

# manager module

**Source:** `src/oglab/plugins/manager.py`

PluginManager — clone GitHub repos and integrate them as lab tools.

Usage from portal:
    POST /api/plugins/install  {"github_url": "https://github.com/user/repo"}

The manager:
1. Clones the repo into ./plugins/<name>/
2. Reads README + requirements.txt
3. Installs deps into the active venv
4. Registers the plugin in a manifest

## Classes

### `PluginManager`

Manages installation and lifecycle of GitHub-sourced plugins.

**Methods:**

- `__init__(self)`
- `install(self, github_url)`
    - Clone a GitHub repo and register it as a plugin.
- `uninstall(self, name)`
    - Remove a plugin by name (owner/repo).
- `list_plugins(self)`
- `get_plugin(self, name)`
- `get_readme(self, name)`
- `toggle(self, name, active)`
