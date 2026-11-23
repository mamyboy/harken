---
name: Vibrant Intelligence
description: Premium social-listening console — lit ice field, violet action, honest data states
colors:
  ink-navy: "#0F1B33"
  ink-slate: "#33415C"
  muted-slate: "#5F6B85"
  muted-faint: "#5C6884"
  hairline: "#E4EBF7"
  hairline-strong: "#D6E2F3"
  glass-card: "rgba(255,255,255,.86)"
  electric-violet: "#6D28D9"
  violet-deep: "#5B21B6"
  violet-wash: "#F2EBFF"
  console-blue: "#1D6FF2"
  blue-ink: "#0B3B86"
  sky-cyan: "#00B8E6"
  cyan-wash: "#E6F8FE"
  cyan-ink: "#046B85"
  cyan-line: "#BFEAF8"
  chip-bg: "#EFF6FF"
  chip-line: "#CFE1FF"
  track: "#EEF3FC"
  hover-wash: "#FAF7FF"
  coral: "#FF6B6B"
  coral-ink: "#C43434"
  positive: "#12692F"
  positive-wash: "#E9F8EF"
  caution: "#8A5A00"
  caution-wash: "#FFF4E2"
  negative: "#C22A2E"
  negative-wash: "#FFECEC"
typography:
  hero:
    fontFamily: "IBM Plex Sans Thai, Noto Sans Thai, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "26px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  data:
    fontFamily: "{typography.hero.fontFamily}"
    fontSize: "26px"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.02em"
    fontFeature: "tabular-nums"
  section:
    fontFamily: "{typography.hero.fontFamily}"
    fontSize: "16.5px"
    fontWeight: 700
    lineHeight: 1.35
    letterSpacing: "-0.01em"
  title:
    fontFamily: "{typography.hero.fontFamily}"
    fontSize: "14.5px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-0.01em"
  body:
    fontFamily: "{typography.hero.fontFamily}"
    fontSize: "14.5px"
    fontWeight: 400
    lineHeight: 1.6
  prose:
    fontFamily: "{typography.hero.fontFamily}"
    fontSize: "13.5px"
    fontWeight: 400
    lineHeight: 1.62
  label:
    fontFamily: "{typography.hero.fontFamily}"
    fontSize: "12.5px"
    fontWeight: 600
    lineHeight: 1.5
  micro:
    fontFamily: "{typography.hero.fontFamily}"
    fontSize: "11.5px"
    fontWeight: 600
    lineHeight: 1.45
rounded:
  sm: "11px"
  md: "12px"
  lg: "14px"
  xl: "18px"
  hero: "22px"
  pill: "999px"
spacing:
  xxs: "7px"
  xs: "9px"
  sm: "11px"
  md: "14px"
  lg: "16px"
  xl: "18px"
  section: "26px"
components:
  button:
    backgroundColor: "#FFFFFF"
    textColor: "{colors.ink-navy}"
    rounded: "{rounded.sm}"
    padding: "9px 13px"
    typography: "{typography.label}"
  button-hover:
    backgroundColor: "#FAF7FF"
    textColor: "{colors.ink-navy}"
  button-pressed:
    backgroundColor: "{colors.electric-violet}"
    textColor: "#FFFFFF"
    rounded: "{rounded.sm}"
    padding: "9px 13px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.muted-slate}"
    rounded: "{rounded.sm}"
    padding: "9px 13px"
  navlink:
    backgroundColor: "rgba(255,255,255,.7)"
    textColor: "{colors.ink-slate}"
    rounded: "{rounded.sm}"
    padding: "8px 13px"
    typography: "{typography.label}"
  navlink-active:
    backgroundColor: "{colors.electric-violet}"
    textColor: "#FFFFFF"
    rounded: "{rounded.sm}"
    padding: "8px 13px"
  chip:
    backgroundColor: "#EFF6FF"
    textColor: "{colors.blue-ink}"
    rounded: "{rounded.pill}"
    padding: "4px 11px"
    typography: "{typography.label}"
  chip-tag:
    backgroundColor: "{colors.violet-wash}"
    textColor: "{colors.violet-deep}"
    rounded: "{rounded.pill}"
    padding: "5px 11px"
  card-glass:
    backgroundColor: "{colors.glass-card}"
    textColor: "{colors.ink-navy}"
    rounded: "{rounded.xl}"
    padding: "15px 18px"
  card-kpi:
    backgroundColor: "{colors.glass-card}"
    textColor: "{colors.ink-navy}"
    rounded: "{rounded.xl}"
    padding: "14px 15px 13px"
  field-search:
    backgroundColor: "#FFFFFF"
    textColor: "{colors.ink-navy}"
    rounded: "{rounded.md}"
    padding: "9px 12px"
  field-picker:
    backgroundColor: "#FFFFFF"
    textColor: "{colors.ink-navy}"
    rounded: "{rounded.md}"
    padding: "9px 10px"
