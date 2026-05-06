# Vision: airgap-honest-mode

**Recommendation:** **proceed**

**Date:** 2026-05-05
**Product:** arail
**Wedge size:** one sprint
**References:** `sprints/2026-05-05-airgap-honest-mode/PLAN.md` (full architecture, file list,
verification matrix). This file ratifies the framing; it does not duplicate the plan.

---

## The six questions

### 1. User
A privacy-skeptical operator who clones ARAIL onto their laptop or home
workstation, leaves `LAB_MODE=airgapped` on, and reads the README's
*"the lab makes zero network calls"* line as a contract — not marketing.
They run a local AirLLM/Ollama node (often on a LAN GPU box at
`192.168.x.y`), let agents loose against it, and expect the lab to
*self-enforce* the boundary they were promised. Concretely: the user
who wrote *"agents can't collect information from the internet"* as
the gate.

### 2. Problem
The README lies. `airgapped` today only blocks the Chat tab's cloud
provider endpoints; agents can still write `requests.get("https://...")`
or hit HuggingFace via Buddy's `LAB_INTERNET_ENABLED` side-flag, and
the duplicated `_is_airgapped()` helpers across 5 files mean any new
agent author silently bypasses the gate. The user can't tell from
inside the product what's actually enforced. There is no choke point
and no audit trail.

### 3. Win condition (specific, observable, falsifiable)
**A reasonable adversarial agent cannot reach the public internet
without raising `EgressBlocked`, and the user can see that in the UI.**
Concretely, all of these must be true on the merged branch:

- `tests/test_egress_guard.py` passes: `requests.get("https://example.com")`
  raises `EgressBlocked` under `LAB_MODE=airgapped`; `requests.get` to
  `127.0.0.1` / `192.168.x.y` / `10.x.y.z` passes through; `urllib.request.urlopen`
  is also caught.
- `lab/data/egress.jsonl` records exactly one structured line per block.
- Click the nav-badge in airgapped mode → modal shows the operational
  definition + recent blocks, populated from `GET /api/airgap/status`.
- Demo (recorded in BUILD_LOG step 2): trigger curator with a goal that
  needs a fetch → block fires within ~10s and Buddy posts a chat
  heads-up referencing the blocked host.
- README §"What local-first means" and §"Airgapped guard" no longer say
  *"zero network calls"*; they state the operational definition
  verbatim.
- `./arail benchmark_models` against a LAN AirLLM node still completes —
  the guard isn't a PITA for the common setup.

The win is *not* "users will feel safer." It's the test passing, the
modal populating, and the README matching reality. All three are
witnessable in one PR.

### 4. Wedge
The plan is the wedge — a single sprint that lands the choke point,
the audit log, the honest UI copy, and Buddy awareness. The wedge is
deliberately scoped to the Python-level guard (the well-meaning-agent
threat model), not OS-level firewalling.

**What this unlocks beyond fixing the bug:**

- Honest privacy claims become a *blueprint* selling point. ARAIL's
  README pitch (*"local-first, fork-and-rename"*) is undercut every
  hour the "zero network calls" line stays false. After this sprint,
  forks inherit a real airgapped guarantee — that's a thing the
  blueprint *gives* you, not a thing you have to wire.
- A single source of truth (`src/arail/airgap.py`) for downstream
  questions (theme/tier/consent/etc.) — collapsing 5 duplicated
  helpers into 1 is the structural win that future event-bus work
  rides on.
- `lab/data/egress.jsonl` is a forensics artifact the SRE agent (and
  future curator policy) can mine. We don't need that today; we won't
  have to retrofit logging when we do.

This is **strengthening the blueprint pitch**, not just lab plumbing.
The README change is the load-bearing deliverable; the code makes the
README true.

### 5. Disconfirming evidence
We were wrong about scoping/value if any of these show up:

