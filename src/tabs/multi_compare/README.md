# Multi Compare Tab

**Status: pre-alpha** — everything is rough and likely broken. Beta targeted for summer 2026.

## Idea

A dedicated workspace for comparing 3–12 images side-by-side in a synchronized grid. Use cases:

- Comparing outputs of multiple upscaling/restoration models
- Evaluating different parameter sets on the same source
- Quick visual A/B/C/D/... comparison without switching pairs

## What works (barely)

- Drag & drop images into the canvas
- Drag reordering / swapping of slots
- Manual divider resize with Redux-backed split weights
- Synchronized zoom (scroll) and pan (middle-click drag)
- Focus mode: double-click a cell to view it fullscreen, double-click again to return
- Keyboard: 1–9 to focus slots, 0 to reset zoom, Escape to exit focus
- GPU rendering via the QRhi canvas path
- Theme-aware background (follows app light/dark theme)
- Export dialog with preview, output directory/favorites, filename, format,
  resolution, aspect-ratio lock, quality, and background settings

## What doesn't work yet

- No filename labels on cells (planned as GL overlay)
- No per-cell zoom indicator
- No diff/analysis overlays
- No slot removal UI (only full clear)
- No integration with the main app's magnifier system
- No playlist/session persistence

## File structure

```
multi_compare/
    tab.py              — TabContract implementation
    controller.py       — image loading, state management
    widget.py           — composite (toolbar + GL grid + footer)
    models.py           — CompareSlot, GridLayout, MultiCompareState
    shaders/            — GLSL vertex/fragment (auto GLES/Desktop)
    ui/
        canvas_widget.py — QRhi canvas host + input adapter
        toolbar.py      — top bar (reset zoom, grid/focus, clear)
        footer.py       — bottom bar (export placeholder)
    services/           — future: export, analysis
    resources/i18n/     — translations (en, ru)
```
