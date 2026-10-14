# DONE — CSD dropdown shortcut region always fits (no left clip)

**Task:** `task-csd-menu-shortcut-2026-10-14`
**Branch:** `agent/csd-menu/work`
**Commit:** `43a23659`

## STATUS

DONE. The right region (shortcut hint) of CSD title-bar dropdown rows no
longer left-clips. Root cause found, fix in-clone, regression test
red-before/green-after, contracts + plugins green, pushed.

## ROOT CAUSE (verified, not assumed)

`CsdMenuRow` is a toolkit `Button` with a widget-wide
`content_padding=(8 + icon_lead, 0, 8, 0)` and a `CustomSplit` that carves the
right region as exactly `trailing = measure_text_width(fm, shortcut) + gap` px.

The toolkit's row painter subtracts the widget-wide `content_padding` from
**every** region rect, not only the leading icon+label one
(`sli_ui_toolkit.ui.widgets.buttons.content._rect(ctx)` →
`rect.adjusted(left, top, -right, -bottom)`; `DrawContext.scoped_to()` keeps
the same whole-widget padding for all regions). So the shortcut region's
*usable* width was `trailing - content_left - content_right`.

With the real row padding (`content_left = 8 + icon_lead = 32`,
`content_right = 8`) the long chord `Ctrl+Shift+O` got a **49px** slot while
the row's render font paints **69px** → the leading **20px** were clipped
(left-clipped because the row is right-aligned and `drawText(rect, …)` clips
to the rect).

Working-sibling diff (diagnosis ladder step 2): the toolkit's canonical
label+shortcut row (`composite/context_menu/rows.ContextMenuRow`) uses
`content_padding = 0` and paints its shortcut directly, so it never hits this;
our split + widget padding row did.

Font mapping was **not** the bug: measurement uses `ui_font(pixel_size=12)`
and the row renders with `ui_font(pixel_size=12, bold=False)` — identical
advance. The whole deficit is the padding.

## FIX (scope: `src/ui/main_window/csd_menu_strip.py` only)

Extend the shortcut region's split rect left by `content_left`, so that after
the painter subtracts the widget-wide content padding the usable slot is the
full `trailing` (measure + gap):

```python
lambda r: QRectF(
    r.right() - trailing - content_left,
    r.top(),
    float(trailing + content_left),
    r.height(),
)
```

`sizeHint()` still uses the unchanged `trailing`, so the flyout/panel width is
**unchanged** (no unrelated row changes). The label region rect is untouched,
so label rendering is unchanged; the group's united fill still spans the full
row width (hover highlight unchanged). The two region rects now overlap by
`content_left` px of empty/left-aligned space — both are `group="row"`, so
hit-testing/hover/click behave identically.

`menu_controller.py` untouched — the shortcut *text* was correct.

`docs/dev/file_size_registry.json` regenerated (line count of the edited file
changed; required by `tests/contracts/test_file_size_policy.py`).

## MEASURED BEFORE / AFTER

Worst case: icon + label `Open Project` + shortcut `Ctrl+Shift+O` (advance 69px).

| quantity | before | after |
|---|---|---|
| shortcut region rect | `122..211` w=89 | `90..211` w=121 |
| content padding applied (L/R) | 32 / 8 | 32 / 8 |
| **effective usable slot** | **49px** | **81px** |
| rendered shortcut advance | 69px | 69px |
| deficit (advance − slot) | **+20px (left-clipped)** | **−12px (slack)** |
| painted ink left edge (pixel diff) | **x=154** (expected 134) | **x=134** |

Pre-fix deficits by UiScale factor (geometry test): `1.0 → 20px`, `1.25 → 17px`,
`1.5 → 14px`, `2.0 → 8px`.

## TESTS

New focused test: `tests/runtime/test_csd_menu_row_shortcut_fit.py`

- `test_shortcut_slot_covers_rendered_width` (parametrized 1.0/1.25/1.5/2.0):
  asserts effective slot (region width − applied padding) ≥ rendered advance.
  **Red before** (`49px < 69px (20px left-clipped)` at 1.0), green after.
- `test_shortcut_glyphs_painted_without_left_clip`: renders the row with and
  without the shortcut (same label/background), diffs the images to isolate
  the shortcut ink, and asserts the ink starts at the unclipped position.
  **Red before** (`ink starts at x=154, expected <= 136`), green after.

Commands (from repo clone root, headless):

```
# new focused test — RED on HEAD, GREEN after
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q \
  tests/runtime/test_csd_menu_row_shortcut_fit.py -p no:cacheprovider
# → 5 passed

# acceptance
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/contracts tests/plugins tests/runtime/test_csd_menu_row_shortcut_fit.py -p no:cacheprovider
# → 2321 passed, 66 skipped

# related runtime suites (no regression)
# tests/runtime/test_main_window_title_bar_menus.py
# tests/runtime/test_csd_menu_strip_scale.py
# tests/runtime/test_ui_scale_live_apply.py
# tests/test_context_menu.py tests/plugins/test_find_action_palette.py
# → 51 passed, 1 skipped
```

Red-before was proven **in-clone** (cp fixed file aside → `git checkout HEAD --`
the file → test fails → restore): no /tmp worktree used.

## INTERFACE

No public API change. `CsdMenuRow` construction, `sizeHint()`,
`minimumSizeHint()`, `region_rect("shortcut")` semantics unchanged in kind
(the shortcut region rect is now `content_left` px wider so its padded content
area is the intended slot). `CsdMenuStrip` / `CsdMenuSpec` /
`menu_controller.py` unchanged. Flyout width unchanged.

## SELF-REVIEW

- Diagnosis ladder: blast radius = host CSD menu rows only (gallery untouched);
  working-sibling diff = toolkit `ContextMenuRow`; cheapest discriminator =
  the padding arithmetic, confirmed by a pixel diff of the real render.
- Did not read toolkit source by absolute path; only runtime import/inspect
  (allowed). No toolkit edit; no `question` needed.
- No gallery files touched. No GUI run.
- Fix keeps the classic look: label left, shortcut right-aligned, same right
  inset (8px) and same panel width.
- Regression test is falsifiable (fails on HEAD with the exact 20px
  under-width) and not a restatement of the fix: it computes the effective
  slot from the toolkit's actual padding behavior + the real render font, and
  the pixel test is independent of that arithmetic.

## SUMMARY

The shortcut hint was clipped on the left because the toolkit applies the
row's whole-widget content padding to the shortcut region too, and the split
only budgeted for the gap. Compensating the region rect by the left content
padding (with `sizeHint` untouched) makes the right region always fit — worst
case went from a 49px slot for 69px of glyphs to an 81px slot, verified by
geometry and by a rendered-pixel diff.
