## Summary

ARAIL has no single "package/version check" that blocks the shell `./arailctl start` path itself — `scripts/start.sh` only does instant `command -v` probes and launches uvicorn. The blocking and side‑effectful checks live in two places: (1) `scripts/setup.sh`, which does hard Python‑version gating, `pip install`s, and `ollama pull` calls with **900 s (15 min) timeouts** — but this is the explicit `setup` verb; and (2) the FastAPI startup event `@app.on_event("startup")` in `src/arail/portal/app.py:747`, which runs several **synchronous** operations before the server accepts any connection — most dangerously an LLM subprocess (`parser.parse`, 60 s timeout, app.py:888), a LanceDB readiness/rebuild (`pkb_index.ensure_ready`, app.py:992), and a Knowledge‑Canvas Neo4j connect (app.py:813). On top of that, every boot spins up a model‑registry health thread that probes Ollama and prints "MODEL TIER DOWN"/"not_installed", plus a boot warm call, an aeroLLM preload loop, an inbox watcher, a dream daemon, and (hybrid only) a deferred `pip-audit` scan. The literal "package/version checks" (`git fetch`, `pip list --outdated`, `ollama --version`, `curl api.github.com`) come from `components.json` and fire from `/api/admin/components` (ungated) and `/api/admin/check-updates` (airgap + boot‑grace gated). Airgap default (`LAB_MODE=airgapped`) already suppresses the network‑touching update/CVE checks; the remaining offenders are local‑but‑blocking and mostly lack a single off‑switch. A `doctor` verb already exists (`arailctl:365`) as the natural home for an explicit, opt‑in checkup.

## Current state

### A. Shell entry + boot scripts (mostly clean)
- `arailctl:206` `setup` → `scripts/setup.sh`; `arailctl:210-229` `start` (daemon path uses `launchctl load/kickstart`, else exec `start.sh`); `arailctl:92` sources `.env`. No version/package check on the `start` path.
- `arailctl:365-374` `doctor` — activates `.venv`, imports `arail`/portal/pkb, `command -v uvicorn/jupyter/ttyd/code-server`. **Explicitly invoked** — the right model for the owner's "unless invoked."
- `start-portal.sh:6` runs uvicorn with `--reload` (dev). `scripts/start.sh:35` daemon guard (`launchctl list`), `:42` `.venv` check, `:53/:66` launch portal + memory service, `:72/:115/:141` `command -v ttyd/jupyter/code-server` (instant, non‑blocking), `:167-179` auto‑opens browser after a `curl` poll loop (≤5 s, backgrounded; gated by `ARAIL_NO_BROWSER`). No package/version checks.
- `scripts/status.sh:66` `curl /api/jobs/state` (localhost, `-sf`). `install-daemon.sh:70` `.venv` check; the launchd plist (`scripts/launchd/io.arail.service.plist.template`) execs `.venv/bin/python -m uvicorn` **directly** — no boot healthcheck/version probe.
- `scripts/update.sh` / `upgrade.sh` — explicit verbs; `update.sh:227` skips remote checks when `ARAIL_MODE=airgapped`; `update.sh:263` runs each `check_cmd` only in non‑airgapped. Not part of boot.

### B. `scripts/setup.sh` — the literal package/version gates (explicit `setup` only)
- `setup.sh:405-432` `ensure_python()` — probes for Python 3.10+; **`error`‑exits** if absent and auto‑install declined. `:411` warns on 3.13+. `:440` `pip install --upgrade pip`.
- `:560/:592` `pip install -e .[dev,<tier>]` / AirLLM; `:614-640` AeroLLM build probe (`ARAIL_SKIP_AEROLLM_PROBE`).
- `:744-773` Ollama install + `ollama --version`; `:831-1006` `ollama show/pull/create` with **`_arail_timeout 900`** on pulls (up to 15 min hang each) and 300 s on creates. Gated by `ARAIL_SKIP_OLLAMA`, `ARAIL_ENABLE_OLLAMA`, `ARAIL_SKIP_MODEL_DOWNLOAD`, `ARAIL_DEFAULT_GEMMA`.
- `:2160-2183` verify: smoke‑test import + `python -m arail.world_mount verify-shipped`.

