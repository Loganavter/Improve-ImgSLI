# Help plugin

In-app hierarchical illustrated manual: a hub/tree dialog over scanned
help topics, with tab-contributed hubs, anchors, generated in-page TOC,
search, and language switching.

Source: `src/plugins/help/`. Authoring/content rules live in
[HELP_SYSTEM.md](../HELP_SYSTEM.md).

## Wiring

`@plugin(name="help", startup_tier="deferred")`. Implements
`IControllablePlugin` (self-controller).

- `initialize(context)` stores `store` + `event_bus`; subscribes
  `SettingsChangeLanguageEvent` to update an open dialog's language.
- `get_controller()` returns the plugin itself; `handle_command` dispatches
  commands like `show_dialog`. No plugin QSS: the dialog surface is painted
  from the `dialog.background` token in `ThemedDialog.paintEvent`.
- `show_dialog(parent=..., language=..., page=..., anchor=...)` opens the
  modeless `HelpDialog` — deliberately never Qt-parented to the main window
  (a transient-for link would make the WM raise the whole main-window group
  and bury independent top-levels like Video Editor / Export); `parent` is a
  geometry hint only.

## Key modules

| Module | Role |
|---|---|
| `dialog.py` | `HelpDialog` — hub/page rendering, language sync, navigation |
| `tree.py` | `HelpTree` / `HelpNode` — scanned topic tree (hubs + pages), path resolution, body/asset resolution, `install_help_contributions`, `build_help_tree` |
| `scan.py` | Filesystem discovery (dirs = hubs, `*.md` = pages) + hub-meta overlay |
| `contribution.py` | `HelpHubContribution` (tab-owned hub presentation, frozen, `owner_tab` + `mount`) |
| `navigator.py` | `HelpNavigator` — page navigation |
| `hub_page.py`, `back_bar.py`, `labels.py`, `layout_geometry.py`, `icons.py`, `text_context_menu.py` | hub rendering, chrome, label handling, icon lookup, text context menu |

## Tree scan contract

Tabs publish hub presentation via `create_service("contribute_help") →
HelpHubContribution`; structure itself is scanned from the filesystem.
The host owns the four shell hubs (root / workspace / ui / platform).
See [HELP_SYSTEM.md](../HELP_SYSTEM.md#tree-scan-contract-web-canon).

## Content

Host topics: `src/resources/help/` (`about`,
`platform/file_project.md`, `platform/hotkeys.md`, `ui/*.md`). Plugin topics:
`src/plugins/<plugin>/resources/help/` (`workspace.export`,
`platform.settings`, `platform.image_properties`,
`platform.getting_started`). Tab topics: `src/tabs/<tab>/resources/help/`.
Keep headings stable — anchors and generated in-page TOC depend on them (see
[HELP_SYSTEM.md](../HELP_SYSTEM.md)).
