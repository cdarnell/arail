# Test report: Concurrent Worlds as independent instances

**Date:** 2026-07-28
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `9ed38b2` (branch `qukaizen/arailctl-concurrent-worlds-33db65`)
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) · **Review:** [REVIEW.md](./REVIEW.md) (WEAK_PASS)
**Allocation used:** 30 start/setup · 30 isolation-correctness · 20 security · 10 happy · 10 regression

## Verdict: **FAIL**

One BLOCKER and one HIGH, both found by doing the thing that had been deferred
twice: **a real two-World launch against a real portal.**

> `./arailctl start --world <slug>` cannot complete a first boot. On any
> machine. The stage `[6/8]` readiness probe targets `GET /api/instance`, and
> `/api/instance` is not on `onboarding_gate`'s allow-list, so a brand-new
> instance — which by construction has never been onboarded — answers **401
> `lab_not_onboarded`**. `curl -sf` discards the 401, the poll never matches a
> token, the 60 s cap expires, the portal is killed, and the operator is told
> "portal did not come up."

This is not a subtle edge case; it is the sprint's headline command failing
100 % of the time on its primary path. It was invisible to every existing test
because **the WP4 driver and `test_instance_start.py` both stub `uvicorn` with
a script that exits immediately and never binds** — nothing in the ~3,500-test
suite had ever spoken HTTP to a real ARAIL portal. The deferral chain
(WP4 → review → QA) is exactly what let it through, and the process worked:
the gate caught it before ship.

Everything downstream of the probe is genuinely good. With the gate worked
around (`ARAIL_PASSWORD` exported), **two Worlds came up side by side on 8090
and 8100**, tokens and checkouts matched, staged trees were disjoint, `status`
answered in 0.50 s, the two tabs were textually unmistakable, `stop --world`
killed exactly one instance, and the F11 409 genuinely prevented the
data-loss path. The design is sound and the implementation is close. It is one
allow-list entry away from working.

---

## Test inventory

