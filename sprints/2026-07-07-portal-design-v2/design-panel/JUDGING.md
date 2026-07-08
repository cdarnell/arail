# Design panel — judging record

Sprint: `2026-07-07-portal-design-v2` · Brief: "modern lab, technical edge"
Three judges, four concepts, four criteria (inviting / impressive / intuitive / systemized, 10 pts each).

## Scores

| Concept | J1 (front-door / family test) | J2 (technical-edge test) | J3 (design-system test) | **Aggregate** |
|---|---:|---:|---:|---:|
| concept-1-precision-instrument | 27 | 31 | 30 | 88 |
| **concept-2-warm-observatory** | **35** ★ | **33.5** | 32 | **100.5** |
| concept-3-editorial-lab | 31 | 31.5 | 31 | 93.5 |
| concept-4-aurora-console | 32 | 31.5 | **34** ★ | 97.5 |

★ = judge's nominated best. J2 nominated concept-1 on the technical-edge lens, but concept-2 still took J2's highest raw total.

## Decision

**Winner: `concept-2-warm-observatory.html`** — refined as `winner-refined.html`, spec in `STYLE-SPEC.md`.

## Rationale (short)

1. **Highest aggregate and the only concept every judge scored ≥ 32.** It won the criterion that gates ARAIL's actual audience (friends/family opening someone else's lab): inviting 9/9/9 across all three judges — no other concept broke 8 with more than one judge.
2. **Its weakness is repairable; the others' aren't.** Observatory's gap is "impressive/technical edge," which is exactly what the judges' flagged steals supply. Concept-1's austerity (inviting 4–6) and concept-4's "seen this on every AI landing page" pattern-match are identity problems, not tuning problems.
3. **Its theming story demoed best** — the only mockup with a live, working world switcher — and its palette move (warm amber instrument-light + cool cyan starlight duotone) is the least generic in the set.

## Synthesis (bound into STYLE-SPEC.md)

| From | Stolen idea |
|---|---|
| concept-1 | Accent discipline: cyan spent almost only on live data; **exactly one glow per view**; mono micro-label style; contrast-ratio annotations kept in the token block |
| concept-3 | The **glow personality dial** (glow strength is a theme scalar — scholarly goes flat, playful glows); mission-as-editorial-headline hero |
| concept-4 | The **derived-token layer** (rail gradient, glow washes, shadows, motion curve computed from base tokens — never set by Worlds); springy hover-lift motion; clear-then-set world-swap JS |
| concept-2 (kept) | Warm indigo base, amber/cyan role-split duotone (amber = actions/mission, cyan = data/links), sans prose with mono quarantined to data, human status copy ("SRE watching · all clear"), live world switcher |

## Fixes applied in `winner-refined.html`

- Hardcoded swatch gradients (`.swatch.lab/.kawaii/.arthist`) replaced by per-item `--sw1/--sw2` primitives (J3's leak).
- World swap JS now clears previous overrides before setting (concept-4's correct mechanism).
- Worlds now also carry the personality scalars (radius trio + glow dial + motion ease) so playful/scholarly repaint shape and glow, not just hue.
- Exactly one glow added (live status dot); everything else stays shadow-based.
- `prefers-reduced-motion` honored.
