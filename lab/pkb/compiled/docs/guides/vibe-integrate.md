---
title: Vibe Integrate
section: docs
tags: [guide]
aliases: [vibe-integrate]
source: docs/vibe-integrate.md
generated: 2026-05-16T03:56:19Z
---
# Arail — Vibe Integration During Setup

Vibe integration is the first-run act of translating the Arail blueprint to
someone else's machine, constraints, and goals. It is not "vibe developing" a
new app. The job is to preserve the same local-first setup and operator UX
while making it land cleanly on the target hardware.

## Where This Forks From

Start with the shared install path in [INSTALL.md](INSTALL.md) and then layer in
the platform notes from [MACOS.md](MACOS.md), [LINUX.md](LINUX.md), or
[WSL.md](WSL.md). This page is the judgment layer on top of those docs: how an
agent or operator adapts the same setup flow for a Mac mini, a newer MacBook
Pro, or a friend's lab without inventing a different product.

If the task is adding package-manager or distro support to
[../scripts/setup.sh](../scripts/setup.sh), that is a platform port. Use
[../AGENTS.md](../AGENTS.md) and [LINUX.md](LINUX.md) for that path.

## Setup Flow

1. Start from the blessed commands: `./arailctl setup`, `./arailctl doctor`, and
    `./arailctl start`.
2. Profile the target machine before changing anything: chip family,
    accelerator, RAM, free disk, and whether the box is portable, desk-bound, or
    effectively headless.
3. Profile the target user: first goal, lab name, privacy posture, and how much
    complexity they can tolerate on day one.
4. Pick the smallest stable tier, backend, and starter model that fit that
    machine.
5. Run setup and let it write `.env`, scaffold the lab, and capture the first
    goal.
6. Start the lab and verify the Dashboard, Chat, and Autoresearch surfaces all
    load on the target machine.
7. Hand off a working first-run experience where the Researcher agent already
    has a real goal to pick up.

## Example: Mac Mini Versus MacBook Pro

The same blueprint should feel different only where the hardware envelope is
actually different.

- A Mac mini usually wants an appliance mindset: quieter always-on usage,
  conservative disk budgeting, and setup choices that survive being left alone
  on a desk.
- A newer MacBook Pro usually wants a personal workbench mindset: browser-first
  startup, higher MLX headroom, and defaults tuned for interactive local work.
- In both cases the command surface stays the same. The integration work is not
  redesigning Arail; it is choosing the right tier, backend, starter model, and
  operating assumptions for that machine.

## Principles To Preserve

1. **One command surface** — Keep the mental model anchored on
    `./arailctl setup`, `./arailctl doctor`, and `./arailctl start`.
2. **Local-first baseline** — Cloud providers stay off until the user opts into
    `LAB_MODE=hybrid`.
3. **Idempotent setup** — Re-running setup should heal a partial install rather
    than forcing a clean slate.
4. **Progressive disclosure** — The user should meet the goal prompt and the
    core surfaces first; heavier agent behavior unfolds after the lab is up.
5. **Visible work** — Setup and startup should make progress legible rather than
    hiding it behind a black box.

## Where The Researcher Agent Fits

The Researcher agent is part of the initial setup experience, but it is not the
whole story.

- Setup captures the first goal and machine defaults.
- Startup makes the dashboard and activity feed legible.
- The Researcher agent then picks up that goal inside an already-working lab.

That is the right level of integration: setup establishes the environment, then
the researcher loop proves the environment is useful.

## Agent Brief

When an agent is doing vibe integration for someone else, the loop should be:

1. Read the install and platform docs first.
2. Detect the target machine's actual ceiling.
3. Adjust configuration and setup choices without redesigning the app.
4. Preserve Arail's local-first, consent-first, visible-progress defaults.
5. Stop when that person can run the same commands and get a working lab.

Contributions that improve this path should keep the setup story clear and
machine-specific without splintering the product surface.
