# Vision: airgap-runtime-toggle

**Recommendation:** **proceed** — but with two non-negotiable architect
constraints (confirm-step UX + bind-address gate). Without those, the
toggle weakens the very claim PR #35 just made true.

**Date:** 2026-05-07
**Product:** arail
**Wedge size:** one sprint
**References:** [`SPRINT.md`](./SPRINT.md) is the kickoff ledger; this
file ratifies the framing and forces the six questions. Don't paraphrase
SPRINT.md — read it.

---

## The six questions

### 1. User
The same operator from PR #35: a privacy-skeptical lab owner running
ARAIL on their own laptop or workstation with `LAB_MODE=airgapped` as
the default. PR #35 made the policy real. This sprint serves *that
same user* on the day they need to deliberately, briefly, open the
door — to test a cloud provider, to sync a HuggingFace model, to
benchmark against Anthropic. They do not want to `vim .env && pkill -HUP`
to do it; they want a button that surfaces the same modal that already
explains the policy. Critically, they also do not want to flip it by
accident (a misclick on the badge), and they do not want a roommate /
LAN peer / browser-tab CSRF to flip it for them.

This is **not** for the friend who installed ARAIL and is browsing
HuggingFace casually — that friend is on `LAB_MODE=hybrid` already.
The toggle is for the operator who lives in airgapped and visits hybrid.

### 2. Problem
PR #35 turned `LAB_MODE` into a real security boundary; the only way
to cross that boundary today is to edit `.env` and restart. That
restart cost discourages legitimate hybrid use, which means in practice
users will either (a) leave `LAB_MODE=hybrid` permanently to avoid the
friction (defeating the whole point of PR #35) or (b) be locked into
airgapped and unable to use the cloud-provider Compute Sources the
README advertises. Either outcome makes the airgap policy a worse
product, not a better one. The user's framing — *"fundamental to all
ARAIL modes"* — is correct: a security mode without a sane mode
transition is a footgun.

### 3. Win condition (specific, observable, falsifiable)
On the merged branch, all of these are true in one demo session:

- Click the nav badge → modal opens → click the "Open the door"
  toggle → confirm step → modal closes and reopens showing `hybrid`
  pill. Within one tick:
  - `arail.airgap.lab_mode()` returns `"hybrid"`.
  - `os.environ["LAB_MODE"] == "hybrid"`.
  - The user's `.env` (or `lab/data/secrets.env` per existing
    convention — architect picks) has the line `LAB_MODE=hybrid`,
    written atomically (temp + rename), preserving every other line
    byte-for-byte including comments and blank lines.
  - `lab/data/egress.jsonl` records a structured `mode_toggle` line
    (or the existing activity-log path emits one — architect picks).
  - Buddy's airgap watcher fires its `Door's open now…` Observation
    on the next tick — the cached `airgap_last_lab_mode` advances.
- Restart the lab. `lab_mode()` still returns `"hybrid"`. The
  `.env` value survives.
- Toggle back. Same sequence in reverse — Buddy posts `Sealed back
  up…`. `EgressBlocked` fires on the next attempted public fetch.
- A new test `tests/test_airgap_toggle.py` covers: env-rewriter
  preserves comments / quoted values / missing line / trailing
  whitespace; concurrent toggles serialize correctly (no torn
  writes); the endpoint refuses when bind-address ≠ loopback (see
  architect constraint below).
- The README + PRIVACY.md are updated to describe the toggle (one
  paragraph) and to state explicitly that flipping to hybrid takes
  effect immediately and persists across restart.

The win is **not** "users can toggle." It's the test passing, the
`.env` round-tripping cleanly, Buddy detecting the flip, and the
threat-model paragraph being honest about what the button does and
who can press it.

### 4. Wedge — what this unlocks
PR #35 was about *honesty*. This sprint is about *control*.
Together they reposition ARAIL's airgap claim:

> *"Local-first by default, with one-click control. The lab makes
> zero outbound calls until you say otherwise — and you can say
> otherwise without leaving the UI."*

That is a meaningfully stronger blueprint pitch than either piece
alone. Forks inherit it for free.

What this **does not** unlock and should not pretend to:

- It does not protect against a localhost-reaching adversary. The
  threat model is the well-meaning operator, the same as PR #35.
- It does not change the Compute Source pivot (cloud providers still
  appear/disappear from the dropdown based on `lab_mode()`). The
  toggle just changes which side of that pivot you're on.

### 5. Disconfirming evidence
We were wrong to ship this if any of the following surface:

- **A user reports an accidental flip.** They didn't mean to enable
  hybrid; they clicked the badge expecting an info modal (the PR-#35
  behavior) and ended up with cloud egress on. If we see this even
  once before merge, the confirmation UX is too soft. Architect must
  pick something stronger than a single click.
- **The portal binds to `0.0.0.0` for someone's LAN access** (a
  documented mode in `docs/MACOS.md` / `docs/LINUX.md` — verify) and
  the toggle endpoint is reachable from the LAN. That means a peer
  on the same Wi-Fi can flip the policy. If true, gate the endpoint
  on bind-address-is-loopback and reject otherwise. Treat this as a
  ship-blocker, not a follow-up.
- **The `.env` rewriter clobbers the user's file.** Comments
  reordered, quoted values mangled, trailing newline lost — any of
  these are user-visible breakage. If QA finds this, defer ship.

### 6. Displacement
What gets less attention while this sprint is running:

- **The min-tier hardening track** (Track A in `~/.claude/plans/
  toasty-hopping-badger.md`). One engineer-week here is one not on
  there. This is the headline trade. **Acceptable** because the
  toggle directly serves the same persona min-hardening is for —
  the lab owner who actually uses airgapped — and an unusable
  airgap is a hardening problem too.
- **The `qukaizen/arail-opencode-curation` branch**, stashed per
  SPRINT.md decisions log. Two stashes parked. Stash rot risk is
  small; mitigation already documented.
- **aerollm Phase-2 HTTP bindings** — unchanged from PR #35's
  displacement analysis. Not blocked by this work; arguably helped
  (cleaner mode transition is what aerollm slots into).

The trade is honest. If the user wants to defer the toggle and
spend the week on min-hardening instead, that's a defensible call —
but the toggle is one sprint, not three, and PR #35 leaves a real
UX wound until the toggle lands.

---

## For the architect

Drop these into ARCHITECTURE.md as constraints, not suggestions.
Every one is a load-bearing decision the builder must not make on
the fly:

- **Confirmation UX is non-negotiable.** Single-click flips the
  security posture; that's a footgun. Pick one of: (a) two-step
  modal-confirm with explicit "Yes, allow outbound calls" copy,
  (b) hold-to-confirm (2s press), (c) text-input-to-confirm
  ("type ENABLE to continue"). The architect picks; default to
  (a) unless there's a reason. Whatever you pick, name it
  explicitly in ARCHITECTURE.md.
- **Bind-address gate.** The toggle endpoint MUST refuse if the
  Flask app is bound to anything other than loopback (`127.0.0.1`,
  `::1`, or `localhost`). Some users run the portal on `0.0.0.0`
  for LAN access — audit `app.py` to confirm this is configurable,
  and refuse the toggle on non-loopback bind. Return a clear error
  message in the modal: *"Toggle disabled: portal is reachable
  beyond this host. Edit `.env` directly to change `LAB_MODE`."*
  Without this gate, the toggle is functionally CSRF-able from any
  device on the LAN.
- **`.env` rewriter race conditions.** Two clients clicking
  simultaneously; portal restart mid-write; power-cut. Use
  atomic temp-file + `os.replace` (POSIX rename guarantee). Hold
  a `threading.Lock` for the rewriter so two requests serialize.
  The watcher tick must not interleave with the writer mid-flight.
- **`.env` parsing edge cases.** All of these must round-trip:
  comments (`# foo`), inline comments (`LAB_MODE=airgapped # default`),
  quoted values (`LAB_MODE="airgapped"`), single-quoted, missing line
  entirely (append, don't fail), duplicate lines (last wins, don't
  duplicate further), CRLF line endings, missing trailing newline,
  Windows BOM. Test each. **Never `dotenv.set_key` blindly** — its
  rewriter has known bugs around comments. Write our own line-by-
  line rewriter or document precisely which library version we
  pinned and why.
