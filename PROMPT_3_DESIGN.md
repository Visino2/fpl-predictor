# FPL Predictor — DESIGN PROMPT
(Paste this as a third, separate instruction — purely visual/UI, no logic.
Matched to the official FPL app's real design language and confirmed
official brand colors, so your tool feels like a natural companion to
the app you already use, not a generic dashboard.)

## Brand colors (official Premier League / FPL palette)

```
--fpl-purple-dark:   #38003C   /* primary background, headers */
--fpl-purple-light:  #963CFF   /* accents, secondary elements */
--fpl-green:         #00FF85   /* primary CTA, positive stats, "live" indicators */
--fpl-cyan:          #04F5FF   /* the "Fantasy" pitch gradient banner, links */
--fpl-pink:          #E90052   /* alerts, captain armband, warnings */
--fpl-white:         #FFFFFF   /* text on dark backgrounds */
--fpl-black:         #0D0D0D   /* body text on light backgrounds */

/* Pitch specifically (from the actual app) */
--pitch-green-dark:  #00A650
--pitch-green-light: #00C65E   /* the diagonal-stripe mown-grass effect */
--pitch-lines:        #FFFFFF  /* semi-transparent white, ~70% opacity */
```

## Typography

- FPL's own app uses a bold, rounded sans-serif for headers (looks like a
  custom/licensed font — don't chase pixel-matching it). Use **Inter** or
  **Poppins** at bold weights (700-800) for headers as a close, freely
  licensed substitute.
- Body text: Inter, regular/medium weight, high contrast against the dark
  purple background.
- Numbers (points, prices) are always bold and slightly larger than their
  labels — points totals are the visual hero of every card.

## Layout patterns (matched to your screenshots)

**Header pattern:**
- Dark purple (`--fpl-purple-dark`) full-width top bar
- Back arrow (left) in a light circular pill button
- Page title centered, bold
- Circular icon button (top right) for a menu/settings/avatar

**Stat summary row (below header):**
- Three-column layout: a plain stat (label under number), a highlighted
  "hero" stat in a rounded gradient card (cyan-to-blue or green-to-cyan
  diagonal gradient), a third plain stat with a ">" affordance if tappable
- This is the pattern you see with "Average / Total Pts / Highest" — reuse
  it for "Avg Predicted / Your Predicted Total / Rank Potential" or similar

**Tab switcher:**
- Two-option pill/segmented control ("Pitch" / "List"), rounded-full
  container, light grey/lavender background, active tab in white with a
  subtle shadow — not filled with a bold color, kept understated

**Pitch view:**
- Diagonal-striped green pitch background (alternating light/dark green
  bands, ~45° angle, subtle — this reads as "grass mown in stripes")
- White pitch markings (box outlines, center circle) at reduced opacity
- Gradient banner across the very top of the pitch reading "Fantasy" on
  both sides — cyan-to-purple-to-blue diagonal gradient, this is the most
  distinctive FPL visual signature, worth replicating exactly
- Players positioned in formation rows (GK alone at top, then DEF row,
  MID row, FWD row) — jersey icon above a name/points pill

**Player card (on pitch):**
- Jersey/shirt icon (team kit) — flat illustration style, not photo
- Small circular badge overlay for captain (C) / vice-captain (V) / star
  (for "next match star" or similar) in the top-left corner of the shirt
- Name in a white rounded-rect pill directly under the shirt
- Points value in a dark purple rounded-rect pill directly under the name
  — points pill is visually the "final word" on that card, always bottom

**Bench row (bottom):**
- Same jersey-card pattern but smaller, laid out horizontally in a single
  row, muted/desaturated background panel (lighter sage-green, not the
  vivid pitch green) to visually signal "not currently playing"
- Position labels (GKP/DEF/MID/FWD) as small caps headers above each slot

## Adapting this for YOUR app's unique screens

**Chip recommendation cards** (new — doesn't exist in official app):
- Reuse the "hero stat" gradient card pattern from the stat summary row
- One card per chip (Bench Boost, Triple Captain, Wildcard, Free Hit)
- Icon + chip name + one-line verdict ("Worth playing this week" /
  "Save it — better fixtures coming") + the number behind the
  recommendation (e.g. "+15.2 predicted bench points")
- Recommended chip: green left-border accent + `--fpl-green` verdict text
- Not-recommended: neutral grey border, muted grey verdict text
- Never use `--fpl-pink` for "don't play this" — reserve pink for actual
  warnings (injury flags, price drops), keep chip advice in the
  green/neutral pair only

**Predicted points vs actual points:**
- When showing predictions, use `--fpl-cyan` for the number (visually
  distinct from real recorded points, which stay in the standard dark
  purple pill) — this matters so you never confuse "predicted" with
  "confirmed" at a glance

**Fitness flag badge** (injury/doubt warnings from predict.py):
- Small `--fpl-pink` triangle-exclamation badge, top-right corner of the
  player card, same visual weight as the captain armband badge but
  opposite corner

## Component-level notes for React + Tailwind

- Define all of the above as CSS custom properties in
  `frontend/src/styles/theme.ts`, then reference via Tailwind's
  `theme.extend.colors` — don't hardcode hex values inside components
- Use `rounded-full` for pills/badges, `rounded-2xl` for cards — the
  official app never uses sharp corners anywhere
- Shadows are soft and minimal (`shadow-sm` / `shadow-md` at most) — the
  app relies on color contrast and rounded shapes for hierarchy, not
  heavy drop shadows
- Mobile-first: your screenshots are phone-width (390px-ish) — build the
  pitch view to work at that width first, then scale up for desktop as a
  secondary concern
