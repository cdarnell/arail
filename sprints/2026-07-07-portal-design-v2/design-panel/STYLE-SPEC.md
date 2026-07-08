# STYLE-SPEC — ARAIL portal design v2 ("Warm Observatory, sharpened")

**Binding for implementation.** Everything here is phrased against the existing v2 token
contract in `src/arail/ui_theme.py` (`ThemeColors` 12 slots, `_derive()` neutrals,
`_PERSONALITY` scalar table) and the World gate in `src/arail/world_theme.py`
(`dac.world-theme/v1`). Reference mockup: `winner-refined.html` in this directory.
Decision record: `JUDGING.md`.

Direction in one line: a night-observatory lab — warm indigo surfaces, amber
instrument-light for actions, cool cyan starlight for data, mono quarantined to
measurements, exactly one glow.

---

## (a) Default theme — "AI Lab · sharp" (`ThemeColors`, dark scheme, personality `technical`)

Replaces `blue-cyan-lab` as the shipped default.

| slot | hex | role |
|---|---|---|
| `bg` | `#110e1c` | deep warm indigo page |
| `surface` | `#191527` | card base |
| `surface2` | `#211c33` | raised/inset surfaces, inputs, bubbles |
| `border` | `#2f2947` | hairlines |
| `text` | `#e9e4f6` | body prose |
| `muted` | `#9d94ba` | secondary text, micro-labels |
| `accent` | `#ffb35c` | **warm amber — actions, mission, primary buttons** |
| `accent2` | `#7fd7ea` | **cool cyan — live data, links, focus rings** |
| `positive` | `#7ed6a2` | ok / gains |
| `warn` | `#ffd166` | caution |
| `danger` | `#ff7a7a` | errors / destructive |
| `info` | `#9aa8ff` | informational periwinkle |

Derived (pin these in `UITheme.derived`; formulas in `_derive()` stay authoritative for World themes):

| derived slot | hex |
|---|---|
| `text_strong` | `#fbfaff` |
| `border_strong` | `#463d68` |
| `surface3` | `#2a2440` |
| `positive_dim` | `#65ab82` |

**The amber/cyan role split is a rule, not a suggestion**: `--accent` (amber) may appear
only on primary actions, the mission card, and selection emphasis; `--accent2` (cyan) owns
live numbers, links, run IDs, focus rings, and sparklines. A surface where both fight for
attention is a bug.

## (b) World demo palettes (same 12 slots — valid `theme.dark` blocks for face.json)

**Pink-playful ("Kawaii Lab", personality `playful`):**

| slot | hex | | slot | hex |
|---|---|---|---|---|
| `bg` | `#1d1119` | | `accent` | `#ff8fc0` |
| `surface` | `#271722` | | `accent2` | `#ffc7e0` |
| `surface2` | `#311d2c` | | `positive` | `#8fdcb0` |
| `border` | `#43293a` | | `warn` | `#ffd166` |
| `text` | `#f7e9f1` | | `danger` | `#ff7a8a` |
| `muted` | `#bd98ac` | | `info` | `#b9a8ff` |

Derived: `text_strong #fff8fc` · `border_strong #63405a` · `surface3 #3c2436` · `positive_dim #72b08d`

**Scholarly ("Art History", personality `scholarly`):**

| slot | hex | | slot | hex |
|---|---|---|---|---|
| `bg` | `#141020` | | `accent` | `#a78bfa` |
| `surface` | `#1c1730` | | `accent2` | `#d8c8a6` |
| `surface2` | `#251e3e` | | `positive` | `#84d1a8` |
| `border` | `#332a52` | | `warn` | `#e6c36b` |
| `text` | `#ece7f7` | | `danger` | `#f2808f` |
| `muted` | `#a49bc4` | | `info` | `#8fb6f2` |

Derived: `text_strong #fdfcff` · `border_strong #4d4178` · `surface3 #2e264c` · `positive_dim #6aa786`

### Contrast verification (WCAG 2.x relative luminance — same math as `world_theme._rel_luminance`)

Gates enforced by `world_theme.py`: `text:bg ≥ 4.5`, `muted:bg ≥ 3.0`, `accent:bg ≥ 3.0`.

| ratio | default | playful | scholarly | gate |
|---|---:|---:|---:|---|
| `text : bg` | **15.31** | **15.60** | **15.42** | ≥ 4.5 ✓ |
| `muted : bg` | **6.69** | **7.20** | **7.17** | ≥ 3.0 ✓ |
| `accent : bg` | 10.74 | 8.67 | 6.86 | ≥ 3.0 ✓ |
| `accent2 : bg` | 11.61 | 12.65 | 11.32 | — |
| `text_strong : bg` | 18.32 | 17.52 | 18.27 | — |
| primary-button ink : `accent` | 11.37 | 9.41 | 7.36 | ≥ 4.5 ✓ |

