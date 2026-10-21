# SettingsDialog

The Settings dialog shell: `SidebarDialogShell` with always-visible
per-tab sections, in-window search over the Find Action catalog, and the
plugin-registered settings pages.

Source: `src/plugins/settings/dialog.py`

## Behavior highlights

- **Per-tab sections are ambient** — sections register through
  `SettingsRegistry` and are visible from any session context (see the
  internal plan `plan_settings_tabs_and_search.md`; `docs/dev/TODO.md` has no
  open "Settings window" entry).
- **In-window search** reuses the Find Action `SearchIndex`/`ActionRegistry`
  catalog (`dialog_search.py`), debounced, Esc clears, re-runs on language
  change.
- Geometry is owned by `src/plugins/settings/layout_geometry.py`
  (`compute_settings_dialog_size`); `shared_toolkit/ui/layout_sizing.py`
  supplies the helpers it imports (`apply_dialog_geometry`, `clamp`,
  `clamp_to_screen`, `measure_scroll_pages_stack`, `GeometryApplyPolicy`).

## Inspection

Family `SettingsDialog`; state: `current_section` (sidebar row).

See also: `docs/dev/UI_TOOLKIT_LIBRARY.md` (dialog geometry),
`docs/dev/ACTIONS.md` (Find Action chrome).