| # | Test / scenario | Category | Covers | Status |
|---|---|---|---|---|
| **New file — `tests/test_instance_edge_cases.py` (52 tests + 11 xfail)** |
| 1 | `slug_jail_accepts_well_formed_slugs` ×7 | security | regex boundaries: 1-char, all-digit, 200-char, hyphens | pass |
| 2 | `slug_jail_rejects_hostile_and_malformed_slugs` ×17 | security | traversal, `$()`, backtick, uppercase, unicode, homoglyph, space, `/`, `..` | pass |
| 3 | `a_nul_byte_cannot_reach_the_slug_jail_at_all` | security | NUL cannot cross argv | pass |
| 4 | `slug_jail_rejects_a_trailing_newline_that_python_slug_re_accepts` | security | **QA-14** bash/Python jail divergence, direction pinned | pass |
| 5 | `inst_record_field_survives_a_non_object_record` ×5 | edge | **QA-6** valid-JSON-wrong-type record | **xfail** |
| 6 | `status_reports_a_non_object_registry_record_instead_of_deleting_it` | edge | **QA-6** F16 violated; record silently pruned | **xfail** |
| 7 | `inst_alive_rejects_every_malformed_portal_pid` | edge | pid 0 / −1 / float / str / null / huge | pass |
| 8 | `inst_read_record_never_follows_a_symlink_out_of_the_registry` | security | quarantine must not move an outside file | pass |
| 9 | `allocation_survives_a_registry_record_with_a_non_numeric_port` | edge | malformed port in registry | pass |
| 10 | `allocation_skips_a_block_whose_lance_port_alone_is_registered` | edge | off-by-one in block reservation | pass |
| 11 | `allocation_never_returns_a_port_on_the_exclusion_list` | edge | 9100 hard stop + exclusion list | pass |
| 12 | `env_pack_round_trips_a_hostile_display_name_through_bash` ×12 | security | `$()`, backticks, quotes, tabs, RTL, ZWSP, emoji, **newline-injected `KEY=value`**, leading/trailing space | pass |
| 13 | `bash_and_python_dotenv_agree_on_the_env_pack` ×3 | isolation | **QA-9** A32.5 falsified | **xfail** |
| 14 | `a_checkout_path_containing_a_dollar_sign_diverges…` | isolation | **QA-9** stated as a path, not a name | pass |
| 15 | `env_pack_is_world_readable_and_carries_no_secret_key` | security | §1.2 "Not in the pack" | pass |
| 16 | `two_concurrent_allocations_for_different_slugs_can_pick_the_same_block` | concurrency | **QA-7** cross-slug TOCTOU | pass (documents) |
| 17 | `claim_is_per_slug_and_does_not_serialise_different_worlds` | concurrency | F6 scope | pass |
| 18 | `json_field_does_not_abort_start_sh_on_a_non_json_probe_response` | start | **QA-8** = REVIEW n2 | **xfail** |
| 19 | `json_field_handles_a_json_scalar_and_a_json_array_body` | start | **QA-8** second shape | **xfail** |
| 20 | `every_registry_reader_is_a_no_op_on_a_missing_registry_directory` | edge | fresh checkout; no side-effect mkdir | pass |
| 21 | `registry_containing_only_quarantine_and_tmp_files_lists_nothing` | edge | `*.json` glob off-by-one | pass |
| 22 | `write_record_leaves_no_tmp_file_behind_on_success` | edge | atomic write hygiene | pass |
| 23 | `write_record_refuses_a_non_json_payload_without_clobbering…` | edge | failed write must not damage the record | pass |
| **New file — `tests/instance_qa_driver.sh` (10 scenarios) + `tests/test_instance_qa_start.py` (2 tests)** |
| 24 | first boot `--port 8888` refuses; no pack left behind | start | exclusion list, happy | pass |
| 25 | **re-boot** `--port 8888` pins a reserved port | start | **QA-1** | pass (XFAIL id) |
| 26 | `--port 0` pinned; LANCE_PORT=4 | start | **QA-2** | pass (XFAIL id) |
| 27 | `--port 70000` pinned; bind check passes vacuously | start | **QA-2** | pass (XFAIL id) |
| 28 | `--port` collides with another record's pinned ports | start | **QA-5** | pass (XFAIL id) |
| 29 | unwritable `registry.d` → "another start … (pid ?)" | start | **QA-3** | pass (XFAIL id) |
| 30 | World dir deleted after catalog build → exit 2, no root, no claim | start | F5 race | pass |
| 31 | `--world` traversal alphabet ×11 → exit 2, nothing created/read/executed | security | F5, jail | pass |
| 32 | `--list` / trailing `--world` / trailing `--port` / non-numeric `--port` | start | argv hygiene, side-effect freedom | pass |
| 33 | secret canary never reaches stdout/stderr/pack/logs; no copy/symlink | security | §7 | pass |
| 34 | `test_the_open_defect_set_has_not_changed` | regression | locks the open-defect set both ways | pass |
| **New file — `tests/test_instance_isolation_audit.py` (15 tests + 1 xfail)** |
| 35 | every config path resolves inside the instance root; models/worlds stay shared | isolation | the `config.py:86` trap | pass |
| 36 | egress + activity + experiments all land under the instance data dir | isolation | §6.3 | pass |
| 37 | wiki cache + LanceDB rooted at the instance PKB | isolation | cross-World retrieval impossible | pass |
| 38 | boot assertion fires for **all five** keys and names each | isolation | F14 (builder tested 1 of 5) | pass |
| 39 | root lab unaffected by the boot assertion | regression | zero-Worlds byte-parity premise | pass |
| 40 | `Path.cwd()` filesystem sites in `app.py` == audited allow-list | isolation | REVIEW m8 pinned | pass |
| 41 | **no `Path.cwd()`-rooted site is a write** (AST walk) | isolation | escape hunt | pass |
| 42 | no module under `src/arail` hardcodes a `lab/…` write path | isolation | escape hunt | pass |
| 43 | `egress.py` is the only `getenv("ARAIL_DATA_DIR")` bypass | isolation | A32.1 pinned | pass |
| 44 | `/api/instance` + `/api/instances` expose no field beyond spec | security | roster must not republish token/PIDs/roots | pass |
| 45 | neither endpoint can spawn a process (follows call graph, bans `subprocess`) | security | §5.3; strengthens REVIEW m4 | pass |
| 46 | portal liveness type-checks the PID (`0`, `-1`, `"1"`, `1.0`, `True`, `None`) | security | `os.kill(0,0)` = signal the group | pass |
| 47 | fresh instance resolves `airgapped` with no `.env` edit | security | hard constraint | pass |
| 48 | `ARAIL_AUTOCHECKS` absent ⇒ off in a fresh instance | security | hard constraint | pass |
| 49 | `<instance>/data` mode | security | **QA-10** §7 says 0700, got 0755 | **xfail** |
| 50 | the instance token is never compared against request data | security | token-as-nonce invariant | pass |
| **New file — `tests/test_instance_live_launch_findings.py` (5 tests + 4 xfail)** |
| 51 | `/api/instance` reachable before onboarding | start | **QA-B1 BLOCKER** | **xfail** |
| 52 | probe targets `/api/instance`; probe cannot distinguish 401 from silence | start | QA-B1 mechanism | pass |
| 53 | onboarding writer never targets the instance pack | security | **QA-B2 HIGH** | **xfail** |
| 54 | pack writer truncates + re-widens to 0644 | security | QA-B2 blast radius | pass |
| 55 | memory probe uses a route the service serves | start | **QA-4** | **xfail** |
| 56 | memory service serves `/health` but not `/` | start | QA-4's premise | pass |
| 57 | root-lab stop patterns are checkout-scoped | isolation | **QA-11** | **xfail** |
| 58 | instance stop is checkout-scoped via the registry | isolation | positive half; confirmed live | pass |
| **Live launch (manual, this pass — the twice-deferred gate)** |
| L1 | two Worlds up on 8090 / 8100 simultaneously | happy | VISION core | **pass** (after QA-B1 workaround) |
| L2 | both `/api/instance` tokens + checkouts match their records | isolation | §2.3 step 4 / M1 | **pass** |
| L3 | staged trees disjoint (`world-alpha` vs `world-beta`); data roots disjoint | isolation | win condition #1 | **pass** |
| L4 | `status` with 2 live instances | perf | win condition #2 (<2 s) | **pass — 0.50 s** |
| L5 | `status --probe` — no false checkout mismatch | start | F4 | **pass** |
| L6 | page titles `Alpha World · :8090` vs `Beta World · :8100` | happy | two-tab visual check | **pass** |
| L7 | `/api/instances` roster correct from **both** portals | happy | §5.2 | **pass** |
| L8 | attach-on-running → names the instance, exit 0, no respawn | happy | §3.3 | **pass** |
| L9 | F11 409 `instance_live`; alpha's staged tree survived | isolation | the data-loss path | **pass** |
| L10 | `stop` with 2 live + no flag → refuses, names both + `--all` | start | §4.2 | **pass** |
| L11 | `stop --world alpha` → 3 verified PIDs; beta live; **Ollama survives**; alpha data preserved | isolation | M2/M3/F15 | **pass** |
| L12 | `stop --all` → clean; no leaked listeners; ports released | regression | — | **pass** |
| L13 | memory service reported degraded while healthy on `/health` | start | **QA-4** | **fail** |
| L14 | `stop --all` killed another checkout's `:7414` memory service | isolation | **QA-11** | **fail** |

