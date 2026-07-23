# Make ARAIL a cleaner experience — master prompt

> Reusable prompt for any session (any model) working on ARAIL polish, features, or
> review. Paste it, or point the session at this file. Born from the 2026-07-23 platform
> assessment (see `ASSESSMENT.md` in this directory).

You are working on ARAIL, a local-first AI research lab whose purpose is to **educate
the user and be an intuitive, inviting playground to explore the powers of AI** — safe
to hand to a non-expert friend. Apply these principles to every change:

1. **Truth-in-UI is the prime directive.** Every surface states what it actually does.
   No copy promising capabilities the code doesn't deliver. If a feature depends on
   something not installed, say so with an actionable next step — never a silent error.
2. **Never fabricate.** Every number shown was measured by code on this machine, or it
   doesn't exist. Honest outcomes include "cannot run" and "unmeasured". Model-authored
   text is always labeled (measured / heuristic / model-narrated) — extend the planning-
   trace provenance pattern, never dilute it.
3. **Nothing probes or blocks unless the user asks.** No synchronous LLM, rebuild, or
   network work in the boot path; every package/version/model check runs only from
   `arailctl doctor` or an explicit button. `ARAIL_AUTOCHECKS` (default off) gates all
   background loops. The airgap/egress guard is load-bearing — never weaken it.
4. **The knowledge contract is sacred:** agents read only human-approved knowledge
   (compiled-KB gate stays fail-closed); no undisclosed egress; no user text in
   third-party URLs; wipe-PKB-wipes-memory with no override holes; transcripts are
   `.jsonl`, never `.json`.
5. **One honest path per user goal.** One name per action, used everywhere. Plain
   language over acronyms. Model building means: persona-wrap (2 commands), the
   distill-now pipeline when it lands, and nothing pretending otherwise.
6. **Say where things land.** Any feature that writes artifacts documents the path
   (`docs/models-on-disk.md` is the registry of record).
7. **Default to inviting.** First-run experience must produce a real, measured win in
   five minutes on a fresh machine with no cloud account. Friendly on-theme defaults;
   failure states teach instead of intimidate.
8. **Docs describe what exists.** Unbuilt designs carry a ROADMAP banner. Prune dead
   surfaces rather than letting them rot. Verify claims against disk before asserting.
9. **Keep and finish the good primitives** (gate, trace, airgap, resume, design tokens)
   — close the last mile; don't rebuild.
10. **Don't break the contracts:** internal package name `arail`; MIT license; "Built
    with Llama" disclosure intact; tokens to `lab/data/secrets.env` 0600, never logged;
    `LAB_MODE=airgapped` default; routes stable (rename labels, not endpoints).
