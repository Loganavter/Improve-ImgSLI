# StartupPlaceholder

Transparent overlay shown over the image area before the first frame loads;
tracks its target widget's geometry and dismisses permanently on first
hide. A `ThemedSurface` subclass (inherits its theme-token background
behavior).

Source: `src/ui/widgets/startup_placeholder.py`

## Construction

| Param | Meaning |
|---|---|
| `parent: QWidget` | host widget |
| `target_widget: QWidget \| None` | widget whose geometry is mirrored |

`set_target(target)` / `sync_geometry()` re-anchor the overlay;
`set_background_color(color)` overrides the token background.

## Inspection

Family `StartupPlaceholder`; state: `target`.

Used by: image_compare and multi_compare page layouts.