### C. Portal startup event — `app.py:747 _startup()` (runs before the server serves)
Synchronous (block the whole portal from accepting connections until done):
- `app.py:754` `egress.install_guard()` — fast, **load‑bearing** (airgap).
- `app.py:813` `await _knowledge_canvas_store.init()` — Neo4j (`bolt://localhost:7687`) + LanceDB connect; maximus/canvas only; try/except but **awaited** → can block if Neo4j is down.
- `app.py:871` `_reconcile_interrupted_research()` — file reads, fast.
- `app.py:878-904` bootstrap goal: `parser.parse(goal_text)` at **:888** spawns an LLM subprocess (`goal_parser`, `ARAIL_GOAL_PARSE_TIMEOUT_SEC=60`) → **blocks boot up to 60 s** if the model is cold/absent; then `researcher.start()` at :904 auto‑starts autoresearch (courtesy delay `LAB_STARTUP_DELAY_SEC=300`). Only when `lab/data/goals/bootstrap_goal.json` exists (written by `setup.sh:1837`) and no current goal.
- `app.py:930/945/961/977` seed packs/skills/loadouts/research files — synchronous file seeding.
- `app.py:992` `pkb_index.ensure_ready()` — opens LanceDB `pkb_pages`; comment notes a **one‑time rebuild** on first boot → potentially heavy/slow, synchronous.
- `app.py:1004-1010` `load_all()` + `start_all_auto()` — imports every agent module and starts opt‑in agent threads.
- `app.py:1059` `_READY = True`.

Fire‑and‑forget (`asyncio.create_task`, non‑blocking to `_READY`):
- `app.py:770` `get_registry().start_background()` (spawns health thread — see D).
- `app.py:779` `aerollm_preload_loop()`; `:842` shipped‑world seal check; `:843` `_warm_primary_router()`; `:844` `_inbox_watcher_loop()`; `:850` `_prewarm_claude_cache_task()`; `:798` conversation orphan sweep.
- `app.py:1018-1025` dream daemon (`LAB_DREAMS`).
- `app.py:1033-1053` **boot security scan** — only `if _lab_mode()=="hybrid"`; `await asyncio.sleep(max(30, boot_grace_seconds()))` (default **3600 s**) then `pip-audit`. Never in airgapped.

UI gate: the warmup overlay (`_nav.html:183-243`) covers the page (z‑index 9999) until `/api/ready` returns `ready && !warming`, self‑dismissing at a 30 s hard cap. `/api/ready` (app.py:1062) reports `warming = not _MODEL_WARM`, which flips only when `_warm_primary_router()` finishes (app.py:5982-6029; gated by `ARAIL_TIER0_BOOT_WARM`).

### D. Background loops / auto‑probes (every boot, runtime)
- **Model registry health** — `registry/health.py:254 start_background()` → daemon thread; `:259` `run_preflight` immediately, then every `MODEL_HEALTH_INTERVAL_SEC` (default **60 s**, `:256`). `_probe_http_models` (`:50-98`) does `requests.get(<endpoint>/models, timeout=2)` + `_probe_ollama_residency` `/api/ps` (`:101`, 2 s); `_probe_aerollm` (`:120`) uses `importlib.util.find_spec("aerollm_api")` + model‑dir check. Emits "MODEL TIER DOWN" / "not_installed" (health.py:236‑248). **Local‑only, non‑blocking, but has no on/off switch — only an interval.** Cloud entries are skipped when airgapped (`core.py:127`, `health.py:167-173`).
- **aeroLLM preload** — `model_warmth.py:107 aerollm_preload_loop`, interval 300 s (`:38`), gated `ARAIL_AEROLLM_PRELOAD` (`:33`); maximus + safe‑window only.
- **Inbox watcher** — `app.py:10942`, polls `lab/pkb/inbox` every 10 s, gated `LAB_INBOX_WATCH`.
- **Scheduler** — `arail/scheduler.py` is passive (window + persisted halt flag, no loop). `portal/scheduler.py` is an in‑process inference semaphore (no loop).
- **egress internet probe** — `egress.py:650 probe_internet()`, **opt‑in** `BUDDY_EGRESS_PROBE=1`, one raw TCP connect to `1.1.1.1:443`, 1 s, cached 60 s.

