# Agents, explained

This is the on-ramp. If you want the reference manual, see
[docs/agents.md](agents.md). If you want to *understand* what an
agent actually is in about five minutes, start here.

## The one-sentence version

**An agent is a loop that notices things and speaks up.**

That's it. Everything else — personalities, skills, dreams, folders,
goal-aware suggestions — is just detail hanging off that sentence.

## The five pieces

Every agent has exactly five parts. Once you see them, the code
stops being magic.

| Piece | What it is | In Buddy |
|---|---|---|
| **Personality** | A few sentences of voice + rules | "Warm, observant, actively helpful lab partner. One short sentence." |
| **Watchers** | Tiny functions that look at the lab | "Is RAM over 92%?", "Is the inbox piling up?" |
| **Memory** | What the agent remembers | Cooldowns on disk, nightly dreams in markdown |
| **Skills** | Procedural knowledge, in markdown | `observe-lab` — how to phrase, what's worth saying |
| **Voice** | One LLM call that turns facts into a sentence | `router.complete(prompt)` |

Buddy adds one piece on top of the canonical five — **suggesters**:
goal-anchored proposers that fire on a slower cadence than watchers
and only when a goal is set. They share the same personality + voice
plumbing; they just propose actions instead of reporting state.

Everything else is plumbing around these five-plus-one. The folder
structure, the loader, the dream daemon — they're all there to make
sure these pieces run reliably and stay editable.

## One tick, traced end to end

Pretend you're Buddy. Every 90 seconds, you wake up. Here's what
happens:

```text
  ┌──────────────────────────────────────────────────────┐
  │  1. Am I allowed to speak?                           │
  │     └─ Check the global cooldown (5 min minimum      │
  │        between utterances). If too soon, go back     │
  │        to sleep for 90s.                             │
  │                                                      │
  │  2. What's going on in the lab?                      │
  │     └─ Run all four watchers (GPU, inbox,            │
  │        researcher wins, plateau). Each returns       │
  │        a fact or None.                               │
  │                                                      │
  │  3. Anything worth saying?                           │
  │     └─ Filter out facts I already said recently      │
  │        (per-watcher cooldowns). If nothing's left,   │
  │        stay quiet.                                   │
  │                                                      │
  │  4. Pick the juiciest one.                           │
  │     └─ Praise beats warn beats info beats suggest.   │
  │                                                      │
  │  5. Phrase it.                                       │
  │     └─ Build an LLM prompt:                          │
  │         • personality (SYSTEM_PROMPT)                │
  │         • yesterday's dream (if any)                 │
  │         • skills (observe-lab's body)                │
  │         • the raw fact                               │
  │        Call router.complete(). Get one sentence.    │
  │                                                      │
  │  6. Say it.                                          │
  │     └─ activity_log.emit("buddy", sentence) → SSE →  │
  │        every dashboard subscriber lights up.         │
  │                                                      │
  │  7. Remember.                                        │
  │     └─ Update cooldowns. Write state.json. Sleep.    │
  │                                                      │
  │  8. (Every 15 min) Anything to suggest?              │
  │     └─ Only if a goal is set: poll SUGGESTERS for    │
  │        a phase nudge / review / skill / experiment   │
  │        proposal, paraphrase, emit. Same cooldown     │
  │        bookkeeping as the reactive cadence.          │
  └──────────────────────────────────────────────────────┘
```

That whole cycle is ~80 lines of Python. Read
[`_builtin_buddy.py`](../src/arail/agents/_builtin_buddy.py) and
you'll recognize every step.

## Where everything lives

The five pieces map cleanly onto files in one folder:

```text
lab/pkb/agents/buddy/
├── AGENT.md        personality, rules, skill list, opt-in toggles
├── buddy.py        watchers + suggesters + loop + voice — the "body"
├── state.json      memory: cooldowns, counts (auto-saved)
├── decisions.md    "why I changed X" — human-authored
└── dreams/
    ├── 2026-04-26.md   last night's reflection
    └── 2026-04-25.md   the night before
```

The separation is intentional:

- **Edit AGENT.md** to change voice, intervals, which skills are active.
- **Edit buddy.py** to add or remove watchers or suggesters.
- **Don't touch state.json** — it's memory, not config.
- **Write to decisions.md** when you make a big change so the agent
  (and future-you) knows what happened and why.
