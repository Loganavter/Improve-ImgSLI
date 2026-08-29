# Export plugin

App-wide still/video export: the Export dialog, GPU export services,
recording/clipboard commands, and a GPU warm-up that runs after the main
window is usable. Depends on the tab-owned `video_editor` plugin for
recording services and control flows.

Source: `src/plugins/export/`. Plugin system: [PLUGINS.md](../PLUGINS.md).

## Wiring

`@plugin(name="export", startup_tier="deferred", startup_order=10)` (loads
after `video_editor`, order 0). Implements `IControllablePlugin` +
`IServicePlugin`.

- `initialize(context)` captures `store`, `thread_pool`, `event_bus`,
  `plugin_coordinator`; resolves the `video_editor` plugin.
- `configure_controller(...)` builds the recording services (via
  `video_editor_plugin.create_recording_services`), the clipboard paste
  service (tab-provided, fallback to bootstrap default), and
  `ExportController`. It schedules a GPU warm-up (`QTimer.singleShot(3000)`)
  and subscribes session-activated + export EventBus events.
- `get_service()` → the recorder; `get_controller()` → `ExportController`.
  No plugin QSS: the dialog surface is painted from the `dialog.background`
  token in `ThemedDialog.paintEvent`.

## Key modules

| Module | Role |
|---|---|
| `controller.py` | `ExportController` — toggle/pause recording, open video editor, video export, clipboard paste; owns `recording_flow` + `video_export_flow` from the video-editor plugin |
| `dialog.py` | `ExportDialog(ThemedDialog)` — preview, output dir/favorites, format/resolution/quality/background, Find Action contribution, language sync |
| `dialog_sections.py` | section builders: preview pane, output path, format row, resolution, quality, PNG options, background, metadata, action bar |
| `models.py` | `ExportDialogState` dataclass |
| `events.py` | frozen events: `ExportToggleRecordingEvent`, `ExportTogglePauseRecordingEvent`, `ExportOpenVideoEditorEvent`, `ExportPasteImageFromClipboardEvent` |
| `services/gpu_export.py` | `GpuExportService` |
| `services/gpu_export_proxy.py` | `GpuExportProxy` — offscreen GPU export proxy |
| `services/gpu_export_layout.py` | `compute_export_stroke_scales` |
| `actions.py` | Find Action contribution / withdrawal for the export dialog |
| `search.py`, `layout_geometry.py` | dialog search + geometry |

## Events (EventBus)

The plugin subscribes to these and forwards to `ExportController`:

- `ExportToggleRecordingEvent`
- `ExportTogglePauseRecordingEvent`
- `ExportOpenVideoEditorEvent`
- `ExportPasteImageFromClipboardEvent`

It also reacts to `WorkspaceSessionActivatedEvent` to re-run GPU warm-up when
a canvas-providing tab becomes active.

## Command surface

`handle_command` dispatches any `ExportController` method by name, e.g.
`toggle_recording`, `open_video_editor`, `paste_image_from_clipboard`.
`get_service()` returns the recorder so other code can drive recording.

## Rendering parity note

Live canvas, export preview, and final export must stay visually consistent.
The export path reuses the same canvas-px composition semantics as live
rendering (see [rendering/index.md](../rendering/index.md)). When changing
visual output, inspect all three paths together.
