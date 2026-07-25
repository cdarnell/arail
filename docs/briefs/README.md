# Hand-off briefs

Self-contained specs written to be handed to a coding agent (e.g. Fable) in a
fresh session. Each brief names the files to read first, states the vision and
the hard guardrails (from `CLAUDE.md` and the "clean experience" master prompt),
and — for large efforts — instructs the agent to produce a design artifact and
STOP for operator approval before building.

| Brief | What it covers |
|-------|----------------|
| [`first-impression-experience.md`](./first-impression-experience.md) | The cold-start AND reset-into-a-new-World experience: clean, inviting, teaches what/why/how, gives a reason to return. Design-first (produce `EXPERIENCE_SPEC.md`, then stop). |
| [`video-games-world-build.md`](./video-games-world-build.md) | Build the Video Games World: Layer A a themed, source-grounded gaming World (shippable alone); Layer B the measured "optimal config for your hardware" autoresearch; Layer C optional consent-gated driver/release scouting. |

These are inputs, not records of completed work — the record of what an agent
actually designs/builds lives in its `sprints/<date>-*/` artifacts and PRs.
