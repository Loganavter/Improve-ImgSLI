# ColorPickerDialog

App-level replacement for the system `QColorDialog`, built from toolkit
atoms so it matches the rest of the app instead of the OS-native picker.
Lives in the app (not `sli-ui-toolkit`) because picker integration — recents
persistence, value-format semantics, geometry persistence — is a product
concern.

Source: `src/ui/widgets/color/picker_dialog.py`

## Construction

| Param | Meaning |
|---|---|
| `initial: QColor` | starting color |
| `title: str = ""` | window title (auto-decorated via the CSD pipeline) |
| `show_alpha: bool = False` | show the alpha slider / 8-digit hex / `A` spinbox |
| `ok_text` / `cancel_text` | button labels (localized defaults when `None`) |
| `recents_store` | `RecentColorsStore` for the recents shelf |

Non-modal, resizable; `colorSelected(QColor)` fires on OK and on recent-chip
clicks, `finished` on close.

## What it does

- SV square (custom, not a linear control) + hue `Slider` + vertical alpha
  `Slider` with a spectrum/checkerboard `track_painter`.
- Single color-value `CustomLineEdit` whose format cycles
  HEX → RGB → HSL via the format button (`color_value_format`).
- RGB(A) `SpinBox` fields, before/after preview chip, recents chip row
  (`RecentColorsRow`).
- Return/Enter accepts (handled in `keyPressEvent`, not a window shortcut);
  the dialog keeps API compatibility with the `QColorDialog` subset the
  callers used.

## Keyboard

The dialog registers one `ToolbarRowsSection` (`tag="color-picker"`) over four
rows in visual order: SV/hue/alpha picker, value fields, recents chips, action
buttons. Chips are `StrongFocus` and paint the toolkit focus ring;
`Enter`/`Space` on a chip applies that colour (the same signal a click
emits), and `Enter` on OK accepts. `Esc` (or OK / Cancel / close) returns
focus to the opener — `opener=` when the caller passes it (e.g.
`ColorSwatch`), otherwise the widget that was focused when the dialog opened.

The SV square is `StrongFocus` (so the row walk reaches it) but, being a 2D
surface with no single row/column axis, it does not consume bare arrows: the
section keeps them for the ring walk and the colour never changes. `Enter`
enters its explicit value-edit mode (`is_editing()` — the toolkit's value-edit
contract): arrows and `W`/`A`/`S`/`D` move the crosshair (`W`/`S` = value,
`A`/`D` = saturation), `Enter` commits and leaves the mode, `Esc` reverts to
the saturation/value captured on entry. The keyboard-focus ring is the
toolkit's shared `paint_focus_ring` (keyboard modality only — a mouse click
focuses without a ring).

## Inspection

Family `ColorPickerDialog`; state: `color`, `show_alpha`, `value_format`.
Config auto-derives from the constructor.

Used by: image_compare settings color pickers, export dialog, onboarding,
multi_compare controller, `ColorSwatch`.
