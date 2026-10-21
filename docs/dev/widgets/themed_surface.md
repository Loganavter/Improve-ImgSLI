# ThemedSurface / ThemedBackgroundContainer

`ThemedWidget` + `QWidget` that paints a live theme-token background in
`paintEvent` instead of relying on Qt's `setPalette`/`autoFillBackground` path
— the theme subscription and refresh are inherited from `ThemedWidget`
(`on_theme_changed`), the class itself only implements the fill. See
`docs/dev/KNOWN_BUGS.md` in `improve-imgsli-internal-docs` (private) and
`docs/dev/THEMING.md`.

Source: `src/ui/widgets/themed_surface.py`

## Construction

| Param | Meaning |
|---|---|
| `color_token` | theme token to resolve; `ThemedSurface` defaults to `label.image.background`, `ThemedBackgroundContainer` to `surface.background` |
| `opaque: bool = True` | set `WA_OpaquePaintEvent` (the container is non-opaque — chrome bars) |

`apply_qrhi_theme_background(widget, theme_manager, color_token=...)` pushes
the token color into a QRhi canvas widget's palette (used by the image
area backgrounds).

## Inspection

Families `ThemedSurface` and `ThemedBackgroundContainer`; state:
`color_token`. `StartupPlaceholder` subclasses `ThemedSurface`.

Used by: main-window startup cover, image_compare chrome bars
(`edit_layout_widget` etc. in `tabs/image_compare/ui/layout.py`), startup
placeholder.
