# Session Picker

The Session Picker is the transient "New Tab" session browser / switcher. It
registers the `session_picker` session blueprint and owns its own tab page.

Local docs live here (`src/tabs/session_picker/docs/`) per the tab-doc
placement rule — see [docs/dev/tabs/index.md](../../../../docs/dev/tabs/index.md).

## Module layout

```text
session_picker/
    plugin.py         # @plugin("session_picker") — session blueprint (transient)
    tab.py            # TabContract implementation
    widget.py         # page wrapper
    geometry.py       # picker geometry
    prelayout.py      # pre-layout pass for the picker's cards
    host_chrome.py    # host chrome helpers
    help.py           # tab-owned Help topics
    icons.py
    recent/           # "Recent projects" shelf: panel, items_view, header_bar, use_cases/
    resources/{i18n,help,icons}/
    tests/            # runtime/ only (no contracts/)
    docs/
```

## The plugin

`SessionPickerPlugin` (`plugin.py`) is an `ISessionPlugin` that registers a
`SessionBlueprint(session_type="session_picker", title="New Tab",
metadata_defaults={"transient": True})`. Transient sessions are the picker's
way to live on the startup stack without persisting as a real workspace.

## Recent projects

The `recent/` subpackage shows recently opened projects in a shared
`ShelfWidget`-based panel (see
[docs/dev/widgets/shelf.md](../../../../docs/dev/widgets/shelf.md)).