---

# Design System: Vibrant Intelligence

## Overview

**Creative North Star: "The Signal Room"**

A lit, ice-blue operating theatre rather than a dark terminal: the page ground is three stacked light gradients (a cool bloom top-left, a cooler one top-right, fading to near-white at the fold), and the analysis surfaces float on it as translucent glass panels. Depth is optical, not decorative — a frosted card over a gradient ground reads as an instrument pane, and the ground keeps moving faintly underneath it as you scroll.

Violet is the language of *action and the present*, cyan the language of *comparison and the past*, coral is a pure alarm hue that appears on almost nothing — its rarity is the mechanism. A single console blue lives one step outside that system: it terminates the zone-hero gradient and lights the brand mark, so the product's identity reads as light rather than as another data role. Numbers are the display voice: 26px, tracked −0.02em, tabular so digits never jitter between renders.

**Key Characteristics:**
- Glass over a lit ground: every analysis surface is `rgba(255,255,255,.86)` + `blur(10px)`; the gradient ground is what makes it read as glass and not as grey
- One hue per time period (violet = current, cyan = previous) held across every view
- A 3px violet→cyan crown on every KPI card — the only "gradient ornament" allowed at that scale
- Coral ≤ ~5% of a screen: peak markers, offline chips, warnings; never small text on white
- Honest states: no data ≠ 0; unconnected sources read "–" plus a chip

## Colors

A cool eight-step neutral ramp carries the structure; two saturated roles do the work and a third stays scarce.