- **CSRF protection on the endpoint.** Even on loopback, a
  malicious browser tab on the same machine can issue
  `fetch('http://127.0.0.1:8080/api/airgap/toggle', {method:'POST'})`.
  Require either a same-origin check (`Origin`/`Referer` header
  match), a CSRF token from the modal, or a `Sec-Fetch-Site:
  same-origin` check. Pick one. Document it.
- **Which file gets rewritten?** SPRINT.md says `.env`; PR #35's
  convention is `lab/data/secrets.env` (chmod 0600, gitignored).
  These are not the same file. The user's `LAB_MODE` lives where?
  Audit both; pick one canonical location; write a short note in
  ARCHITECTURE.md so the builder doesn't guess. If both exist,
  the writer must rewrite the *active* one (whichever the loader
  reads from at startup).
- **Activity log + Buddy ordering.** Per SPRINT.md notes: set
  `os.environ["LAB_MODE"]` BEFORE writing the activity-log line,
  so the next watcher tick sees the new mode and emits the right
  Observation. Document this as an invariant.
- **Buddy's `airgap_last_lab_mode` schema dependency.** PR #35's
  re-review §2 noted that state.json is informally co-owned;
  read-merge-write pattern. The toggle's activity-log emit feeds
  the watcher's mode-toggle branch, which writes
  `airgap_last_lab_mode`. Confirm the merge invariant still holds
  with a third writer (the toggle endpoint, indirectly via the
  watcher). No new direct writers to `state.json` from the toggle
  path — keep the schema fragmentation contained.
- **Modal copy must not minimize the change.** "Open the door" is
  cute; the confirmation step must say plainly: *"This allows
  agents to make outbound network calls to public hosts. Cloud
  provider keys in `lab/data/secrets.env` will be used. Continue?"*
  Copy is a load-bearing artifact here, not decoration.

---

## Recommended next step
Proceed to `/architect` design phase. Architect must produce
ARCHITECTURE.md that names the confirmation UX, the bind-address
gate, the `.env` rewriter strategy (atomic + lock), the CSRF
mitigation, and the canonical file location explicitly. The
builder must not make any of those calls on the fly.
