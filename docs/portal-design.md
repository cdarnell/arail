---
title: Portal Design Spec
category: Design
order: 10
tags:
  - design
  - architecture
  - philosophy
audience: architect
related:
  - agents-explained
  - api-conventions
buddy_prompt: Walk me through the ARAIL portal design spec — tokens, layout primitives, and component patterns.
---
# ARAIL — Design Spec

> A rail gun for AI. Terminal‑hacker aesthetic, server‑rendered, no JS frameworks.
> This doc is the single source of truth for visual decisions across the portal.
> If the CSS drifts from this doc, the doc is wrong — fix it.

---

**Sections:** §1 brand · §2 tokens · §3 layout · §4 components · §5 interactions · §6 pending · §7 themes · §8 how to extend.

## 1. Brand anchors

- **Name:** ARAIL — Autoresearch AI Labs (configurable per fork via `LAB_NAME`; see [`brand.py`](../src/arail/brand.py)).
- **Tagline:** *A rail gun for AI* — fast, precise, single‑shot. The UI should feel like aiming a precision instrument, not browsing a dashboard product.
- **Voice:** terse, technical, lowercase‑comfortable. Prefer `parse goal` over `Submit your goal for parsing`. Status sentences, not paragraphs.
- **Logo:** `⟨Autoresearch⟩` glyph in nav — green‑on‑black, glow, JetBrains Mono. Forks override via `LAB_LOGO`.
- **Signature visual:** the **rail line** — a 1px gradient stripe under the nav bar (green → blue), faintly shimmering. It's the only persistent ornament. Everything else stays flat and quiet.

---

## 2. Tokens

All tokens live in `:root` of [`static/style.css`](../src/arail/portal/static/style.css). Templates and other CSS files **must** reference tokens, not raw hex/rgba.

### Palette

| Token | Hex | Use |
|---|---|---|
| `--bg` | `#0a0a0f` | App background |
| `--surface` | `#0f1118` | Nav, cards |
| `--surface2` | `#151821` | Hover, nested panels, tooltips |
| `--border` | `#1e2230` | Default 1px borders |
| `--border-hi` | `#2a3040` | Hover/focus borders |
| `--text` | `#c8cdd8` | Body text |
| `--text-hi` | `#e8ecf4` | Headings, input values |
| `--muted` | `#78839a` | Labels, timestamps, captions |
| `--green` | `#00ff41` | Primary action, success, "online" |
| `--green-dim` | `#00cc33` | Pressed/secondary green |
| `--blue` | `#00d4ff` | Links, knowledge, info |
| `--amber` | `#ffb000` | Caution, hybrid mode, warnings |
| `--red` | `#ff3355` | Halt, errors, destructive |
| `--purple` | `#b48eff` | Agents, personality, special |

### Alpha tiers

For tinted backgrounds and borders, use the alpha tiers — never hand‑roll `rgba(...)`.

- `-a08` → ~8% (subtle wash, idle chip background)
- `-a16` → ~16% (hover wash)
- `-a28` → ~28% (active border)

Available for: `--green`, `--blue`, `--amber`, `--red`, `--purple`.

### Spacing scale

4‑px rhythm. Compose layouts from these only.

| Token | Value |
|---|---|
| `--s-1` | 4px |
| `--s-2` | 8px |
| `--s-3` | 12px |
| `--s-4` | 16px |
| `--s-5` | 24px |
| `--s-6` | 32px |
| `--s-7` | 48px |

### Type scale

JetBrains Mono everywhere. No exceptions.

| Token | Size | Use |
|---|---|---|
| `--fs-xs` | 0.65rem | Mode badges, micro labels |
| `--fs-sm` | 0.75rem | Captions, nav, clock |
| `--fs-md` | 0.85rem | Body, inputs |
| `--fs-lg` | 1rem | Logo, prominent body |
| `--fs-xl` | 1.4rem | Card numbers, gauges |

### Radius & elevation

- `--radius` 6px (everything except pills, which are `999px`).
- `--elev-1` `0 2px 8px rgba(0,0,0,.35)` — hover lift on cards.
- `--elev-2` `0 6px 24px rgba(0,0,0,.55)` — tooltips, popovers.
- Glows (`--glow-green`, `--glow-blue`, `--glow-amber`, `--glow-red`) replace shadows on focus/active for accent elements.

---

## 3. Layout primitives

- **Page width:** content centered in a max‑width column (~1280px). Full‑bleed only for nav, the rail line, and the scanline overlay.
- **Nav:** 0.6rem × 1.5rem padding, single row, logo + tier‑gated links + clock + mode badge. Sticky‑ish (currently static; revisit if pages get long).
- **Rail line:** 1px height, full width, immediately below nav. `linear-gradient(90deg, transparent 0%, var(--green) 30%, var(--blue) 70%, transparent 100%)` with a 12s ease‑in‑out shimmer.
- **Cards:** `--surface` bg, `--border` 1px, `--radius` corners, `--s-5` padding, `h2` is an UPPERCASE 0.7rem `--muted` label with optional 6px colored indicator dot.
- **Grids:** prefer CSS grid with `gap: var(--s-4)`. Avoid floats and absolute positioning except for tooltips/badges.
- **Scrollbars:** thin (6px), `--border-hi` thumb on `--bg` track. Hidden everywhere except where overflow is real.

