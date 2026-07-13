# Canvas & Rendering Documentation

How canvas features and the QRhi renderer are organized, and the contracts
that keep them consistent across the live editor, preview, and export paths.

## Contents

- **[overview.md](overview.md)** — Quick Start, layer split (`canvas_infra` / features / presentation / renderer), examples, doc status
- **[package-structure.md](package-structure.md)** — feature package layout, auto-discovery, splitting a feature into subpackages, current feature status
- **[feature-decomposition-playbook.md](feature-decomposition-playbook.md)** — step-by-step procedure for splitting an overgrown feature into the subpackage taxonomy (the `magnifier/` refactor, generalized)
- **[render-pass-contract.md](render-pass-contract.md)** — `CanvasRenderPass` lifecycle, stack roles, scene visibility, alpha/blending rules
- **[rendering-model.md](rendering-model.md)** — live authoring path vs. snapshot replay path, snapshot renderer notes
- **[coordinate-systems.md](coordinate-systems.md)** — normalized base-image space, canvas-px overlay model, base-image-anchored geometry, the single-resolver rule
- **[contracts.md](contracts.md)** — `CanvasWidgetFeature`, `CanvasSceneFeature`, `CanvasFeatureProperty`, command aliases, canvas layout contract, scene pipeline, keyframing, source-of-truth rules
- **[zoom-pan.md](zoom-pan.md)** — gesture bindings, viewport change contract, zoom/pan invariants, semantic geometry vs paint extents, debugging
- **[checklist.md](checklist.md)** — anti-patterns and the pre-merge checklist
- **[display-image-pipeline.md](display-image-pipeline.md)** — unify → display-cache → render pipeline; single-writer/single-picker rule for `render_cache.display_cache_image1/2`
- **[tile-rendering-system.md](tile-rendering-system.md)** — GPU tile grid for oversized sources (`TileTextureService`), apron padding, residency/draw-plan invariant, and host-side memory bounding (`_texture_upload_cache` LRU, `LazyPixelSource`)
- **[investigations/divider-blank-white-and-drag-desync.md](investigations/divider-blank-white-and-drag-desync.md)** — divider-vs-image sync: the `blank_white`/`requires_content` load-flash fix, and why the drag-time "ghosting" is likely compositor tearing, not app code

**Core idea**: a feature doesn't handle zoom, pan, coordinate transforms, raw
Qt events, or serialization — the infrastructure does. See
[Feature Isolation Model](../CONTRACTS.md#feature-isolation-model-the-abstraction).
