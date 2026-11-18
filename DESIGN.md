---
name: Vibrant Intelligence
description: Premium social-listening console — navy anchor, violet action, honest data states
colors:
  midnight-navy: "#111B38"
  navy-raise: "#1B2850"
  ice-white: "#F5F8FF"
  card-white: "#FFFFFF"
  electric-violet: "#6D28D9"
  violet-ink: "#4C1D95"
  violet-wash: "#F1EAFF"
  sky-cyan: "#00B8E6"
  cyan-wash: "#E4F7FE"
  coral: "#FF6B6B"
  coral-deep: "#D6403F"
  coral-wash: "#FFEDED"
  ink: "#131A2C"
  ink-2: "#3D4763"
  muted: "#5A6480"
  hairline: "#E3E9F7"
  hairline-2: "#CDD7EE"
typography:
  display:
    fontFamily: "IBM Plex Sans Thai, Noto Sans Thai, system-ui, sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  title:
    fontFamily: "{typography.display.fontFamily}"
    fontSize: "15px"
    fontWeight: 700
    lineHeight: 1.4
  body:
    fontFamily: "{typography.display.fontFamily}"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.7
  data:
    fontFamily: "{typography.display.fontFamily}"
    fontSize: "29px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.03em"
    fontFeature: "tabular-nums"
  label:
    fontFamily: "{typography.display.fontFamily}"
    fontSize: "12.5px"
    fontWeight: 600
    lineHeight: 1.5
rounded:
  sm: "9px"
  md: "11px"
  lg: "14px"
  pill: "999px"
spacing:
  xs: "7px"
  sm: "9px"
  md: "14px"
  lg: "16px"
  xl: "18px"
  page: "26px"
components:
  button-primary:
    backgroundColor: "{colors.electric-violet}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "42px"
  button-primary-hover:
    backgroundColor: "{colors.violet-ink}"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    rounded: "{rounded.md}"
  card-metric:
    backgroundColor: "{colors.card-white}"
    rounded: "{rounded.lg}"
    padding: "16px 18px"
  card-hot:
    backgroundColor: "{colors.electric-violet}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.lg}"
  chip-filter:
    backgroundColor: "{colors.violet-wash}"
    textColor: "{colors.violet-ink}"
    rounded: "{colors.pill}"
  nav-active:
    backgroundColor: "{colors.electric-violet}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.md}"
---

# Design System: Vibrant Intelligence

## Overview

**Creative North Star: "The Signal Room"**

A calm, ice-white operations room whose left wall is midnight navy: the heavy anchor rail makes the bright analysis field feel like an instrument panel, not a marketing page. Purple is the language of *action and present*; cyan is the language of *comparison and past*; coral is reserved exclusively for spikes and warnings and appears on almost nothing — its rarity is the mechanism. Data numbers are the display voice (tabular, tightly tracked, navy); prose stays small and quiet.

**Key Characteristics:**
- Navy rail + violet active pill as the brand signature; content never leaves the ice field
- One hue per time period (violet = current, cyan = previous) held across every view
- Coral ≤ ~5% of any screen: peak markers, offline chips, warnings only — never small text on white
- Exactly one violet→cyan gradient card (fastest-growing keyword); analysis surfaces stay flat, hairline-bordered, softly lifted
- Honest states: no data ≠ 0; unconnected sources read "–" plus a chip

## Colors

Six named data roles on a cool neutral ramp; the violet owns actions, cyan only ever compares.

