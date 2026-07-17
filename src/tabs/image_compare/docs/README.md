# Image Compare

Image Compare is the primary two-image comparison workspace. It is now a
tab-owned domain under `src/tabs/image_compare/`, not a collection of generic
app plugins and shared UI modules.

## Current Ownership

The tab owns:

| Area | Path |
|---|---|
| Tab contract and page assembly | `tab.py`, `widget.py` |
| Session loading and playlist operations | `_session_controller.py`, `services/playlist*`, `use_cases/` |
| Two-image canvas widget and QRhi renderer | `canvas/` |
| Canvas features | `canvas/features/<name>/` |
| Canvas input routing | `events/` |
| Image-compare presenters | `presenters/` |
| Export and snapshots for this tab | `services/image_export/`, `services/gpu_export_scene.py`, `services/snapshot_render_plan_builder.py`, `services/video_snapshot_rendering/` |
| Analysis/diff/metrics | `services/analysis/` |
| Video recording/editor integration | `video_editor/` |
| Tab-specific state reducers/models | `state/` |
| Tab-specific settings UI | `ui/settings_*.py` |

App-level `plugins/` modules can still expose commands, dialogs, or lifecycle
hooks, but image-compare behavior should live here unless it is genuinely
shared by multiple tabs.

## Local Docs

- [ARCHITECTURE.md](ARCHITECTURE.md) - current tab architecture and boundaries.

## Rules

- Keep canvas-feature details in this package. Generic host docs should link
  here instead of naming `divider`, `magnifier`, or other image-compare
  features directly.
- Keep export/live/video snapshot parity inside this tab's services. Shared
  rendering modules may define contracts, but they should not import
  `tabs.image_compare`.
- Keep video editor and analysis code in this tab unless the code is extracted
  into a real multi-tab/shared contract.
