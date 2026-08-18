# Investigation: widget weight reduction

## Problem

Several widgets under `src/ui/widgets/` impose excessive burden on consumers
through dead code, test-only compatibility aliases, constructor bloat, and
missing convenience APIs. The shelf widget (`ui/widgets/shelf/`) is the
primary offender, but `glass_hud/`, `form_controls.py`, and `rating_item.py`
also contribute.

Measured impact:

| Widget | Lines | Consumer burden | Issue |
|---|---|---|---|
| `glass_hud/panel_display.py` | 294 | N/A | 175 lines of dead RHI fallback code |
| `shelf/widget.py` | 314 | 9+ API points for inheritors | Static method locked on class |
| `session_picker/recent/panel.py` | 918 | 60 lines of test-only aliases | Property aliases for backward compat |
| `form_controls.py` (OutputPathSection) | 234 | ~16 lines per consumer | Aliasing boilerplate |
| `rating_item.py` | 693 | 171-line constructor | Mixed concerns in __init__ |

## Plan

### Phase 1: Dead code removal (LOW risk)

**1a. Delete `GlassPanelDisplayWidgetRhi`** from `glass_hud/panel_display.py`

The RHI fallback (150 lines + 20 lines of imports) is documented as
non-functional — QRhiWidget-class widgets always composite as their own
opaque base layer. Remove the class, the `_USE_RHI_DISPLAY` env var check,
and the unused RHI imports. The factory function simplifies to always return
the CPU widget. Rename `GlassPanelDisplayWidgetCpu` → `GlassPanelDisplayWidget`.

Estimated savings: ~175 lines.

**1b. Fix duplicate `inspect_spec`** in `shelf/widget.py`

Lines 290-314 assign `ShelfWidget.inspect_spec` twice with identical
content but different `docs` paths. Remove the first assignment (lines
290-301).

Estimated savings: ~12 lines.

### Phase 2: Test alias cleanup (MEDIUM risk)

**2a. Update test references** to use real composition paths

Replace 63 test references from aliases to direct access:

```python
# Before:
panel._scroll            → panel._items.scroll_area
panel._grid_columns      → panel._items.grid_columns
panel._sort_button       → panel._header.sort_button
panel._view_button       → panel._header.view_button
panel._sort_order_button → panel._header.sort_order_button
panel._items_host        → panel._items.items_host
panel._drag_active       → panel._drop.drag_active
panel._panel_bg          → panel.content_bg() / panel.panel_bg()
panel._chrome            → panel (direct shelf method calls)
```

**2b. Remove aliases** from `panel.py`

Delete the `# --- test / legacy aliases ---` block (lines 226-285) and
`_ShelfChromeCompat` class (lines 76-88).

Estimated savings: ~60 lines in panel.py.

### Phase 3: API improvements (LOW risk)

**3a. Extract `apply_opaque_widget_fill`** to module scope in `shelf/__init__.py`

Move from `ShelfWidget.apply_opaque_widget_fill` (static method) to a
standalone function exported by the shelf package. Update `items_view.py`
to import the function directly instead of `ShelfWidget`.

Estimated savings: ~6 lines (import cleanup), architectural clarity.

**3b. Add `OutputPathSection.apply_to(dialog)`** method

Single method that wires all sub-widgets onto the dialog object, replacing
the ~8-line aliasing block at each consumer site.

Estimated savings: ~16 lines across 2 consumers.

**3c. Split `RatingListItem.__init__`** into named methods

Extract from 171-line constructor into:
- `_init_core_state()` — identity, callbacks, drag state (~15 lines)
- `_init_layout()` — QHBoxLayout + labels (~35 lines)
- `_init_rating_buttons()` — +/- buttons, signals, event filters (~40 lines)

Estimated savings: 0 net lines (reorg), constructor drops to ~30 lines.

## Execution order

1. Phase 1a — delete RHI dead code (immediate, no test changes needed)
2. Phase 1b — fix duplicate inspect_spec (trivial)
3. Phase 3a — extract apply_opaque_widget_fill (independent)
4. Phase 3b — add apply_to method (independent)
5. Phase 3c — split rating_item constructor (independent)
6. Phase 2a — update test references (depends on nothing, but highest risk)
7. Phase 2b — remove aliases (depends on 2a)

## Verification

After each phase:
- `./launcher.sh test tests/contracts -q` (architecture dogmas)
- `python -m py_compile` on changed files
- Manual smoke test: `./launcher.sh run --ui-inspector --debug`
