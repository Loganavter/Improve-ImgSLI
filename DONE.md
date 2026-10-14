# DONE — gallery dark theme [task-gallery-dark-theme-2026-10-14]

## STATUS

COMPLETE. Branch `agent/gallery-dark-theme/work`. Three coherent dark-theme
color defects fixed (badge ink, status-danger contrast, six fallback-only
hardcoded hexes tokenised). Light theme verified unchanged. Acceptance suite
green.

## TESTS

Command (repo clone root):

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m pytest -q src/tabs/image_gallery/tests tests/contracts -p no:cacheprovider
```

Result: **3189 passed, 68 skipped, 0 failed** in 134.86s (EXIT=0).

Focused new/updated tests:

- `src/tabs/image_gallery/tests/test_dark_contrast.py` (new, 6 tests):
  token coverage in BOTH palettes, dark severity-trio contrast ≥ 3:1 on
  card + grid, dark danger ≥ 4.5:1 as the error-row text (red-before: old
  `#D93025` < 3:1), dark neutral ≥ 4.5:1, rank-badge ink ≥ 4.5:1 on the rank
  pill in both themes, and a "light palette unchanged" guard.
- `src/tabs/image_gallery/tests/runtime/test_card_parity.py` (3 tests were
  pinning the bug — `txt == "#000000"` in **dark**): rewritten to assert the
  theme-aware ink and the red-before/green-after contrast.
- `tests/contracts/test_no_hardcoded_qcolor.py` still green (net −1 literal:
  the removed `QColor("#000000")`; the new helper uses only string fallbacks).

## INTERFACE

No public API change. Private module helper `_badge_text_color()` added to
`ui/card/visuals.py`. `src/resources/themes.json` gained 6 keys in **both**
the `light` and `dark` dicts (key-set parity preserved).

## SELF-REVIEW

- **Method**: captured every gallery surface on a private Xvfb (`:97`) in both
  themes — the two shipped devtool surfaces (`gallery`, `gallery-populated`)
  plus five sub-surfaces I rendered with a throwaway harness
  (`shots/_audit.py`): triage (stats-strip + series headers + rank pills),
  list view, quick-look (blocked — see below), clean review, Ask AI, and an
  unreadable-item card. Pixel-sampled + WCAG-contrast-computed each.
- **Quick Look limitation**: `show_quick_look` hard-exits the process on a real
  X display (QRhi/GL init) exactly as `docs/dev/SCREENSHOTS.md` documents, so
  it is not headlessly capturable. Its colors were audited statically from
  `ui/quick_look/**`; the two changes that touch it are token additions
  (values identical to the previous fallbacks in dark → no rendering change).
- **Light-unchanged evidence**: the light captures are byte-identical between
  the pre-fix and post-fix trees except for known-transient frames
  (scrollbar fade in `gallery-triage`, JPEG-free thumbnail re-decode in
  `gallery-cleanreview`/`gallery-unreadable`); re-capturing the *same* tree
  twice reproduces the identical transient differences, proving they are
  nondeterminism, not the change. No light token value moved.
- **Token values for `gallery.nav.*` / `gallery.pill.background` /
  `gallery.card.unreadable.plate` are identical in light and dark** on
  purpose: these are overlay controls drawn over arbitrary image content
  (nav discs) or a deliberately-dark "unreadable" plate, so they must stay
  high-contrast regardless of theme. Tokenising them removes the hardcoded
  hexes / makes them overridable without moving any pixel.
- **Not changed**: toolkit, other tabs, help, i18n JSON; no QSS anywhere.

## SUMMARY

### Defect 1 — dark rank-badge text was invisible (hardcoded black ink)

The `#N` rank pill fill is `button.toggle.background.checked`
(light `#c0c0c0`, dark `#555555`), but the ink was hardcoded
`QColor("#000000")`. In the dark theme black-on-`#555555` measures **2.79:1**
— the pill digits all but vanish.

- Before: `shots/base/dark/gallery-triage.png`, zoom `shots/base/dark/_badge.png`
- After: `shots/after/dark/gallery-triage.png`, zoom `shots/after/dark/_badge.png`,
  side-by-side `shots/after/dark/_badge_cmp.png`
- Fix: `ui/card/visuals.py` → new `_badge_text_color()` resolves
  **`button.primary.text`** (→ `WindowText` → light/dark fallback), so the ink
  is `#000000` light / `#ffffff` dark. Dark contrast 2.79 → **7.58:1**; light
  unchanged (`#000000`).

### Defect 2 — dark danger red below the contrast floor

`gallery.status.danger` dark was `#D93025` = **2.46:1** on
`gallery.card.background` (`#383838`) and **2.97:1** on
`gallery.grid.background` (`#2b2b2b`) — under the WCAG 3:1 non-text floor, and
illegible as the red "unreadable — excluded from triage" error-row text and
the flagged severity dots.

- Before: `shots/base/dark/gallery-unreadable.png`, comparison
  `shots/after/dark/_err_cmp.png` (top)
- After: `shots/after/dark/gallery-unreadable.png`, comparison
  `shots/after/dark/_err_cmp.png` (bottom)
- Fix: `src/resources/themes.json` dark **`gallery.status.danger`** →
  `#ff7b72` = **4.65:1** on the card / **5.62:1** on the grid. Light stays
  `#c0392b`.

### Defect 3 — six tokens referenced by the UI but missing from BOTH palettes

These always fell through to inline fallback hexes, so they never followed the
theme (THEMING.md: same key set in light + dark). Added to **both** palettes:

| token | light | dark | consumer |
|---|---|---|---|
| `gallery.status.neutral` | `#8a8a8a` | `#a6a6a6` | `ui/quick_look/metrics.py` muted "— · not measured" rows (dark contrast **3.40 → 4.82:1**) |
| `gallery.nav.glyph` | `#23262b` | `#23262b` | `ui/quick_look/overlay_build.py` nav chevron / SOURCE-inset title |
| `gallery.nav.fill` | `#f1f2f4` | `#f1f2f4` | nav disc fill |
| `gallery.nav.border` | `#d7dade` | `#d7dade` | nav disc ring |
| `gallery.pill.background` | `#ffffff` | `#ffffff` | `ui/quick_look/overlay_build.py` white SOURCE pill (documented white-in-both) |
| `gallery.card.unreadable.plate` | `#303030` | `#303030` | `ui/card/regions.py` "!" cover plate |

Light values equal the previous fallbacks, so light is pixel-unchanged; the
only value with a distinct dark branch is `gallery.status.neutral`.
