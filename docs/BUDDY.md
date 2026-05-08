# Buddy

Buddy is the lab's personality agent — context-aware, goal-tracking, offline by
default. This doc covers two things: how Buddy works at the desk, and what
"Buddy Tunnel" actually means when it claims to follow you across messaging
channels.

## TL;DR

- **Buddy at the lab**: works fully airgapped, no network needed. This is the
  default and the lab's safest mode.
- **Buddy Tunnel** (off by default): aspirational reach across messaging
  channels. Most channels require a gateway and internet. Airgapped mode
  blocks Buddy Tunnel by design.

## Buddy in airgapped mode

When `LAB_MODE=airgapped` (the default), Buddy:

- Loads its skills, memory, and personality entirely from local disk.
- Talks to the lab's local model via the `my_machine` provider.
- Cannot reach Anthropic, OpenAI, OpenRouter, NVIDIA NIM, or HuggingFace —
  the portal blocks every cloud-provider API at `/api/providers/*`.
- Persists everything to `lab/data/`. Conversations never leave the box.

This is the mode Buddy is designed for. Everything below assumes you have
explicitly opted out of it.

## Buddy Tunnel: the honest version

The marketing pitch is that Buddy follows you across iMessage, Signal,
WhatsApp, Telegram, Slack, and Discord, and is the only agent registered on
each channel. The architectural reality is that each channel has a different
access model and not all of them can be reached cleanly from a private box.

### Cleanest channels

| Channel    | Access path                                | Notes                                                                           |
| ---------- | ------------------------------------------ | ------------------------------------------------------------------------------- |
| Telegram   | Official Bot API + MTProto                 | Cleanest. Runs against the public Telegram servers, no third party in the path. |
| Slack      | Official OAuth + Events API                | Clean. Workspace-scoped; the bot user is registered, not impersonated.          |
| Discord    | Official Bot API                           | Clean. Per-guild bot credential.                                                |
| Signal     | `signal-cli` / `libsignal`                 | Doable locally with a registered phone number, but every message still rides   |
|            |                                            | Signal's relay servers — no LAN-only mode.                                      |

### Compromised channels

| Channel  | Access path                                            | Why it's not clean                                                                                                                           |
| -------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| iMessage | Apple-locked. macOS AppleScript / `imessage.framework` | Requires a Mac in the loop to relay. Apple has no official bot API. Third-party bridges (Beeper Mini, AirMessage) own the integration risk.  |
| WhatsApp | Meta Business API (paid + gated) or `whatsapp-web.js`  | Either you pay Meta and pass review, or you ride an unofficial library that violates WhatsApp ToS. Both paths break airgapped guarantees.    |

### What "Buddy is the only agent registered on each channel" actually means

For the cleanest channels (Telegram, Slack, Discord), Buddy holds the bot
credential and is the only registered identity on that channel for your lab.
The platform's own server still mediates; Buddy's claim is **integrity**
(no other agent of yours is on that channel), not **secrecy** (the platform
operator can still see plaintext if their architecture allows it — read each
platform's encryption story before trusting it).

For Signal, the platform itself encrypts end-to-end, so Buddy reading or
writing is equivalent to a regular Signal client. For iMessage and WhatsApp,
the bridge layer in the middle is part of the trust boundary; Buddy alone
cannot make claims about it.

### Required infrastructure

Buddy Tunnel needs a gateway component (call it whatever you want — bridge,
adapter, federation layer) that:

1. Holds per-channel credentials (bot tokens, OAuth grants, signal-cli state).
2. Normalizes inbound messages from every channel to a single internal event
   format.
3. Dispatches Buddy's outbound responses back through the right adapter.

Without that gateway, Buddy is desk-only. With it, Buddy is reachable from
every channel you authorized — but only while the lab box has internet, and
only for channels whose servers you can reach.

## Why airgapped mode breaks Buddy Tunnel

Every channel above terminates on a server you do not control:

- Telegram, Signal, Slack, Discord, WhatsApp: vendor-hosted message servers.
- iMessage: Apple Push Notification Service.

If the lab is airgapped, none of those servers are reachable, so the gateway
has nothing to talk to. The portal therefore disables Buddy Tunnel when
`LAB_MODE=airgapped`. This is intentional, not a bug.

To use Buddy Tunnel:

1. Set `LAB_MODE=hybrid` in `.env`.
2. Restart the portal.
3. Configure the gateway (channel credentials, registration, etc.).
4. Authorize Buddy on each channel you want.

Switching back to airgapped immediately re-blocks the tunnel; there is no
"sometimes online" middle state. Either you opted in to the messaging
network for this session, or the lab is sealed.

## When to leave airgapped mode

There are three reasonable reasons:

1. You want Buddy Tunnel reach (this doc).
2. You want to use a cloud teacher temporarily for a domain Buddy doesn't
   have a strong local model for.
3. You are building, not researching, and need to fetch a package or a
   model artifact.

Anything else — and especially anything where the lab has been ingesting
sensitive material — should stay airgapped.

## Where Buddy lives in the repo

- `src/arail/agents/buddy.py` — backcompat import surface.
- `src/arail/agents/_builtin_buddy.py` — built-in personality + skills.
- `src/arail/agents/loader.py` — seeds Buddy from PKB or builtin, caches
  one shared instance.
- `lab/pkb/agents/buddy/` — Buddy's PKB profile, skills it loads.

The "tunnel" code does not yet exist in this repo. When it does, it will
live behind a feature flag that respects `LAB_MODE` and refuses to start
in airgapped mode.

## Related

- [INSTALL.md](INSTALL.md) — install Arail (and therefore Buddy).
- [PRIVACY.md](PRIVACY.md) — exactly what the lab does and does not send
  off the box.
- [vibe-integrate.md](vibe-integrate.md) — how an agent walks a fresh user
  to a working production build of the lab.
- [agents-explained.md](agents-explained.md) — Buddy in context with
  Drafter, Curator, Researcher, SRE.
