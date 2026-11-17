---
name: Sellbird
description: A calm local control room for an outreach pipeline you approve.
colors:
  cobalt: "#1D4ED8"
  cobalt-deep: "#1E40AF"
  cobalt-wash: "#EBF1FE"
  cobalt-hairline: "#CCDBFC"
  chart-muted: "#BCD0FA"
  paper: "#F6F6F7"
  surface: "#FFFFFF"
  surface-inset: "#F3F3F4"
  surface-pressed: "#EBEBED"
  hairline: "#E7E7EA"
  hairline-strong: "#D6D6DB"
  ink: "#111113"
  ink-secondary: "#5B5B63"
  ink-tertiary: "#8B8B93"
  status-good: "#1F7A4D"
  status-good-bg: "#E8F6EE"
  status-waiting: "#8A5A00"
  status-waiting-bg: "#FFF4DE"
  status-bad: "#B4232F"
  status-bad-bg: "#FDECEE"
  status-active: "#0E7490"
  status-active-bg: "#E5F6F9"
  status-note: "#6A3FB0"
  status-note-bg: "#F2ECFC"
typography:
  page-title:
    fontFamily: "Geist, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  kpi:
    fontFamily: "Geist, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Geist, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Geist, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0em"
  ui:
    fontFamily: "Geist, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "0em"
  caption:
    fontFamily: "Geist, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.35
    letterSpacing: "0em"
  overline:
    fontFamily: "Geist, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "0.06em"
  mono:
    fontFamily: "Geist Mono, ui-monospace, SF Mono, Menlo, monospace"
    fontSize: "0.85em"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0em"
rounded:
  xs: "4px"
  sm: "6px"
  md: "10px"
  lg: "14px"
  pill: "99px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "24px"
  "6": "32px"
  "7": "48px"
components:
  button-primary:
    backgroundColor: "{colors.cobalt}"
    textColor: "{colors.surface}"
    typography: "{typography.ui}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "32px"
  button-primary-hover:
    backgroundColor: "{colors.cobalt-deep}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.ui}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "32px"
  button-secondary-hover:
    backgroundColor: "{colors.surface-inset}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-secondary}"
    typography: "{typography.ui}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "32px"
  button-danger:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.status-bad}"
    typography: "{typography.ui}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "32px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "36px"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.ink-secondary}"
    typography: "{typography.ui}"
    rounded: "{rounded.sm}"
    padding: "0 10px"
    height: "32px"
  nav-item-active:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "24px"
  badge-waiting:
    backgroundColor: "{colors.status-waiting-bg}"
    textColor: "{colors.status-waiting}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    padding: "0 8px"
    height: "22px"
  tag-accent:
    backgroundColor: "{colors.cobalt-wash}"
    textColor: "{colors.cobalt}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    padding: "0 8px"
    height: "22px"
---

# Design System: Sellbird

## Overview

**Creative North Star: "The Quiet Control Room"**

Sellbird's dashboard is where a part-time operator checks on a machine that has been working without them. The room is calm by default: cool neutral paper, white surfaces, one typeface, almost no colour. When something needs a decision, it is the only thing that speaks. Cobalt marks where to act; five status hues mark what state things are in; everything else stays grey on purpose, so colour always carries meaning.

Density is that of a working tool, not a brochure: a fixed 236px sidebar, content capped at 1180px, 13–14px interface text on a small, strict scale, and tabular numbers so columns line up and changing counts never shift the layout. Surfaces are lifted with hairline shadows rather than outlined; space groups things, shadows lift surfaces, lines only divide. Motion is feedback only: buttons press, hovers exist only on real pointers, and nothing animates on a tab switch.

Light and dark are the same design re-tokenised. Only the token layer changes between them; no component has a theme-specific rule.

**Key Characteristics:**
- One cobalt accent on a cool neutral ground; colour is reserved for action and status.
- A single sans family (Geist) on a tight 12–28px scale, with Geist Mono for codes and keys.
- Concentric radii: 6px controls inside 14px cards.
- Hairline ring shadows instead of borders for every lifted surface.
- Feedback-only motion with a fast ease-out; no decorative animation.

## Colors

A cool, nearly colourless neutral palette with one cobalt accent and a disciplined set of paired status tints.

