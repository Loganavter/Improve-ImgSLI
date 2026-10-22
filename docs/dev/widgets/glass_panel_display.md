# GlassPanelDisplayWidget

Blits the already-composited glass sprite (computed canvas-side via
`src/engine/gpu/glass_panel.py`) onto the screen — the display half of the
GlassHUD split. One family, CPU/`QPainter`: it paints a `QImage` copy of the
sprite. A `QRhiWidget`/`QOpenGLWidget` variant is deliberately *not* used
(always its own composited base layer, never alpha-blends into arbitrary
sibling z-order — see the class docstring).
The old CPU/RHI family split and the never-read
`IMGSLI_GLASS_PANEL_DISPLAY_BACKEND` gate are gone.

Source: `src/ui/widgets/glass_hud/panel_display.py`

## Construction

| Param | Meaning |
|---|---|
| `parent` | host widget |

`create_glass_panel_display_widget(parent=None)` is the factory the HUD uses;
it always returns the CPU/`QPainter` path.

## Wiring

`set_source(source_widget, panel_key)` is the only wiring API. The renderer
publishes its GPU→CPU readback as `source_widget._glass_panel_images`
(`ready_images` from `GlassPanelRenderer`), and `paintEvent` looks up
`panel_key` in that dict each frame — no image, no paint.

`target_watch` does the actual call: `hud._display.set_source(target_widget,
id(hud))` (`src/ui/widgets/glass_hud/target_watch.py`), where `target_widget`
is the canvas whose renderer sets `_glass_panel_images`
(`tabs/image_compare/canvas/rhi_renderer/renderer.py`,
`tabs/multi_compare/scene/renderer.py`).

## Inspection

Family `GlassPanelDisplayWidget` (regions + layers enabled; no config, low-value
state).

Used by: `GlassHUD` only.
