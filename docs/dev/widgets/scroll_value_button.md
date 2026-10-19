# ScrollValueButton

Scroll-driven numeric button: icon + hover value split (hover shows the
digit inside the button, no flyout), with an underline whose thickness tracks
the value — used for divider/guide widths in Image Compare and Multi Compare.

Source: `src/ui/widgets/scroll_value_button.py`

## Construction

| Param | Meaning |
|---|---|
| `min_value` / `max_value` / `start` | value range and initial value |
| `*button kwargs` | toolkit `Button` parameters (icon, size, …) |

Built on the toolkit button region/layer pipeline (`ButtonRegion`,
`BackgroundLayer`, `ContentLayer`, `BadgeLayer`, `UnderlineLayer`,
`VerticalSplit`, …). Scrolling over the button cycles the value; hovering
shows the value split (the digit) **inside** the button — no flyout. Keyboard
focus is parked off QRhi canvases on Wayland/Vulkan via
`ui.canvas_infra.rhi.rhi_focus`.

## Keyboard

Hovering the button shows only the digit inside it; the value pill above the
button is a **focus** affordance — giving the button keyboard focus (or
focusing it with a click) raises it (the preview never steals focus). `Up`
moves the keyboard into the pill; `Left`/`Right` step the value there (the
underline follows); `Down` hands the keyboard back to the button with the
pill still visible (`Up` re-enters); `Esc` dismisses the pill and restores
the button's own digit. `Enter` still toggles the legacy edit mode, in which
all four arrows step the value.

No `ScrollValueButton` carries a colour of its own, so `Enter` never opens
the colour picker here — the colour-carrying control is
`ui.widgets.color.ColorSwatch`.

## Inspection

Family `ScrollValueButton`; state: `value`, `min_value`, `max_value`,
`saved_value`, `checked`; regions enabled.

Used by: image_compare primitives (divider/guide widths), multi_compare
toolbar, onboarding pages.
