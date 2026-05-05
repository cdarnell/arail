# Sprint: airgap-honest-mode

**ID:** 2026-05-05-airgap-honest-mode
**Started:** 2026-05-05
**Product:** arail
**Branch:** `qukaizen/arail-airgap-honest-mode` (cut from `origin/main` @ 9aa8354)

## Task

Close the airgap gap. Today `LAB_MODE=airgapped` only blocks the cloud-LLM
provider endpoints in the Chat tab; the README claims "the lab makes zero
network calls" but agents can reach the internet through several paths
(Buddy's HF papers fetch behind the unrelated `LAB_INTERNET_ENABLED` flag,
any future raw `requests.get(...)` call written by an agent author, etc.).

Redefine `airgapped` to mean **"agents cannot collect information from
the internet."** Local services (loopback + RFC1918 + link-local) stay
reachable so the common LAN-GPU-box setup keeps working. Enforce at the
HTTP-client layer with a Python-level egress guard that wraps `requests`
and `urllib`, raises `EgressBlocked` loudly on deny, and writes one line
per block to `lab/data/egress.jsonl`. Surface the operational definition
in a nav-badge modal. Add a Buddy watcher that posts a chat heads-up on
each block and on every `LAB_MODE` toggle. Fix the README + PRIVACY docs
to match reality.

Approved plan and full architecture sketch in `PLAN.md` (this sprint dir).

## Phases

| Phase | Subagent | Artifact | Status | Started | Finished | Verdict |
|---|---|---|---|---|---|---|
| think | visionary | VISION.md | done | 2026-05-05 | 2026-05-05 | proceed |
| plan | architect (design) | ARCHITECTURE.md | done | 2026-05-05 | 2026-05-05 | proceed |
| build | builder | BUILD_LOG.md | pending | — | — | — |
| review | architect (review) | REVIEW.md | pending | — | — | — |
| test | qa | TEST_REPORT.md | pending | — | — | — |
| ship | — | PR | pending | — | — | — |

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-05 | Local allow-list = loopback + RFC1918 + link-local | Common arail setup is GPU box on LAN (Ollama/vLLM); loopback-only would force reverse tunnels. Attacker on your LAN is past the airgapped threat boundary. |
| 2026-05-05 | Block behavior = raise `EgressBlocked` (RuntimeError subclass), no synthetic-response fallback | Loud failure is the airgapped value prop. Silent stub responses let agents pretend they got data. |
| 2026-05-05 | v1 Buddy awareness = airgapped events only | LAB_MODE toggle + egress.jsonl tail. Theme/UI toggle awareness deferred to a follow-up sprint. |
| 2026-05-05 | `setup.sh` is out of scope | Runs before portal boot; guard installs at portal-startup / agent-load time. Initial weight downloads aren't agent-collected info. |
| 2026-05-05 | Branch cut fresh from origin/main | Independent of `qukaizen/arail-airllm-subprocess-isolation`; benchmark_models.py changes stashed for that branch. |
| 2026-05-05 | Modal CSS: inline-duplicate in airgap modal template (do NOT extract to style.css this sprint) | Architect-recommended; keeps blast radius small. Cleanup is a follow-up. |
| 2026-05-05 | Repave Buddy duplication this sprint (canonical = `src/arail/agents/_builtin_buddy.py`) | User chose cleaner end state. PKB version is gitignored — duplication was workstation-only. Architect addendum (`af5c1c1`) reflows implementation order: repave is step 3, watcher single-file at step 6. |
| 2026-05-05 | Egress probe stays opt-in via `BUDDY_EGRESS_PROBE=1` | Documented as the only intentional exemption; surfaced in README, PRIVACY.md, and modal known-gaps. |

## Skipped phases

| Phase | Reason |
|---|---|
| (none) | full pipeline — security-relevant change with bypass paths the architect must explicitly review |

## Notes

- Plan file: `PLAN.md` (snapshot of the approved plan from
  `~/.claude/plans/ok-yeah-let-s-add-gleaming-dolphin.md`).
- Architect's paranoid review must explicitly address bypass paths:
  `httpx`, `aiohttp`, raw `socket`, subprocess `curl`/`wget`, `os.system`.
  Decide: block at agent-import time, document as known gap, or both.
- QA allocation per arail product gate: 30% setup, 30% Buddy, 20%
  security, 10% happy, 10% regression. Security tests must include
  the bypass attempt list.
- Pre-sprint stash: `lab/tools/benchmark_models.py` changes stashed as
  `stash@{0}` (`WIP airllm-subprocess-isolation: benchmark_models.py
  changes (pre-airgap-sprint stash)`). Restore on `qukaizen/arail-airllm-subprocess-isolation`
  via `git stash pop` when this sprint completes.
