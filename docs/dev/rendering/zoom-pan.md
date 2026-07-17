# Zoom, Pan & Interaction

A surprising number of bugs in canvas features come from getting zoom and pan
wrong. Read this section before adding any feature that draws geometry or
hit-tests at a specific image position; it complements — doesn't replace —
[coordinate-systems.md](coordinate-systems.md).

## Gesture Bindings (Mouse Routing)

Shared event code (`src/events/image_label/mouse.py`) must not branch on
feature-specific flags to decide which feature owns a click. Instead each
feature declares its mouse gestures via `WIDGET_FEATURE.build_gesture_bindings`,
and `mouse.py` walks them through `GestureResolver`.

### Contract

```python
from ui.canvas_infra.scene.widget_contract import CanvasFeatureGestureBinding

CanvasFeatureGestureBinding(
    gesture_id="my_feature.do_thing",   # unique, namespaced by feature
    button=Qt.MouseButton.LeftButton.value,
    matches=fn(ctx) -> bool,            # predicate run on press
    is_active=fn(store) -> bool,        # is this gesture currently driving?
    begin=fn(handler, local_pos) | None,
    update=fn(handler, local_pos) | None,
    end=fn(handler) | None,
    owner=str | None,                   # input_session owner id
    priority=int,                       # lower wins; resolver sorts ascending
)
```

The `matches`/`is_active`/`begin`/`update`/`end` callables live inside the
feature package. They are free to call `handler.geometry.*`, `handler.preview.*`,
and `get_canvas_feature_command_by_alias(...)` — but shared event code must
not.

### Rules

1. **No feature literals in `mouse.py`.** No alias name starting with
   `overlay.`, `splitter.`, `magnifier.`, etc. No reads of `view_state.<feature_flag>`
   or `interaction_state.is_dragging_<feature>`. Enforced by
   `tests/contracts/test_events_no_feature_branching.py`.
2. **Predicates gate against app-level workflows.** If the click is part of
   space-bar / preview / single-image-mode handling, the predicate must
   return False so the gesture does not fire (see magnifier's
   `_matches_capture_drag` rejecting space-pressed state).
3. **Fallback gestures use high priority numbers.** Divider's split-drag has
   `priority=1000` so any overlay-style feature can claim the click first.
4. **`begin`/`end` are self-contained.** They wrap the alias call AND any
   `emit_viewport_change`/geometry calls needed to finalize the gesture.
   Shared code never combines them.

### Why This Matters

With gesture bindings, `mouse.py` knows nothing about which features exist —
it just asks the resolver. Adding or hiding an overlay does not require
editing the central mouse router, and routing does not peek into another
feature's `overlay.active_state` payload shape.

## Viewport Change Contract

When feature commands modify state that affects UI rendering or panel visibility, they must emit viewport changes to notify the system.

### Pattern

All feature commands that modify state should follow this pattern:

```python
def viewport_set_feature_property(store, value):
    if store is None or getattr(store, "viewport", None) is None:
        return None

    # Modify state via store service
    result = StoreService(store).update_property(value)

    # Always emit full viewport change after state modification
    if hasattr(store, 'emit_viewport_change'):
        store.emit_viewport_change()

    return result
```

### Rules

1. **Always emit after state changes** — UI panels and buttons won't update without viewport change notification
2. **Check for `emit_viewport_change` method** — during initialization, store may be wrapped in `StoreProxy` which lacks this method
3. **Use full viewport change** — call `emit_viewport_change()` without subdomain parameter, not `emit_viewport_change("interaction")`
4. **Don't emit during read-only operations** — queries and hit-tests should not emit changes

### Why This Matters

Without viewport changes:
- Toggle buttons won't update their visual state
- Toolbar panels won't appear/disappear
- Capture area highlights won't recalculate
- User must move mouse to trigger re-render

With viewport changes:
- All UI updates happen immediately
- State changes are visible instantly
- No need for user interaction to see feedback

## Pan at any zoom

Middle-button pan is allowed at every zoom level, including fit (`zoom == 1.0`).
At fit zoom this can reveal letterbox/empty margins — that is intentional.

Shader, split **display**, and overlay formulas must use the **same** raw pan
values. Do not special-case `zoom <= 1.0` by forcing pan to `(0, 0)` in the
display path while the base shader still applies pan — that desyncs the image
from overlays. Pan drag/wheel math lives in `compute_zoom_wheel_transform` /
`compute_zoom_pan_drag_transform` (`src/ui/canvas_infra/viewport/zoom.py`).

## Split: content-anchored at fit, camera-anchored when zoomed in

``split_position`` / ``split_position_visual`` are **base-image** fractions
(`0.0..1.0` along the comparison content — see
[coordinate-systems.md](coordinate-systems.md)).

