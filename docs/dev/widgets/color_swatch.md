# ColorSwatch

Round color-chip `Button` that opens a themed `ColorPickerDialog` on click.
App-level composite: picker integration is a product concern, not a generic
toolkit primitive.

Source: `src/ui/widgets/color/swatch.py`

## Construction

| Param | Meaning |
|---|---|
| `color: QColor \| None` | chip color (defaults to white) |
| `size: int = 28` | button side in design px (circle = size/2 corner radius) |
| `alpha: bool = True` | allow alpha editing in the picker |
| `hover: bool = False` | keep hover overlays (flat swatches opt out) |

`colorChanged(QColor)` fires when the picker selects a valid color. The
border uses a contrast token (`list_item.text.normal`) so the chip stays
visible on `flyout.background`.

## Inspection

Family `ColorSwatch`; state: `color`, `alpha_enabled`.

Used by: `FontSettingsFlyout` (text foreground/background).