- **Read dreams/** when you want to know what the agent was thinking.

And for skills:

```text
lab/pkb/skills/observe-lab/
└── SKILL.md        procedural knowledge the agent loads into its prompt
```

Skills live next door. An agent composes its voice from **its own
personality + any skills it has loaded**. Edit a skill's markdown,
the next tick uses the new version. No restart.

## The hello-world agent

Strip away the personality, the skills, the dreams. Here's an agent
that does exactly one useful thing — say "hello" once a minute:

```python
# lab/pkb/agents/hello/hello.py
import asyncio
from arail.activity import activity_log


class HelloAgent:
    def __init__(self):
        self._task = None
        self.status = "idle"

    def start(self):
        self.status = "running"
        self._task = asyncio.create_task(self._tick())

    async def _tick(self):
        while True:
            await asyncio.sleep(60)
            activity_log.emit("hello", "👋 hi there", "info")


hello = HelloAgent()  # <-- must match the folder name
```

With a two-line `AGENT.md` next to it:

```yaml
---
name: Hello
auto_start_env: LAB_HELLO
---

# Hello — minimum viable agent
```

Restart the portal. Now `/agents` has a fourth activity source
called `hello`, saying "👋 hi there" every minute. That's the whole
mechanism.

**From here, everything else is just layers:**

- Add **watchers** (like Buddy does) so it speaks only when something
  interesting happens.
- Add a **personality** to shape what "hi there" becomes.
- Add **skills** to give it domain expertise it can consult.
- Add **suggesters** to propose actions when a goal is set.
- Add **state.json** to remember cooldowns across restarts.
- Add **dream()** to reflect nightly.

Each layer is optional. You can ship a useful agent with just the
hello-world skeleton above.

## Why it works this way

Three design choices, each intentional:

### 1. Agents live in markdown + Python, not a database

Everything about an agent — config, code, memory, decisions, dreams
— is a plain file under the PKB. The wiki indexes them, `/knowledge`
browses them, `git` tracks them if you want, `./arail reset pkb`
wipes them cleanly. No hidden state, no mystery DB rows.

### 2. Agents are Python, not JSON schemas

Claude's API has a tool-calling protocol where the model says "I'd
like to use tool X" and the harness routes it. We don't need that
layer because agents *are* Python — they import `activity_log`,
`pkb.search`, `router.complete` directly. Skills ship procedural
**knowledge** (markdown); tools ship procedural **capability**
(Python). Both are first-class; neither needs a JSON schema.

### 3. One loop, not many tasks

Buddy is one asyncio task that polls a list of watchers (and, on a
slower cadence, a list of suggesters). You could imagine every
watcher being its own task — more "proper" async, more moving parts.
We don't do that. Watchers are cheap, simple functions; running
them in sequence once a minute is fine, and the single-loop
structure is easier to reason about, cancel, and debug.

## The "magic" is three steps of indirection

If agents still feel magical after reading this, it's usually
because three indirections compound:

1. **Dynamic import.** The file at `lab/pkb/agents/buddy/buddy.py`
   gets loaded into Python at runtime by
   [`loader.py`](../src/arail/agents/loader.py) using
   `importlib.util.spec_from_file_location`. That's why edits to
   the file take effect on next restart — Python re-reads the whole
   file, no package reinstall, no restart in the middle of a tick.

2. **SSE fan-out.** When Buddy calls `activity_log.emit`, that event
   goes to every dashboard page currently watching the
   `/api/activity/stream` endpoint. The "message appeared on my
   screen" magic is just a server-sent-events subscription — one
   message in, N clients out.

3. **LLM paraphrase.** The step "turn a fact into one sentence" is
   one `router.complete()` call. The prompt is three deterministic
   strings concatenated (personality + skills + fact); the output
   is whatever the local model feels like saying that tick. That's
   where the personality comes alive — but also where debugging
   gets tricky. When Buddy sounds weird, check the prompt first.

That's the whole magic. Everything else is code you can read in
one sitting.

## Go deeper

- [`src/arail/agents/_builtin_buddy.py`](../src/arail/agents/_builtin_buddy.py) —
  the canonical agent. Read this second.
- [`src/arail/agents/loader.py`](../src/arail/agents/loader.py) —
  how the folder structure turns into running code.
- [`src/arail/skills_loader.py`](../src/arail/skills_loader.py) —
  how SKILL.md becomes part of an agent's prompt.
- [`src/arail/agents/dream_daemon.py`](../src/arail/agents/dream_daemon.py) —
  the nightly reflection scheduler.
- [`docs/agents.md`](agents.md) — the full reference (architecture,
  contracts, rationale). Read this when you're ready to ship an agent.
