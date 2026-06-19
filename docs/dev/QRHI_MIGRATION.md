# QRhi Migration Plan

## Goal

Replace the OpenGL rendering backend with **Qt RHI** (Rendering Hardware Interface),
the Qt-native abstraction layer that compiles to Vulkan on Linux/Android,
Metal on macOS/iOS, and D3D11/12 on Windows. OpenGL is gradually being
deprecated on real hardware (macOS already, Wayland increasingly emulated via Zink)
and PyOpenGL adds an extra layer of indirection that we no longer need now that
we are on PySide6.

This is **Variant A: full replacement.** No parallel backend, no abstraction
layer over both APIs — a long-tail compat shim would cost more than the
migration itself.

## Prerequisites (done)

- [x] Migrated from PyQt6 to PySide6 (QRhi bindings only exist in PySide6).
- [x] Verified QRhi works on this machine: Vulkan backend live on NVIDIA RTX 4060 Ti.
- [x] `qsb` shader compiler available (`/usr/lib/qt6/bin/qsb`, `qt6-shadertools`).
- [x] `glslangValidator` available.
- [x] Branch `migrate/pyside6` ready as the base.

## Scope

### GL passes to port

| Pass | Difficulty | Notes |
|---|---|---|
| `divider` | low | one rectangle |
| `guides` | low | lines (line-as-quad in QRhi) |
| `capture` | low | rectangle outline |
| `paste_overlay` | medium | textured quad with alpha |
| `filename_overlay` | medium | text atlas, VAO equivalent |
| `magnifier` | high | multiple shader variants via `MagShaderKey` (disk + circle + content) |
| `multi_compare/gl_grid` | high | own subsystem with own shaders |
| `gl_canvas/render_passes` (core) | critical | base pipeline, image upload, framebuffer |
| `plugins/export/gpu_export_scene` | high | offscreen render for PNG export |
| `plugins/video_editor/preview_gl` | high | video preview with keyframing |

### Shader inventory

Approximately 10–15 vert/frag pairs across:
- `src/ui/canvas_features/magnifier/shaders/`
- `src/ui/canvas_features/filename_overlay/shaders.py` (inline)
- `src/ui/canvas_features/paste_overlay/gl_passes.py` (inline)
- `src/ui/canvas_features/guides/gl_passes.py` (inline)
- `src/ui/canvas_features/capture/gl_passes.py` (inline)
- `src/ui/canvas_features/divider/gl_passes.py` (inline)
- `src/tabs/multi_compare/shaders/`
- `src/ui/widgets/gl_canvas/shader_sources/`

All are simple vertex/fragment with no compute, geometry, or tesselation.

## Strategy

### Order: core first, then features by ascending complexity

1. **Core widget swap** — replace `QOpenGLWidget` with `QRhiWidget` in
   `gl_canvas/widget.py`. Stub all passes with no-ops. Verify the window
   opens and clears to background.
2. **Core image upload + base draw** — the textured-image pipeline in
   `gl_canvas/render_passes.py` must work before any feature is meaningful.
3. **Feature passes** in order: `divider` → `guides` → `capture` →
   `paste_overlay` → `filename_overlay` → `magnifier` →
   `multi_compare/gl_grid`.
4. **Plugins** — `export/gpu_export_scene` and `video_editor/preview_gl` last,
   using `QRhi::OffscreenSurface` for headless render.
5. **Cleanup** — delete PyOpenGL from `requirements-gui.txt`, remove all
   `from OpenGL import GL` imports, remove `QOpenGLWidget`/`QOpenGLShaderProgram`
   imports, drop `gl_canvas/render_common.py` GL-specific helpers.

### Shader pipeline

Add `scripts/compile_shaders.py` (or a Makefile rule) that:
- Scans `**/shaders/*.vert`, `*.frag` and inline-shader registries.
- Runs `qsb --glsl 100,300es,330 --hlsl 50 --msl 12 -o output.qsb input.vert`.
- Outputs `.qsb` files committed to the repo alongside sources.

