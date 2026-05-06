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
| build | builder | BUILD_LOG.md | done | 2026-05-05 | 2026-05-05 | proceed |
| review | architect (review) | REVIEW.md | done (1st pass) | 2026-05-05 | 2026-05-05 | BLOCK — loops to build |
| build (loopback 1) | builder | BUILD_LOG.md (append) | done | 2026-05-05 | 2026-05-05 | _save_state fix + audit comments |
| plan addendum #2 | architect (design) | ARCHITECTURE.md (append) | done | 2026-05-05 | 2026-05-05 | SRE de-duplication |
| build (loopback 2) | builder | BUILD_LOG.md (append) | done | 2026-05-05 | 2026-05-05 | SRE repave per addendum #2 |
| review (re-pass) | architect (review) | REVIEW.md (append) | done | 2026-05-05 | 2026-05-05 | PASS |
| test | qa | TEST_REPORT.md | done (1st pass) | 2026-05-05 | 2026-05-05 | WEAK_PASS — 1 real bug (Buddy watcher ValueError on malformed state.json) |
| build (loopback 3) | builder | BUILD_LOG.md (append) | pending | — | — | — |
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

## Loops

| When | Phase | Trigger | Resolution |
|---|---|---|---|
| 2026-05-05 | review → build | BLOCK on Buddy watcher state-key persistence (`_save_state()` overwrites watcher keys with only BuddyAgent's 5 keys; offset lost across restarts). Plus ASK on 3 misleading `# noqa-airgap` comments at `backends.py:231,440,590`. | Builder loopback 1 (commits `faa6898`, `4f641e0`, `df44306`): read-merge-write in `_save_state` + regression test + audit comment corrections. Done. |
| 2026-05-05 | mid-flight finding → architect addendum #2 → build | Orchestrator discovered SRE has the same canonical-vs-PKB duplication Buddy had pre-repave. Builder's PKB SRE edit was on disk but gitignored; would be overwritten by `ensure_sre_folder()`'s `shutil.copy` of the unmodified canonical. User chose: repave SRE this sprint (mirror Buddy). | Architect addendum #2 committed (`426df90`) — option (a) port PKB-only logic INTO canonical, ~150 lines / 5 symbols ported, 0 dropped. Builder loopback 2 (`fc0aa8f`, `64aeb50`, `faca252`) — 614 lines canonical post-port, 19-name shim. Re-review verdict PASS (`419e605`). |
| 2026-05-05 | qa → build | QA WEAK_PASS — 1 real bug: Buddy watcher raises `ValueError` if `state.json` has a non-int `airgap_last_egress_offset` (degraded-state robustness miss). Per arail's CLAUDE.md, Buddy quality is 30% of QA gating; user chose to fix before ship. | Builder loopback 3 in flight: one-line `try/except (ValueError, TypeError):` at `_builtin_buddy.py:513` matching the pattern `_load_state` already uses. |

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
