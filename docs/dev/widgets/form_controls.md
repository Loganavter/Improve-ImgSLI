# Form controls (DialogActionBar, OutputPathSection)

Two cross-dialog building blocks used by Settings, Export, and the Video
Editor dialogs. App-side generic (no app imports) but kept out of the
toolkit because the exact composition is a product choice.

Source: `src/ui/widgets/form_controls.py`

## DialogActionBar

OK/Cancel bar with scale-aware minimum sizes; stretch above so a height
squeeze collapses the stretch, never the buttons.

| Param | Meaning |
|---|---|
| `primary_text` / `secondary_text` | OK / Cancel labels |
| `primary_min_size` / `secondary_min_size` | design-px button minimums |

## OutputPathSection

Directory + browse + favorites + filename export section.

| Param | Meaning |
|---|---|
| `directory_label_text` / `browse_text` / `set_favorite_text` / `use_favorite_text` / `filename_label_text` | localized labels |
| `on_browse` / `on_set_favorite` / `on_use_favorite` | callbacks |
| `use_custom_line_edit` / `filename_editor_factory` | filename input (toolkit `CustomLineEdit` by default) |
| `button_min_size` / `button_fixed_height` | button geometry overrides |

Exposes `edit_dir`, `filename_edit`, `btn_browse_dir`,
`btn_set_favorite`, `btn_use_favorite` for dialog wiring.

## Inspection

Families `DialogActionBar` and `OutputPathSection`; state (section):
`directory`, `filename`. Config auto-derives.
