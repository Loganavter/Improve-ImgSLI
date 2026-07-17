# Action catalog (Find Action)

Host-owned discovery surface for the command palette.

Related: [TODO.md](./TODO.md) (P2 Action palette),
[tabs/capability-mechanisms.md](./tabs/capability-mechanisms.md).

## Ownership

| Piece | Location |
|-------|----------|
| Types (`ActionDescriptor`, `ActionTarget`) | `src/core/actions/` (no Qt UI) |
| Registry | `src/ui/actions/registry.py` — `get_action_registry()` |
| Chrome index (`SearchGroup` / `SearchIndex`) | `src/ui/actions/search_index.py` |
| Dialog bridge (temporary contribute) | `src/ui/actions/dialog_contribute.py` |
| Flyout bridge (lazy ensure_visible) | `src/ui/actions/flyout_contribute.py` |
| Platform contributions | `src/ui/actions/platform.py` via `MainWindowMenuController` |
| Tab chrome contributions | active tab `create_service("contribute_actions", registry)` → tab `actions.py` |
| Settings bridge | `plugins/settings/actions.py` (expands `SearchIndex`; pages tag via `plugins/settings/search` re-export) |
| Palette package | `src/ui/actions/palette/` — `row.py`, `dialog.py`, `__init__.py` (show/shortcuts) |
| Keymap resolve | `src/ui/actions/keymap.py` — defaults + `SettingsState.keyboard_overrides` |
| Shortcut binder | `src/ui/actions/binder.py` — `ActionShortcutBinder` / `resync_action_shortcuts` |
| Host service | `TabContext.services["show_command_palette"]` |

Do **not** put the catalog in `plugins/help/` — help opens *from* actions.
Do **not** add catalog hooks on `TabContract` — use capability mechanisms:
tab chrome actions via active-tab `create_service("contribute_actions", …)`;
settings pages via broadcast `notify_all("contribute_settings", …)`;
keyboard defaults listing via `notify_all("contribute_keymap_defaults", …)`.

## Shortcuts (keymap)

`ActionDescriptor.shortcut` is the **default** chord (PortableText).

Effective binding:

- key missing in `store.settings.keyboard_overrides` → use default;
- key present with `""` → unbound;
- key present with a sequence → that sequence (normalized).

`ActionShortcutBinder` installs `QShortcut`s on the main window for runnable
actions in `registry.list_for(active_tab=…)`. **First chord wins**; later
conflicts are skipped and logged. Resync after platform register, tab
`contribute_actions`, and Settings apply.

Settings page `builtin.keyboard` (`plugins/settings/pages/keyboard.py`) edits
sparse overrides only. Listing all tabs uses metadata via
`contribute_keymap_defaults` (no live widgets).

Hard-coded and **out of keymap**: WASD / Space / overlay movement in
`GlobalKeyboardHandler` and canvas keyboard. Video-editor dialog-local
shortcuts (Space / Ctrl+Z / …) stay local on the dialog; their Find Action
rows may list the same chords as hints only.

`Ctrl+V` / `Ctrl+S` / `Ctrl+Shift+S` are catalog actions
(`platform.paste_clipboard_image`, tab `*.quick_save` / `*.save`).

## Descriptor shape

```python
ActionTarget(widget=live_widget)   # explicit ref; no getattr(widget, "btn_x")
ActionTarget(widget=menu_trigger, menu_action_id="file.settings")  # open menu + pulse row
ActionTarget(
    ensure_visible=open_session_picker,
    resolve_widget=lambda: picker.card_for("image_compare"),
)  # bring page on screen, then pulse
ActionTarget(
    ensure_visible=lambda: show_settings_section("builtin.general"),
    resolve_widget=lambda: dialog.sidebar_row_widget_for("builtin.general"),
)  # open Settings page, then pulse sidebar row
ActionDescriptor(
    action_id="image_compare.magnifier.enabled",
    label_key="image_compare.action.magnifier",  # tab i18n namespace
    description_key=...,
    breadcrumb=("image_compare.action.breadcrumb.toolbar", "..."),
    owner_tab="image_compare" | None,  # None = platform / always visible
    topic="magnifier",
    shortcut="Ctrl+Shift+P",
    help_page="magnifier",
    help_anchor=None,
    run=callable,
    target=ActionTarget | None,
)
```

Platform Settings / Help / Quit / Find Action targets point at the title-bar
File/Help triggers with the matching `menu_action_id`. Plate click / Shift+Enter
closes the palette, opens that dropdown, and pulses the menu row
(`ui.actions.reveal.reveal_action_target`).

Settings **page** actions (`settings.page.*`, mirrored from `SettingsRegistry`):
- `run` / reveal `ensure_visible` → `show_settings_dialog(section_id=…)`
- `resolve_widget` → `SettingsDialog.sidebar_row_widget_for(section_id)` (sidebar
  row button pulse). Host wires resolve via `MainWindowMenuController`.
