# ScrollValueButton

Scroll-driven numeric button: icon + hover value split (hover shows the
digit inside the button; keyboard focus, click or scroll raise a value pill
above it), with an underline whose thickness tracks
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
shows the value split (the digit) **inside** the button, while keyboard
focus, click or scroll raise the transient value pill above it (`_ScrollValueFlyout`). Keyboard
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

### Enter is the secondary action (right click)

Owner rule 2026-10-20: on this control `Enter`/`Return` does what a mouse
right click does — it emits `rightClicked` — so the colour pickers the
consumers already wire to that channel open from the keyboard too
(`multi_compare` divider width → `divider_color_clicked`; onboarding
`b_expert` → colour dialog). Enter never changes the value and never enters an
edit mode.

This is a deliberate exception to the app-wide Enter-to-edit contract
(`improve-imgsli-internal-docs/docs/dev/KEYBOARD_NAVIGATION.md` §15): `is_editing()` always returns `False`, so
`ToolbarRowsSection` keeps handing every arrow to ring navigation. The
keyboard value path is the wheel and `Left`/`Right` inside the `Up` pill. The
contract registry (`tests/runtime/test_value_control_edit_contract.py`) marks
this control `enter_edit=False` with the reason, and a guard keeps that
exception set at exactly one control.

The digit capsule drawn over the underline uses the same ordered background
stack as the button (base + the group's hover/checked wash), so it reads as
part of the control, not a floating chip.

The control itself carries no colour; the **consumers** wire `rightClicked`
to the colour picker of the element it sizes (divider/guide colour), which is
exactly why `Enter` was pointed at that signal.

## Inspection

Family `ScrollValueButton`; state: `value`, `min_value`, `max_value`,
`saved_value`, `checked`; regions enabled.

Used by: image_compare primitives (divider/guide widths), multi_compare
toolbar, onboarding pages.