Primary-button ink = `color-mix(in srgb, var(--bg) 45%, black)` (dark ink on amber, never white-on-amber).

## (c) Typography

- **Sans for everything a human reads**: `--font-sans` (Inter → system-ui stack). Body 15px/1.6.
  Headings sans, weight 650, tracking −0.015em. In the `_PERSONALITY` table this means
  **`--heading-font: var(--font-sans)` for the retuned `technical` personality** (mono headings
  remain only in `hacker`, which is preserved verbatim).
- **Mono only for measured things**: `--font-mono` (JetBrains Mono → ui-monospace stack) with
  `font-variant-numeric: tabular-nums` — metrics, timestamps, run IDs, table cells, paths,
  keys. Mono in a sentence of prose is a bug.
- **Micro-label style** (the one uppercase voice, stolen from concept-1): mono, 10–11px,
  weight 500, `letter-spacing .14em`, uppercase, color `--muted` (or `--accent2` for section
  eyebrows). Emitted via `--label-transform` / `--label-tracking`. Never applied to sentences.
- Weights: 400 body · 500 mono/data · 550–600 emphasis · 650 headings · 700 max (brand only).

## (d) Personality scalars (`_PERSONALITY` retune)

New scalar `--glow-mix` (concept-3's dial): the percentage fed to
`color-mix(in srgb, <color> var(--glow-mix), transparent)` for every glow wash. Derived glow
tokens read it; Worlds select it only via personality.

| scalar | `technical` (default) | `scholarly` | `playful` |
|---|---|---|---|
| `--radius-s / -m / -l` | 6 / 10 / 16px | 5 / 8 / 12px | 12 / 18 / 26px |
| `--radius-pill` | 999px | 999px | 999px |
| `--glow-mix` | 10% | **0% (dead flat)** | 26% |
| `--glow-alpha` (legacy pair) | 0.10 | 0 | 0.26 |
| `--motif-scanline-alpha` | 0.03 max | 0 | 0 |
| `--dur-1 / -2 / -3` | 100/170/280ms | 120/200/320ms | 140/230/380ms |
| `--ease-accent` | `cubic-bezier(0.2,0,0,1)` | `cubic-bezier(0.2,0,0,1)` | `cubic-bezier(0.34,1.56,0.64,1)` (spring) |
| hover lift | −2px translateY | −1px | −3px + scale 1.01 |
| `--heading-font` | sans | sans | sans |
| `--label-transform` / `--label-tracking` | uppercase / .14em | none / .01em | none / .02em |
| `--rail-from` / `--rail-to` | accent / accent2 | accent2 / accent | accent / accent2 |

Motion rules: animate **transform, opacity, box-shadow only**; 100–380ms; always
`var(--ease-accent)`; a `prefers-reduced-motion: reduce` block kills all of it.

**Derived layer (computed in `style.css` from primitives — Worlds must never set these):**

```css
--rail:     linear-gradient(90deg, var(--rail-from), var(--rail-to));
--glow-a:   color-mix(in srgb, var(--accent)  var(--glow-mix), transparent);
--glow-b:   color-mix(in srgb, var(--accent2) var(--glow-mix), transparent);
--shadow-1: 0 1px 0 color-mix(in srgb, var(--text-strong) 4%, transparent) inset,
            0 18px 50px -18px color-mix(in srgb, var(--bg) 30%, black);
```

## (e) Component notes

- **Nav + rail**: sans nav links 14px/500; active link gets `surface2` + `border` +2px underline
  of `var(--rail)`. The signature rail is a 1px `var(--rail)` gradient under the nav with a 14px
  `--glow-b` fade below (shadow-like, not a glow effect). Brand mark: `surface2` chip, `--radius-m`.
- **Status bar**: mono 11.5–12px `tabular-nums` in `--muted`, values in `--text`. Mode badge =
  positive-tinted pill, uppercase mono, `letter-spacing .1em`. Its live dot carries **the one
  permitted glow** (`0 0 8px currentColor` + 2.4s pulse). Human copy on the right
  ("SRE watching · all clear") — narrative, not telemetry.
- **Cards**: `surface` + 1px `border`, `--radius-l`, `box-shadow: var(--shadow-1)`. Metric cards
  use `--radius-m`; hover = translateY(-2px) + `border-strong`, duration `--dur-2`, ease
  `--ease-accent`. Metric numerals mono 30px in `--text-strong`; label above in micro-label style;
  sparkline stroke `--accent2` with a `--glow-mix`-strength area fill. No gradient-clipped numerals.
- **Buttons**: `--radius-s`, sans 14px/600. Primary = solid `--accent`, dark ink (see (a)),
  soft accent shadow, hover lifts −1px. Ghost = transparent + `border-strong`, hover `surface2`.
  Danger = 13% `--danger` wash + 38% border, text `--danger`. Never gradient-filled, never glowing.
- **Inputs**: `surface2` bg, `border` hairline, `--radius-s`, text in `--text-strong`, placeholder
  `--muted`. Focus: border `--accent2` + `0 0 0 3px` 18%-mix `--accent2` ring (this ring is a focus
  affordance, not a glow — exempt from the glow budget). `.mono` variant for paths/keys. Every
  input gets a plain-English hint line that teaches (progressive-disclosure pedagogy).
- **Tables**: mono 12.5px `tabular-nums`, no vertical rules. Thead = micro-label style over a
  `border-strong` rule; body rows `border` hairlines; hover wash `surface2` at 60%. Run IDs in
  `--accent2`; deltas in `positive`/`warn`. Numeric columns right-aligned. Wrap in
  `overflow-x: auto`.
- **Pills**: `--radius-pill`, mono 11px, pattern = state color text + 12%-mix bg + 28%-mix border
  + 6px `currentColor` dot. States map to `positive/warn/danger/info/accent2(running)` only.
- **Modals**: `surface2` panel, `border-strong`, `--radius-l`, deep drop shadow; backdrop =
  62%-mix `--bg` + `blur(3px)` (the only permitted backdrop-filter). Title sans 650; body
  13.5px `--muted`; inline `code` in mono `--accent2` on 10% wash. Footer actions right-aligned,
  ghost-then-primary.
- **Chat bubbles**: max-width 78%. Assistant = `surface2` + `border`, top-left corner clipped to
  4px; user = 13%-mix `--accent2` over `surface2`, top-right clipped. Meta line above in
  micro-label style ("buddy · my machine · llama-ai-eng"). Avatars 32px round; assistant avatar
  is the **one permitted gradient fill** besides the rail (`135deg, --accent → --accent2`); user
  avatar `surface3` + `border-strong`. Compute-source chip: mono pill in `--accent2` tint with
  live dot.
- **World-switcher swatches**: 26–28px rounded squares, `linear-gradient(135deg, var(--sw1), var(--sw2))`
  where `--sw1/--sw2` are set per item from *that world's* `accent/accent2`. This is the **only**
  place hardcoded foreign-world hexes are allowed (they depict other worlds). Dropdown =
  `surface2` + `border-strong` + `--radius-l`; head/footer teach the contract ("Themes are token
  swaps — nothing else changes."). Active item gets an `--accent` check.

## (f) Do NOT

Phrased against the v2 token names; each of these is a review-blocking violation.

1. **No glow soup.** Budget: exactly **one** glow per view (the live status dot). Everything
   else that wants "glow" must go through `--glow-a/--glow-b` (i.e. `--glow-mix`), which
   scholarly sets to 0% — if a surface breaks when `--glow-mix: 0%`, it's wrong.
2. **No scanlines above `--motif-scanline-alpha: 0.03`**, and the token must be `0` outside
   `technical`/`hacker`. Never hardcode a scanline alpha.
3. **No hardcoded hex in page/component CSS.** Colors come from the 12 slots, the derived
   neutrals (`--surface3`, `--border-strong`, `--text-strong`, `--positive-dim`), or
   `color-mix()` of them. Sole exception: world-switcher swatch `--sw1/--sw2` values.
4. **Worlds never set derived tokens.** face.json themes carry only the 12 slots + personality
   id; `--rail`, `--glow-*`, `--shadow-1`, radii, easings are computed/selected, never supplied.
   (This keeps `world_theme.py`'s fail-closed gate airtight.)
5. **No gradient-clipped text** (`background-clip: text` numerals) and **no gradient button
   fills** — the 2025-AI-landing-page tropes the panel explicitly rejected. Gradients live in
   exactly three places: the rail, the assistant avatar, world swatches.
6. **No glass.** `backdrop-filter` only on modal backdrops (≤ 4px blur). Cards are opaque
   `--surface`.
7. **Don't spend `--accent` on data or `--accent2` on actions** — the duotone role split is
   the hierarchy system.
8. **No uppercase mono on prose.** Micro-label style is for labels ≤ 3 words; error messages,
   hints, and empty states speak human sentences in sans.
9. **Don't animate layout** (width/height/top/left) or exceed `--dur-3`; don't ship any motion
   that ignores `prefers-reduced-motion`.
10. **Don't drop below the gates**: any new palette must pass `text:bg ≥ 4.5`, `muted:bg ≥ 3.0`,
    `accent:bg ≥ 3.0` through `world_theme.py`'s validator — no eyeballing.
11. **Don't remove a loading affordance without replacing it** (standing rule: a silent busy
    surface reads as broken).
