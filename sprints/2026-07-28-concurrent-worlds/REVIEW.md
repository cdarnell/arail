# Review: Concurrent Worlds as independent instances

**Date:** 2026-07-28
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `5cef466`
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at `f28e525`
**Diff reviewed:** `a2bb7f8..5cef466 -- . ':!sprints'` (29 files, +4411/−61)
**Mode:** review

## Verdict: BLOCK

Two BLOCKER findings. Both are on the `arailctl` entry-point paths — the exact
surfaces this sprint set out to make trustworthy — and both fail *silently*,
which is the failure shape VISION named as the harm. Everything else is good
work: the registry design is sound, the O_EXCL claim is correct, the kill path
is genuinely verified for the two uvicorn PIDs, and 86 new tests pass.

---

## 1. Failure-mode cross-reference (F1–F17)

| # | Status | Evidence / assessment |
|---|---|---|
| F1 | **PARTIAL** | Child-death detection works (`start.sh:521-523`), but the readiness probe (`start.sh:524`) only checks that `/api/instance` returns 200 — it never compares `token` or `checkout`, which §3.5 stage 5 requires verbatim ("require token **and** checkout match"). The named error text (`port … was taken during startup`) is also absent; the operator gets the generic `portal did not come up`. See **M1**. |
| F2 | **DONE** | `inst_prune`/`inst_prune_all` (`instances.sh:185-206`), pruned by `status` after render (`status.sh:173`) and by `start` stage 3 (`start.sh:389`). Data untouched. |
| F3 | **PARTIAL** | Portal + memory PIDs verified on module *and* port (`reset.sh:206-221`) — correct. The **launcher** check (`reset.sh:226`) is a bare substring test and is unsound. See **M2**. |
| F4 | **DONE (fragile)** | `status --probe` renders the mismatch line (`status.sh:156-158`). `checkout` is `Path.cwd()` in the portal (`app.py:3304`) vs `REPO_ROOT` from `cd … && pwd` in the shell — logical vs physical path; symlinked checkouts make step 4 fail permanently. See **m5**. |
| F5 | **DONE for `start`** | `_instance_resolve_world` (`start.sh:249-295`) applies `_SLUG_RE` + prefix jail + `verify_seal`, and runs at stage 2 — **before** any directory is created (stage 4). Verified. Not applied to `stop --world`; see **M5**. |
| F6 | **PARTIAL** | `set -o noclobber` in a subshell (`start.sh:400`) is a correct O_EXCL race guard, and the 120 s stale-break is present (`start.sh:392-399`). But the spec says "trap … **EXIT** removes the claim on every exit path"; only `INT` and `TERM` traps are installed (`start.sh:402-403`). See **M4**. |
| F7 | **DONE** | `data_root_missing` computed (`status.sh:67-69`), rendered (`status.sh:161-162`), record not pruned. |
| F8 | **NOT REACHABLE** | `start.sh:317-322` implements the refusal, but `arailctl:225-241` intercepts `start` first when `daemon_active` and never reaches `start.sh`. See **B2**. |
| F9 | **DONE** | `daemon_active` = plist + numeric launchctl PID (`instances.sh:299-310`); `start.sh:59-61` prints the dim informational line. The trap is retired. Pinned by `test_daemon_predicate.py`. |
| F10 | **DONE** | `start.sh:326-342`; refuses, prints roster + stop command, no eviction; `LAB_MAX_INSTANCES ≥ 4` soft-warns per §3.7. |
| F11 | **DONE** | 409 `instance_live` inserted after the path jail and after the CSRF envelope (`app.py:3403-3421`). Keyed on `bundle_dir.name`. |
| F12 | **DONE** | 20 s cap, warn-and-continue (`start.sh:546-558`). |
| F13 | **DONE** | Ollama probe warn-and-continue; pidfile written to the instance's own data dir (`start.sh:563-580`). |
| F14 | **DONE** | `_assert_instance_paths_absolute()` at import (`app.py:65-90`), gated on `ARAIL_INSTANCE`, names the offending key. Root lab unaffected. Subprocess-level test present. |
| F15 | **REGRESSED** | The port-scoping is present (`reset.sh:120-122`) and does stop root-lab-stop from reaching instances — but `reset.sh` never sources `lab.conf`, so on any machine where setup bumped a port the root lab is no longer stopped at all. See **B1**. Also defeated by the launcher-trap path, **M3**. |
| F16 | **PARTIAL** | Quarantine works (`instances.sh:141-143`). The `✗ unreadable` row (`status.sh:61-64`, `status.sh:147-149`) is **unreachable**: `inst_list_slugs` (`instances.sh:176`) already calls `inst_read_record`, which quarantines the file, so the slug never enters the loop. Corrupt records disappear with no operator-visible message. See **M7**. |
| F17 | **PARTIAL** | Stage 5 refuses on a busy port and prints the `lsof` command (`start.sh:502-506`), but does not list the PID holding the port as §8 F17 specifies. No auto-kill — correct. |

**Scorecard: 9 implemented as specified, 6 partial, 1 regressed, 1 unreachable.**

---

## 2. Findings by severity

### BLOCKER

**B1 — `./arailctl stop` silently stops nothing on a port-bumped machine.**
`scripts/reset.sh:120-122` (introduced by WP5)

```
"uvicorn.*arail\.portal\.app.*--port ${PORTAL_PORT:-8080}"
"uvicorn.*arail\.memory_service.*--port ${LANCE_PORT:-7414}"
"uvicorn.*arail\.mlx_openai_server.*--port ${MLX_OPENAI_PORT:-11435}"
```