- **The guard makes the common setup painful.** A user reports a
  reasonable LAN/loopback workflow that hits `EgressBlocked` and they
  have to set `LAB_MODE=hybrid` to unstick it. Means the allow-list
  (loopback + RFC1918 + link-local) was wrong or the guard caught a
  legitimate path. If we see this twice, revisit the allow-list.
- **A trivial bypass ships in v1.** QA's bypass-attempt suite finds
  that `httpx` / `aiohttp` / `subprocess curl` / raw socket all reach
  the internet despite the guard, and we shipped without documenting
  the gap. Means the architect punted on the threat model and the
  README's new claim is *still* false. Block ship until the gap is
  either closed or explicitly documented.
- **Buddy's egress notifications become noise.** First three days, ten
  blocks/hour from a single agent's polling loop spam the chat. Means
  the watcher needs rate-limiting / dedup before merge — not after.

If 2+ of these surface during QA, defer ship until addressed.

### 6. Displacement
QuKaiZen has three products. This sprint is one engineer-week on
arail. What gets less attention while it's running:

- **aerollm Phase-2 HTTP bindings** (the Compute Source pivot's planned
  next consumer). Acceptable: that work is not blocked by airgap
  honesty; if anything, an honest airgapped surface is what aerollm
  swaps *into* later.
- **The `qukaizen/arail-airllm-subprocess-isolation` branch**, stashed
  per the SPRINT.md decision log. Restore-on-completion is documented;
  small risk of stash rot. Mitigation: the stash list is one file.
- **Theme/UI toggle awareness** (the user mentioned it; deferred to a
  follow-up). Acceptable per the decisions log.

Nothing else gets displaced. The trade is honest.

---

## For the architect

Drop these into ARCHITECTURE.md as constraints, not suggestions:

- **Bypass triage is a deliverable, not a footnote.** `httpx`,
  `aiohttp`, `socket.socket().connect()`, `subprocess` calling `curl`/`wget`,
  `os.system`, and `urllib3` direct usage all sidestep a `requests`-only
  adapter. Decide for each: (a) wrap at import time in agent space,
  (b) document as known gap in the modal + PRIVACY.md, or (c) both.
  Default to **document loudly** rather than silently leak.
- **`urllib.request` opener install must be idempotent and survive
  re-imports.** Tests that monkeypatch openers will collide otherwise.
- **`EgressBlocked` must subclass `RuntimeError`, not `Exception`** — the
  plan says so; lock it. Agents that `try: ... except Exception:` already
  exist; we want them to crash visibly, not swallow.
- **`lab/data/egress.jsonl` rotation under load.** A polling agent in
  airgapped that retries every 5s writes 17k lines/day. Cap and rotate
  at ~5MB; reads for the modal must be bounded (last-N tail, not
  full-file slurp).
- **The egress probe (`BUDDY_EGRESS_PROBE=1`) is itself a network call
  in airgapped mode.** It's opt-in for a reason. Make sure the guard
  *itself* doesn't catch the probe (or does, and that's documented as
  intentional). The irony surface is real and the README copy must
  not promise what the probe contradicts.
- **`@allow_egress("reason")` context manager has airgapped semantics
  too.** Plan says "not used in airgapped — there is no escape hatch."
  Enforce that at the function level: in airgapped, the decorator
  raises *immediately*. Otherwise a future contributor weakens the
  guarantee in two lines.
- **The README change is a code change.** Do not let the builder ship
  without the three README spots and `docs/PRIVACY.md` updated. The
  whole sprint's value collapses if the lying paragraph stays.
- **Subprocess agents are out of scope (per plan), but call it out
  explicitly in ARCHITECTURE.md** so it's a known gap before aerollm
  Phase-2 lands HTTP bindings, not a surprise then.

---

## Recommended next step
Proceed to `/architect` design phase with this VISION.md and the
existing PLAN.md as joint inputs. Architect's paranoid review must
explicitly enumerate the bypass list above and decide each one before
the builder starts.
