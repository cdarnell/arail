<!--
Thanks for sending a PR! Keep this short — reviewers should be able to
pick up cold and understand what changed and why.
-->

## What this changes

<!-- One paragraph. What's different after this PR? -->

## Why

<!--
One paragraph. The motivation — the bug it fixes, the user need it
addresses, or the constraint it removes. PRs without "why" get
asked about it; save the round trip.
-->

## How to verify

<!--
Concrete steps. The reviewer should be able to copy-paste these.
-->

- [ ] `./arailctl setup` still completes end-to-end on a clean checkout
- [ ] `pytest` passes (note any pre-existing failures separately)
- [ ] If portal-facing: opened the affected tab in a browser and clicked through

## Surface(s) touched

<!-- Check all that apply -->

- [ ] Setup / CLI (`arailctl`, `scripts/setup.sh`)
- [ ] Portal (FastAPI app, templates, static assets)
- [ ] Agents (Buddy / SRE / Researcher / new)
- [ ] Knowledge Base ingest / LanceDB
- [ ] Autoresearch loop
- [ ] Tier gating / surface visibility
- [ ] Compute Source / chat backends
- [ ] Docs only
- [ ] Tests only

## Tier impact

- [ ] Minimalist behaviour unchanged or improved
- [ ] Maximus behaviour unchanged or improved
- [ ] N/A — no tier-facing change

## Notes for reviewer

<!--
Anything they'd otherwise have to dig for: trade-offs you considered,
follow-ups you deferred, files that look big but are mechanical.
-->