GLSL adaptations expected:
- Uniform blocks must use `layout(std140, binding = N)`.
- Vertex inputs use explicit `layout(location = N)`.
- Sampler bindings via `layout(binding = N)`.
- No GL-only built-ins like `gl_FragCoord` Y-flip workarounds — QRhi normalizes.

### Pass contract changes

Current `CanvasGLPass` contract is stateful and GL-specific:

```python
class CanvasGLPass:
    def initialize(self, widget): ...   # called from initializeGL
    def paint(self, widget, ...): ...   # called from paintGL, may bind/draw inline
```

New `CanvasRenderPass` contract is command-buffer-based:

```python
class CanvasRenderPass:
    def initialize(self, rhi: QRhi, target: QRhiRenderTarget): ...
    def record(self, cb: QRhiCommandBuffer, ...): ...
    def release(self): ...   # explicit, since RHI resources are not GC-tied
```

Each pass owns its `QRhiGraphicsPipeline`, `QRhiBuffer`s, `QRhiShaderResourceBindings`,
and is responsible for releasing them. Reuse helpers (e.g. one shared
"textured quad" pipeline factory) will be in `gl_canvas/rhi_common.py`.

### Tests

`tests/render/` will be audited before starting. Tests that:
- Work on `PlanBuilder → Plan` decisions (declarative scene): survive.
- Mock `gl.glBindTexture` or similar primitives: must be rewritten or deleted.

Where tests verify *behavior* (e.g. magnifier-divider coupling, edge clamping,
overlay z-order), they should mostly survive because they assert plan-level
properties.

Where tests verify *GL specifics* (e.g. shader binding indices), they
become obsolete — the equivalent for QRhi is whether the pipeline matches
the shader resource bindings, which QRhi validates internally.

A new test suite will verify QRhi initialization, pipeline creation, and
that each pass can be `record`-ed without errors on the Null backend
(headless, no GPU needed).

### Visual parity

For each ported pass, before merging:
1. Run app with both backends (during transition) or capture screenshots
   of GL version saved earlier as reference.
2. Pixel-diff key views: empty canvas, single image, divider at various
   positions, magnifier active, multi-compare grid.
3. Tolerance: ~1–2 LSB for sampling/blending differences. Anything larger
   means the shader or pipeline state differs.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| `QRhiWidget` API differences across Qt 6.7 / 6.8 / 6.9 | Pin to Qt 6.11 in `requirements-gui.txt`, document minimum |
| Visual regressions hard to spot | Reference screenshots before starting, pixel-diff during |
| Shader translation breaks subtle math | Keep `glslangValidator` validation step, test on simple shape first |
| Video export goes via offscreen QRhi — different code path than widget | Port export last, only after widget path is stable |
| NVIDIA-only verification | Test path: Vulkan (NVIDIA), OpenGL fallback backend in QRhi, Null backend for CI |
| `QRhiWidget` does not work in PySide6 6.11 | Already verified working; if it regresses on future Qt update, fall back to `QQuickRhiWidget` (Qt Quick) |

## Interim app state

The current `migrate/pyside6` branch app fails to render with PySide6's
QOpenGLWidget (`GLError 1282` on `glActiveTexture`). Two options:

- **Live with it** during QRhi migration: app cannot launch, but we're
  rewriting the whole stack anyway.
- **Temporary GL fix**: add `QSurfaceFormat.setDefaultFormat()` with explicit
  desktop GL profile before QApplication creation. ~10 minutes of work,
  deleted when QRhi is in. Recommended for the convenience of running the
  app between checkpoints.

## Branch strategy

Migration happens on `migrate/qrhi`, branched from `migrate/pyside6`.
Merged into `main` only after all passes are ported and visual parity is
verified. No partial intermediate merges — the GL and QRhi codepaths
cannot coexist in one binary.