Dual-mode via ``compute_zoom_split_position_for_view_transform``:

| Zoom | Store spit on pan/zoom | Line / seam feel |
|---|---|---|
| ``zoom <= 1`` | unchanged (``None``) | rides with the image |
| ``zoom > 1`` | rewritten (clamped to ``[0, 1]``) so **screen** spit stays fixed | sticks to the viewport ("follows the camera") |

Drawing maps content → screen via ``compute_zoom_display_split_position``:

```text
display = (base - 0.5 + pan) * zoom + 0.5
```

Do **not** clamp display to ``[0, 1]`` when zoomed out — that pins the line to
the viewport edge while the image keeps moving.

The base-image shader compares spit in **letterboxed image UV** (magnifier
``internalSplit`` parity). The white divider uses the view-transformed
letterbox + fragment clip. Full write-up:
[investigations/divider-zoom-pan-detach.md](investigations/divider-zoom-pan-detach.md).

## Semantic geometry vs paint extents

Feature geometry has two different meanings that must stay separate:

| Kind | Examples | May affect |
|---|---|---|
| **Semantic geometry** | overlay center, capture/crop rect, guide endpoint, handle anchor, split position, hit-test shape | store state, scene objects, hit-test, guides, export layout, keyframes |
| **Paint extent** | stroke width, antialiasing fringe, shadow blur, hover outline, selected border, glow | render draw bounds, scissor/clipping, dirty rect inflation |

Do not use paint extent as a clamp margin for semantic geometry. If a circle is
allowed to touch the image edge, clamp its center to `edge + radius`, not
`edge + radius + stroke/2 + aa`. Otherwise every consumer that reads the
semantic point will inherit a fake offset: guides attach to the wrong place,
hit-tests disagree with the visual edge, export/live paths diverge, and
positions can "jump" when a post-interaction rebuild uses a different render
scale.

Correct pattern:
- Clamp semantic objects using only semantic size and image/content bounds.
- Let render passes clip or antialias strokes at the edge.
- Inflate dirty rects or scissor decisions locally in the renderer if paint
  can extend outside semantic bounds.
- Keep live scene geometry and plan/export geometry sourced from the same
  semantic rect (`_inner_content_rect_px` when fit-content padding is active,
  otherwise `_content_rect_px`).

When reviewing overlay code, names like `stroke_margin`, `aa`, `border_width`,
`shadow_radius`, or `hover_padding` inside functions that update store state,
build scene objects, hit-test, or calculate guide endpoints are a red flag.

## Where pan and zoom live

There are two separate-but-related concepts:

- **Widget zoom/pan** (`zoom_level`, `pan_offset_x`, `pan_offset_y`) —
  viewport state owned by `CanvasWidget`. The shader reads these to apply
  zoom-around-cursor.
- **Store-level split / overlay positions** — semantic positions of overlays
  in canvas-px (`split_position`, magnifier centers, etc.). Stored in the
  Store, persisted across sessions.

These two layers are coordinated by **viewport features** in
`src/ui/canvas_infra/viewport/`. Don't bypass them by reaching into widget
state from your feature.

## Debugging zoom/pan issues

Use the [runtime tracer](../TRACING.md). The minimal-noise category set for
viewport debugging is:

```bash
IMGSLI_TRACE=1 \
IMGSLI_TRACE_KINDS="input.wheel,input.mpress,input.mrel,dispatch.begin,dispatch.end,hit_test,render.apply_plan,store.emit_viewport" \
python src/__main__.py
```

Then `print_tree --top 3` to see the slowest causal chains. Common symptoms
and where to look:

| Symptom | Likely cause | Where to look |
|---|---|---|
| Overlay drifts during pan at fit zoom | Some path still zeros pan when `zoom <= 1.0` | `git grep 'zoom.*<=.*1' src/ui/canvas_infra src/tabs/image_compare/canvas/` |
| Overlay flickers / jumps during interaction | Reducer reset a runtime-cache field | Check `_build_new_viewport_state` for missing field carryover; move field to `ViewportRuntimeCache` |
| Mouse hit lands on wrong feature | Hit-test uses widget-px but feature stores widget-px instead of canvas-px | Search for direct `widget.width()` / `widget.height()` in your feature's geometry math |
| Position correct at `zoom = 1` but wrong otherwise | Feature draws using raw store value instead of going through the viewport display formula | Use `compute_display_split_position` / equivalent contract instead of reading store directly in render |
| Overlay can never reach the image edge, or guides attach a few px away from the visual target | Paint margin leaked into semantic geometry clamp | Search for `stroke`, `aa`, `border`, `shadow`, or `padding` in scene/build/hit-test/layout helpers; move it to render-only clipping/draw code |