---

## 4. Component inventory

| Component | Where | Notes |
|---|---|---|
| **Logo** | every page (nav) | Green, glow. Tooltip shows tier. |
| **Nav link** | every page | `--muted` default → `--text` hover → `--green` active. |
| **Mode badge** | nav (`airgapped` / `hybrid` / `window-*`) | Pill with tinted bg + matching border. Pulses on `airgapped`. |
| **Goal chip** | nav (when set) | Blue pill, ellipsis on overflow, links to /chat. |
| **Card** | dashboards, agents, knowledge | Flat surface with muted heading + optional indicator dot. |
| **Button** | global | `.btn` base + variant (`-primary -blue -amber -red -ghost`) and `-sm` size. |
| **Goal form** | dashboard | `parse_goal>` prefix in green, mono input, focus glow. |
| **Activity row** | dashboard | Timestamp · agent · message; alternating row tint optional. |
| **Indicator dot** | card headings | 6×6 round, color signals state (green online, amber working, red error, blue info). |
| **Tooltip / popover** | tooltips, parse helper | `--surface2` bg, `--border-hi`, `--elev-2`. |
| **Toast (proposed)** | corner, Buddy whisper | See §6. |
| **Gauge (Mission Status)** | dashboard | Currently number + bar; needs step‑context (see §6). |

States every interactive element must define: **idle, hover, focus, active, disabled, loading**.

---

## 5. Interaction patterns

- **Streaming responses (chat, agents):** SSE via FastAPI `StreamingResponse`, rendered token‑by‑token with a blinking caret (`▍`) until done. Caret is `--green` for local models, `--blue` for cloud.
- **Tier gating:** server decides surfaces (`min` vs `max`); UI never renders a disabled link. Upgrades are a CLI action, not a UI button — keeps tiers honest.
- **Empty states:** one line of `--muted` text + the next action as a `.btn-ghost`. No illustrations.
- **Loading states:** prefer optimistic render + caret. For unknown‑duration jobs (research run), use a horizontal indeterminate bar in the parent card header.
- **Errors:** inline `--red` line at the relevant control. Never modal. Halt + Resume buttons are the only red buttons in the nav.
- **Motion:** 150ms ease for hovers, 12s ease for the rail shimmer, 3s for the airgapped pulse. Nothing else animates without a reason.

---

## 6. Pending / open questions

Tracked in `memory/project_pending_ui_work.md`. Mirror here so contributors see them.

- **Mission Status step‑context.** Gauge should sit next to a 1–2 line "what step are we in" caption, not stand alone.
- **Corner‑toast whisper.** Proactive low‑volume notifications from Buddy. Bottom‑right, `--surface2` + `--purple` left border, auto‑dismiss 8s, click → opens chat focused on that thread.
- **Sticky nav?** Pages are getting longer (chat, knowledge). Decide before adding more.
- **Single CSS file vs per‑surface files.** Currently 7 css files (style + agents + research + knowledge + skills + graph + wiki). Fine for now. Re‑evaluate when style.css crosses 3000 lines.

---

## 7. Themes

Themes swap **only the accent palette + alpha tiers + glows**. Backgrounds, surfaces, text, spacing, type, and radius stay shared. That rule is what keeps a new theme from breaking layouts — if a theme has to redefine `--surface` or `--s-4`, it's a redesign, not a theme.

Apply via `data-theme` on `<html>`:

```html
<html data-theme="default">     <!-- terminal hacker green (current) -->
<html data-theme="laser-blue">  <!-- electric cyan, "precision instrument" -->
```

`nav.js` runs a tiny bootstrap that reads the theme from `localStorage["arail-theme"]` and applies it before the rest of the page initializes. A cycle‑button (`.theme-picker`) is injected into the nav on every page; clicking it advances to the next registered theme and persists.

### Registered themes

| id | Label | Accent (--green) | Vibe |
|---|---|---|---|
| `default` | Default | `#00ff41` (terminal green) | matrix, hacker, alive |
| `laser-blue` | Laser Blue | `#5cf0ff` (laser cyan) | precision, cool, surgical |

### Adding a theme

1. Add a `html[data-theme="<id>"] { ... }` block in `style.css` redefining: `--green`, `--green-dim`, `--blue`, `--amber`, `--red`, `--purple`, all 15 `*-a08/16/28` alpha tokens, and the four `--glow-*` shadows.
2. Add a row to the `THEMES` array at the top of `nav.js` with `{ id, label, swatch }`.
3. Add a row to the table above.

### Public JS API

```js
window.ARAIL.theme.list             // [{id,label,swatch}, …]
window.ARAIL.theme.get()            // current id
window.ARAIL.theme.set('laser-blue')// apply + persist
window.ARAIL.theme.cycle()          // advance to next
```

---

## 8. How to extend

1. Need a new color or size? **Add a token first**, then use it. PRs that hard‑code a hex or px value get bounced.
2. Need a new component? Add a row to §4 with a one‑line description. If it has more than three states, sketch them as a HTML snippet in this doc.
3. Changing the brand for a fork? Override env vars (see [`brand.py`](../src/arail/brand.py)) — never edit CSS to rebrand.
4. Big visual proposal? Open a PR that updates this doc *first*, with the CSS change second. Discussion happens on the doc.
