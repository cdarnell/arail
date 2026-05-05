# Plan — close the airgap gap

## Context

**The problem.** ARAIL ships with `LAB_MODE=airgapped` as the default and the
README claims *"the lab makes zero network calls"* — but exploration shows
that today airgapped only blocks the cloud-LLM provider endpoints in the
Chat tab. Agents can still reach the internet through several paths:

- `_is_airgapped()` is duplicated across 5 files with subtly different
  fallback chains; one-off enforcement at each call site.
- No HTTP-layer guard exists. Any `requests.get("https://...")` written
  tomorrow inside an agent leaks silently — there's no central choke point.
- `LAB_INTERNET_ENABLED` is a *separate* flag from `LAB_MODE`, used only
  by Buddy's HuggingFace papers fetch — confusing and inconsistent.
- The user can ping `google.com` from the host shell while the lab claims
  to be airgapped, with no in-product explanation of the discrepancy.

**What the user wants.** A clear, honest, self-enforced definition:

> **Airgapped = agents cannot collect information from the internet.**
> Local services on this machine and your private network still work.

The lab itself doesn't try to firewall the user's host (out of scope —
that's an OS concern). It enforces *its own* outbound network policy
on agent-originated calls and explains the boundary clearly in the UI.

**Outcome.** A single source of truth for what airgapped means; an
HTTP-layer egress guard that catches future raw-`requests` code paths
agent authors write; a Buddy watcher that tells the user when something
got blocked or the policy changed; UI copy that matches reality; tests
that lock the behavior in.

---

## Operational definition

In `airgapped` mode, agent-originated outbound calls are allowed only to:

- Loopback: `127.0.0.0/8`, `::1`, `localhost`.
- RFC1918 private ranges: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`.
- Link-local: `169.254.0.0/16`, `fe80::/10`.

Everything else (public DNS, public IPs, `*.huggingface.co`, `api.openai.com`,
arXiv, etc.) is **denied loudly**: the guard raises `EgressBlocked` (a
`RuntimeError` subclass) and appends one line to `lab/data/egress.jsonl`.
No silent fallbacks, no synthetic-response stubs — agents that try to
reach the internet halt with a clear traceback. This is deliberate: a
loud failure is the airgapped value prop. Curator's existing
"no-consent" graceful path operates *before* it ever calls `requests`,
so it isn't affected.

In `hybrid` mode, the existing per-domain consent model (curator approvals)
remains the gate; the egress guard is a no-op pass-through.

**Why RFC1918 is in the allow-list:** ARAIL is commonly run with a
GPU box on the LAN (Ollama, vLLM, an aeroLLM node). Restricting to
loopback only would force users to reverse-tunnel every local service,
which is the "PITA" the user asked us to avoid. RFC1918 + link-local
is the standard "private network" semantics; an attacker who can
already address your LAN is past the airgapped threat boundary.

---

## Architecture

### Layer 1 — Source of truth

**New** `src/arail/airgap.py`:

```python
def lab_mode() -> str: ...                  # "airgapped" | "hybrid", LAB_MODE → ARAIL_MODE → "airgapped"
def is_airgapped() -> bool: ...
def is_local_host(host: str) -> bool: ...   # loopback + RFC1918 + link-local
def should_allow_egress(url: str) -> tuple[bool, str]: ...   # (allowed, reason)
class EgressBlocked(RuntimeError): ...
```

**Reused / consolidated:** the existing `_lab_mode()` / `_is_airgapped()`
in `src/arail/portal/app.py:858-862`, `src/arail/research/program_drafter.py:181`,
`lab/pkb/agents/sre/sre.py:293`, `src/arail/agents/curator.py:73,109`, and
`src/arail/config.py:31` all collapse to delegating into `arail.airgap`.

### Layer 2 — Egress guard

**New** `src/arail/egress.py`:

- `install_guard()` — called once at portal startup and once on agent
  load. Mounts a `requests.adapters.HTTPAdapter` subclass that calls
  `should_allow_egress()` in `send()`. Also installs a `urllib.request`
  opener with a request-handler hook that does the same check. Both
  raise `EgressBlocked` on deny.
- `record_block(url, caller, reason)` — append to `lab/data/egress.jsonl`
  (rotating, max ~5 MB). Schema: `{ts, url_host, caller, reason, lab_mode}`.
  Bounded read API for the UI.
- `@allow_egress("reason")` context manager — for the few legitimate
  *user-initiated* hybrid-mode calls (cloud provider test/list/save) that
  need to bypass the deny-by-default *even within hybrid*. Not used in
  airgapped — there is no escape hatch in airgapped.

This is the "PITA-free" part: agent authors don't need to learn a new
HTTP API. They keep writing `requests.get(...)`. In airgapped mode the
adapter rejects internet hosts; local hosts pass through unchanged.

### Layer 3 — UI / Buddy / docs

**API:** new `GET /api/airgap/status` returns:

```json
{
  "lab_mode": "airgapped",
  "definition": "Agents cannot collect information from the internet. ...",
  "recent_blocks": [{"ts": "...", "url_host": "huggingface.co", "caller": "curator"}, ...],
  "host_can_reach_internet": null
}
```

`host_can_reach_internet` is `null` by default. Optional (off by default,
opt-in via `BUDDY_EGRESS_PROBE=1`) one-shot TCP-connect to `1.1.1.1:443`
with a 1s timeout — pure socket connect, no DNS, no payload. If true and
mode is airgapped, we surface the *honest disclosure*: "your host has
internet; the lab refuses to use it." Off by default because probing
the network in airgapped mode is itself ironic.

**Nav badge** (`src/arail/portal/templates/_nav.html:56,63`) becomes
clickable → opens a small modal showing the definition + last 5 blocks.

**Chat banner** (`src/arail/portal/templates/chat.legacy.html:311-314`)
keeps current copy but links to the same modal.

**Buddy watcher** in `lab/pkb/agents/buddy/buddy.py` — new
`_watch_airgap_events()`:

- Tails `lab/data/egress.jsonl` for new entries → posts a one-shot
  suggestion: *"Curator just tried to reach huggingface.co — I blocked it.
  That's airgapped doing its job."*
- Detects `LAB_MODE` toggle (compare `lab_mode()` to last cached value
  in agent_workflows.json) → posts: *"Door's open now — agent fetches
  will go through."* / *"Sealed back up. Agents can't reach the
  internet."*
- Drops the standalone `LAB_INTERNET_ENABLED` flag at
  `lab/pkb/agents/buddy/buddy.py:778-810` — fold the HF-papers fetch
  behind the unified `is_airgapped()` gate.

**Docs:**

- `README.md:60-62, 96-99, 143-145` — replace "zero network calls" with
  the operational definition. Make it consistent across all three spots.
- `docs/PRIVACY.md:28-48` — align with the new definition; the existing
  consent-store paragraph is correct for hybrid, leave that.

---

## Files to touch

| File | Change |
|------|--------|
| `src/arail/airgap.py` | **new** — single source of truth |
| `src/arail/egress.py` | **new** — HTTP adapter + jsonl logger + context manager |
| `src/arail/config.py` | re-export `lab_mode()` from `airgap`; drop duplicate read |
| `src/arail/portal/app.py` | replace `_lab_mode()` / `_is_airgapped()` with delegations; add `GET /api/airgap/status`; call `egress.install_guard()` at startup |
| `src/arail/agents/loader.py` | call `egress.install_guard()` once before first agent import (idempotent) |
| `src/arail/research/program_drafter.py` | replace `_allow_live_fetch()` body with `not is_airgapped()` |
| `src/arail/agents/curator.py:73,109` | replace inline env reads with `is_airgapped()` |
| `lab/pkb/agents/sre/sre.py:293` | replace `_sre_lab_mode()` with `lab_mode()` |
| `lab/pkb/agents/buddy/buddy.py` | drop `LAB_INTERNET_ENABLED`; add `_watch_airgap_events()` watcher |
| `src/arail/portal/templates/_nav.html` | nav badge → modal trigger |
| `src/arail/portal/templates/chat.legacy.html` | banner copy + modal link |
| `src/arail/portal/templates/_airgap_modal.html` | **new** — definition + recent blocks list |
| `README.md` | rewrite the three airgapped paragraphs |
| `docs/PRIVACY.md` | align with new definition |
| `tests/test_egress_guard.py` | **new** |
| `tests/test_airgap_helpers.py` | **new** |
| `tests/test_buddy_airgap_watcher.py` | **new** |
| `tests/test_program_drafter.py` | extend existing `test_drafter_skips_external_fetch_in_airgapped_mode` to use new helper |

---

## Reused functions

- Existing `_is_airgapped()` semantics (`src/arail/portal/app.py:861`) —
  same boolean, just hoisted.
- Existing nav-badge populate path — `/api/providers/state` already returns
  `lab_mode`. We add `/api/airgap/status` for the modal's richer payload
  rather than overload the providers endpoint.
- Existing `BuddyHost` protocol (`lab/pkb/agents/buddy/buddy.py:68-181`)
  for the watcher to read `lab/data/egress.jsonl`.
- Existing test pattern from `tests/test_program_drafter.py`
  (`monkeypatch.setenv("LAB_MODE", ...)`).
- Existing activity-log pattern from `src/arail/portal/app.py:6452`
  for the toggle messages — reuse the same activity stream.

---

## Out of scope (deliberate)

- **OS-level firewalling.** We don't shell out to `pf` / `iptables`.
  Python-level guard is sufficient for the threat model (well-meaning
  agents that try to fetch a paper, not an adversary on the host).
- **Blocking the user's own shell / REPL.** Only agent-loaded code
  paths and portal-internal calls go through the guard.
- **Subprocess agents.** All current agents load in-process; if that
  changes (Phase-2 aeroLLM HTTP bindings, etc.), revisit.
- **Theme/UI toggle awareness.** The user mentioned it ("toggle the
  colors and he's like yeah that's nice"); confirmed deferred to a
  follow-up sprint. This one is airgapped clarity only — Buddy only
  watches LAB_MODE toggles and egress blocks. No generic event bus
  yet; if/when v2 wants theme reactions, we'll build the bus then.
- **Removing AGENTS.md / setup.sh model-fetch checks.** `./arail setup`
  legitimately needs the internet to download initial weights. The
  guard is *runtime* — `setup.sh` runs before the portal starts, so
  it's outside the guard's scope by construction.

---

## Verification

**Unit (`tests/test_airgap_helpers.py`):**

- `is_local_host("127.0.0.1") == True`, `("localhost") == True`,
  `("192.168.1.50") == True`, `("10.0.0.5") == True`,
  `("172.16.5.5") == True`, `("8.8.8.8") == False`,
  `("huggingface.co") == False`.
- `should_allow_egress("https://huggingface.co/api/papers")` →
  `(False, "airgapped")` when airgapped, `(True, "hybrid")` when hybrid.
- `should_allow_egress("http://127.0.0.1:11434/api/tags")` →
  `(True, ...)` always.

**Integration (`tests/test_egress_guard.py`):**

- With `LAB_MODE=airgapped` and guard installed:
  - `requests.get("https://example.com")` raises `EgressBlocked`.
  - `requests.get("http://127.0.0.1:65535/x", timeout=0.1)` raises
    `ConnectionRefused`/`Timeout` (NOT `EgressBlocked`).
  - `requests.get("http://192.168.1.50:11434/api/tags", timeout=0.1)`
    is allowed by the guard (passes through to whatever the LAN says).
  - `requests.get("http://10.0.0.5/x", timeout=0.1)` allowed by guard.
  - `urllib.request.urlopen("https://example.com")` also raises
    `EgressBlocked` (urllib opener is wrapped too).
- With `LAB_MODE=hybrid`: all of the above attempt the actual call.
- A blocked attempt produces exactly one new line in `lab/data/egress.jsonl`
  with `url_host="example.com"`, `caller=<test module>`, `reason="airgapped"`.
- Confirm `EgressBlocked` is a `RuntimeError` subclass, not a sentinel
  return — agents that catch nothing crash; agents that catch
  `RuntimeError` get the chance to handle it.

**End-to-end (manual, documented in BUILD_LOG):**

1. `LAB_MODE=airgapped ./arail start` → click nav badge → modal opens
   with definition + empty blocks list.
2. Trigger curator with a goal that needs an internet fetch → block
   appears in modal within ~10s; Buddy posts a suggestion in the chat.
3. `BUDDY_EGRESS_PROBE=1 ./arail start` in airgapped → modal shows
   "host has internet; lab refuses to use it"; Buddy posts a heads-up.
4. Toggle to hybrid via portal settings → activity log shows toggle;
   Buddy posts "door open"; cloud provider test endpoints work again.
5. Toggle back → activity log + Buddy post "sealed up"; verify next
   curator attempt blocks again.
6. Run `./arail benchmark_models` (which talks to local AirLLM via
   loopback) → completes without hitting the egress guard. This is the
   "not a PITA" check.

**Regression:** existing `tests/test_program_drafter.py`,
`tests/test_setup_extras.py`, `tests/test_admin_security_endpoints.py`
must still pass against the consolidated helpers.

---

## Sprint shape

This is `/sprint`-shaped, not a one-shot:

1. **VISION** (skip — captured here).
2. **ARCHITECTURE** — flesh out the egress adapter's exact
   `HTTPAdapter.send()` override, the jsonl rotation, the modal HTML.
3. **BUILD** — files-to-touch list above, in roughly this order:
   helpers → egress guard → consolidate call sites → API + modal →
   Buddy watcher → docs → tests last (alongside, not after).
4. **REVIEW** — paranoid pass on bypasses: `httpx`, `aiohttp`, raw
   sockets, subprocess curl, `os.system("wget ...")`. The Python-level
   guard does **not** catch these. Decide whether to deny those imports
   in agent space or document them as known gaps.
5. **QA** — arail allocation: 30% setup, 30% Buddy, 20% security, 10%
   happy, 10% regression. Security gets the network-bypass attempt list.
   Buddy gets the "did the watcher fire when curator was blocked" check.