### E. On‑demand version/package checks (page‑load triggered, not boot)
- `components.json` supplies `version_cmd`/`check_cmd`: `git fetch origin main`, `.venv/bin/pip list`, `pip list --outdated --format=json`, `ollama --version`, `agent-browser --version`, `npm outdated -g`, `curl -sf https://api.github.com/...`, `docker images`.
- `/api/admin/components` (`app.py:4754-4853`) runs every `version_cmd` (`shell=True`, `timeout=10` each) — **not airgap/boot‑grace gated**; fired on Admin page load (`admin.html:1479`). This is the `pip list` / `ollama --version` "package check."
- `/api/admin/check-updates` (`app.py:4856`) runs `check_cmd`s (30 s each); gated by airgapped (`:4860`) **and** boot‑grace (`:4866`, `_within_boot_grace`, `ARAIL_BOOT_GRACE_SEC=3600`). Fired quietly on **every dashboard load** (`dashboard.html:1131/1146`), and streamed into the **live‑checks modal** (`/api/admin/check-updates/stream`, `app.py:4891`) from the "Updates Available"/"Check Updates" buttons (`dashboard.html:374/1118`, `admin.html:1308`).
- `/api/admin/security` scan (`app.py:5283`) → `security_scan.run_and_persist` (`security_scan.py:264`, `pip-audit` subprocess). Manual button + boot (hybrid) + SRE + SSE triggers.
- `/api/system/health` (`app.py:8519`) — concurrent localhost port probes + OpenAI‑compat probes (3 s each, threaded); fired on dashboard/admin/graph load. Local, fast, non‑blocking to boot.

## Key files
- `src/arail/portal/app.py:747-1059` — the startup event; the only place with **synchronous, boot‑blocking** auto‑work (parser.parse, pkb_index rebuild, canvas Neo4j, seeds, agent load).
- `src/arail/portal/app.py:4754-5013, 5283-5330` — component `version_cmd`/`check_cmd` runners + live‑checks/security stream endpoints (the literal package/version checks).
- `components.json` — the manifest whose `version_cmd`/`check_cmd` are `git fetch`, `pip list --outdated`, `ollama --version`, `curl api.github.com`, etc.
- `src/arail/registry/health.py:50-98,120-145,206-269` — per‑boot model health thread that probes Ollama and declares "not_installed"/"MODEL TIER DOWN"; interval‑only, no off switch.
- `src/arail/portal/model_warmth.py:107-133` + `app.py:5982-6029` — aeroLLM preload loop and Tier‑0 boot warm (issue completions to Ollama).
- `src/arail/portal/security_scan.py:264-420` — `pip-audit` wrapper (boot scan is hybrid‑only, deferred by boot‑grace).
- `scripts/setup.sh:405-432, 744-1006, 2160-2183` — Python version gate, `pip install`s, `ollama pull` (900 s timeouts), verify — explicit `setup` verb.
- `scripts/start.sh` / `scripts/launchd/io.arail.service.plist.template` — the actual boot path; no package/version checks.
- `src/arail/egress.py:442-485,650-700` + `src/arail/airgap.py` — egress guard (load‑bearing airgap enforcement) and opt‑in internet probe.
- `src/arail/portal/app.py:83-104` (`boot_grace_seconds`/`_within_boot_grace`) and `.env.example:154,228-257` — the existing env gates.

