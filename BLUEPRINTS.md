# Blueprints

A blueprint is a lab you can run. It ships with a goal (or asks for one), a
set of agents, a tier config, and default models. You spin it up in a few
minutes; from there you change whatever you want.

## The principle

Here is a blueprint. Build on top of it, or replace it.

The default one is **Autoresearch**. It ships with a researcher agent, a
curator, and an experiment tracker. Give it a topic; it starts gathering,
organizing, and writing. If that's not your work, fork it. Change the agents.
Swap the models. Rewire the integrations. The Python package (`arail`) stays
the same; your lab looks different.

Rename your fork in one line of `.env`:

```bash
LAB_NAME="Sam's AI Lab"
```

Every banner, nav logo, activity line, and wiki page rebrands on restart.

## What's next

More blueprints are planned — each a fork of Autoresearch with different
agents and defaults:

- A **status digest** that reads your calendar and docs and writes a Monday
  morning update.
- An **inbox triager** that drafts replies for you to approve.
- A **client follow-up** assistant for consultants.

## Sharing a blueprint

Built one worth sharing? Open a pull request. Include a short readme that
says what goal it solves, which agents it ships, which install tier it
needs, and any external integrations.
