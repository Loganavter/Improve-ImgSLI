# GlassPanelDisplayWidget

Blits the already-composited glass sprite (computed canvas-side via
`shared/rendering/glass_panel.py`) onto the screen — the display half of
the GlassHUD split. CPU/QPainter variant by default; an RHI variant is
env-gated (`IMGSLI_GLASS_PANEL_DISPLAY_BACKEND=rhi`) and loads the
package-local shaders (`glass_hud/shaders/`).

Source: `src/ui/widgets/glass_hud/panel_display.py`

## Construction

| Param | Meaning |
|---|---|
| `parent` | host widget |

`create_glass_panel_display_widget(glass_spec, parent)` is the factory the
HUD uses; `GlassPanelDisplayWidget` aliases the CPU variant.

## Inspection

Families `GlassPanelDisplayWidgetCpu` and `GlassPanelDisplayWidgetRhi`
(config auto-derives; low-value state, intentionally empty).

Used by: `GlassHUD` only.
