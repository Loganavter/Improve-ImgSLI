# FontSettingsFlyout

Text/font-settings panel for canvas text overlays (filename labels): font
size / weight / opacity sliders, foreground and background `ColorSwatch`es,
a draw-background `Switch`, and placement radios. A pinned `BaseFlyout`
(`flyout_group = "font_settings"`).

Source: `src/ui/widgets/font_settings_flyout.py`

## Construction

| Param | Meaning |
|---|---|
| `parent: QWidget` | flyout host |

`set_values(size, weight, opacity, fg, bg, draw_bg, placement)` applies the
full state with signal blockers; `settings_changed` fires on any edit.
Signals: `settings_changed`, `closed`, `interaction_started`,
`interaction_finished`. Find Action chrome is tagged via
`font_settings_search` (`ui.actions.search_index`).

## Inspection

Family `FontSettingsFlyout`; state: `font_size`, `font_weight`, `opacity`,
`draw_background`, `placement`, `foreground`, `background`.

Used by: multi_compare widget and the main-window presenter (labels
toolbar).
