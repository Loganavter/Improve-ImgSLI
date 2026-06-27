# Multi Compare

Multi Compare is the multi-image comparison workspace. It is built as a tab
module, not as a branch of the main image-compare canvas.

## Current status

Status: active feature work.

What works:

- Drag and drop images into the canvas.
- Add images through the toolbar.
- Drag a slot over another slot or split gap to rearrange the layout.
- Manual divider resize with Redux-backed split weights.
- Synchronized zoom and pan for the scene.
- Focus mode: double-click a cell to view it fullscreen, double-click again or
  press Escape to return.
- Keyboard shortcuts: `1`-`9` focus slots, `0` resets zoom, Escape exits focus.
- QRhi rendering through the tab-owned canvas path.
- Theme-aware clear/background color.
- Always-on split dividers in the overlay pass.
- Camera-fixed filename labels with tab-local label settings.
- Export dialog with preview, output directory/favorites, filename, format,
  resolution, aspect-ratio lock, quality, and background settings.
- Offscreen GPU export routed through the same canvas-px composition semantics
  as live rendering.

Known gaps:

- No diff/analysis overlays yet.
- No integration with the main app magnifier system yet.
- No playlist/project persistence yet.
- Per-session state is still kept in `MultiCompareTab._session_states`; it
  should move to workspace `state_slots`.
- Export above QRhi/GPU texture limits is not tiled yet.

## Module layout

```text
multi_compare/
    tab.py               # TabContract implementation and session snapshots
    controller.py        # image loading, save/export orchestration
    widget.py            # toolbar + QRhi canvas + footer composition
    models.py            # slots, layout tree, MultiCompareState
    context_menu.py      # tab-owned context menu provider
    docs/                # local architecture and backlog docs
    plugins/export/      # export dialog state and UI
    resources/i18n/      # tab-owned translations
    scene/               # local Redux store and QRhi render passes
    services/            # composition builder and export helpers
    shaders/             # QRhi shaders and compiled qsb files
    ui/                  # canvas widget, toolbar, footer, labels, geometry
```

## Ownership rules

- UI-visible text lives in `resources/i18n/<lang>/multi_compare.json`.
- Canvas state lives in `MultiCompareStore` and is replaced via reducer output.
- Scene layout is represented by `LeafNode` / `SplitNode`; render layout is a
  `CompositionPlan`.
- Rendering code must keep canvas-px and framebuffer/sr-px separate. See
  [ARCHITECTURE.md](ARCHITECTURE.md).