**Totals: 4 new test files, 106 new test functions (12 xfail-strict) + 10 driver scenarios + 14 live checks.**

---

## Failures

Severity key: **BLOCKER** = ships broken · **HIGH** = security/data-loss ·
**MEDIUM** = wrong behaviour on a documented path · **LOW** = cosmetic/latent.

| # | Symptom | Minimal repro | Site | Severity |
|---|---|---|---|---|
| **QA-B1** | `./arailctl start --world <slug>` **always** fails first boot: 60 s at `[6/8]`, then "portal did not come up". Root cause: `/api/instance` → 401 `lab_not_onboarded`; `curl -sf` swallows it. Also disables attach-on-running, `status --probe`, `inst_probe_matches`, and M1's whole token check. | `./arailctl start --world <any>` on a fresh instance. Confirmed inverse: with `ARAIL_PASSWORD` exported the identical launch reaches `[6/8] ✓`. | `app.py:383` allow-list ↔ `start.sh:596` | **BLOCKER** |
| **QA-B2** | `POST /api/welcome/setup` writes `ARAIL_PASSWORD` **and** `OPEN_NOTEBOOK_ENCRYPTION_KEY` in plaintext into `instance.env` — the file §1.2 declares secret-free and 0644. Worse: `inst_write_env_pack` truncates the pack and re-`chmod 0644`s it, and that path runs on any `--port` change ⇒ `start --world X --port N` **silently destroys the passphrase and the notebook encryption key**. | onboard a live instance, then `grep -i password lab/instances/<slug>/instance.env` → plaintext. Then re-run with a different `--port` → gone. | `app.py:286` `_env_file_path`; `instances.sh:464,473` | **HIGH** |
| **QA-1** | `--port` on the **re-boot** branch skips `inst_port_excluded`. First boot correctly refuses 8888; a second invocation pins it. | `start --world ai --port 8888` twice → pack `PORTAL_PORT=8888` | `start.sh:496-515` (vs the guard at `:521`) | MEDIUM |
| **QA-2** | `--port` validates `^[0-9]+$` only. `--port 0` → pack pinned `PORTAL_PORT=0 / LANCE_PORT=4`; every later boot burns 60 s. `--port 70000` → `[5/8] Bind ports… ✓` on an impossible port. | `start --world ai --port 0` | `start.sh:94-97` | MEDIUM |
| **QA-3** | An unwritable `registry.d` is reported as `another start for 'ai' is in progress (pid ?)`. `( set -o noclobber; … )` cannot tell EACCES from EEXIST. The literal `?` is the tell. | `chmod 0500 lab/instances/registry.d && ./arailctl start --world ai` | `start.sh:453-474` | MEDIUM |
| **QA-4** | Stage `[7/8]` probes `GET /` on the memory service, which has no `/` route → 404 → `curl -sf` fails. **Every** launch reports a false 20 s degradation while `/health` returns `status: ok`. | any instance launch; then `curl :LANCE_PORT/health` | `start.sh:635` | MEDIUM |
| **QA-5** | `--port` skips the registry port-collision check `inst_allocate_ports` performs. Two Worlds can be permanently pinned to the same block. | register `fin`→8090, then `start --world ai --port 8090` | `start.sh:496-534` | MEDIUM |
| **QA-6** | A registry file holding **valid JSON that is not an object** (`[1,2,3]`, `"x"`, `42`) makes `inst_record_field` raise. `status` prints **6 raw Python tracebacks**, renders **no** `✗ unreadable` row, writes **no** `.bad` quarantine, then `inst_prune_all` classifies it stale and **deletes it**. F16's contract is violated for this whole class; M7 fixed only malformed JSON. | `echo '[1,2,3]' > lab/instances/registry.d/x.json && ./arailctl status` | `instances.sh:159`; `status.sh:52-117` | MEDIUM |
| **QA-9** | **A32.5 is false.** `_set_env_var` escapes `$`/`` ` `` for bash's double-quote rules; `python-dotenv` does not un-escape them. bash reads `World $(id)`; dotenv reads `World \$(id)`. §6.1 states the two mechanisms "cannot disagree." Latent but isolation-relevant: a checkout path containing `$` makes `LAB_ROOT`/`ARAIL_DATA_DIR` resolve to **different directories** depending on launch method, while still passing the §6.4 assertion. | see `test_bash_and_python_dotenv_agree_on_the_env_pack` | `setup.sh` `_set_env_var` → `shell_safe` | MEDIUM |
| **QA-11** | `stop_services`' patterns are port-scoped but **not checkout-scoped**. Two ARAIL checkouts on one machine both default to 8080/7414, so `./arailctl stop` in checkout A kills checkout B's root-lab services. Reproduced **accidentally** during this pass: `reset.sh stop --all` in a sandbox checkout killed a `:7414` memory service belonging to another checkout. (It was respawned; no lasting harm.) The instance path is immune — records carry `checkout`. Note this is the BRIEF's motivating incident scenario verbatim. | two checkouts, both root labs up, `./arailctl stop` in one | `reset.sh:131-133` | MEDIUM |
| **QA-7** | `inst_allocate_ports` is non-atomic across slugs (the O_EXCL claim is per-slug; the record is written only at the end of 8 stages). Two overlapping `start --world A/B` both pick 8090. The loser fails with a named error and writes no record — but its pack stays pinned to a port it can never have, so every later boot fails identically until the pack is deleted. | two concurrent `inst_allocate_ports` → both print `8090 8094` | `instances.sh:412-440` | LOW |
| **QA-8** | = REVIEW **n2**, still open. `_json_field` has no `try/except`; a non-JSON HTTP-200 probe body aborts stage `[6/8]` with a raw `JSONDecodeError` instead of M1's named error. Now on the critical path: fixing QA-B1 is what makes the probe start receiving real bodies. | see test; reproduced under `set -euo pipefail` | `start.sh:350-357` | LOW→MED |
| **QA-10** | `<instance>/data` is created **0755**, not the 0700 §7 specifies for the directory that will hold `secrets.env`. `inst_scaffold_instance_root` uses a bare `mkdir -p`, so the mode is the operator's umask. (`secrets.env` itself is still 0600, so no disclosure today — the defence-in-depth layer is simply absent.) | `inst_scaffold_instance_root qa && stat -f %Lp …/data` → `755` | `instances.sh:323-332` | LOW |
| **QA-12** | `status` on an unwritable registry emits a raw `rm: …: Permission denied` to stderr and continues. `inst_prune`'s `rm -f` is unguarded. | `chmod 0500 registry.d` with a stale record, then `status` | `instances.sh:200` | LOW |
| **QA-13** | `POST /api/worlds/select` 409s an instance re-mounting **its own** World, with a self-referential message ("stop it first: `./arailctl stop --world beta`" — addressed to beta). Not UI-reachable (§5.3's matrix offers Unmount there), but the API is over-broad. | `curl -X POST :8100/api/worlds/select -d '{"slug":"beta"}'` from beta | `app.py:3407-3421` | LOW |
| **QA-14** | Python `_SLUG_RE` accepts a trailing newline (`$` before `\n`); bash `INST_SLUG_RE` does not. §1.2 claims they match. **bash is the stricter side and guards the destructive path**, so the direction is safe — pinned so it cannot silently invert. | `_SLUG_RE.match("ai\n")` is truthy; `inst_valid_slug $'ai\n'` is false | `world_mount.py:141` ↔ `instances.sh:25` | LOW |

**No test regressions.** No previously-green test was broken by anything here.

---

## Security review

Nothing below is checked off without naming what was actually inspected.

| Surface | What I checked | Findings |
|---|---|---|
| **User input — slugs** | Drove `inst_valid_slug` through 24 payloads via **argv** (never string interpolation): traversal (`..`, `../etc`, `ai/../../outside`, `/etc`), command substitution (`$(id)`, `` `id` ``), separators (`;`, space, `/`, `\`), case, underscore/dot, non-ASCII (`école`), a **Cyrillic homoglyph** (`аi`), 200-char, empty. All rejected; no payload executed. Ran the same 11 traversal payloads through the **real `start.sh`** and confirmed exit 2 with no instance root, no claim, no read outside `lab/worlds/`, and a decoy file outside the jail untouched. NUL cannot cross argv (pinned). | Clean. QA-14 (jail divergence) is LOW and points the safe way. |
| **User input — display names → env pack** | 12 hostile `display_name` values written through the real `inst_write_env_pack` → real `_set_env_var` → sourced by real bash: `$()`, backticks, quotes, backslash, tabs, leading/trailing whitespace, emoji, RTL Arabic + zero-width space, and two **newline-injection** attempts (`World\nPORTAL_PORT=31337`, `World\nARAIL_DATA_DIR=/tmp/pwned`). No marker file was ever created ⇒ no command substitution executed. Values round-trip byte-identically under bash. Injected `KEY=value` lines stay **inside** the quoted value, and the readers' `head -n1` plus the key ordering (ports/roots written *before* LAB_NAME) means nothing is displaced — **but that is incidental, not designed**, so it is now pinned. | Clean for bash. **QA-9**: dotenv disagrees. |
| **Secrets** | Planted a `CANARY` secrets.env in a fake root lab and ran a real start: no canary in stdout, stderr, the env pack, or any instance log; no copy or symlink into the instance. Asserted the pack contains none of `ARAIL_INSTANCE_TOKEN`/`LAB_MODE`/`ARAIL_AUTOCHECKS`/`SECRET`/`API_KEY`/`PASSWORD`/`IDE_PASSWORD`. Verified the pack is 0644 **and** that being 0644 is only sound because it is secret-free. | **QA-B2 (HIGH)** — onboarding puts a plaintext passphrase + notebook encryption key in that very file, and a later `--port` rewrite truncates it and re-widens the mode. **QA-10** — the data dir is 0755, not §7's 0700. |
| **Crypto** | The instance `token` is `uuid4()` (CSPRNG-backed), generated per boot, never persisted outside the gitignored registry, never written to the pack. Confirmed by AST/regex that **no code path compares it against request data** — so it is genuinely a liveness nonce, not a credential, and publishing it via `/api/instance` and `status --json` is not a disclosure. Pinned that invariant with a test so repurposing it as auth breaks the build. Constant-time compare is correctly **not** required here. No new algorithm, IV, or KDF is introduced by this sprint. | Clean. |
| **Network I/O** | Probes are loopback-only, `-m 0.7` bounded, capped at 60 s/20 s. `/api/instances` deliberately does **not** HTTP fan-out (stall-safe). No SSRF surface: no endpoint takes a caller-supplied URL. Confirmed a fresh instance resolves `LAB_MODE=airgapped` with **no `.env` edit** and `ARAIL_AUTOCHECKS` absent ⇒ off. | Clean. |
| **Code-execution surface** | Walked `api_instance`, `api_instances`, `_read_instance_records`, and `_instance_record_alive`, banning `subprocess.Popen/call/check_output`, `os.system/exec/spawn/popen`, `eval(`, `exec(`, `pty.spawn`, `asyncio.create_subprocess`. The **only** spawn is `_instance_record_alive`'s read-only `ps -p <pid> -o command=`, now explicitly blessed by an assertion so it cannot silently become something else. This closes REVIEW **m4**, whose assertion inspected only the two decorated handlers. §5.3's "Launch renders a command, never spawns" holds. | Clean. |
| **Deserialization** | Every registry read is `json.loads` on a local, gitignored, machine-owned file — no `pickle`, no `yaml.load`, no `eval`. Attacked it anyway with malformed JSON, JSON arrays/scalars/numbers/`null`/`true`, non-numeric ports, and pid values `0 / -1 / "eighty" / 3.5 / null / 99999999`. All PIDs correctly read dead. Confirmed the portal's liveness helper `isinstance`-checks the PID before `os.kill` (a `0` would signal the caller's whole process group). Confirmed the quarantine `mv` cannot move a file **outside** the registry via a symlinked entry. | **QA-6** — the non-object class raises and the record is silently deleted. |
| **File I/O / path traversal** | Static AST walk: **no `Path.cwd()`-rooted write** anywhere in `app.py`; the `Path.cwd()` read set is pinned to an audited allow-list (closes REVIEW **m8**'s "the claim should be pinned"). No module under `src/arail` reaches a write call with a hardcoded `lab/{pkb,data,models,worlds}` literal. `egress.py` is confirmed the **only** `getenv("ARAIL_DATA_DIR")` bypass, as A32.1 claims. `stop --world` traversal is jailed (M5 verified still closed). | Clean, plus **QA-11** (cross-checkout kill on the legacy root path). |
| **Dependencies** | No new dependency. `python-dotenv` is pre-existing; the only new fact about it is QA-9's escaping mismatch. | Clean. |

---

## Isolation — the falsifiable core (proven live, not just in-process)

REVIEW **m12** ("no single test proves the composition") is **CLOSED** by this pass.

Two real portals, two real Worlds, one machine:

- Distinct `uuid4` tokens; both matched their registry records; both `checkout`
  fields matched (`pwd -P` ↔ `Path.cwd()` — m5's fix confirmed under real
  conditions).
- `alpha/pkb/sources/` held **only** `world-alpha`; `beta/pkb/sources/` **only**
  `world-beta`. `_sweep_other_worlds` never crossed a root.
- Per-instance `data/`, `pkb/.cache/lancedb`, and `data/lance` — confirmed by
  the LanceDB init lines in each instance's own log.
- The memory service's `/health` reported an **instance-scoped** `workflow_file`.
- `ARAIL_MODELS_DIR` / `ARAIL_WORLDS_DIR` stayed shared (the `config.py:86`
  trap is genuinely avoided).
- **F11 held under real conditions**: beta's attempt to mount alpha returned
  409 `instance_live` and alpha's staged tree was byte-present afterward.
- **`stop --world alpha` killed 3 verified PIDs and nothing else** — beta stayed
  up, the shared Ollama survived (M3 confirmed live), alpha's data was preserved.

The one escape found is **QA-11**, and it is on the legacy root-lab path, not
the instance path.

---

## Performance

No benchmark file — this sprint is not on an inference hot path.

| Win condition | Target | Measured | Verdict |
|---|---|---|---|
| `status` with multiple instances | < 2 s | **0.50 s** wall, 2 live instances, human mode | **PASS** |
| Instance launch, warm | < 60 s | **~25 s** to `[6/8] ✓` … but **+20 s wasted** on QA-4's false memory-probe failure, and a **cold first boot exceeded the 60 s cap outright** on this machine | **AT RISK** |

The 60 s cap is tight. A cold first boot (LanceDB dataset creation, docs
registry, wiki init) blew through it here on an M-series Mac; the second boot
fit. Combined with QA-4's guaranteed 20 s penalty, the launch budget has less
headroom than the design assumes. Recommend fixing QA-4 (reclaims 20 s) and
raising the stage-`[6/8]` cap, or emitting progress during the wait.

---

## Coverage delta

Both figures are from full-suite runs on this worktree in this pass, not
carried forward from BUILD_LOG.

| | Baseline (`9ed38b2`, pre-QA) | After (QA tests added) |
|---|---|---|
| passed | 3,488 | **3,562** (+74) |
| failed | 47 | **47** |
| errors | 7 | **7** |
| xfailed | 1 | **17** (+16) |
| skipped | 3 | 2 |
| named FAILED/ERROR lines | 54 | 54 |

**The 54-line failure set is byte-for-byte identical** (`diff` clean), so the
47 pre-existing reds are independently re-confirmed and **this pass introduced
zero regressions**. The +74 passed / +16 xfailed are entirely the new files.

New: **4 files, 106 test functions** (16 strict-xfail pinning open defects),
**10 driver scenarios**, **14 live checks**.

---

## Ship-risk ruling on the open MINORs

| Item | Ruling |
|---|---|
| **n1** — daemon-mode argv forwarding is an allow-list, not `[[ $# -gt 0 ]]` | **Not ship-blocking.** Daemon-only, and the two flags that matter (`--world`, `--list`) are forwarded. Fix when convenient. |
| **n2** — `_json_field` has no `try/except` (= **QA-8**) | **Fix with QA-B1.** Not blocking alone, but QA-B1's fix is what makes the probe start receiving real bodies, so n2 moves onto the live path the moment the blocker is closed. Shipping the blocker fix without n2 trades one bad error message for another. |
| **n3** — picker-launched instances fail the launcher check | **Not ship-blocking.** Confirmed live that the `--world` path verifies all three PIDs and the warning does not appear. Cosmetic for the auto-select/picker paths; the launcher exits on its own. |
| **m12** — no test proves the composition | **CLOSED** by this pass's live two-World launch. |
| **m5** — logical-vs-physical checkout | **CLOSED** — verified live, `checkout` matched on both instances. |
| **m1, m3, m4, m6, m7, m8, m10, m11** | **Not ship-blocking.** m4 and m8 are materially strengthened by this pass's tests; the rest stand as filed. |
| **m6** (pack re-read doesn't undo escaping) | Upgrade its priority: **QA-9** shows the escaping mismatch is real on a second reader too, so both halves want one fix. |

**None of the previously-open minors is what fails this report.** The FAIL is
QA-B1 and QA-B2, both newly found, both on the primary path, and neither
reachable by any stub-based test.

---

## Win-condition assessment (VISION)

| # | Win condition | Verdict |
|---|---|---|
| 1 | **Provable isolation** | **MET.** Structural, verified live and by a static escape audit. The single escape (QA-11) is on the legacy root path. |
| 2 | **`status` < 2 s** | **MET.** 0.50 s with 2 live instances. |
| 3 | **No silent failures** | **NOT MET.** QA-B1 fails for 60 s naming the wrong cause; QA-4 reports healthy infrastructure as degraded on every launch; QA-3 blames a phantom concurrent start for a permissions error; QA-6 deletes a registry record while printing tracebacks. |
| 4 | **Legible launch** | **MET once past QA-B1.** Staged `[n/8]` banners with real checks, URL + data root, unmistakable tab titles, honest attach. This part is genuinely good. |

---

## Required before re-QA

1. **QA-B1** — add `/api/instance` to `onboarding_gate`'s allow-list (it is
   read-only, loopback-bound, and returns a non-credential nonce — the same
   reasoning that already puts `/api/system/health` there). Then **re-run a real
   two-World first boot**, not a stub.
2. **QA-B2** — make `_env_file_path()` refuse to hand the onboarding writer an
   instance's `instance.env`; give an instance a separate secret sink under
   `<instance>/data/` at 0600. Add a test that a `--port` rewrite cannot destroy
   a credential.
3. **QA-8 / n2** — `try/except` in `_json_field` (ship with QA-B1).
4. **QA-4** — probe `/health`, not `/`.
5. **QA-1, QA-2, QA-5** — route the `--port` override through the same
   exclusion-list, range, and registry-collision checks `inst_allocate_ports`
   applies, on **both** the first-boot and re-boot branches.
6. **QA-6** — widen `inst_record_field`'s `try/except` past `json.loads`, and
   have `inst_read_record` quarantine a non-object record as F16 requires.
7. **QA-11** — scope `stop_services`' patterns to this checkout.

QA-3, QA-7, QA-9, QA-10, QA-12, QA-13, QA-14 are acceptable as filed follow-ups.

---

## Notes for the next QA pass

- **Stubs that never bind are how QA-B1 survived eight work packages and two
  reviews.** Any sprint that adds a readiness probe needs at least one test that
  speaks HTTP to a real process. Recommend a `@pytest.mark.live` tier.
- The whole `--port` override is a second, unaudited path through stage `[4/8]`
  that skips every check its allocator sibling performs. Three of this pass's
  MEDIUMs are the same structural omission.
- `inst_record_field` is called from ~10 sites under `set -euo pipefail`; its
  error contract ("empty string, not an error") is load-bearing far beyond
  QA-6's repro. Worth a dedicated contract test.
- The 60 s launch cap has no headroom on a cold boot. Measure it on a slow disk
  before calling win condition #3 met.
- `lab/instances/` is gitignored wholesale, so a corrupted pack or a wedged
  claim is invisible to `git status`. `./arailctl status` is the only window;
  QA-6 shows it can lose a record without saying so.

---
---

# Re-test (QA-fix pass)

**Date:** 2026-07-28
**Fix pass:** `6206067..0218c43` (10 commits) on top of `b417159`
**Re-verified:** the four QA suites + the driver, a fresh **live two-World
first boot with no workaround**, the QA-B2 credential trace, and a full-suite
parity run.

## FINAL VERDICT: **WEAK_PASS**

**The BLOCKER is genuinely, verifiably dead.** I rebuilt the two-World sandbox
from scratch and ran a cold first boot with **no `ARAIL_PASSWORD` workaround**:

```
[6/8] Portal up… ✓
[7/8] Memory up… ✓
[8/8] World bound + index… ✓ (2 term(s) staged)
  Alpha World is running.   Dashboard: http://127.0.0.1:8090
  Beta World is running.    Dashboard: http://127.0.0.1:8100
```

`/api/instance` now answers **HTTP 200** pre-onboarding on both ports, tokens
and checkouts match their records, `status --probe` verifies both in 0.77 s,
attach-on-running exits 0, F11 returns 409, `stop --world alpha` kills exactly
3 verified PIDs while beta and the shared Ollama survive, and alpha's staged
tree is preserved. **16/16 strict xfails flipped, verified independently.**

Not a PASS, because re-testing surfaced **four new findings, three of them
created or newly exposed by the fixes themselves** — including one the fix
pass explicitly classified as an accepted cosmetic residual which is in fact
an environment-variable exfiltration primitive.

None is a blocker. All four are narrow, same-user, and have one-line-class
fixes. Ship with them filed; do not ship with them unrecorded.

## Fix quality

I diffed every change to my own test files. **No assertion was weakened.**
xfail markers were removed and the underlying assertions inverted to pin the
correct behaviour; several got *stronger* (the QA-9 path test now asserts
byte-equality with the literal path rather than the escaped form; the driver's
scenarios now assert refusal messages *and* that no env pack is left behind).
The `EXPECTED_OPEN_DEFECTS` set was correctly emptied rather than deleted, so
the two-way lock still holds. The atomic-commit methodology described in
BUILD_LOG.md checks out against the diffs.

## Per-finding closure

| # | Sev | Claimed | Verified | Evidence |
|---|---|---|---|---|
| **QA-B1** | BLOCKER | fixed | ✅ **CLOSED** | `/api/instance` on `onboarding_gate`'s allow-list (`app.py:407`; `startswith` covers `/api/instances`). **Live cold first boot completed on both Worlds with no workaround** — the exact scenario that failed 100 % before. Probe now also captures `%{http_code}`, so a future gate regression is named rather than reported as "portal did not come up". |
| **QA-B2** | HIGH | fixed | ✅ **CLOSED (for the pack)** | `_env_file_path()` redirects an instance to `_secrets_path()`. Live trace: onboarded alpha → `instance.env` **byte-unchanged** (1623 b, same mtime), no credential; `<instance>/data/secrets.env` created **0600** with the passphrase. Blast radius checked — only 2 callers, both secret-related. **But the same handler's second write is still unfixed → QA-15.** |
| **QA-8 / n2** | LOW→MED | fixed | ✅ **CLOSED** | `_json_field` try/except covers `json.loads`, `isinstance`, and `.get`. Both shapes pass under production `set -euo pipefail`. |
| **QA-4** | MED | fixed | ✅ **CLOSED** | Probe targets `/health`. Live: `[7/8] Memory up… ✓` on both instances — previously a guaranteed false 20 s degradation. Reclaims 20 s of the launch budget. |
| **QA-1** | MED | fixed | ✅ **CLOSED** | Re-boot `--port 8888` now refused; pack stays pinned at 8090. |
| **QA-2** | MED | fixed | ✅ **CLOSED** | `--port 0` and `--port 70000` rejected at argv-parse time; no env pack left behind. |
| **QA-5** | MED | fixed | ✅ **CLOSED** | `--port 8090` against another record's pinned block refused; the pre-existing record untouched. |
| **QA-3** | MED | fixed | ✅ **CLOSED** | Unwritable `registry.d` now names the real cause instead of a phantom concurrent start. |
| **QA-6** | MED | fixed | ✅ **CLOSED** | Non-object records (`[1,2,3]`, `"x"`, `42`, `null`, `true`) raise inside the existing try/except → quarantined by `inst_read_record`, empty string from `inst_record_field`. `status` renders `✗ unreadable`, writes `.bad`, no tracebacks, record not deleted. |
| **QA-9** | MED | fixed (1 residual) | ⚠️ **PARTIALLY CLOSED** | Single-quoting fixes `$(…)`, backtick, and the reachable-and-harmful `$`-in-checkout-path case (now asserts byte-equality). The `${NAME}` shape remains — and is **worse than filed → QA-18**. |
| **QA-10** | LOW | fixed | ✅ **CLOSED** | Live: both instance data dirs are mode **700**. |
| **QA-11** | MED | fixed | ⚠️ **CLOSED WITH A NEW GAP** | `--app-dir "$REPO_ROOT"` marker + checkout-scoped patterns; a foreign checkout's same-port uvicorn survives. **But the marker is invisible on an already-running lab → QA-17.** |

**10 of 12 fully closed. 2 closed-with-a-successor.** Every fix is at the site
my report named; none is a workaround.

## Live launch result

| Check | Result |
|---|---|
| Cold first boot, two Worlds, **no workaround** | **PASS** — `[6/8] ✓` both |
| `/api/instance` pre-onboarding | **200** on 8090 and 8100 (was 401) |
| token + checkout match record | **PASS** both |
| `[7/8] Memory up` | **✓** both (QA-4 closed) |
| `status --probe`, 2 live | **PASS**, 0.77 s (< 2 s) |
| Page titles | `Alpha World — first run` / `Beta World — first run` — distinct |
| attach-on-running | **PASS**, exit 0, names the instance |
| `/api/instances` roster from both portals | **PASS** |
| F11 `instance_live` | **409**, alpha's staged tree intact |
| `stop --world alpha` | 3 verified PIDs; beta up; **Ollama survived**; alpha data preserved |
| `stop --all`, no leaked listeners | **PASS** |
| instance data dir mode | **700** both |
| staged trees disjoint | `world-alpha` / `world-beta` |

Cold boot fit inside the 60 s cap this time — QA-4's fix reclaiming 20 s is
what bought the headroom. That margin is still thin; see Notes.

## New findings

| # | Symptom | Repro | Site | Sev |
|---|---|---|---|---|
| **QA-18** | **The "accepted cosmetic residual" is an env-var exfiltration primitive.** A World `display_name` of `${IDE_PASSWORD}` is written literally to the pack, read literally by bash, and **expanded to the real secret** by python-dotenv, which sets it as `LAB_NAME` — a field rendered in the page title/nav/brand. `start.sh` exports `IDE_PASSWORD` into the environment via `set -a; source lab.conf`, so the variable is present. **Mitigated in the primary path only** by ordering: `set -a; source pack` pre-sets `LAB_NAME` and `load_dotenv` defaults to `override=False`. The expansion lands on §6.1's *second, explicitly-designed-for* mechanism (a process started without the shell wrapper) and on any `dotenv_values()` caller. | End-to-end through the real writer: pack line `LAB_NAME='${IDE_PASSWORD}'` → bash `${IDE_PASSWORD}` → `dotenv_values()` `SUPERSECRET-ide-pw` | `setup.sh` `shell_safe` / `inst_write_env_pack` | **MED** |
| **QA-15** | QA-B2 fixed one of the onboarding handler's two credential writes. `_patch_lab_conf_password` still writes `IDE_PASSWORD=<passphrase>` into the **CWD-relative, checkout-shared** `lab.conf` from inside an instance process. Live: alpha onboarded (`CANARY-alpha-pw-1`), then beta (`CANARY-beta-pw-2`) — the shared file ended up holding **only beta's**. Since `start.sh`/`reset.sh` do `set -a; source lab.conf`, **alpha's process environment carries beta's passphrase**. That is the work-lab/personal-lab separation the BRIEF names, breached on the credential path (§7: "Isolation that has an exception is not isolation"). Mitigating: `lab.conf` is 0600 (same-user only) and `IDE_PASSWORD` governs code-server, which §3.6 says instances never start. | onboard two instances with different passphrases; `cat lab.conf` | `app.py:1480` `_patch_lab_conf_password` | **MED** |
| **QA-17** | QA-11's fix keys on `--app-dir <REPO_ROOT>`, an argv marker only the **new** `start.sh` emits. A lab already running when the operator upgrades has the old argv, so `stop_services` matches nothing: `./arailctl stop` prints **"No running services found."** and leaves it running. This is REVIEW.md **B1's exact silent-stop shape**, re-created in a narrower form, and every upgrading user hits it once. A cwd check on the matched PID would cover both generations. | process with pre-upgrade argv → new pattern no match, old pattern matches, `reset.sh stop` reports nothing running | `reset.sh:131-133` | **MED** |
| **QA-16** | `/api/welcome/setup` also routes `LAB_NAME`/`LAB_SHORT_NAME` through `_write_env_kv`, so for an instance they now land in `secrets.env` — which `config.py` never loads. The welcome flow's "name your lab" step is a **silent dead write** for an instance (the pack's World-derived name wins). Arguably correct behaviour, but unsignalled; also puts identity keys in a file named for secrets. | onboard an instance with `lab_name`; `grep LAB_NAME <instance>/data/secrets.env` | `app.py:1401-1403` | **LOW** |

### Also fixed (my own test defect, found while re-verifying)

`instance_qa_driver.sh` leaked a **real** portal onto :8090. The stub `uvicorn`
is shadowed by `source .venv/bin/activate`, which prepends the venv's bin to
`PATH` — so scenarios past stage [4/8] spawn the real binary. Before QA-B1 was
fixed those all died at the probe timeout and nothing leaked; **now they
succeed and the launcher blocks in `wait` forever.** I observed an orphan
holding :8090 from the builder's own verification run. Added a cleanup trap
that kills registry-recorded PIDs and any sandbox-cwd uvicorn, and documented
the stub's real limits. Driver re-runs 10/10 with zero leaks.

## Ruling on the `${NAME}` residual (item 4)

**A strict-xfail pin is *not* an acceptable ship state on its own.** The fix
pass's reasoning — "not reachable via this writer's callers today; World
`display_name` and instance paths have no reason to contain literal `${...}`"
— is a statement about *well-behaved* input, and the writer's whole job is to
be safe against input that isn't. World bundles are authored by fork users and
shared between them; the sprint's own §9 security allocation treats
`display_name` as an attacker-controlled field, which is why hostile-name
tests exist at all.

The residual is not a cosmetic divergence. It is a read primitive for the
portal process's environment, landing in a **displayed** field. The correct
fix is at the writer — reject or neutralise a literal `${` in a pack value
(a display name has no legitimate need for it) — **not** `config.py`'s
`interpolate=False`, which the builder correctly identified as too broad.

That said, the primary launch path is protected by ordering, so this is
MEDIUM, not a blocker. **Ship-acceptable as a filed, pinned follow-up
(QA-18); not acceptable as an "accepted cosmetic residual."** The
classification is what I am overruling, not the decision to ship.

## No new failure modes

- My four suites: **88 passed, 1 xfailed** (the residual, now re-filed as QA-18).
- New file `test_instance_qa_fix_regressions.py`: **4 passed, 3 xfailed**.
- `instance_qa_driver.sh`: **OK: 10 scenario(s)**, zero `XFAIL:` lines, zero leaks.
- Full suite: **47 failed / 3579 passed / 7 errors / 2 skipped** — the 54-line
  failed+error name set is **byte-for-byte identical** to the pre-QA baseline
  (`diff` clean). **Zero regressions.**
- Blast-radius checks done by hand: `_env_file_path`'s 2 callers are both
  secret-related (no config read was rerouted); `_write_env_kv` still
  `_chmod_600`s; `--app-dir` precedes `--port` on all three root-lab
  invocations (pattern-order dependency pinned by a new test).
- Environment left clean: no leaked listeners, ports released, Ollama healthy.

## Required before ship

Nothing. All four new findings are filed, pinned, and non-blocking.

## Recommended next (one sprint, all one-line-class)

1. **QA-18** — reject/neutralise `${` in env-pack values at the writer.
2. **QA-15** — give `_patch_lab_conf_password` the same instance guard
   `_env_file_path` just got.
3. **QA-17** — verify the matched PID's cwd instead of trusting an argv marker,
   so a pre-upgrade lab is still stoppable.
4. **QA-16** — either honour or explicitly decline the welcome flow's lab name
   for an instance; don't write it somewhere nothing reads.
5. Carried and still open: QA-7, QA-12, QA-13, QA-14 (all LOW, unchanged).

## Notes for the next QA pass

- **Three of four new findings were created or exposed by the fixes.** A fix
  pass on an isolation boundary needs its own adversarial re-read, not just a
  re-run of the tests that prompted it — the tests that caught the original bug
  are exactly the ones that cannot see its replacement.
- **Argv markers are a fragile identity mechanism** (QA-17). Anything that
  identifies a process by a flag it was started with breaks across upgrades.
  Prefer a property of the running process (cwd, an fd, a pidfile).
- The `/api/welcome/setup` handler writes to **three** places (env file,
  `lab.conf`, and now the instance secret store). QA-B2 and QA-15 are the same
  omission found twice. Any future change there should enumerate all sinks
  first.
- The 60 s stage-[6/8] cap still has little headroom on a cold boot; it only
  fits now because QA-4's fix returned 20 s. Measure on a slow disk before
  treating win condition #3 as settled.