## Gaps
1. **Boot‑blocking LLM subprocess in the startup event.** `app.py:888` `parser.parse(goal_text)` runs an LLM subprocess with a **60 s** timeout synchronously inside `@app.on_event("startup")`, so with a cold/absent model the entire portal is unreachable for up to 60 s on first start after `setup` writes `bootstrap_goal.json`. Evidence: `app.py:878-904`, `goal_parser/__init__.py:16-19,144-165`. It is not wrapped in `create_task` (unlike the warm/preload tasks).
2. **Other synchronous startup work has no gate and can block the server.** `pkb_index.ensure_ready()` (app.py:992, "one‑time rebuild") and `await _knowledge_canvas_store.init()` (app.py:813, Neo4j connect) run before `_READY`, with no env flag to skip. A slow LanceDB rebuild or an unreachable Neo4j delays first byte.
3. **The model‑registry health thread has no off‑switch — only an interval.** `registry/core.py:431-438` + `health.py:254-269` always start on boot and re‑probe every 60 s, emitting "MODEL TIER DOWN"/"'model' not_installed" (`health.py:236-248`, `_probe_http_models`, `_probe_ollama_residency`). There is a `MODEL_HEALTH_INTERVAL_SEC` but no `MODEL_HEALTH=off`. This is the check most likely perceived as "package check" noise, and it fires whether or not the user asked.
4. **`/api/admin/components` runs `pip list`/`ollama --version`/git ungated.** Unlike `/api/admin/check-updates`, `admin_components` (app.py:4754‑4853) is **not** gated by airgap or boot‑grace and runs `version_cmd` (`shell=True`, 10 s each) for all 8 components on every Admin page load — `.venv/bin/pip list` on ~147 packages is the slow one (`components.json:34`).
5. **`setup.sh` can hang for up to 15 minutes per model on `ollama pull`.** `_arail_timeout 900` on `ollama pull llama3.2:1b` / `qwen2.5:7b` (`setup.sh:845,969,992,885,950`). If the owner treats `setup`/re‑`setup` as part of "boot," this is the hardest block; offline/slow networks stall the whole run.
6. **No unified "no automatic checks" master switch.** Disabling all auto‑behavior today requires knowing ~7 separate vars (`ARAIL_TIER0_BOOT_WARM`, `ARAIL_AEROLLM_PRELOAD`, `LAB_DREAMS`, `LAB_INBOX_WATCH`, `ARAIL_PREWARM_CACHE`, `ARAIL_BOOT_GRACE_SEC`, plus the researcher auto‑start via bootstrap goal) and there is no gate at all for the health thread (Gap 3) or the synchronous startup work (Gaps 1‑2). Evidence: `.env.example:228-257`.
7. **Autoresearch auto‑starts on boot from a shipped bootstrap goal.** `app.py:904` `researcher.start(parsed)` begins a compute loop (after a 300 s courtesy delay) with no explicit user action beyond having answered the setup goal prompt — a side‑effectful startup behavior, not just a check.
8. **`start-portal.sh` uses `--reload`.** `start-portal.sh:6` runs uvicorn with `--reload`, which re‑executes the whole import + startup event (and thus all the above) on any file touch — amplifying every boot‑time check during development.

## Quick wins
- **Defer the bootstrap `parser.parse` off the critical path** (Gap 1): move `app.py:878-914` into an `asyncio.create_task` (like `_warm_primary_router`), or call `parser.parse_offline` at boot and upgrade later. Immediately removes the 60 s server‑unreachable window. Load‑bearing? No — offline parse already exists (`goal_parser/__init__.py:187`).
- **Add a single master gate** consulted at the top of `_startup` and by the health thread, e.g. `ARAIL_NO_AUTOCHECKS=1` (or reuse `doctor` as the only checkup surface): skip registry `start_background`, `_warm_primary_router`, `aerollm_preload_loop`, boot security scan, and `check-updates`. The `doctor` verb (`arailctl:365`) is the natural explicit trigger the owner wants.
- **Give the health thread an off switch** (Gap 3): honor `MODEL_HEALTH_INTERVAL_SEC=0` / `MODEL_HEALTH=off` in `registry/health.py:256` to skip the loop (keep on‑demand probing via the Models pill / `doctor`).
- **Gate `/api/admin/components` like `/api/admin/check-updates`** (Gap 4): wrap the `version_cmd` loop in `_within_boot_grace()` / airgap short‑circuit, or make version resolution lazy (importlib.metadata only, no `pip list` subprocess) so the Admin page doesn't shell out on load.
- **Make the model pulls opt‑in and fail‑fast in `setup.sh`** (Gap 5): default `ARAIL_SKIP_MODEL_DOWNLOAD` for non‑interactive/offline runs and lower the `_arail_timeout 900` to something interruptible, so setup never appears to hang for 15 minutes.
- **Keep the airgap/egress guard exactly as‑is** — `egress.install_guard()` (app.py:754) and the airgap gating in `registry/health.py:167-173` / `core.py:127-141` are genuinely load‑bearing and already prevent involuntary network checks; only the *local* probes and the LLM/rebuild work need gating.
- **Document a "quiet boot" recipe** in `.env.example` collecting the existing gates (`ARAIL_TIER0_BOOT_WARM=0`, `ARAIL_AEROLLM_PRELOAD=0`, `LAB_DREAMS=off`, `LAB_INBOX_WATCH=0`, `ARAIL_PREWARM_CACHE=0`, `ARAIL_BOOT_GRACE_SEC` behavior) so non‑expert users get a silent local‑first start without reading the source.