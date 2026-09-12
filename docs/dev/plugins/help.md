# Help plugin

In-app hierarchical illustrated manual: a hub/tree dialog over `tree.json`
help topics, with tab-contributed subtrees, anchors, generated in-page TOC,
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
| `tree.py` | `HelpTree` / `HelpNode` — topic tree (hubs + pages), aliases, body/asset resolution, `load_help_tree`, `merge_help_contributions`, `build_help_tree` |
| `contribution.py` | `HelpContributionRegistry` / `HelpSubtreeContribution` — tab → host help fragments merged into the host tree |
| `navigator.py` | `HelpNavigator` — page navigation |
| `hub_page.py`, `back_bar.py`, `labels.py`, `interpolate.py`, `layout_geometry.py`, `icons.py`, `text_context_menu.py` | hub rendering, chrome, label handling, icon lookup, text context menu |

## Tree merge contract

Tabs publish topic subtrees via the `contribute_help` notify hook; the host
owns the shell tree (root / workspace / ui / platform). See
[HELP_SYSTEM.md](../HELP_SYSTEM.md#tree-merge-contract) and
`tree.merge_help_contributions`.

## Content

Host topics: `src/resources/help/` (`tree.json` + `en|ru/ui|platform/`).
Tab topics: `src/tabs/<tab>/resources/help/`. Keep headings stable — anchors
and generated in-page TOC depend on them (see [HELP_SYSTEM.md](../HELP_SYSTEM.md)).
