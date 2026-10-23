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
- Focus mode: click a cell to fill the split view with it; click again or
  press Escape to return. Double-clicking a divider resets its split
  weights to equal.
- Canvas keys: arrows pan, `+`/`-` zoom, `0` resets the view, Escape exits
  focus (while a cell is focused).
- QRhi rendering through the tab-owned canvas path.
- Theme-aware clear/background color.
- Always-on split dividers as GPU quads (`GridDividersPass`).
- Camera-fixed filename labels with tab-local label settings, including a
  `Show text` master switch in the text flyout (live and export together).
- Export dialog with preview, output directory/favorites, filename, format,
  resolution, aspect-ratio lock, quality, and background settings.
- Offscreen GPU export routed through the same canvas-px composition semantics
  as live rendering.

Known gaps:

- No diff/analysis overlays yet.
- No integration with the main app magnifier system yet.
- Export above QRhi/GPU texture limits is not tiled yet.

## Module layout

```text
multi_compare/
    plugin.py            # @plugin("multi_compare") — session blueprint + slot
    tab.py               # TabContract implementation, SessionState chrome, session snapshots
    controller.py        # image loading, save/export orchestration
    widget.py            # toolbar + QRhi canvas + footer composition
    models.py            # slots, layout tree, MultiCompareState
    actions.py           # action catalog + keymap defaults
    bootstrap_reducers.py  # registers the multi_compare slot reducer
    context_menu.py      # tab-owned context menu provider
    help.py              # tab-owned Help topics
    docs/                # local architecture and backlog docs
    resources/i18n/      # tab-owned translations (multi_compare.json + tooltips.json)
    canvas/              # canvas widget integration + features/{grid_dividers,focus_dim,
                         # layer_labels,drag_drop_overlay}
    pipeline/cache.py    # composition/texture cache (load-bearing)
    scene/               # local Redux store and QRhi render passes
    services/            # composition builder, image export, save flow
    shaders/             # QRhi shaders and compiled qsb files
    ui/                  # canvas widget, toolbar, footer, labels, geometry, chrome
    use_cases/           # loading, crop, placement, export, persistence, preview decode
```

Export has no `plugins/` subpackage: the dialog is the host service
`context.call_service("open_image_export_dialog")` and the flow lives in
`use_cases/export.py` + `services/image_export.py`.

## Local Docs

- [ARCHITECTURE.md](ARCHITECTURE.md) - current tab architecture and boundaries.
- [plugins/multi_compare.md](plugins/multi_compare.md) - the tab's `@plugin`
  (session blueprint + state slot).
- **investigations** (private, `improve-imgsli-internal-docs` repo, this
  same path `src/tabs/multi_compare/docs/investigations/`) — long-form case
  write-ups for rendering bugs confined to this tab (transient zoom nudge,
  mip-cascade). Cross-tab investigations live at
  `docs/dev/rendering/investigations/` in that same private repo.

## Ownership rules

- UI-visible text lives in `resources/i18n/<lang>/multi_compare.json`.
- Canvas state lives in `MultiCompareStore` and is replaced via reducer output.
- Scene layout is represented by `LeafNode` / `SplitNode`; render layout is a
  `CompositionPlan`.
- Rendering code must keep canvas-px and framebuffer/sr-px separate. See
  [ARCHITECTURE.md](ARCHITECTURE.md).