### Primary
- **Cobalt** (#1D4ED8): the primary action button, the active nav item's icon, the main series in a chart, focus outlines and links to act. Deepens to **Cobalt Deep** on hover. In dark mode it brightens to #3D6FF5 (hover #5A85FF).
- **Cobalt Wash** and **Cobalt Hairline**: the soft fill and edge for accent tags, nav counts, sent message bubbles and drafted replies awaiting approval. **Chart Muted** is the secondary series beside cobalt.

### Neutral
- **Paper** (#F6F6F7): the page and sidebar ground, a touch cool.
- **Surface** (#FFFFFF): cards, tables, active nav items, inputs and secondary buttons.
- **Surface Inset** / **Surface Pressed**: hover fills and inset panels; pressed states, tracks and the segmented-control well.
- **Hairline** / **Hairline Strong**: dividers inside tables and panels; input borders and link underlines.
- **Ink**, **Ink Secondary**, **Ink Tertiary**: primary text; supporting text and idle controls; labels, metadata, placeholders and zero values.

### Status (paired: foreground, tint background, hairline)
- **Good** (#1F7A4D): sent, verified, connected, success.
- **Waiting** (#8A5A00): needs the user, pending approval, warming up.
- **Bad** (#B4232F): bounced, invalid, failed, destructive actions.
- **Active** (#0E7490): running now, in progress.
- **Note** (#6A3FB0): informational, offers and annotations.

Each status also has a hairline tone for badge borders. Dark mode swaps every pair for a brighter foreground on a deep tinted ground; the roles never change.

### Named Rules
**The One Accent Rule.** Cobalt marks the primary action, the current page and the main chart series. Nothing else is blue.

**The Colour Means Something Rule.** Status hues appear only on status: badges, tags, result banners and their icons. Never as decoration, section colour or illustration.

## Typography

**Body Font:** Geist (with -apple-system, BlinkMacSystemFont, Segoe UI)
**Label/Mono Font:** Geist Mono (with ui-monospace, SF Mono, Menlo)

**Character:** one neutral grotesk carries everything, so hierarchy comes from size, weight and colour, not from a second voice. Mono appears only for literal things the user might type or copy.

### Hierarchy
- **KPI** (600, 1.75rem/28px, 1.1, -0.03em): the four headline counts on Today. Zero values drop to Ink Tertiary.
- **Page title** (600, 1.375rem/22px, 1.2, -0.02em): one per view, with a 14px Ink Secondary description capped at 68ch.
- **Title** (600, 0.875rem/14px, -0.01em): card and empty-state headings; 16px for empty-state titles and legend values.
- **Body** (400, 0.875rem/14px, 1.5): default text; long copy capped at 68ch, empty-state copy at 48ch.
- **UI** (500, 0.8125rem/13px, line-height 1): buttons, nav items, table cells, form labels.
- **Caption** (400–500, 0.75rem/12px): metadata, badges, table footers, hints.
- **Overline** (500, 11px, 0.06em, uppercase): sidebar group labels only.

### Named Rules
**The Tabular Rule.** All numbers render with tabular figures, set once on the body.

**The One Typeface Rule.** Geist for everything, Geist Mono for codes and keys. No display or serif face is part of the dashboard.

## Layout

A two-column app shell: a sticky, full-height sidebar (236px) on the paper ground, and a content column capped at 1180px. Pages open with a section head (title, description, actions on the right), then KPI rows, cards and tables.

Spacing runs on a 4px base (4, 8, 12, 16, 24, 32, 48), one step per nesting level. The gap between groups is at least twice the gap inside a group: 12px inside a KPI row, 24px below it; 16px between cards; 32px above a subhead.

Grids collapse rather than squeeze: the main two-up grid goes single column below 1180px, the KPI row from four to two columns below 1000px, two-up card grids to one below 760px, with further simplifications at 900, 860, 700 and 520px. On narrow screens inputs grow to 16px text so mobile browsers do not zoom.

## Elevation & Depth

Depth comes from ring shadows: a 1px hairline ring plus a faint drop, so surfaces read as lifted paper rather than boxed regions. Borders are kept for dividers and inputs only. In dark mode the drop disappears and the ring becomes a 7% white hairline; popovers keep a deep, soft drop.

### Shadow Vocabulary
- **Resting surface** (`0 0 0 1px rgb(17 17 19 / 0.06), 0 1px 2px -1px rgb(17 17 19 / 0.06), 0 2px 4px 0 rgb(17 17 19 / 0.04)`): cards, tables, empty states, the active nav item and the selected segment.
- **Hovered surface** (`0 0 0 1px rgb(17 17 19 / 0.09), 0 1px 2px -1px rgb(17 17 19 / 0.08), 0 2px 6px 0 rgb(17 17 19 / 0.06)`): clickable cards on pointer hover.
- **Popover** (`0 0 0 1px rgb(17 17 19 / 0.08), 0 12px 32px -8px rgb(17 17 19 / 0.18)`): menus, dialogs, toasts.
- **Button** (`0 0 0 1px rgb(17 17 19 / 0.10), 0 1px 2px rgb(17 17 19 / 0.06)`): secondary, danger and small icon buttons.
- **Primary button** (`inset 0 1px 0 rgb(255 255 255 / 0.18), 0 0 0 1px #1A44C2, 0 1px 2px rgb(17 17 19 / 0.12)`): a top highlight and darker cobalt ring.

### Named Rules
**The Lines Only Divide Rule.** Space groups things, shadows lift surfaces, lines only divide. Never outline a card with a border.

## Shapes

Soft, concentric corners. Controls (buttons, inputs, nav items, segments) are 6px; inner panels and nested tables 10px; cards 14px, so a control sitting in a card's padding shares its curvature. Tags, keys and inline code are 4px. Badges, counts and progress bars are full pills. Conversation bubbles are 14px with the corner nearest the speaker tucked to 4px. Icons are a single set on a 24px grid, 1.75 stroke, round caps, drawn in `currentColor`.

## Components

### Buttons
Compact, quiet, and physical: they press.
- **Shape:** gently rounded (6px), 32px tall, 12px horizontal padding; 28px small variant, square icon variants.
- **Primary:** Cobalt with white 13px/500 text and the primary-button shadow. One per view region.
- **Secondary:** white surface with the button ring; hover fills to Surface Inset.
- **Ghost:** no fill or ring, Ink Secondary text; hover fills and darkens.
- **Danger:** secondary shape with Bad text; never a red fill.
- **Hover / Focus / Active:** 150ms ease-out colour changes, hover only under `(hover: hover)`; press scales to 0.96; focus shows a 2px cobalt outline at 2px offset; disabled drops to 50% opacity.

### Badges and Tags
The only coloured text in the system.
- **Badge:** 22px pill, 12px/500, a 6px dot in the current colour, tinted background and hairline in one of the five status pairs, or an idle grey.
- **Tag:** the same pill without the dot, neutral grey by default, cobalt wash for accent tags.

### Cards / Containers
- **Corner Style:** 14px.
- **Background:** Surface on the paper ground.
- **Shadow Strategy:** resting surface ring; hovered ring when clickable.
- **Border:** none (a transparent 1px border keeps sizing stable).
- **Internal Padding:** 24px; flush variant for edge-to-edge tables, which nest at 10px with no shadow.

### Inputs / Fields
- **Style:** 36px tall, white surface, 1px Hairline Strong border, 6px radius, 14px text; labels 13px/500 above with 6px gap.
- **Focus:** border turns Cobalt with a 3px Cobalt Wash halo.
- **Search:** a 15px Ink Tertiary icon inset left at 10px.
- **Result banners:** status-tinted 6px panels for test-connection success, error and pending.

### Navigation
- **Sidebar items:** 32px rows, 10px icon gap, 13px/500 Ink Secondary text with Ink Tertiary icons, grouped under 11px uppercase overlines.
- **Hover:** Surface Inset fill, text to Ink (pointer devices only).
- **Active:** white surface with the resting ring, Ink text and a Cobalt icon.
- **Counts:** cobalt-wash pills appear only when a section has items waiting.
- **Segmented control:** a Surface Pressed well with 28px segments; the selected one lifts to Surface with the resting ring.

### Conversation Thread (signature)
Sent messages sit right in Cobalt Wash with a cobalt hairline; received messages sit left on Surface Inset. A drafted reply waiting for approval is a dashed 1.5px Cobalt Hairline bubble with a small cobalt "draft" label, so an unsent message can never be mistaken for a sent one.

### Empty States
Centred, 48px top padding, a 40px rounded glyph tile on Surface Inset, a 16px title and 48ch Ink Secondary copy that says what will appear and how to make it happen.

## Do's and Don'ts

### Do:
- **Do** reserve Cobalt for the primary action, the current page and the main chart series.
- **Do** use the five status pairs only for state, always as foreground + tint + hairline together.
- **Do** lift surfaces with the ring shadows and keep borders for dividers and inputs.
- **Do** keep controls at 6px inside 14px cards, and pill shapes for badges and counts.
- **Do** keep numbers tabular and zero values in Ink Tertiary.
- **Do** gate hover styles behind `(hover: hover)` and keep motion to 120–150ms feedback (400ms for bar and progress fills).
- **Do** change only tokens between light and dark.

### Don't:
- **Don't** introduce a second accent hue, gradients or decorative colour.
- **Don't** outline cards or panels with borders.
- **Don't** add a second typeface or a display face to the dashboard.
- **Don't** animate on tab switches or page changes.
- **Don't** use a red filled button; destructive actions are red text on a neutral button.
- **Don't** style an unsent draft like a sent message.