- `platform.settings` stays on the File-menu row; pages enter the dialog.
- Declare chrome once as `SearchGroup` / `SearchIndex`
  (`plugins/settings/search.py` re-exports host `ui.actions.search_index`;
  or import the host module directly). Reuse the same group in `build()`.
- `plugins/settings/actions.contribute_settings_actions` is the only
  Settings → Find Action bridge. It expands the index into three tiers, all
  **always listed** in the empty palette (browsable, not search-only):
  - thin `settings.page.<section_id>` jump rows (sidebar page title only);
  - `settings.group.<section_id>.<title_key>` fieldset slots, matched only
    by their own title;
  - `settings.group.<section_id>.<title_key>.<member_key>` — one row per
    control inside the fieldset. A query hits the control by its own name
    («Vulkan», «Светлая») with the fieldset in the breadcrumb, instead of
    surfacing the generic group row for e.g. `vulkan` or «тема».
    Enter **applies** the control via a hidden Settings dialog
    (`apply_settings_member`) without showing the window; Shift+Enter /
    plate reveal still opens Settings and pulses the chrome.
  Each row gets an explicit `ActionDescriptor.sort_key` (`(section.order,
  tier, group_order, ...)`) so the empty palette lays pages → groups →
  members out directly, without the palette parsing the hierarchy back out
  of the action id.
  Page builders tag controls with `SearchGroup.tag_member` /
  `tag_combo` + `note_combo_option` (Qt props `action_search_*`);
  `SettingsDialog.member_widget_for` resolves them for reveal. Group rows
  pulse the fieldset; member rows pulse the tagged control (combo options
  also open the dropdown via ``schedule_combo_dropdown`` / ``showDropdown(focus_index=…)``
  and pulse the dropdown row (``dropdown_row_widget``), without committing
  ``setCurrentIndex`` on the closed field.
  Do not hand-register Settings chrome or parallel `search_keys` lists in
  `ui/actions/platform.py`.
- Haystack resolves every `search_key` in **all** UI languages (`en` / `ru` /
  `zh` / `pt_BR`), and folds `ё`→`е` before comparing so «тёмная»/«темная»
  match the same slot. New Settings chrome must go through `SearchGroup` +
  i18n — bare string literals are invisible to Find Action.
  This per-language expansion is independent of the *active* UI language, so
  `ui/actions/registry.py` caches it per action id (`_HAYSTACK_CACHE`,
  invalidated on `register`/`unregister`) instead of recomputing it on every
  keystroke.

Workspace actions:
- `workspace.open_session_picker` → pulse the workspace-tabs **Add** button;
  run/reveal activate an existing Session Picker when present (no duplicate tab)
- `workspace.new_image_compare` / `new_multi_compare` → ensure Session Picker
  visible (reuse existing), then pulse the matching create-card

Platform / palette strings stay in host `src/resources/i18n/*/ui/actions.json`.
Tab chrome strings live under `tabs/<tab>/resources/i18n/`.

## Filtering

`ActionRegistry.list_for(active_tab=..., query=..., topic=...)`:

- includes platform actions (`owner_tab is None`);
- includes tab actions only when `owner_tab == active_tab`;
- skips actions whose live `target.widget` is currently `isHidden()` (UI-mode
  toolbar slots that are off the active layout) — lazy targets with
  `ensure_visible` / `resolve_widget` stay listed;
- optional word filter on id / keys / translated label & description /
  breadcrumb / topic (every whitespace-separated token must match);
- ranks each action once per call and reuses that rank for both the filter
  and the sort (no second pass through `_best_match_rank`);
- empty-query ordering: `platform.settings` first, then any action with a
  non-empty `sort_key` in that order, then remaining platform actions, then
  tab actions — see `_empty_list_sort_key`.

`FindActionDialog` debounces `_reload()` (`_RELOAD_DEBOUNCE_MS`, palette
`dialog.py`) so a burst of keystrokes rebuilds the row widgets once, not
once per character — rebuilding is the expensive part (each row is a themed
`Button` with painter layers), not the text filter itself. Keyboard-shortcut
overrides are resolved once per rebuild (`current_keyboard_overrides` in
`palette/common.py`) and passed into every row instead of each row walking
`QApplication.topLevelWidgets()` on its own.

## Registration sites

1. **Platform** — once when the title bar menus are built
   (`register_platform_actions` + `register_settings_page_actions`).
2. **Active tab** — `create_service("contribute_actions", registry)`:
   - on tab `on_activated` (tab-private `_register_actions`);
   - after host toolbar `connect_signals` via generic refresh in
     `ui/presenters/main_window/connections.py` (no tab import / no tab name).
3. **Open dialogs** — temporary chrome while a dialog is alive:
   - Declare a dialog `SearchIndex` (e.g. `video_editor/search.py`,
     `export/search.py`), tag widgets at build time, then call
     `ui.actions.dialog_contribute.contribute_dialog_search_actions`.
   - Video Editor: `tabs/image_compare/plugins/video_editor/actions.py`
     (`image_compare.video_editor.*`). Register in dialog `__init__` and again
     on reuse / `showEvent`. Withdraw via `unregister_prefix` on `closeEvent` /
     `destroyed`. Local `Ctrl+Shift+P` via `install_dialog_find_action_shortcut`.
     Ids look like `…group.<title_key>.<member_key>` (preview quality combo
     options included). `run` clicks / toggles / selects — not Settings-style
     navigate-only. Combo-option rows select the index and open the dropdown
     via `schedule_combo_dropdown` (retries until settled); reveal uses the
     same prep via `ensure_visible`. Palette `run` is deferred after `accept()`
     so modal Hide/Close does not collapse toolkit overlays. After
     `ensure_visible`, reveal waits ~200ms before resolve/pulse so a cold
     Settings open can finish activation/geometry first.
   - Export: `plugins/export/actions.py`
     (`image_compare.export_dialog.*`), same helper; register on construct /
     `showEvent`, withdraw on `finished`.
   - Use `ActionRegistry.unregister_prefix` — never
     `unregister_owner("image_compare")` for dialog teardown (that would
     wipe toolbar actions). Dialog-local shortcuts stay on the dialog
     window; the main-window binder does not see modal/non-modal dialog
     focus (`WindowShortcut`).
   - Do **not** put dialog chrome into `SettingsRegistry` — different lifecycle.

4. **Toolbar flyouts** — closed-by-default panels (e.g. label text settings):
   - Declare a flyout `SearchIndex` (`ui/widgets/font_settings_search.py`),
     tag controls in the flyout constructor (`FontSettingsFlyout`).
   - Expand via `ui.actions.flyout_contribute.contribute_flyout_search_actions`
     from the tab’s `register_*_actions` (same pass as toolbar buttons).
   - Use **lazy** `ActionTarget(ensure_visible=show_flyout, resolve_widget=…)`
     — plain `widget=` refs are filtered out while the flyout is hidden
     (`_action_chrome_is_available`).
   - `show_flyout` must **open**, not toggle-close (IC:
     `ui_manager.show_font_settings_flyout`; MC:
     `MultiCompareWidget.show_font_settings_flyout`).
   - IC: `FontSettingsController.show` turns on filename labels / the bottom
     edit row when `btn_text_settings` is hidden, then anchors to a visible
     `btn_text_settings` or `btn_file_names` (avoids flyouts at a stale
     hidden-button geometry).
   - Pulse (`ui.actions.widget_pulse`): one overlay for all widgets; when the
     target is inside a flyout the overlay is parented to that flyout so the
     ring paints above sliders. Thin targets are padded.
   - Ids: `image_compare.font_settings.group.<title>.<member_key>` /
     `multi_compare.font_settings.…` (MC omits placement radios).
   - Enter runs meaningful controls (switch / radio); sliders / swatches
     open the flyout and pulse on reveal.

Host code under `ui/presenters/` and `ui/main_window/` must not import
`tabs.*.actions` (enforced by `tests/contracts/test_host_actions_isolation.py`).

## Find Action entry points

- Help menu → Find Action
- `Ctrl+Shift+P` on the main window (`install_find_action_shortcut`)
- `Ctrl+Shift+P` on Video Editor / Export dialogs
  (`install_dialog_find_action_shortcut`)
- `context.call_service("show_command_palette", query=..., topic=...)`

Opening the palette always calls `refresh_open_dialog_find_actions()` so any
visible Video Editor / Export window re-contributes its temporary chrome
(even when the shortcut was pressed on the main window).

Palette: ↑↓ / Enter or ↵ icon run / Esc / click plate or Shift+Enter reveal /
Ctrl+Enter or the «Подробнее» / Learn more region on the row. F1 opens with topic/preselect and
`auto_pulse` when focus matches a target.

Learn more / `help_page` open the hierarchical Help dialog. Short topic ids
(`magnifier`, `export`, `hotkeys`, …) resolve through `resources/help/tree.json`
aliases — see [HELP_SYSTEM.md](./HELP_SYSTEM.md).

## Later

- Video links / `video_url`.
- F1 → topic page directly (without requiring the palette).

## Contract tests

`tests/contracts/test_action_registry.py` — ids, filtering, `create_service`
contribute path, help_page tagging, `unregister_prefix`.
`tests/contracts/test_host_actions_isolation.py` — no host import of tab actions.
`tests/plugins/test_dialog_find_actions.py` — video/export dialog contribution
lifecycle + dialog Find Action shortcut.
`tests/plugins/test_font_settings_flyout_find_actions.py` — text flyout tags,
listed while hidden, run toggles switch.
