# ScrollValueButton

Scroll-driven numeric button: icon + hover value split, with an underline
whose thickness tracks the value — used for divider/guide widths in Image
Compare and Multi Compare.

Source: `src/ui/widgets/scroll_value_button.py`

## Construction

| Param | Meaning |
|---|---|
| `min_value` / `max_value` / `start` | value range and initial value |
| `*button kwargs` | toolkit `Button` parameters (icon, size, …) |

Built on the toolkit button region/layer pipeline (`ButtonRegion`,
`BackgroundLayer`, `ContentLayer`, `BadgeLayer`, `UnderlineLayer`,
`VerticalSplit`, …). Scrolling over the button cycles the value; the hover
flyout shows the value split. Keyboard focus is parked off QRhi canvases
on Wayland/Vulkan via `ui.canvas_infra.rhi.rhi_focus`.

## Inspection

Family `ScrollValueButton`; state: `value`, `min_value`, `max_value`,
`saved_value`, `checked`; regions enabled.

Used by: image_compare primitives (divider/guide widths), multi_compare
toolbar, onboarding pages.