## Time estimate

3–5 weeks of focused work, broken down approximately as:
- Week 1: core widget swap, shader pipeline, divider/guides/capture.
- Week 2: paste_overlay, filename_overlay, magnifier.
- Week 3: multi_compare grid.
- Week 4: export plugins, video_editor.
- Week 5: visual parity sweep, cleanup, PyOpenGL removal.

## Concrete first deliverable

A commit on `migrate/qrhi` where:
- `gl_canvas/widget.py` extends `QRhiWidget` instead of `QOpenGLWidget`.
- All feature `*_passes.py` modules export no-op render passes.
- The shader compile script exists and produces `.qsb` for one trivial shader.
- The app launches, shows an empty canvas filled with the theme background
  color, and does not crash.

From there, each subsequent commit ports exactly one pass and shows a
visual diff against the reference. This gives a clear cadence and easy
rollback if any pass introduces a regression.

## Appendix A — `tests/render/` classification

Audit performed before Step 1 to know what must be rewritten and what
survives the backend swap.

**Plan-level (survive as-is, or with trivial import path updates):**

| Test file | Why it survives |
|---|---|
| `test_canvas_preserve_zoom_contracts.py` | Letterbox / focus math, no GL primitives. One sub-test mocks `glViewport`; that one needs the mock target updated to the RHI equivalent, but its assertion (focus is preserved) is backend-agnostic. |
| `test_gl_canvas_read_only_contracts.py` | Read-only viewport input handling, interaction layer; no GL calls. |
| `test_magnifier_divider_coupling.py` | Pure spacing-threshold math on plan inputs. |
| `test_magnifier_edge_clamp_contracts.py` | Edge-clamp geometry on plan inputs. Has one monkeypatch on an internal helper, not GL itself. |
| `test_magnifier_overlay_order.py` | Stacking policy (`CanvasStackRole`); backend-agnostic. |
| `test_magnifier_plan_overlay_contracts.py` | Plan-overlay geometry conversion through inner content rect. |
| `test_magnifier_snapshot_store.py` | Magnifier model normalization, pure data. |
| `test_scene_mode_apply_contracts.py` | Scene mode application logic; uses `SceneVisibility` from contract module — survives the contract rename if `SceneVisibility` keeps its identity. |

**GL-specific (rewrite against the QRhi contract, or delete if obsolete):**

| Test file | Disposition |
|---|---|
| `test_canvas_clear_state_contracts.py` | Mocks `gl.glBindTexture` / `glTexImage2D` in `texture_parts.layers`. **Rewrite:** mock the new RHI upload helper instead. Test intent (slot clear resets runtime flags) is still valid. |
| `test_divider_render_contracts.py` | Imports `DividerPass` and asserts on its `paint()` behavior. **Rewrite:** target the new `record()` entry point. Intent (paints only with two images + content rect) survives. |
| `test_gl_canvas_state_reset_contracts.py` | Asserts on `gl.GL_SCISSOR_TEST` toggle and viewport reset per frame. **Delete:** QRhi command buffers do not carry persistent scissor/viewport state across recordings, so the contract being tested becomes a non-issue. |
| `test_paste_overlay_feature_contracts.py` | Reads source code of `gl_passes.py` and asserts substring `gl.glBlendFunc(...)`. **Rewrite:** the two assertions about feature discoverability and own shader + preview stack role survive; drop the source-string blend-func check. |
| `test_single_preview_render_contracts.py` | Imports `DividerPass`/`CaptureRingPass` and checks they don't paint in single-preview mode. **Rewrite:** same pattern as `test_divider_render_contracts.py`. |

**Total: 8 survive, 5 need rewrite, 1 to delete.** Out of 14 files, roughly 60% backend-agnostic, which validates the layering choice in `canvas_presentation/` (the whole reason `PlanBuilder` exists).