### Primary
- **Electric Violet** (#6D28D9): primary button, active nav pill, current-period line, selected borders, keyword tags. Hover deepens to **Violet Ink** (#4C1D95) — text/line use of violet-ink, never hover-only #5B21B6 approximations.
- **Midnight Navy** (#111B38): rail, page H1, KPI numerals, drawer headings — the weight anchor.

### Secondary
- **Sky Cyan** (#00B8E6): previous-period dashed line, comparison bars, connected-source emphasis, link-hover-free accents. Wash #E4F7FE for chips on cyan.

### Tertiary
- **Coral** (#FF6B6B) with deep #D6403F on white-ground text and wash #FFEDED: spike rings/flags, "ยังไม่ได้เชื่อมต่อ" chips, offline banners. **The Coral Rarity Rule.** If coral covers more than a sliver of a screen, a spike is being described in the wrong color.

### Neutral
- **Ice White** (#F5F8FF) page ground; **Card White** surface; ink ramp #131A2C → #3D4763 → #5A6480; hairlines #E3E9F7 / #CDD7EE.
- Positive deltas use #0B6E43 on #E3F7EC (green is a delta role only, never a data series).

## Typography

**Display Font:** IBM Plex Sans Thai (fallback Noto Sans Thai, system)
**Body Font:** same family — one face, weight-differentiated
**Label Font:** same, 12–12.5px

**Character:** a single Thai-capable sans keeps tone marks and vowels intact at every size; hierarchy comes from weight and tracking, not font switching. 24 → 15 → 14 gives a clear step ladder.

### Hierarchy
- **Display** (700, 24px, -0.025em): page title only.
- **Data** (700, 29px KPI / 18–24px drawer, -0.03em, tabular-nums): metric numerals — the real display voice of this product.
- **Title** (700, 15px): panel headings; 19px drawer h3.
- **Body** (400/500, 14–15px): posts, descriptions, labels of controls.
- **Label** (600, 12.5px, muted): meta, legends, table heads, chips.

**The Thai Integrity Rule.** No line-height below 1.5 at ≤13px; check that ่ ้ ี ึ ั and ๆ are never clipped at card edges or line tops.

## Layout

12-column spirit at ≥1200px: 232px fixed navy rail + fluid ice field, page padding 26px, content cap 1360px. KPI row = 4 cards → 2×2 ≤1080 → single column ≤560. Main analysis grid = chart 2fr + issues 1fr, collapsing single-column ≤1200px. Spacing rhythm 7/9/14/16/18; more space above a heading than below it. ≤860px the rail becomes a horizontal scroll tab strip; the drawer goes full-bleed and stops reflowing padding.

## Elevation & Depth

Hybrid: flat by default, tonal for meaning, shadow only for lift. Cards carry `0 1px 2px rgba(60,64,75,.04)` at rest; hover adds `0 2px 6px + 0 12px 28px rgba(60,64,75,.10)` with a 1px rise; the drawer is the single strong lift `-18px 0 48px rgba(60,64,75,.14)`. Shadow color is always neutral-slate rgba(60,64,75,…), never a brand hue glow.

**The Flat-Analysis Rule.** Charts and panels stay flat + hairline; only interactive affordances (cards, drawer) are lifted.

## Shapes

Gently curved: 9/11/14px ladder, pills (999px) for chips/tags/bars, 11–14px icon tiles. No hard offsets, no clip-paths. Bar tracks are pill capsules with 8–10px height; disabled tracks are transparent with a chip inside, not a filled misleading capsule.

## Components

### Buttons
- **Shape:** soft 11px corners. **Primary:** violet fill, white 14px semibold, 42px tall. Hover deepens to violet-ink. Quiet variant: transparent, muted text, violet-wash on hover.

### Chips & tags
- Filter chips: violet-wash ground, violet-ink text, hairline violet border, × kill-button; keyword tags cyan (violet variant) pills at 11px; offline chip coral-wash on white ground.

### Cards / Containers
- 14px corners, white, #E3E9F7 hairline, ambient shadow. Selected state: violet border + violet-wash ground (never a glow ring). The one gradient card uses 135deg violet→cyan with translucent white text roles.

### Navigation
- Navy rail, 14.5px items; hover navy-raise; active = solid violet pill; count badges white@16%.

### Trending list
- rank numeral (tabular, muted) | name + meta stacked | change pill right. Rows are buttons; selected = violet-wash + inset hairline.

### Inputs / Selects
- white field, #CDD7EE border, 10px radius; focus = violet border + 3px violet@14% ring; selects carry an inline muted label.

### [Signature] Chart-as-Portal
- SVG line chart: violet current line (3px), cyan dashed previous (2.2px 5/5), 5% violet-fade area wash, 4-step gridlines with tabular axis numerals. Points are 26px hit targets; the peak is a coral ring + wash + flag "ยอดพุ่ง N". Clicking any point reflows the page — main column gains right padding and the detail drawer slides in without ever covering the chart; Escape/× closes and focus returns.

## Do's and Don'ts

### Do:
- **Do** keep series hues locked: violet = current period, cyan = comparison, everywhere and every view.
- **Do** pair every meaning with a second channel (dash pattern, text label, icon) — color never alone.
- **Do** show "–" + status chip for unconnected sources, and say which platforms are excluded from totals.
- **Do** animate only state changes: 260ms drawer slide, 140ms hover tints, filter loading = skeletons ~480ms; all off under prefers-reduced-motion.
- **Do** keep KPI numerals tabular and tracked -0.03em at 29px.

### Don't:
- **Don't** use coral for body/small text on white; minimum coral text role is the 10.5px chip, and only on coral-wash.
- **Don't** put a hue glow on anything; shadows are rgba(60,64,75,…) only.
- **Don't** display 0 where data was never fetched.
- **Don't** add a second gradient surface or a glass/decoration blur (topbar blur is the only one).
- **Don't** open modals that occlude the chart — the drawer reflows; that is the product's promise.
