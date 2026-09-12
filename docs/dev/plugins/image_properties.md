# Image Properties plugin

App-wide image metadata dialog: shows file/source info, image dimensions,
mode, and metadata rows for a given image or path, plus any app-specific rows
the caller passes in.

Source: `src/plugins/image_properties/`. Plugin system:
[PLUGINS.md](../PLUGINS.md).

## Wiring

`@plugin(name="image_properties", startup_tier="deferred")`. Implements
`IControllablePlugin` (self-controller).

- `initialize(context)` — no heavy setup (dialog built on demand).
- `get_controller()` returns the plugin itself; `handle_command` dispatches
  `open_dialog` and other commands.
- `open_dialog(parent=..., path=..., display_name=..., image=...,
  app_rows=..., language=..., tr_func=..., probe_image=...)` builds properties
  via `service.build_image_properties` and runs a modal `ImagePropertiesDialog`.

## Key modules

| Module | Role |
|---|---|
| `service.py` | `build_image_properties` — assembles `ImageProperties` from path/image/app rows; `_read_source_info`, `_file_rows`, `_image_rows`, `_metadata_rows`, `_image_dimensions`, `_image_mode` |
| `dialog.py` | `ImagePropertiesDialog(ThemedDialog)` — renders the property list, language-aware, `HelpDocumentView`-style presentation |
| `render.py` | property rendering helpers |
| `layout_geometry.py` | dialog geometry |

## Usage

Tabs (e.g. image_compare, multi_compare) and the host call
`plugin_coordinator.execute_command("image_properties", "open_dialog", ...)`
to show properties for a selected image. App rows let the caller inject
tab-specific metadata rows beyond the generic file/image rows.
