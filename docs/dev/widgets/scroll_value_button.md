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
button is a **focus** affordance, raised only by a *user* grant — keyboard
focus (arrow/Tab) or the pointer over the button (a click). A bare programmatic
focus (the new tab's activation focus landing on the first control) raises
nothing; `Up` then creates the pill on demand and enters it. The preview never
steals focus. `Up`
moves the keyboard into the pill; `Left`/`Right` step the value there (the
underline follows); a second `Up` leaves the pill upward to the control above
(it never steps); `Down` hands the keyboard back to the button with the
pill still visible (`Up` re-enters); `Esc` dismisses the pill and restores
the button's own digit. Only `Left`/`Right` change the value. `Enter` mirrors
a right-click — it emits `rightClicked` and nothing else; the control has no
edit mode.

The digit capsule drawn over the underline uses the same ordered background
stack as the button (base + the group's hover/checked wash), so it reads as
part of the control, not a floating chip.

No `ScrollValueButton` carries a colour of its own, so the right-click/`Enter`
signal never opens a colour picker here — the colour-carrying control is
`ui.widgets.color.ColorSwatch`.

## Inspection

Family `ScrollValueButton`; state: `value`, `min_value`, `max_value`,
`saved_value`, `checked`; regions enabled.

Used by: image_compare primitives (divider/guide widths), multi_compare
toolbar, onboarding pages.
