# ValueSlider / ValueSliderRow

Shared value-slider family: the toolkit `Slider` plus a "value above the
thumb on hover" flyout, extracted from the image_compare magnifier panel
into the shared widget layer so every value slider in the app shows the
same behavior.

Source: `src/ui/widgets/slider_hint.py`

## ValueSlider

`Slider` subclass: hovering the *thumb* (via `Slider.hoverHitTest`) shows a
`SliderHintFlyout` with the formatted value, kept live while the value
changes (e.g. dragging).

| Param | Meaning |
|---|---|
| `*args, **kwargs` | toolkit `Slider` parameters |
| `hint_formatter` | `SliderTextFormatter` for the flyout text (default: percent) |
| `hint_enabled` | flyout on/off (`set_hint_enabled()` to toggle; off → no flyout) |

The hint controller is created lazily on first show (the flyout needs a
real window).

## ValueSliderRow

`ValueSlider` + an always-visible right-hand value label: `[track] [label]`.
The hover hint flyout is disabled in favor of this persistent readout; the
fixed-width right pad (sized to the widest formatted value over the
slider's range) keeps the slider's geometry stable as the value text
changes. No left pad — the track starts flush at the row's left edge.
Pad width follows the label font through live `UiScale` changes.

| Param | Meaning |
|---|---|
| `slider: Slider` | the underlying slider |
| `hint_formatter` | value text formatter (inherits the slider's when unset) |

## Inspection

Families `ValueSlider` (state: `value`) and `ValueSliderRow` (state:
`value`, `minimum`, `maximum`).

Used by: image_compare primitives, export dialog sections, settings
interface page, font-settings flyout.
