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
button is a **focus/click** affordance, raised by a *user* grant — keyboard
focus (arrow/Tab), the pointer over the button, or a press (a click also raises
it when focus was already granted, e.g. the tab bootstrap or the return from a
previous pill interaction). A bare programmatic focus raises nothing. The
preview never steals focus. `Up`
moves the keyboard into the pill; `Left`/`Right` step the value there (the
underline follows); a second `Up` leaves the pill upward to the control above
(it never steps); `Down` hands the keyboard back to the button with the
pill still visible (`Up` re-enters); `Esc` dismisses the pill and restores
the button's own digit.

### Value-edit mode (Enter)

`Enter` follows the app-wide value-edit contract
(plan-nav-coverage-2026-10-19), the same state machine as the toolkit
`Slider`: the first press enters edit mode and captures the entry value,
arrows and `W`/`A`/`S`/`D` then adjust the value (the pill stays up as the
readout), a second `Enter` commits, and `Esc` reverts to the entry value.
`is_editing()` exposes the state — `ToolbarRowsSection` only trial-dispatches
arrows to a focused widget while it reports edit mode, so while merely
navigating every arrow still moves the focus ring. Losing focus ends edit mode
with the value as-is.

`rightClicked` remains the **mouse** right-button signal (colour/context
menus are still reached with a real right click); `Enter` no longer mirrors it.
The pill's own `Left`/`Right` stepping is a separate preview affordance and is
unchanged.

The digit capsule drawn over the underline uses the same ordered background
stack as the button (base + the group's hover/checked wash), so it reads as
part of the control, not a floating chip.

No `ScrollValueButton` carries a colour of its own, so the right-click
signal never opens a colour picker here — the colour-carrying control is
`ui.widgets.color.ColorSwatch`.

## Inspection

Family `ScrollValueButton`; state: `value`, `min_value`, `max_value`,
`saved_value`, `checked`; regions enabled.

Used by: image_compare primitives (divider/guide widths), multi_compare
toolbar, onboarding pages.
