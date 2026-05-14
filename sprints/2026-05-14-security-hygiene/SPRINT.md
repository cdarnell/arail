# Sprint: security-hygiene

**ID:** 2026-05-14-security-hygiene
**Started:** 2026-05-14T21:29:13Z
**Product:** arail
**Branch:** qukaizen/arail-security-hygiene (cut from main)

## Task

Close four deferred security-shaped follow-ups in one sprint. Items share
security framing but touch four different code surfaces — architect must
partition cleanly so the items don't entangle.

### Items

1. **PRIVACY.md trust-model paragraph** — Document that 127.0.0.1 is the
   lab's trust boundary: any loopback peer has full host privileges. One
   paragraph added to `docs/PRIVACY.md`. Source: `sprints/2026-05-04-opencode-in-workbench/SPRINT.md`
   carryover #2.

2. **Token redaction in opencode logs** — `lab/logs/opencode.log` may
   contain provider tokens that opencode received via env. Redact at
   write-time or rotate aggressively. Source:
   `sprints/2026-05-04-opencode-in-workbench/SPRINT.md` carryover #4
   (architect F-SEC-4).

3. **`os.setsid` for opencode subprocess** — Spawn opencode with
   `os.setsid` (or `preexec_fn=os.setsid`) so portal SIGTERM cascades
   and the child isn't orphaned on portal kill. Source:
   `sprints/2026-05-04-opencode-in-workbench/SPRINT.md` carryover #5
   (architect F-PROC-3).

4. **Sec-Fetch-Site defense-in-depth on `/api/airgap/toggle`** — Now that
   the confirm-token is gone (sprint 2026-05-14-airgap-onetap-toggle),
   the `Origin` header is the sole browser-CSRF defense. Add
   `Sec-Fetch-Site` check as a modern complement. Source:
   `sprints/2026-05-07-airgap-runtime-toggle/REVIEW.md` follow-up #1
   and `sprints/2026-05-14-airgap-onetap-toggle/REVIEW.md` tech debt.

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | skipped | — | — | — |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-05-14T21:29Z | 2026-05-14T21:33Z | proceed (4 items partitioned, 5f1dda8) |
| build | builder | BUILD_LOG.md | pending | — | — | — |
| review | architect (review) | REVIEW.md | pending | — | — | — |
| test | qa | TEST_REPORT.md | pending | — | — | — |
| ship | — | PR | pending | — | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-14 | Skip visionary phase | Bug-fix shape; four security follow-ups with documented prior-sprint sources. No strategic ambiguity. |
| 2026-05-14 | Bundle four items in one sprint | Shared security framing + shared QA pass amortizes overhead. Architect must partition scope cleanly so the items don't entangle. |

## Skipped phases

| Phase | Reason |
|---|---|
| think | Bug-fix shape with concrete carryover sources. |

## Notes

- Per `arail/CLAUDE.md` QA allocation: 30% setup / 30% Buddy / 20% security
  / 10% happy / 10% regression. Security weight applies to all four items.
- Architect should produce one ARCHITECTURE.md covering all four, with
  a clear per-item subsection. Failure modes per item.
- Affected code surfaces (working set):
  - Item 1: `docs/PRIVACY.md`
  - Item 2: opencode subprocess wiring + log file handling — find with
    `grep -rn "opencode" src/arail/`
  - Item 3: same surface as item 2 (subprocess spawn site)
  - Item 4: `src/arail/portal/app.py` `/api/airgap/toggle` (single
    function-level edit) and a JS-side check in
    `src/arail/portal/static/nav.js` if needed
- Prior-sprint reference artifacts (architect must read before designing):
  - `sprints/2026-05-04-opencode-in-workbench/REVIEW.md`
  - `sprints/2026-05-04-opencode-in-workbench/BUILD_LOG.md`
  - `sprints/2026-05-07-airgap-runtime-toggle/REVIEW.md`
  - `sprints/2026-05-14-airgap-onetap-toggle/REVIEW.md`
  - `sprints/2026-05-14-airgap-onetap-toggle/ARCHITECTURE.md`
    (threat-model delta on Origin/loopback gates)

## How to resume this sprint

If interrupted:
```
git checkout qukaizen/arail-security-hygiene
cat sprints/2026-05-14-security-hygiene/SPRINT.md
```
Then continue from the next pending phase row.