### Primary
- **Electric Violet** (#6D28D9): pressed buttons, active nav pill, current-period series, selected rows and tags, focus rings. Hover/active deepens to **Violet Deep** (#5B21B6) — never an approximation like #5B21B6 replaced by #7C3AED.
- **Ink Navy** (#0F1B33): body text, KPI numerals, tooltip ground, drawer headings — the weight anchor.

### Secondary
- **Sky Cyan** (#00B8E6): previous-period series, comparison fills, platform pills (as wash #E6F8FE with text #046B85), the right-hand terminus of every violet→cyan gradient.
- **Console Blue** (#1D6FF2): brand mark gradient and the far end of the zone-hero ramp only. It is identity light, never an action or a series colour; **Blue Ink** (#0B3B86) is its readable text pair on blue wash.

### Tertiary
- **Coral** (#FF6B6B) with **Coral Ink** (#C43434) for text: spike rings, "ยังไม่ได้เชื่อมต่อ" chips, offline banners on #FFF4F4. **The Coral Rarity Rule.** If coral covers more than a sliver of a screen, a spike is being described in the wrong colour.

### Neutral
- **Ink Slate** (#33415C) for secondary prose, **Muted Slate** (#5F6B85) for meta, **Muted Faint** (#5C6884) for tertiary hints and column labels. Both grey steps were darkened from #6B7A99/#8C99B4 because the lit ground dropped them to 3.6:1 and 2.4:1; they now measure 4.52:1 and 4.71:1 on the darkest part of the gradient.
- Hairlines are **#E4EBF7** for panel borders and **#D6E2F3** for field borders and idle controls; both are cool-shifted so they stay invisible against the glass.
- Delta roles: **Positive** #12692F on #E9F8EF (6.2:1), **Caution** #8A5A00 on #FFF4E2 (5.44:1), **Negative** #C22A2E on #FFECEC (5.04:1). Text uses these darker siblings; the bright originals (#16A34A / #D98A18 / #E5484D) survive only as bar fills. These three are status only, never data series.

## Typography

**Display Font:** IBM Plex Sans Thai (fallback Noto Sans Thai, system stack)
**Body Font:** same family — one face, weight- and size-differentiated
**Label Font:** same, 11.5–12.5px semibold

**Character:** a single Thai-capable sans keeps tone marks and vowels intact at every size, which is why the system never switches family for emphasis. Hierarchy comes from four moves only: size (26 → 16.5 → 14.5 → 12.5 → 11.5), weight (700 → 600 → 400), tracking (−0.02em on numerals and headings, 0 on prose), and colour (navy → slate → muted).

### Hierarchy
- **Hero** (700, 26px, −0.02em, 1.2): zone hero title on the violet gradient, and 22px at ≤640px.
- **Data** (700, 26px, −0.02em, 1.15, tabular-nums): KPI numerals — the real display voice; 22px at ≤640px.
- **Section** (700, 16.5px): the heading that marks a new analysis zone.
- **Title** (600, 14.5px): card heads.
- **Body** (400, 14.5px/1.6): posts and descriptions.
- **Prose** (400, 13.5px/1.62): snippets, list bodies.
- **Label** (600, 12.5px): table heads, chips, pagination.
- **Micro** (600, 11.5px): KPI keys, chart titles, platform pills.
- **Axis** (600, 12px, tabular-nums, ink-slate): chart ticks and date labels. Charts render at the container width so one SVG unit equals one CSS pixel; a fixed 900-unit viewBox scales 12px text down to ~5px on a phone.

**The Measured-Contrast Rule.** A colour pair is not finished when it looks right on the design file: measure it against the darkest part of the lit ground, not against white. Text ≥4.5:1, large text ≥3:1, and any non-text graphic that carries meaning (axis, icon stroke) ≥3:1.

**The Thai Integrity Rule.** No line-height below 1.5 at ≤13px; verify ่ ้ ี ึ ั and ๆ are never clipped at card edges or line tops. Tabular numerals are mandatory on every metric, axis label, and table cell that holds a number.

## Layout

Glass panels on a fixed gradient ground, inside a 1460px shell with 18px gutters (12px at ≤640px). KPI row is a 5-up grid at ≥1180px, 3-up to 900px, then 2-up — never one column, because paired metrics lose meaning alone. The main analysis grid is 1.7fr + 0.9fr and collapses to a single column at ≤1180px; secondary grids are 2-up and 3-up, both collapsing at ≤900px. Section headings are separated by 26px above and 11px below, so a new zone reads as a seam rather than a paragraph. Below 720px tables restack into cards (`td[data-l]` supplies the label) instead of scrolling sideways, and every tap target clears 40px.

## Elevation & Depth

Hybrid: optical depth from glass, structural depth from two navy-tinted shadows. Every panel sits at `--shadow` (`0 1px 2px rgba(15,27,51,.04), 0 10px 28px rgba(15,27,51,.07)`) and lifts on hover to `--shadow-lg` (`0 2px 6px .06, 0 22px 48px .10`) with a 1–2px rise. Shadow colour is always neutral navy `rgba(15,27,51,…)`; the only coloured lifts in the system are the zone hero (`0 16px 40px rgba(76,29,149,.30)`) and the brand mark (`0 10px 22px rgba(29,111,242,.32)`), where the glow is the identity.

**The Glass-Is-Identity Rule.** Blur is not ornament here: `rgba(255,255,255,.86)` + `backdrop-filter: blur(10px)` on cards, KPI tiles, and filter bars is what makes the lit ground legible as a surface behind the data. Keep the alpha high enough that body text stays at AA on the busiest part of the gradient.

**The Flat-Analysis Rule.** Charts, tables, and list interiors have no shadow and no blur of their own — they live inside a lifted panel. Only panels and interactive rows lift.

## Shapes

Gently curved, one ladder: **18px** is the panel radius and the default for anything that holds content; 14px for inner cells (chart cells, mobile table cards), 12px for fields and banners, 11px for buttons, nav pills, and rows, 22px for the zone hero, 999px for every pill, chip, tag, and bar track. Progress and ranking bars are capsules 6–9px tall; disabled tracks are a flat `#EEF3FC` capsule with no fill rather than a misleading sliver. No clip-paths, no hard offsets, no square corners.

## Components

### Buttons
- **Shape:** 11px corners, white ground, `1px solid #D6E2F3`.
- **Primary path to emphasis:** hover turns the border violet and the ground to #FAF7FF; a pressed/toggled control is the only state that fills solid violet with white text (`[aria-pressed="true"]`). There is no permanently-filled violet button; the accent is earned by state.
- **Quiet:** transparent, muted text, white ground on hover.
- **Focus:** 2px violet ring at 2px offset, 8px radius, on every focusable element.

### Chips & tags
- **Filter chips:** `--chip-bg` #EFF6FF ground, `--chip-line` #CFE1FF border, Blue Ink text, 12.5px semibold, with an × kill target.
- **Keyword tags:** violet wash #F2EBFF, #DDCDFF border, Violet Deep text; pressed state fills violet/white.
- **Platform pills:** cyan wash with #BFEAF8 border and #046B85 text, 11px.

### Cards / Containers
- `rgba(255,255,255,.86)` + blur(10px), 18px radius, #E4EBF7 hairline, `--shadow`.
- Head: 15px 18px 0, title 14.5px/600, hint right-aligned at 12px Muted Faint. Body: 14px 18px 18px.
- KPI tiles add the 3px violet→cyan crown (`::before`, opacity .85) and lift 2px on hover; selected rows use violet wash + inset 3px violet bar, never a glow.

### Inputs / fields
- White field, #D6E2F3 border, 12px radius, 9px vertical padding; the select carries an inline 11.5px muted label.
- **Focus:** border goes violet plus `0 0 0 3px rgba(109,40,217,.12)` — a ring, not a glow.

### Navigation
- A top strip, not a rail: 42px gradient brand mark (14px radius, blue→cyan) + 17px/700 wordmark, nav links as 11px-radius pills on 70% white. Active = solid violet. ≤640px: 15px wordmark, 12px links, all ≥40px tall.

### [Signature] Zone hero
- 22px radius, `linear-gradient(140deg,#241355 0%,#4C1D95 46%,#6D28D9 78%,#1D6FF2 130%)`, 46px top padding so a floating back-link never collides with the title, a radial white bloom anchored bottom-centre, kicker at 11px uppercase 0.1em, title 26px, platform chips at white@16%, and a 3-cell stat group on the right (10.5px keys, 22px tabular values).
- It is the one place in the product where a saturated field is allowed to fill a whole block.

## Do's and Don'ts

### Do:
- **Do** keep series hues locked: violet = current period, cyan = comparison, everywhere.
- **Do** keep the glass at high alpha (.86) and the blur at 10px; pair it with the lit gradient ground or the panels turn grey.
- **Do** put numbers in tabular figures at −0.02em tracking; this product is read as a table of magnitudes.
- **Do** pair every meaning with a second channel (dash pattern, label, icon) — colour never alone.
- **Do** animate state only: 180ms hover lift, 130ms row tints, 120ms tooltip fade, 480ms skeletons; all off under `prefers-reduced-motion`.
- **Do** restack tables into cards below 720px and keep every target ≥40px.
- **Do** honour `prefers-reduced-motion`: skeletons go static (#EEF3FB), hover lifts drop the translate, no status dot loops. State must still be visible without motion.
- **Do** draw charts at the measured container width, never a fixed wide viewBox — that keeps axis text at a real 12px on a phone.
- **Do** strip colour out of a nested container: a filter bar inside a card is transparent and borderless (.filters-inline), never a second panel.

### Don't:
- **Don't** use coral for body or small text on white; the smallest coral text role is a chip on coral wash.
- **Don't** put a hue glow on analysis panels or rows — coloured lifts belong to the zone hero and brand mark only.
- **Don't** display 0 where data was never fetched.
- **Don't** fill a whole analysis card with a violet→cyan gradient; at that scale the gradient is limited to the 3px KPI crown, progress fills, and ranking bars.
- **Don't** treat Console Blue as an action colour — buttons, links, and active states are violet.
- **Don't** stack a shadow and a blur on the same element beyond the panel pattern; interior cells stay flat.
