# RecentColorsRow

Recent-colors shelf inside the color picker: shared `ShelfWidget` chrome
(caption in the header) + large card-style swatch chips in the content well.
Chips are custom-painted because alpha < 255 colors must sit on a
checkerboard, which the toolkit `Button` painter pipeline cannot do.

Source: `src/ui/widgets/color/recents.py`

## Construction

| Param | Meaning |
|---|---|
| `caption: str = ""` | shelf header text |
| `parent` | shelf parent |

`set_colors(hex_codes)` rebuilds the chips (capped at `RECENT_COLORS_CAP`);
`recentPicked(QColor)` fires when a chip is clicked (applies without
accepting the dialog). The whole shelf hides while empty. Chips wrap onto
extra rows via manual layout in `resizeEvent`.

## Inspection

Family `RecentColorsRow`; state: `chip_count`, `caption`.

Persistence: `RecentColorsStore` (QSettings-backed `#RRGGBBAA` list) in the
same module; `parse_hex_color` / `color_to_hex_string` are the canonical
hex round-trip helpers (Qt's 8-digit parse is `#AARRGGBB`, not this
module's `#RRGGBBAA`).