`reset.sh` sources `.env` (`:31`) but **never `lab.conf`** (verified: `lab.conf`
appears in `reset.sh` only at `:484` and `:570`, both unrelated). `lab.conf` is
where `setup.sh:1637-1646` writes the *resolved* — possibly auto-bumped —
`PORTAL_PORT`/`MLX_OPENAI_PORT`, and `.env.example:335` ships a static
`PORTAL_PORT=8080`. `start.sh:30-32` sources both, so the lab runs on the
lab.conf port; `reset.sh` matches the `.env`/default port. Result: on every
machine where 8080 (or 11435) was occupied at setup time, `./arailctl stop`
prints `No running services found.` and leaves the lab running. Before this
sprint the pattern was port-agnostic and worked.

This is a silent regression on the primary stop path, and the ARCHITECTURE's own
§6.2 ruling ("`lab.conf` without `set -a` — IN SCOPE") was applied to `start.sh`
but not extended to the file that newly *depends* on those values.

*Fix:* add, immediately after `reset.sh:31`:
`[[ -f lab.conf ]] && set -a && source lab.conf && set +a`
and add a `test_instance_stop_scope.py` case with `lab.conf` pinning a bumped
`PORTAL_PORT` asserting `stop_services` still matches.

---

**B2 — `./arailctl start --world <slug>` silently discards `--world` under
daemon mode.**
`arailctl:224-243`

```
start)
    if daemon_active; then
        for label in $(daemon_agents); do launchctl load … ; done
        launchctl kickstart "gui/$(id -u)/io.arail.portal" …
        echo "Lab supervised by launchd — portal: http://…:${PORTAL_PORT:-8080}"
        exit 0
    fi
    exec bash "$REPO_ROOT/scripts/start.sh" "$@"
```

`"$@"` is never inspected in the daemon branch. On a daemon-active machine,
`./arailctl start --world finance` kickstarts the **root lab**, prints a success
line naming the wrong lab, and **exits 0**. F8's named refusal and the two-line
remedy (`start.sh:317-322`, `ARCHITECTURE §4.4`) are dead code — nothing can
reach them, because `arailctl` short-circuits first.

