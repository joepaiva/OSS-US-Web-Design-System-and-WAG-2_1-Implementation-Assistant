# Responsive Design — Chassis Policy

**Current as of chassis v0.10.0.**

**Chassis version:** ≥0.6.2
**Standard:** USWDS 3.7 (US Web Design System) — mobile-first responsive grid + breakpoints.
**Target devices:** All modern browsers on phones (320 px+), tablets (640–1024 px), and desktops (≥1024 px).
**Status:** Chassis-locked. Slot authors and LLM-generated code MUST NOT override the chassis's responsive policy. They MAY add slot-specific layouts that build *on top of* the chassis grid (e.g., a custom dashboard tile), but those layouts MUST themselves be responsive.

---

## What the chassis ships

### Viewport + meta tags (every page)

```html
<meta name="viewport" content="width=device-width, initial-scale=1">
```

Lives in `app/templates/base.html`. Every slot template extends `base.html`, so every page is mobile-aware by default.

### USWDS 3.7 grid + breakpoints

USWDS uses these breakpoints (mobile-first — styles cascade upward from the smallest):

| Token | Min width | Typical device |
|---|---|---|
| (default) | 0 | Phones — single-column flow |
| `mobile-lg` | 480 px | Large phones |
| `tablet` | 640 px | Small tablets, large phones in landscape |
| `tablet-lg` | 880 px | Tablets |
| `desktop` | 1024 px | Small laptops |
| `desktop-lg` | 1200 px | Standard desktops |
| `widescreen` | 1400 px | Large monitors |

Grid usage in slot templates:

```html
<div class="grid-row grid-gap">
  <div class="grid-col-12 tablet:grid-col-6 desktop:grid-col-4">
    <!-- Full width on phone, half on tablet, third on desktop. -->
  </div>
</div>
```

### Touch target sizing

USWDS components ship with **minimum 44 × 44 px** touch targets (matching WCAG 2.1 SC 2.5.5 / Apple HIG / Material). Slot authors MUST NOT override `padding` or `min-height` on USWDS components in ways that shrink the touch area below 44 px on mobile.

### Hamburger / mobile navigation

`app/templates/base.html` uses the `<usa-header>` component, which automatically collapses to a hamburger menu at `tablet` breakpoint (< 640 px). No slot code change needed — the chassis nav is responsive by default.

### Typography fluid scaling

`stripe-overrides.css` uses USWDS typography tokens that scale with viewport. Body text reads correctly at 16 px on phone (no horizontal scroll, no zoom required) and at 18 px on desktop. Slot code SHOULD use USWDS typography classes (`font-body-xs`, `font-body-md`, `font-heading-lg`, etc.) rather than fixed pixel values.

### Form input sizing on mobile

USWDS form inputs (`usa-input`, `usa-select`, `usa-textarea`) ship with `font-size: 16px` minimum on mobile to prevent iOS Safari's "auto-zoom on focus" behavior. Do not override.

---

## What slot code MUST do

1. **Use USWDS grid classes** (`grid-row`, `grid-col-*`, `tablet:grid-col-*`, `desktop:grid-col-*`) for any multi-column layout. Do not use `display: flex` or `display: grid` with custom CSS unless USWDS grid genuinely can't express the layout.

2. **Always wrap content in a USWDS container**: `<main class="usa-section"><div class="grid-container">…</div></main>`. The `grid-container` gives correct max-width + horizontal padding on all viewports.

3. **Use USWDS form components** for all inputs (`usa-input`, `usa-select`, `usa-checkbox`, `usa-radio`, `usa-button`). Custom inputs MUST be tested at 320 px viewport.

4. **Test at 320 px viewport** (the de-facto smallest phone). No horizontal scroll. No content cut off. All actions reachable.

---

## What slot code MUST NOT do

- Override viewport meta (already set in base.html).
- Use fixed pixel widths for content containers (use `grid-container` instead).
- Build custom hamburger menus (the chassis `<usa-header>` handles this).
- Shrink USWDS touch targets below 44 px on mobile.
- Force `font-size` below 16 px on form inputs (causes iOS Safari auto-zoom).
- Hide content on mobile with `display: none` solely to fit a small screen — restructure the layout instead.

---

## Test viewport matrix (chassis pytest enforces)

| Viewport | Width | Device class | Tested layouts |
|---|---|---|---|
| 320 × 568 | iPhone SE | Smallest phone | No horizontal scroll on every chassis page |
| 768 × 1024 | iPad | Tablet | Layout uses tablet-tier grid columns |
| 1280 × 800 | Laptop | Desktop | Layout uses desktop-tier grid columns |

These viewports are validated by `tests/test_responsive.py` on every chassis CI run.

---

## How to override the chassis default

The chassis policy is **mandatory by default**. If a slot author has a documented business need to deviate (e.g., a hardware-control kiosk app where touch targets are larger than 44 px), the override mechanism is:

1. **Spec it explicitly** in the application's `REQUIREMENTS.md` as a slot-defined requirement, with a clear justification.
2. **Annotate the override** in slot code with a `# CHASSIS-OVERRIDE: responsive-design` comment + reference to the FR-ID.
3. **Surface the override** in the Wizard's UI/UX guide — the "ask once, accept default" flow (K.9) captures the deviation in the Golden Record.

Without this annotation, post-build verification will FAIL: `pytest tests/test_responsive.py` checks for `# CHASSIS-OVERRIDE:` markers on any element that violates the responsive policy.
