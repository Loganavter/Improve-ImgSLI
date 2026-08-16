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
- Return/Enter accepts; the dialog keeps API compatibility with the
  `QColorDialog` subset the callers used.

## Inspection

Family `ColorPickerDialog`; state: `color`, `show_alpha`, `value_format`.
Config auto-derives from the constructor.

Used by: image_compare settings color pickers, export dialog, onboarding,
multi_compare controller, `ColorSwatch`.