This re-introduces, in a new place, precisely the defect §3.1 forbids
("Silently ignoring argv is the bug we are fixing; do not re-introduce it in a
new place") and it does so on the *daemon* path, i.e. the same trap family that
motivated the sprint.

*Fix:* in `arailctl`'s `start)` branch, before the `daemon_active` test, detect
`--world`/`--list`/`--help` in `"$*"` and `exec` `start.sh` unconditionally for
those (letting `start.sh:317-322` own the refusal message); or move the whole
daemon branch into `start.sh` after arg parsing. Add a `test_daemon_predicate.py`
case driving the real `arailctl` `start)` branch with `--world` and a stubbed
`launchctl`, asserting exit ≠ 0 and that the message names the slug.

---

### MAJOR

**M1 — The readiness probe does not verify the token or the checkout.**
`scripts/start.sh:524`

```
if curl -sf -m 0.7 "http://${BIND}:${portal_port}/api/instance" >/dev/null 2>&1; then
```

§3.5 stage 5 and §2.3 step 4 both require token **and** checkout equality here;
this only requires HTTP 200. The registry record is written on the strength of
this check (`start.sh:614`), so §2.2's core guarantee — "a record's existence
means this instance was, at some point, actually serving" — is downgraded to
"*something* answered on this port." The window is narrow (uvicorn exits on
`EADDRINUSE`, and the loop breaks on child death), but it is exactly F1's
scenario, and it is wide open on any host without `lsof`/`ss`, where
`_port_in_use` (`setup.sh:298-306`) returns "assume free" and stage 5 is a no-op.

*Fix:* capture the response body, and require
`token == $instance_token && checkout == $REPO_ROOT` before setting
`portal_ready=1`. On mismatch, kill the child and emit the F1 message naming the
port. A driver scenario with a stub server answering `/api/instance` with a
foreign token should assert exit 1 and no registry record.

---

**M2 — Launcher-PID "verification" is a substring test that matches any ARAIL
launcher.**
`scripts/reset.sh:226`

```
if [[ -n "$cmd" && "$cmd" == *"start.sh"* && "$cmd" == *"$slug"* ]]; then
```

The launcher cmdline is `bash /Users/…/qukaizen-arail/scripts/start.sh --world finance`.
For the slug `ai` — the architecture's own worked example (§1.1, §4.1) — the
substring `ai` is present in `arail` in the *path*, so **every** ARAIL
`start.sh` process passes this check. A stale `ai` record whose `launcher_pid`
has been recycled onto the `finance` launcher means `./arailctl stop --world ai`
SIGTERMs the finance lab. §4.2 step 2 says an unverified PID is "skipped and
reported — never killed"; this check does not deliver that.

*Fix:* require the exact token pair, e.g.
`[[ "$cmd" == *"/scripts/start.sh"* && "$cmd" == *"--world $slug"* ]]`
(and accept `--world=$slug`). Add a stop-scope test with slug `ai` and a decoy
`start.sh --world finance` process asserting it is skipped.

---

**M3 — `stop --world X` can kill the machine-shared Ollama out from under
instance Y.**
`scripts/reset.sh:239` (kill of the launcher) → `scripts/start.sh:403,639,234-245`

`stop_instance` SIGTERMs the launcher; the launcher's TERM trap runs
`_instance_cleanup_and_exit`, which kills **every** PID in `_INST_PIDS` —
including `ollama_pid` when this instance was the one that started
`ollama serve` (`start.sh:567-569`). That fires *before* and *regardless of*
`stop_instance`'s careful `remaining == 0` last-instance guard at
`reset.sh:262-271`. Ctrl-C on the same launcher does the same thing. Net: the
shared model backend can die while a sibling instance is live — a cross-instance
side effect §11 forbids ("Nothing cross-instance") and A32.4 depends on not
happening.

*Fix:* exclude the Ollama PID from `_INST_PIDS`; track it separately and, in
`_instance_cleanup_and_exit`, kill it only when no other slug satisfies
`inst_alive`. Same guard the `stop_instance` path already implements — it just
needs to live in the launcher too. Regression test: two stub instances, TERM the
first launcher, assert the ollama stub survives.

---

**M4 — No `EXIT` trap: a `set -e` abort between stage 3 and the record write
leaks the claim.**
`scripts/start.sh:400-403`

Only `INT` and `TERM` are trapped. Every *explicit* failure path correctly calls
`_instance_cleanup_and_exit`, but the implicit `set -euo pipefail` aborts do not:
`inst_write_env_pack` failing (`:435`, `:471`), `source "$pack_file"` failing
(`:496`), `inst_load_port_helpers` failing (`:501`), the `python3` record
serialiser failing (`:600-613`), or `SIGHUP` from a closed terminal. F6's text is
explicit: "trap … **EXIT** removes the claim on **every** exit path." The 120 s
stale-break bounds the damage, but within that window a retry is refused with
`another start for 'X' is in progress (pid <dead pid>)` — a misleading message
for a wedged slug.

*Fix:* `trap '_instance_cleanup_and_exit $?' EXIT` immediately after the claim
succeeds, and clear it (`trap - EXIT`) once the launcher enters its final `wait`.

---

**M5 — `stop --world` has no slug jail: path traversal read plus arbitrary
`*.json` deletion.**
`scripts/reset.sh:649,689` → `scripts/lib/instances.sh:71-74,193,272`

`STOP_WORLD` is taken verbatim from argv and passed straight to `stop_instance`,
which calls `inst_read_record` → `inst_registry_file` →
`"$REPO_ROOT/lab/instances/registry.d/${slug}.json"`. Nothing calls
`inst_valid_slug`. `./arailctl stop --world ../../../../tmp/x` reads
`/tmp/x.json`, and if it parses as JSON, `reset.sh:272`'s
`rm -f "$(inst_registry_file "$slug")"` **deletes it**. §9 Security #2 requires
the jail on `--world`; `start.sh` has it (stage 2), the destructive path does
not.

*Fix:* at `reset.sh:687`, `inst_valid_slug "$STOP_WORLD" || { error "invalid
World slug"; exit 2; }`. Same for any future `--world` consumer. Add a security
test asserting `--world ../foo` exits 2 and touches nothing.

---

**M6 — Instance PKBs are unreachable by every `reset` mode; the "wipe the PKB =
wipe memory" contract is silently broken for instances.**
`scripts/reset.sh:316,338,371` (all target the root `MODELS_DIR`/`DATA_DIR`/`pkb_dir`)

`reset pkb`, `reset data`, and `reset full` all operate on the root lab's
`config.py`-resolved paths. `lab/instances/<slug>/pkb/` — which holds that
instance's conversations, staged World layer, and LanceDB index — is untouched
by all of them, and `lab/instances/<slug>/data/secrets.env` survives `reset env`.
CLAUDE.md states the contract flatly ("wipe the PKB = wipe memory"), and
`docs/conversation-memory.md` and `docs/agents.md` both lean on it. Neither
`docs/concurrent-worlds.md` nor `CHANGELOG.md` mentions the gap (grepped: no
occurrence of `reset`/`wipe` in `docs/concurrent-worlds.md`).

This is a privacy-contract regression, not merely a missing feature. It was not
anticipated in ARCHITECTURE §8 or §12 — file it as new debt (see §5).

*Fix (minimum, this sprint):* document it loudly in
`docs/concurrent-worlds.md` and `CHANGELOG.md`, and make `reset pkb`/`reset data`
either (a) refuse with a list of instance roots they will not touch, or
(b) accept `--world <slug>`. Silence is not acceptable here.

---

**M7 — F16's `✗ unreadable` row can never render.**
`scripts/lib/instances.sh:176` vs `scripts/status.sh:56-64`

`inst_list_slugs` calls `inst_read_record` to filter, which quarantines the
corrupt file to `<slug>.json.bad` and then does not echo the slug. By the time
`_status_build_rows` re-reads, the record is gone, so the `rc == 2` branch is
dead and the `unreadable` renderer at `status.sh:147-149` is unreachable. Net
behaviour: a corrupt registry record vanishes from `status` with no message at
all — the opposite of F16's "row rendered `✗ unreadable`".

*Fix:* have `inst_list_slugs` emit every `*.json` basename without reading, and
let the caller classify; or emit `<slug>\tunreadable` lines. Add a test that
writes `registry.d/x.json` containing `{oops` and asserts `status` prints
`unreadable` and the `.bad` file exists.

---

### MINOR

- **m1 — `status.sh:27` sources `lab.conf` without `set -a`.** ARCHITECTURE §6.2
  names both files explicitly ("One line in `start.sh` and one in
  `status.sh:16`"); only `start.sh` got it. No functional impact today (nothing
  in `status.sh` forks a python that reads `PORTAL_PORT`), but the stated fix is
  half-applied. *Fix:* `[[ -f lab.conf ]] && set -a && source lab.conf && set +a`.
- **m2 — `start.sh:54-61`'s daemon guard runs before argument parsing.**
  `./arailctl start --help` and `--list` on a daemon-active machine exit 1 with
  the wrong message (when B2 is fixed and they reach `start.sh` at all). The
  §4.4-specific message at `start.sh:317-322` is dead. *Fix:* move the guard
  below the `while` arg loop and delete the duplicate.
- **m3 — F17 doesn't name the PID holding the port.** `start.sh:504` prints only
  the `lsof` command. *Fix:* run `lsof -tiTCP:$portal_port -sTCP:LISTEN` and
  include the PID and its cmdline in the error.
- **m4 — `/api/instances` forks one `ps` per registry record per request**
  (`app.py:3252-3265`), and `test_instance_api.py:153-159`'s "never spawns a
  process" assertion inspects only the two decorated functions' own source and
  does not ban `subprocess.run`. The assertion reads stronger than it is. *Fix:*
  add `subprocess.` to the banned list and inspect
  `_instance_record_alive`/`_read_instance_records` too, then either bless the
  `ps` call with an explicit comment or replace it with `psutil`/`/proc` reads.
- **m5 — `checkout` comparison is logical-vs-physical.** `app.py:3304` uses
  `Path.cwd()` (symlink-resolved); `start.sh:4` uses `cd … && pwd` (logical).
  A checkout reached through a symlink makes predicate step 4 fail forever —
  attach never works and `status --probe` cries wolf. *Fix:* `pwd -P` in
  `start.sh`, or `os.path.realpath` on both sides.
- **m6 — Pack re-read does not undo the writer's escaping.** `start.sh:422,430-431`
  use `grep | cut -d= -f2- | tr -d '"'`, but `_set_env_var` escapes `\`, `"`,
  `$`, and backtick. A path containing any of those round-trips wrong. Ports are
  numeric so this is latent. *Fix:* re-read via `set -a; source` into a subshell
  and echo the variable, as the code already does at `:494-496`.
- **m7 — `arailctl:249` `[[ "$*" == *--all* ]]` is an unanchored substring match**
  — `stop --allocate-nothing` would route to the instance path. *Fix:* iterate
  `"$@"` and match whole tokens.
- **m8 — `Path.cwd()`-rooted reads leak the root lab into instance processes.**
  `app.py:9753-9754` (`lab/data/activity.jsonl`, `agent_workflows.json`) and
  `app.py:10029` (`.env`) are read by an instance's diagnostics surface. A32.1
  claims `egress.py:92` is "the one known bypass"; it is not. Read-only today, so
  low impact, but `test_instance_isolation.py` should pin the claim. *Fix:* add
  an assertion to `test_instance_isolation.py` enumerating `Path.cwd()`-rooted
  filesystem sites and pinning the allowed set.
- **m9 — `reset.sh:649` `--world) STOP_WORLD="${2:-}"; shift 2`** aborts under
  `set -e` when `--world` is the final token (`shift 2` returns non-zero).
  *Fix:* `shift; [[ $# -gt 0 ]] && shift`.
- **m10 — `arailctl_version` is the literal string `concurrent-worlds-wp4`**
  (`start.sh:613`); §2.1 specifies `git describe` or a version string. *Fix:*
  `git -C "$REPO_ROOT" describe --tags --always 2>/dev/null || echo unknown`.
- **m11 — Ctrl-C on an instance leaves a live-looking registry record.**
  `_instance_cleanup_and_exit` (`start.sh:234-245`) removes the claim but not the
  record. Self-heals on the next `status`/`start` prune, so this is within F2 —
  but the roster in the *other* instance's nav shows a phantom `● :8090` until
  someone runs `status`. *Fix:* remove the record in the cleanup path when
  `_INST_CLAIM_FILE` is empty (i.e. we owned it).
- **m12 — The "falsifiable core" test never uses a second process.**
  `test_instance_isolation.py` drives `wm.mount(..., pkb_root=..., data_dir=...)`.
  §3.5's REFINEMENT explicitly blesses this ("the kwargs stay for tests"), and
  `test_instance_paths.py` covers pack→`arail.config` in a real subprocess, so
  the two halves are each covered — but no single test proves the *composition*.
  Acceptable; QA should close it with the manual two-World launch.

### NIT

- Stage banners read `[1/8]`…`[8/8]` but there are nine stages (Ollama has no
  number) — §3.5's table has stages 0–8. Cosmetic.
- `inst_record_field` (`instances.sh:150-162`) prints a Python `repr` for
  non-scalar values; every current field is scalar.
- `instances.sh:20`'s `set -uo pipefail` mutates the *sourcing* shell's options.
  Every current caller already sets them, but it is a surprising side effect for
  a library.

---

## 3. Deviations assessment (the five documented in BUILD_LOG.md)

| # | Deviation | Verdict |
|---|---|---|
| 1 | **WP2 `reset.sh` touch** (bare `launchctl list` inside `stop_services`) | **Sound.** The WP2 gate is literal ("appear in exactly one place each") and the string was genuinely there. The conditional source + `command -v daemon_active` guard is the right shape for a file that is unit-tested as a standalone copy, and the NOTE degrades to silence rather than to a wrong claim. No design change smuggled. |
| 2 | **WP3 extraction instead of `export -f`** | **Sound, correctly reasoned.** `export -f` propagates only to child processes of the same shell; extraction is what actually satisfies §10's "do not copy them" across independent invocations, and it reuses a technique already established in `shell_source_safety_driver.sh`. One caveat to record as debt: `awk "/^${name}\(\)/,/^}/"` truncates at the first column-0 `}`, so it is brittle against future edits to `setup.sh`'s formatting. Worth a comment in `setup.sh` above `_port_in_use`/`_set_env_var` saying "extracted by `scripts/lib/instances.sh` — keep the closing brace at column 0." |
| 3 | **WP4 `face.json` → `LAB_THEME`/`LAB_INTENT` mapping** | **Sound, ratified.** §1.2 deliberately left the mapping open and the values are cosmetic pre-mount fallbacks superseded by `effective_identity()`. `theme.personality` and `LAB_INTENT = slug` are both defensible; `LAB_INTENT = slug` in particular dodges the prose-vs-enum mismatch the BRIEF flagged. No further change needed. |
| 4 | **WP7 `worlds.js` + `app.py` Jinja global** | **Sound and mechanically necessary.** `worlds.html` genuinely contains no button markup — the matrix cannot be built without `worlds.js`, and the title suffix needs a value only Python has. The one-line `templates.env.globals["portal_port"]` is the minimum. Correctly flagged up front rather than done silently. |
| 5 | **WP8 `test_launchd_render.py` fixture fix** | **Sound fix, but it exposes a process gap worth naming.** The fixture was right to be updated. What it reveals is that WP2 made `install-daemon.sh:26` source `scripts/lib/instances.sh` **unconditionally**, while `reset.sh:28` got a `[[ -f ]]` guard — an inconsistency that only surfaced because a test happened to sandbox one file and not the other. Recommend giving `install-daemon.sh` the same guard, and recording the lesson: per-WP targeted regression subsets missed a real break for six work packages. WP8's baseline-diff methodology (disposable worktree at `9c51502`, byte-for-byte failure-set diff) is exemplary and should become the standard closing gate. |

**None of the five smuggled in a design change.** All were file-list or
mechanism gaps between what the architecture named and what the code required,
and all were flagged before the fact rather than discovered in review. That is
the behaviour the process is supposed to produce.

---

## 4. Non-goals check (§11)

| Non-goal | Status |
|---|---|
| No per-instance model processes | **Respected.** The instance path starts portal + memory only; ttyd/jupyter/code-server/MLX are root-lab-exclusive (`start.sh:725-804` is below the instance return). |
| No unification with `blueprint create` / repo-root `instances/` / `ARAIL_HOME` | **Respected.** `scripts/blueprint.sh` received a 10-line header comment only, which §12's mitigation clause explicitly calls for. `sprints/BACKLOG.md` filed. |
| No launchd multi-instance | **Respected.** Guard present (though unreachable via `arailctl` — see B2). |
| Nothing cross-instance | **VIOLATED in effect.** The shared-Ollama kill paths (**M3**) are a cross-instance side effect. Design intent was right; implementation leaks. |
| Do not remove `POST /api/worlds/select` | **Respected.** Endpoint intact, 409 added. The UI narrows the affordance for the in-place-switch case, but that is §5.3's own matrix, not drift. |
| No eviction / quotas / auto-shutdown | **Respected.** |
| `GET /api/pkb/search` stays open | **Respected** — untouched. |
| No Windows/WSL work beyond not regressing | **Respected.** `daemon_active` gates on `uname -s == Darwin`; `stat -f`/`stat -c` fallback at `start.sh:394`; `lsof`/`ss` capability check inherited. |
| No portal redesign | **Respected.** Four surgical edits as specified. |
| No change to `_sweep_other_worlds` | **Respected.** `src/arail/world_mount.py` is not in the diff. |

---

## 5. Test coverage assessment

- **86/86 new instance tests pass** on the shared venv (independently re-run
  during this review: `test_instance_registry` · `test_instance_paths` ·
  `test_instance_ports` · `test_daemon_predicate` · `test_instance_stop_scope` ·
  `test_instance_api` · `test_worlds_ui` · `test_instance_isolation` ·
  `test_instance_secrets`). `test_instance_start.py` (10 driver scenarios) is
  venv-gated and skips cleanly.
- **Full-suite baseline diff** (47 failed / 3477 passed vs 47 / 3390 at
  `9c51502`, failure-set byte-identical) is the right gate and I accept it.
- **Coverage on changed lines is good in breadth, weak on the destructive and
  daemon-entry paths.** Specific gaps, each tied to a finding above:
  - No test drives `arailctl`'s own `start)`/`stop)` dispatch → **B2** invisible.
  - No test pins `stop_services` against a bumped `lab.conf` → **B1** invisible.
  - No test feeds `stop --world` a traversal slug → **M5** invisible.
  - No test uses a slug that is a substring of the repo path → **M2** invisible.
  - No test asserts the readiness probe rejects a foreign token → **M1** invisible.
  - No test writes a corrupt `registry.d/*.json` and asserts the `unreadable`
    row → **M7** invisible.
- **Security allocation (§9's 20 %)** is partially met: slug injection into the
  pack is tested at both layers (good — `test_instance_ports.py`'s hostile
  `LAB_NAME` case is the right test), traversal on `start --world` is tested,
  secrets 0600/no-copy/no-log is well covered (`test_instance_secrets.py`, 7
  tests, including a source-level guard against `shutil.copy`/`os.symlink`).
  Traversal on `stop --world` and the no-spawn assertion's depth are the two
  holes.

**Token-as-non-credential assessment: accepted.** It is generated per boot,
never written to the pack (`start.sh:512-513` exports it into the child env
only), never persisted except inside the gitignored registry, and no endpoint
accepts it as authorization. The `/api/instance` docstring documents this
correctly and warns against repurposing it. Serving it on a loopback-bound
endpoint is not a disclosure. `secrets.env` never enters the pack, the record,
or any log — verified by reading the key set at `start.sh:601-613`.

---

## 6. Performance assessment

`status` with 3 registered instances is well under the 2 s win condition
(no-network predicate; measured ~0.2–0.4 s per BUILD_LOG, test asserts < 2.0).

One note not in the architecture: `inst_write_env_pack` invokes `_set_env_var`
once per key, and `_set_env_var` spawns a python interpreter that reads and
rewrites the whole file each time — 15 python processes and 15 full rewrites per
first boot (~1–2 s). Correct, and only on first boot, so it does not threaten
the 60 s launch budget. Worth a one-line comment so a future reader does not
"optimise" it into a hand-rolled writer and lose the quoting discipline.

`/api/instances` forking a `ps` per record per request (**m4**) is the only hot-path
concern, and the nav dropdown calls it on every open.

---

## 7. Tech debt delta vs ARCHITECTURE §12

**Predicted and confirmed added:** the second "instances" namespace (backlog item
filed), the fourth path-resolution site, the liveness nonce, cross-instance nav
tiles. All four landed as forecast.

**Predicted repaid — 8 of 10 confirmed.** Not delivered as predicted:
- #3 "`reset.sh`'s port-agnostic kill-everything is scoped" — scoped, but into a
  *new* silent-failure mode (**B1**). Net worse until fixed.
- #10 "`start.sh` silently discarding argv — fixed" — fixed in `start.sh`,
  re-created one level up in `arailctl` (**B2**).

**New debt not anticipated by §12 — must be recorded before any PASS:**
1. **Instance PKB/data/secrets are unreachable by every `reset` mode** (**M6**).
   This is a privacy-contract gap, not cosmetic. Add to `sprints/BACKLOG.md` and
   to ARCHITECTURE §12 "Added".
2. **The `awk`-range function-extraction coupling** between
   `scripts/lib/instances.sh` and `scripts/setup.sh`'s formatting (deviation 2).
3. **Two parallel liveness implementations** (bash `inst_alive`, python
   `_instance_record_alive`) with no shared conformance test. §2.3 sanctions the
   parallelism; nothing pins them to the same truth table. Add a conformance test
   or a shared fixture.
4. **`Path.cwd()`-rooted reads in `app.py`** as an isolation bypass class beyond
   the single `egress.py:92` A32.1 acknowledged (**m8**).

---

## 8. Required actions before merge

**Must fix (BLOCKER):**
1. `reset.sh` — source `lab.conf` before `stop_services` uses the ports, plus a
   bumped-port regression test. (**B1**)
2. `arailctl` — stop discarding `--world`/`--list`/`--help` in the
   `daemon_active` branch; make F8's refusal reachable, with a test that drives
   the real `arailctl` dispatch. (**B2**)

**Must fix (MAJOR) — all are small and all are on safety paths:**
3. Readiness probe must compare `token` and `checkout`. (**M1**)
4. Launcher-PID verification must match `--world <slug>`, not a bare substring. (**M2**)
5. Ollama must not be killed by a launcher's cleanup while a sibling instance is
   live. (**M3**)
6. Install a `trap … EXIT` on the claim. (**M4**)
7. Jail the slug on `stop --world`. (**M5**)
8. Document (at minimum) that `reset pkb`/`reset data`/`reset env` do not touch
   instance roots, in `docs/concurrent-worlds.md` and `CHANGELOG.md`; file the
   `--world`-aware reset as a backlog item. (**M6**)
9. Make the `✗ unreadable` row reachable. (**M7**)

**Must record before re-review:**
10. Add the four new debt items above to ARCHITECTURE §12 and `sprints/BACKLOG.md`.

**MINOR findings m1–m12** may be taken as follow-up tickets rather than
re-review blockers, except **m5** (symlinked-checkout probe failure), which
should be fixed alongside M1 since it is the same predicate.

Re-review after 1–9. QA should not run until the BLOCKERs are cleared — several
of the deferred manual gates (two-World launch, attach-on-running) sit directly
downstream of M1 and B2.

---
---

# Re-review (fix pass)

**Date:** 2026-07-28
**Fix pass:** `9c7e120..893ea23` (11 commits) on top of `5cef466`
**Reviewed:** BUILD_LOG.md "## Review-fix pass", the full product diff
`git diff 5cef466..893ea23 -- arailctl scripts/`, the four touched/new test
files, plus re-run verification.

## FINAL VERDICT: WEAK_PASS

Both BLOCKERs and all seven MAJORs are genuinely closed — not papered over.
Every fix is the one this review prescribed, implemented at the site named, with
an end-to-end regression test that drives the *real* script rather than a
re-implementation. Three new MINOR findings fell out of the fix diffs; none is a
BLOCKER or MAJOR. Ship with the follow-up ticket list in §R4.

### Verification performed

- `pytest` over the 11 instance-adjacent suites → **98 passed**.
- `pytest` over the 9 pinned "must stay green" + reset/launchd suites →
  **86 passed, 3 failed** — the same three pre-existing failures
  (`test_reset_stop_scope.py`'s two `awk`-extraction cases,
  `test_shell_source_safety.py`'s `tomllib`-on-3.9 case). Baseline unchanged.
- `tests/instance_start_driver.sh` → **11/11 scenarios pass** (including M4's new
  claim-leak scenario).
- Read every hunk of the product diff; independently reproduced the one new
  hazard I claim (n2) in a shell harness.

---

## R1. Per-finding closure table

| # | Claim | Verified | Assessment |
|---|---|---|---|
| **B1** | `reset.sh` sources `lab.conf` | ✅ **CLOSED** | `reset.sh:32-42` — `[[ -f lab.conf ]] && set -a && source lab.conf && set +a`, placed after `.env` and well before `stop_services()` at `:117`. `test_stop_matches_bumped_lab_conf_port_not_default` is a genuine end-to-end test: real `reset.sh`, `.env` pinning 8080, `lab.conf` pinning 9321, a real backgrounded process whose argv carries `--port 9321`, asserting `No running services found.` is absent. This would have failed hard before the fix. |
| **B2** | `--world`/`--list`/`--help` always reach `start.sh` | ✅ **CLOSED** | `arailctl:225-242` scans `"$@"` and `exec`s `start.sh` before the `daemon_active` branch; `start.sh:99-128` now hosts the guard *after* arg parsing and renders §4.4's slug-naming refusal. `_instance_start`'s duplicate check is deleted (`start.sh:369-374`) — correctly, since the top-level guard is now the single site. Both tests drive the real `arailctl` with a stubbed `HOME`/`launchctl`/`uname`; the negative assertion (`"Lab supervised by launchd" not in out`) is exactly the right one. F8 is now reachable. **Caveat: the forward list is not exhaustive — see n1.** |
| **M1** | Probe verifies token AND checkout | ✅ **CLOSED** | `start.sh:583-616`. Captures the body, requires `token == $instance_token && checkout == $REPO_ROOT`, and on mismatch emits the F1-named message (`port N was taken during startup … token/checkout mismatch`) and calls `_instance_cleanup_and_exit 1`. Correctly rejects a *root lab* answering on the port (its `token` is `null` → empty → `-n` fails). **m5 folded in and closed**: `REPO_ROOT` is now `pwd -P` (`start.sh:4-9`), matching `Path.cwd()`. 4 extraction tests pin the comparison matrix. **Caveat: the harness runs without `set -e` — see n2.** |
| **M2** | Launcher verification is an exact token | ✅ **CLOSED (correctness)** | `reset.sh:234-249` — requires `*"scripts/start.sh"*` **and** an exact `--world <slug>`/`--world=<slug>`. `test_stop_instance_launcher_verification_rejects_slug_substring_match` uses slug `ai` against a decoy path containing `arail`, which is the precise case I raised. The unsound substring test is gone. **Caveat: over-tight for picker-launched instances — see n3.** |
| **M3** | Ollama survives a sibling | ✅ **CLOSED** | `start.sh:260-269, 284-296, 652-660`. `_INST_OLLAMA_PID` is tracked outside `_INST_PIDS`, and `_instance_cleanup_and_exit` kills it only after walking `inst_list_slugs`/`inst_alive` for a live sibling — the same "last one out" guard `stop_instance` already applied. The `stop --world X` → launcher-TERM → trap → shared-Ollama-death chain is severed at the trap, which is the right layer. Two tests cover both branches. |
| **M4** | `EXIT` trap on the claim | ✅ **CLOSED** | `start.sh:457-466` installs `trap '_instance_cleanup_and_exit $?' EXIT` immediately after the claim; `:729-737` clears it once the record is written and the claim removed; `_instance_cleanup_and_exit` disarms all three traps on entry (`:271`) so it cannot recurse. Driver scenario 11 forces a `set -e` abort mid-stage-4 by breaking `_set_env_var` and asserts no claim survives — a real fail-before test. F6's "every exit path" is now literally true. |
| **M5** | `stop --world` jails the slug | ✅ **CLOSED** | `reset.sh:709-718` — `inst_valid_slug` rejection with exit 2, placed *before* `stop_instance`/`inst_read_record`, so no filesystem call is reached. `test_stop_world_traversal_slug_is_rejected_before_touching_disk` asserts exit 2, the message, and that a decoy `foo.json` outside the registry is untouched by mtime-ns. Exactly the prescribed fix. |
| **M6** | Reset gap documented | ✅ **CLOSED at the agreed minimum** | New section in `docs/concurrent-worlds.md`, a `CHANGELOG.md` entry, and a `sprints/BACKLOG.md` item with a named manual workaround. This is precisely the minimum my review allowed ("Document (at minimum) … file the `--world`-aware reset as a backlog item"). The privacy-contract *gap itself* remains open by design; it now has a home and is discoverable. |
| **M7** | `✗ unreadable` row reachable | ✅ **CLOSED** | `instances.sh:166-184` — `inst_list_slugs` now emits every basename unread and lets the caller classify, exactly as prescribed. I traced the downstream consumers (`inst_prune`, `inst_prune_all`, `inst_any_alive`, `stop_all_instances`, the ceiling counter, the picker, `_instance_print_roster`): all call `inst_read_record`/`inst_alive`, which handle the corrupt case non-fatally, so admitting unreadable slugs to the list is safe. `test_status_renders_unreadable_row_for_corrupt_registry_record` writes `{oops` and asserts the row renders, `.json.bad` exists, and `.json` is gone. |
| **m2** | Guard moved below arg parsing | ✅ **CLOSED** | Folded into B2, correctly — `--list` must bypass the guard for B2's fix to be coherent. Duplicate at `_instance_start` deleted. |
| **m9** | `shift 2` on a trailing `--world` | ✅ **CLOSED** | `reset.sh:668` — `shift; [[ $# -gt 0 ]] && shift`. |
| **m5** | Logical-vs-physical checkout | ✅ **CLOSED** | Folded into M1 via `pwd -P`. |

**Closure: 9/9 BLOCKER+MAJOR, plus m2, m5, m9. Zero regressions.**

Two additional latent fixes landed unrequested and are correct: `start.sh:34-42`
now guards `source lab.conf` with `[[ -f ]]` (the bash 3.2 `|| true` landmine
already fixed in `status.sh:27`), and `_instance_cleanup_and_exit` disarms its
own traps. Both are in files the pass already rewrote; neither is scope drift.

---

## R2. New findings from the fix diffs

All three are MINOR. None blocks.

**n1 — B2's forward list is not exhaustive; `--port`/`--no-browser`/`--yes`/
unknown flags are still silently discarded under daemon mode.**
`arailctl:232-236`

```
case "$_arail_start_arg" in
    --world|--world=*|--list|-h|--help) _arail_start_forwards_argv=1; break ;;
esac
```

`./arailctl start --port 9000` on a daemon-active machine still falls into the
launchd branch, kickstarts the root lab on its own port, prints
`Lab supervised by launchd — portal: …:8080`, and exits **0**. So does
`./arailctl start --bogus`, which should be a usage error with exit 2. This is
the same defect class B2 fixed, narrowed rather than eliminated.

*Fix:* forward whenever `[[ $# -gt 0 ]]` and let `start.sh` — which already owns
both the daemon refusal and the unknown-flag exit 2 — be the single authority on
`start`'s argv. That is strictly simpler than the current allow-list and removes
the possibility of a future flag being forgotten.

---

**n2 — A non-JSON probe response aborts stage `[6/8]` with a Python traceback
instead of M1's named error.**
`scripts/start.sh:297-304` (`_json_field`) consumed at `:594-595`

```
probe_token="$(_json_field "$probe_response" token)"
```

`_json_field` has no `try/except` (unlike `inst_record_field`,
`instances.sh:150-162`, which does). A foreign process that answers the probe
with HTTP 200 and a non-JSON body makes `json.loads` raise; the command
substitution fails; under `set -euo pipefail` the assignment aborts the script.
Reproduced in a harness:

```
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
SUBSTITUTION FAILED rc=1
```

Consequence is bounded — M4's new `EXIT` trap fires, so the child uvicorn is
killed and the claim is removed, and the exit code is non-zero — but the operator
gets a raw traceback rather than
`port N was taken during startup … token/checkout mismatch`, which is the very
message M1 exists to deliver, in the most likely foreign-responder case (a
code-server / jupyter / unrelated web app on that port). `curl -sf` filters
non-2xx, so only a 200-with-non-JSON triggers it.

*Note on test coverage:* `test_instance_readiness_probe.py:_run_probe` drives the
extracted block under `set -uo pipefail` — deliberately **without `-e`** — so it
cannot observe this. The tests pin the comparison matrix correctly but not the
errexit behaviour of the surrounding stage.

*Fix:* give `_json_field` the same `try/except → print("")` shape
`inst_record_field` already has (5 lines), or call `inst_record_field` directly.
Add a `_run_probe` case with `curl_body="<html>"` asserting the named message.

---

**n3 — M2's exact-token launcher check never verifies a picker-launched or
auto-selected instance.**
`scripts/reset.sh:242-243`

The launcher's cmdline only contains `--world <slug>` when the operator typed it.
Both other entry paths — `|W| == 1` auto-select (`start.sh:181-182`) and the
interactive picker (`start.sh:193-227`) — call `_instance_start "$TARGET_SLUG"`
from a process whose argv is bare `bash …/scripts/start.sh`. For those
instances `stop --world X` now always prints
`launcher pid N did not verify — skipped, not killed` and leaves the launcher
running.

Impact is small: the launcher is blocked in `wait`, so once portal and memory are
killed it returns and exits on its own. But (a) the warning is alarming for an
entirely normal case, and (b) the launcher's `INT/TERM` trap never runs, so the
instance's `.ollama-started-by-arail.pid` is left behind by that path
(`stop_instance`'s own Ollama block still handles the actual process, so nothing
leaks but the file).

This is a real trade — M2's fix is unambiguously right for the substring hazard;
the verification predicate just needs a second accepted shape.

*Fix:* also accept a cmdline matching `*scripts/start.sh*` when the recorded
`instance_root` appears in the process's environment or when
`ARAIL_INSTANCE=<slug>` is in `ps -p <pid> -o command=`'s sibling `ps -E` output;
simplest and sufficient: have `_instance_start` re-`exec` itself with the slug in
argv, or record a launcher marker in the registry at start time. Add a stop-scope
test driving a launcher whose argv has no `--world`.

---

## R3. Hazard review of the fixes themselves

Checked specifically, as instructed:

- **B2's argv forwarding.** `for … in "$@"` with an empty `$@` is a no-op; the
  trailing `unset` of a never-assigned `_arail_start_arg` is safe under the
  `set -u` that `instances.sh:20` imposes on the sourcing shell. `exec` preserves
  argv exactly. No new hazard beyond n1's incompleteness.
- **M1's probe under `set -e`.** The token/checkout comparisons themselves are
  `[[ ]]` inside an `if`, correctly exempt. The `curl` call is `|| true`-guarded.
  The one unguarded failure is `_json_field` — n2.
- **M4's `EXIT` trap.** Cannot double-fire (disarmed on entry to the handler),
  cannot kill a successfully-launched instance (cleared at `:737` before `wait`),
  and covers the SIGHUP/implicit-abort class it was added for. Correct.
- **M3's cleanup.** Spawns `python3` via `inst_list_slugs`/`inst_alive` from
  inside a signal handler. Acceptable during shutdown; worth knowing if Ctrl-C
  latency is ever measured.
- **M7's widened `inst_list_slugs`.** Traced all seven consumers; all tolerate a
  slug whose record does not parse. No caller assumes readability.
- **B1's `set -a` on `lab.conf` in `reset.sh`.** This now exports `IDE_PASSWORD`
  (written into `lab.conf` by `setup.sh:1656`) into the environment of every
  child `reset.sh` spawns. `start.sh` has always done this, so it is consistent
  with existing practice and not a new class of exposure — but `reset.sh`'s
  `destroy` path shells out far more than `start.sh` does, and it writes
  `/tmp/arail-destroy.log`. I checked: nothing on that path dumps the
  environment, so this is a NIT, not a finding. Flagging it so it is on the
  record.

---

## R4. Open items at ship time (follow-up tickets, not merge blockers)

**New, from this pass:** n1 (complete B2's argv forwarding), n2 (`_json_field`
needs `try/except`; harden the probe test with `set -e`), n3 (launcher
verification for picker-launched instances).

**Carried, acknowledged by the builder:** m1, m3, m4, m6, m7, m8, m10, m11, m12,
plus the three NITs from §2. The deferral reasoning in BUILD_LOG.md is sound in
every case — each is genuinely outside the touched-file set or not one-line-class,
and none is on a data-loss or silent-failure path.

**Debt to record in ARCHITECTURE §12 / `sprints/BACKLOG.md`** (from §7 of this
review, still outstanding): the instance-reset gap (now filed via M6), the
`awk`-range coupling to `setup.sh`'s formatting, the two unconformed parallel
liveness implementations, and the `Path.cwd()` bypass class.

## R5. Why WEAK_PASS and not PASS

No BLOCKs remain and the fix quality is high — the tests added are end-to-end
against the real scripts, which is what made them able to fail before the fix.
Fourteen MINORs are open, though, and two of the three new ones (n2, n3) sit
directly on paths this pass just rewrote: n2 defeats M1's own named-error promise
in its most likely case, and n3 makes a normal stop emit a scary
"did not verify" warning. Neither is severe enough to hold the merge, and both
have one-line-class fixes. Ship with notes; file n1–n3 before QA so the manual
two-World launch is run against a known list.

**QA is now unblocked.** The two deferred manual gates — a real two-World launch
on 8090/8100 with matching `/api/instance` tokens, and the two-tab visual
distinctness check — should be the first thing run, since M1 and B2 were the
findings standing between them and a meaningful result.
