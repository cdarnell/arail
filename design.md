# Design Spec

This file is the design contract for ARAIL's operator-facing UI.

## Intent

- Keep the lab readable in one glance.
- Separate navigation from status.
- Make the current mission visible without letting it dominate every page.
- Let people re-skin the lab without rewriting the whole frontend.

## Navigation

- The top bar is split into two rows.
- Row 1 is status and identity:
  - brand mark on the left
  - mission chip on the right
  - clock, airgapped status, and scheduler controls on the right
- Row 2 is just the main surfaces:
  - Dashboard
  - Chat
  - Autoresearch
  - Knowledge
  - Agents
  - Skills
  - Notebooks
  - Admin
  - Docs

## Mission pattern

- The mission should be compact in shared chrome.
- Use a short mission chip in the top-right status rail.
- Clicking the mission opens a curated **Mission Dossier** view.
- The dashboard still owns mission editing and launch, but it should not feel
  like the whole page is only a form.

## Status pattern

- Airgapped / hybrid state lives in the top-right status rail.
- Halt and Resume are operational controls, not primary tabs.
- Work-window labels belong with status, not with page navigation.

## Docs pattern

- The Docs tab is a curated in-app reading surface.
- It should surface install, troubleshooting, agent docs, design, and platform
  notes without sending the operator out to GitHub.
- Any design-facing customization guidance should be reachable from Docs.

## Theme guidance

Default theme: **Blue Cyan Lab**

- Backgrounds: near-black navy, not pure black
- Primary accent: cyan / electric blue
- Secondary accent: muted green for success and active state
- Warning: amber
- Danger: vivid red
- Typography: monospace remains the default voice

Suggested pre-baked theme presets:

1. Blue Cyan Lab
   - the default ARAIL look
   - closest to the current visual language
   - high contrast, cold, crisp, operator-focused
2. Emerald Terminal
   - more classic hacker-terminal green
   - use when the operator wants the retro lab feel turned up
3. Night Amber
   - blue-black base with amber highlights
   - good for slower, warmer reading-heavy sessions
4. Slate Violet
   - muted slate base with cooler violet accents
   - good for softer personal forks of the lab

## Theme switching

- Theme presets are selected with `LAB_UI_THEME` in `.env`.
- Current shipped values:
  - `blue-cyan-lab`
  - `emerald-terminal`
  - `night-amber`
  - `slate-violet`
- The Admin page should always show the active preset and the exact env line to copy.
- Restart the lab after changing the preset.

## Theming implementation guidance

- Prefer CSS variables over one-off color overrides.
- Keep theme changes concentrated near the root token block.
- Avoid re-theming individual components in isolation.
- Preserve semantic roles:
  - primary action
  - active surface
  - success
  - warning
  - danger
  - muted text

## Interaction guidance

- The dashboard should feel like a cockpit, not a settings page.
- Large actions should stay obvious.
- Secondary detail should be reachable in one click from compact surfaces.
- If a new surface competes with Dashboard or Chat for attention, it is probably
  too loud.