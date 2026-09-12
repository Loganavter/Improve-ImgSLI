# Canvas & Rendering Documentation

How canvas features and the QRhi renderer are organized, and the contracts
that keep them consistent across the live editor, preview, and export paths.

## Contents

- **[overview.md](overview.md)** — Quick Start, layer split (`canvas_infra` / features / presentation / renderer), examples, doc status (eager unified envelope `max(w1,w2)` — single owner `base_images.py`)
- **[package-structure.md](package-structure.md)** — feature package layout, auto-discovery, splitting a feature into subpackages, current feature status
- **[feature-decomposition-playbook.md](feature-decomposition-playbook.md)** — step-by-step procedure for splitting an overgrown feature into the subpackage taxonomy (the `magnifier/` refactor, generalized)
- **[render-pass-contract.md](render-pass-contract.md)** — `CanvasRenderPass` (`src/ui/canvas_infra/scene/pass_contract.py:75`) interface + host call sequence, stack roles, scene visibility, alpha/blending rules; composition via `src/ui/canvas_presentation/composition.py`
- **[rendering-model.md](rendering-model.md)** — live authoring path vs. snapshot replay path (same eager `max` letterbox, single `resolve_canvas_content_geometry` owner), snapshot renderer notes
- **[coordinate-systems.md](coordinate-systems.md)** — normalized base-image space, canvas-px overlay model, base-image-anchored geometry, the single-resolver rule (`src/ui/canvas_infra/scene/frame_geometry.py::resolve_canvas_content_geometry`), composition tree (`src/ui/canvas_presentation/composition.py`)
- **`patterns.md`** (private, `improve-imgsli-internal-docs` repo) — patterns & anti-patterns (short rules + links to case write-ups)
- **`qrhi-gotchas.md`** (private, `improve-imgsli-internal-docs` repo) — QRhi / Wayland / scissor / compositing case catalog
- **[contracts.md](contracts.md)** — interface field catalog (`CanvasWidgetFeature`, scene/property/aliases, layout, `CanvasRenderPass`/`CompositionPlan`); glossary in [CONTRACTS.md](../CONTRACTS.md#three-senses-of-contract)
- **[zoom-pan.md](zoom-pan.md)** — gesture bindings, viewport change contract, zoom/pan invariants, semantic geometry vs paint extents, debugging
- **[checklist.md](checklist.md)** — pre-merge tick list (stack_role/visibility, `resolve_rhi_scissor`, eager envelope)
- **[display-image-pipeline.md](display-image-pipeline.md)** — unify → display-cache → render pipeline; single-writer/single-picker rule for `render_cache.display_cache_image1/2`
- **[tile-rendering-system.md](tile-rendering-system.md)** — GPU tile grid for oversized sources (`TileTextureService`), apron padding, residency/draw-plan invariant, and host-side memory bounding (`HostTextureUploadCache` LRU, `TiledPixelStore` memmap spill)
- **[plan_comparison_letterbox.md](../plan_comparison_letterbox.md)** — eager `max` envelope target, single owner, no HOLD for geometry (pixel fallback LOD is separate)
- **`glass-panel-text-vibrancy-plan.md`** (private, `improve-imgsli-internal-docs` repo, `docs/legacy/rendering/`) — in-progress: per-pixel HUD text color adaptation (GPU text mask + shader recolor), phased plan + status
- **investigations** (private, `improve-imgsli-internal-docs` repo) — long-form case write-ups. Shared/cross-tab ones at `docs/dev/rendering/investigations/`; tab-specific ones at `src/tabs/<tab>/docs/investigations/` in that same private repo
- **archive** (private, `improve-imgsli-internal-docs` repo, `docs/legacy/rendering/`) — closed design/phased-implementation plans (texture-array tile atlas, image_compare/multi_compare renderer unification), kept for the reasoning behind constants and architecture decisions still cited from the docs above

**Core idea**: a feature doesn't handle zoom, pan, coordinate transforms, raw
Qt events, or serialization — the infrastructure does. See
[Feature Isolation Model](../CONTRACTS.md#feature-isolation-model-the-abstraction).