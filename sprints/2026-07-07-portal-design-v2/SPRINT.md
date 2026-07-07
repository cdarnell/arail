# Sprint: 2026-07-07-portal-design-v2

**Branch:** `qukaizen/portal-design-v2`
**Goal:** Complete visual overhaul of the ARAIL portal — "Modern Lab, Technical Edge" design system v2 with a token architecture that DaC World themes can drive (Sprint 2 follow-up: `world-theme-data`).

## Ledger

| Phase | Description | Status | Artifact |
|---|---|---|---|
| think | Win condition locked by user-approved plan (aesthetic, world theming depth, light-readiness, scope) | done (plan approval supersedes VISION.md) | ARCHITECTURE.md §Decisions |
| plan | Architecture from exploration + Plan agent, approved by user | done | ARCHITECTURE.md |
| build 0 | Prep: branch, launch.json, delete chat.legacy.html, pytest baseline | in progress | BUILD_LOG.md |
| build A | Foundation: base.html, token contract v2, ui_theme.py restructure, self-hosted fonts, retire nav.js theming | pending | BUILD_LOG.md |
| build B | Ultracode design panel → default theme + component pass | pending | BUILD_LOG.md, design mockups |
| build C | Per-surface fan-out (C1–C6) | pending | BUILD_LOG.md |
| review | Architect review of foundation + surfaces | pending | REVIEW.md |
| test | Smoke, recolor regression, token-compliance lint, visual pass | pending | TEST_REPORT.md |
| ship | Merge to main | pending | — |

## Notes

- Full plan of record: ARCHITECTURE.md (seeded from the user-approved plan file).
- Phase D (world theme block in face.json + validator + switcher previews) is deliberately split into Sprint 2 (`world-theme-data`) — only dependency is the Phase A3 UITheme structure.
- OOM caution on this machine: single uvicorn instance for visual verification, no --reload.
