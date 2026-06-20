# C++ Qt + Rust Core Migration Plan

Migration from Python/PySide6 to a hybrid C++ Qt6 (UI / Qt integration) + Rust (pure logic and IO) stack.

Status: **Phase 5 in progress** (plugin contract + registry landed with skeleton ports for all 4 plugins; deep per-plugin logic ports incrementally)

Phase 0 (scaffolding) and Phase 1A (pure-logic Rust core) are done. Phase 1
is split into two halves because the remaining work is **not** purely
language-level — it requires C++ Qt feature contracts that don't exist yet.

- **Phase 1A — Pure-logic core (done).** Everything portable without C++/Qt:
  domain primitives, settings, state shape, Action enum, reducer, Store with
  subscribers, render plan POD, plan keys + letterbox math, hit-test geometry,
  LRU image-pair cache, cxx bridge, PyO3 wrapper for parallel validation.
  **55 cargo tests passing. PyO3 module loads and round-trips dispatch from
  Python 3.14.**
- **Phase 1B — Qt-coupled core (blocked on Phase 3).** PlanBuilder feature
  command integration, virtual canvas layout, feature-state typed actions.
  These call into the 90+ feature commands, which are Qt-coupled and live in
  the C++ side once Phase 3 starts. Porting Phase 1B before C++ feature
  contracts exist would just rebuild the Python coupling in Rust.

## Why

Accumulated problems that are not solvable while staying on Python:
- GIL limits real parallelism in render and IO paths.
- QRHI / Qt private headers are awkward to reach from PySide6.
- Plugin loading, distribution, and cold-start performance are bottlenecked by Python.
- Type-checking gaps in a large architecture with 90+ feature aliases.

Goals:
- Keep the existing architecture (Redux store, EventBus, Feature contracts, Plan/Applicator) intact across the move.
- Migrate incrementally; the Python app stays runnable until late Phase 3.
- C++ owns everything that talks to Qt. Rust owns pure logic and image IO. FFI is via the `cxx` crate.

## Stack Decisions

| Layer | Technology |
|---|---|
| UI / windows / widgets | C++ Qt6 Widgets |
| Canvas / GPU | C++ `QRhiWidget` + GLSL/SPIR-V (via `qsb`) |
| FFI | `cxx` crate (no `cxx-qt` for now — see Risks) |
| Core logic | Rust crate `imgsli-core` |
| Image IO / decode | Rust (`image`, `zune-*`, optionally `libvips` bindings) |
| Build | CMake + [Corrosion](https://github.com/corrosion-rs/corrosion) (cargo inside CMake) |
| Tests | GoogleTest (C++) + `cargo test` (Rust) |
| i18n | Qt Linguist `.ts` (generated from current JSON dictionaries) |
| Packaging | AppImage / `.deb` / `windeployqt` / `.app` + `.dmg` |

Reference layout will live under `cpp/` in this repo during the transition, parallel to `src/`.

## Phases

### Phase 0 — Scaffolding (1–2 weeks)

Goal: empty-but-buildable C++/Rust skeleton, plus an inventory of what moves where.

- `cpp/` workspace: top-level CMake, Corrosion integration, a "hello window" Qt target, a `imgsli-core` Rust crate with one toy `cxx` bridge function.
- CI matrix: Linux / Windows / macOS. clang-format, clang-tidy, `cargo clippy`, `cargo fmt --check`.
- Module inventory across three buckets:
  - **Easy (pure logic):** `core/store*.py`, reducers, action types, `ui/canvas_presentation/plan*.py`, `ui/canvas_infra/scene/hit_test.py`, `gesture_resolver.py`.
  - **Medium (Qt-coupled):** widgets, presenters, dialogs, settings dialog, i18n loader.
  - **Hard (GL/QRHI/IO):** `ui/canvas_features/*/gl_passes.py`, `ui/widgets/gl_canvas/*`, image cache, export.
- Freeze current contracts as C++ headers (`include/imgsli/contracts/`):
  - `CanvasWidgetFeature`, `CanvasFeatureProperty`, `GLPassContract`, `CanvasRenderPlan` shape.

Exit criteria: `cmake --build` produces an empty Qt window that calls into Rust and prints a version string.

### Phase 1 — Rust Core, no UI (3–5 weeks)

Goal: pure logic in Rust, callable from both C++ and (temporarily) Python for parallel validation.

Modules migrating to `imgsli-core`:
- **State / Store / Reducers** — `Action` enum, `State` struct, pure reducer functions. Pattern-matched, easy to test.
- **PlanBuilder / PlanApplicator** — `CanvasRenderPlan` construction. Pure data in, pure data out.
- **HitTest, GestureResolver** — coordinate math, no Qt.
- **Image IO / decode** — via `image` + `zune-jpeg`; consider `libvips-rs` if perf matters.
- **Image cache** — LRU keyed by `(path, mtime, requested_size)`, via `moka`.
- **Settings (de)serialization** — `serde` + JSON, mirroring `core/store_settings.py`.

Parallel validation strategy:
- Expose `imgsli-core` to Python via PyO3 under crate `imgsli-core-py`.
- Swap one Python module at a time for the Rust-backed equivalent.
- Run existing pytest suite against both — bit-exact equivalence is the bar for store / plan, allow tolerance for image decode.

Exit criteria: the Python app runs with Rust-backed store, plan builder, hit-test, and image cache. Old Python modules deleted or marked `# moved-to-rust`.

#### Phase 1A landed

| Module | Source mirrored |
|---|---|
| `imgsli_core::domain` (Point, Color, Rect, SizeF) | `src/domain/types.py` |
| `imgsli_core::settings::SettingsState` (full, serde JSON) | `src/core/store_settings.py` |
| `imgsli_core::state` (RenderConfig, ViewState, GeometryState, InteractionState, ImageSessionState, ViewportState, DocumentModel, WorkspaceSession, WorkspaceState, AppState) | `src/core/store_viewport.py`, `store_document.py`, `domain/workspace.py` |
| `imgsli_core::action::Action` (28 variants — settings, view, geometry, interaction, document, workspace, opaque feature blob) | scattered mixin methods on the Python `Store` |
| `imgsli_core::reducer::{apply, reduce, Scope}` (pure, total, no-IO) | `core/store_operations.py`, `core/store_workspace.py` |
| `imgsli_core::store::Store` (state + subscribers, single-threaded) | `core/store.py` |
| `imgsli_core::plan::*` POD (TextureId, CaptureCircle, GuideSet, OverlaySlot, OverlayLayout, CanvasRenderPlan) | `src/ui/canvas_presentation/plan.py` |
| `imgsli_core::plan_keys` (SourceKeyInputs, DisplayCacheKeyInputs, fingerprints, letterbox math) | hashing portions of `plan_builder.py`; canvas-px invariant from `ARCHITECTURE.md` |
| `imgsli_core::hit_test` (point_in_rect, point_in_circle, distance_to_divider) | `src/ui/canvas_infra/scene/hit_test.py` + magnifier/divider hit testers |
| `imgsli_core::image_cache::ImagePairCache` (LRU, monotonic-counter eviction) | `core/store_viewport.py::RenderCacheState.unified_image_cache` + `image_cache.py` |
| cxx bridge: `core_version`, `core_greeting`, `settings_default_json`, `settings_roundtrip_json`, `state_default_json`, `state_dispatch_action`, `letterbox_rect` | — |
| `imgsli_core_py` PyO3 crate: `version`, `settings_default_json`, `settings_roundtrip_json`, `state_default_json`, `dispatch`, `letterbox_rect`, `ImagePairCache` | parallel-validation shim |

**Verification**
- `cargo test` — 55 tests passing.
- `cmake --build cpp/build` — `imgsli_app` links and shows greeting, default-settings dump, and round-tripped partial JSON.
- PyO3 module loads in CPython 3.14 (`PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1`); `dispatch` round-trips `SetTheme("dark")` end-to-end; `ImagePairCache` put/get verified.

#### Phase 1B (deferred — blocked on C++ feature contracts)

These cannot move to Rust ahead of Phase 3 without re-creating Qt coupling on
the Rust side:

- Full `PlanBuilder` logic (~550 lines, depends on 90+ feature commands and
  `VirtualCanvasLayout` which is Qt-coupled).
- Per-feature canvas state (`canvas_widget_state` dict). Currently round-trips
  through `Action::SetFeatureState(serde_json::Value)`; will become typed
  actions once each feature has a C++ contract.
- Image IO / decode pipeline (depends on the Qt thread pool and the
  `sli_ui_toolkit.workers.GenericWorker` abstraction).
- Image scaling worker (`start_scaling_worker` and `on_display_scaling_ready`)
  — same reason.
- Session blueprints application (`_apply_session_blueprint`) — depends on
  feature commands.

These will land alongside the corresponding C++ feature ports in Phases 3–4.
A parallel-validation pattern using `imgsli_core_py` can substitute Rust
implementations one Python module at a time as the C++ side grows.

#### Workspace layout

```
cpp/
  Cargo.toml             cargo workspace (members: core, core_py)
  core/                  imgsli_core (no Python, no Qt deps)
  core_py/               imgsli_core_py (PyO3 bindings, parallel validation)
  app/main.cpp           C++ Qt smoke app
  app/vulkan_smoke.h     QVulkanInstance probe + QRhiWidget(Vulkan) canvas
  CMakeLists.txt         Qt6 + Corrosion
```

### Smoke verification — Vulkan on Wayland

One of the explicit reasons for the migration is that on the old PySide6
stack a Vulkan-backed window could not be opened in a Wayland session
without falling back to `xcb`. The original Phase 0 smoke app used
`cpp/app/main.cpp` + `cpp/app/vulkan_smoke.h`; the active Phase 3 renderer now
lives in `cpp/app/canvas_widget.*`.

**Setup verified (local dev box):**
- Arch Linux, GNOME 48 Wayland session (`Mutter`), Qt 6.11.1, `qt6-wayland`
  6.11.1, `vulkan-radeon` 1.4.350.
- The Phase 0 smoke attached a `QVulkanInstance` to the top-level window and
  embedded a `QRhiWidget(Api::Vulkan)`.
- The Phase 3 canvas lets `QRhiWidget` own Vulkan initialization. Attaching a
  second `QVulkanInstance` to the top-level window was removed: with Qt
  6.11.1/Wayland it crashes in `QtWaylandClient` while destroying the window
  after a rendered frame.

**Results:**
- `QVulkanInstance::create()` returns OK; `apiVersion 1.2.*` reported.
- The window opens under nominal Wayland (`QT_QPA_PLATFORM` unset) — no
  `xcb` fallback required.
- `QRhiWidget` with `Api::Vulkan` brings up a real Vulkan swapchain without
  protocol errors. (Switching the same widget to `Api::OpenGL` while the
  `QVulkanInstance` stays attached *does* trigger
  `Wayland: protocol error` — that combination is invalid, recorded as a
  reminder not to mix Vulkan-instance attachment with non-Vulkan backends.)
- `xcb` fallback also works (`QT_QPA_PLATFORM=xcb`), kept as the
  development fallback for the GNOME-decoration issue below.

**Known issue — `QRhiWidget` + GNOME = no window decorations.**

Any window that contains a `QRhiWidget` (Vulkan backend confirmed; suspected
to apply across backends because of how the surface is attached) opens
**without** client-side decorations under GNOME Wayland. A peer Qt 6 widget
app (e.g. `designer6`) on the same session, with the same env
(`QT_WAYLAND_DECORATION=adwaita`, `qadwaitadecorations-qt6` from AUR
installed), shows the expected Adwaita-style frame. So:

- Cause is not `qadwaitadecorations` itself (it is installed, plugin loads).
- Cause is not the version of `qt6-wayland`.
- Cause is `QRhiWidget`'s surface management interacting with Mutter's
  xdg-decoration negotiation. We hit the same class of issue documented in
  upstream Mutter bug GNOME/mutter#3435 (Qt 6.7+ surfaces under Wayland) and
  in distro release notes ("by default there is no server side decoration
  for Qt apps").

**Plan**
- For Phase 0–2 development: ignore the missing frame. Window is usable; if
  needed, run with `QT_QPA_PLATFORM=xcb` for a development session with
  decorations. The decoration issue does not block any feature work.
- During Phase 3, keep Vulkan ownership inside `QRhiWidget`; do not attach a
  second `QVulkanInstance` to the top-level window. Continue testing
  `Qt::WA_NativeWindow` and default-surface-format mitigations for decorations,
  and file an upstream issue with a minimal reproducer if needed.
- For release packaging: bundle `qadwaitadecorations` into the AppImage so
  end-users on GNOME do not need an AUR package; combine with whichever
  in-code workaround Phase 3 settles on.

This is recorded in the Risks table below as a Phase 3 follow-up.

### Phase 2 — C++ Qt Shell (2–3 weeks)

Goal: a minimal C++ app that opens a file and shows a single image, going through the full Rust core.

- `main.cpp`, `QApplication`, `QMainWindow`.
- Port **sli-ui-toolkit** to C++ first — it is already a separate package, ideal pilot. This gives a baseline of widgets before tackling the main app.
- `cxx` bridge for `Store`:
  - C++ `class Store : public QObject` wraps `rust::Box<RustStore>`, exposes `dispatch(Action)`, emits `stateChanged(const State&)` from a Rust-side callback marshalled onto the Qt event loop.
- Single screen: open file → Rust decodes → C++ shows in a placeholder widget. Just to prove the pipeline.

Exit criteria: file open → decode → render in the C++ app, dispatched through Rust store.

#### Phase 2 progress

- [x] C++ `QObject` Store owns an opaque stateful `RustStore` through `cxx`.
- [x] Qt actions dispatch through the Rust reducer; Rust invokes a C++ observer
  through `cxx`, and the observer queues `stateChanged(stateJson, scope)` onto
  the Qt event loop.
- [x] Smoke UI can change the theme through the live Rust store.
- [x] Port the reusable baseline controls needed from `sli-ui-toolkit`:
  standalone CMake library, light/dark token palettes, compact custom-painted
  `Button` and `ComboBox`, used by the shell.
- [x] Add Rust image decode across the `cxx` bridge (PNG/JPEG/WebP/BMP/GIF/TIFF,
  RGBA8 output, 16384 px edge guard).
- [x] Add open-file workflow and show the decoded image in a placeholder
  C++ Qt widget.

Phase 2 exit criterion is satisfied: file open → Rust decode → Rust store
dispatch → C++ rendering. The same flow is available without a dialog through
`imgsli_app --open <path>` for smoke verification.

### Phase 3 — Canvas and Render (4–8 weeks, the heavy one)

Goal: port the GL/QRHI canvas. This is where the biggest current pain lives.

Order of work:

1. **GLCanvas widget** as a C++ `QRhiWidget` (Qt 6.7+) — falls back to `QOpenGLWidget` for older Qt.
2. **Plan execution split:** Rust produces `CanvasRenderPlan` (positions, sizes, texture ids, shader params — all plain data). C++ executes draw calls. This keeps Qt-private dependencies (QRhi) in C++ and out of the FFI surface.
3. **Pass registry / stacking policy** — port `stacking_policy.py` to Rust, `gl_pass_registry.py` to C++.
4. **GL passes**, ported one at a time, simplest first:
   - `background` → `divider` → `magnifier` → `guides` → `filename_overlay` → `capture` → `paste_overlay`.
   - Shaders (GLSL) copied as-is, compiled through `qsb` for QRHI.
   - Each pass keeps its current contract (uniforms, inputs).
5. **Feature contracts** — `CanvasWidgetFeature` becomes a C++ interface (`Q_DECLARE_INTERFACE`). Auto-discovery via static registration macros (no `pkgutil` equivalent — explicit registry is fine and easier to reason about).

Exit criteria: canvas works in the C++ app; magnifier + divider + guides functional; FPS at parity or better.

#### Phase 3 progress

- [x] C++ `CanvasWidget : QRhiWidget` with Vulkan backend and explicit QRhi
  resource lifecycle.
- [x] Build-time shader compilation through `qt_add_shaders`.
- [x] Rust-produced single-image render-plan POD with stable logical texture id.
- [x] C++ image registry resolves the logical id, uploads `QRhiTexture`, and
  records a letterboxed textured draw.
- [x] Real Wayland/Vulkan smoke:
  `imgsli_app --open <image> --smoke-exit` reaches `frameRendered` and exits
  cleanly. QRhiWidget owns its Vulkan instance; no top-level attachment.
- [x] Two-image vertical/horizontal split render plan produced by Rust and
  executed by C++.
- [x] Rust stacking policy plus sorted C++ pass registry.
- [x] Ported passes: background, divider, magnifier frame/content, guides,
  filename overlay, capture ring, and paste preview.
- [x] `CanvasWidgetFeature` C++ interface, static registration, semantic
  command lists, and command execution.
- [x] Interactive divider drag and magnifier drag; guide geometry follows the
  shared render-plan state.
- [x] Vertical and horizontal Vulkan snapshots verified with two distinct
  source images. The horizontal matrix also verifies paste-preview composition.
- [x] 300-frame Vulkan benchmark with all default comparison passes:
  **222.55 FPS** on the final Phase 3 build, above the 60 FPS interactive
  parity target.
- [x] `ctest` contract check validates required passes, features, commands,
  and a divider command roundtrip without requiring a GPU.

Phase 3 exit criterion is satisfied: the C++ canvas works, divider/magnifier/
guides are interactive and rendered through QRhi, and measured throughput is
above the current 60 FPS interaction target.

### Phase 4 — Dialogs, Settings, Tabs (3–4 weeks)

- Settings dialog (`plugins/settings/dialog*.py`) → C++ Qt Widgets.
- `application_service.py`, `manager.py`, `models.py` → either C++ (if Qt-bound) or Rust (if pure).
- i18n: `QTranslator` + `.ts` files. Convert `src/resources/i18n/**/*.json` to `.ts` via a one-shot script, or keep JSON and load from Rust.
- Multi-compare tab, video editor, export plugin.

#### Phase 4 progress

- [x] `models.py` ported to `imgsli_core::settings_dialog::SettingsDialogData`
  — 22 fields, serde JSON, `normalize()` clamping numeric ranges and
  enum-like strings against allowlists, `is_interpolation_conflict()`,
  `diff()` returning a sorted `Vec<FieldChange>`. Exposed via `cxx`
  and PyO3 for parallel validation. 16 unit tests.
- [x] Settings dialog shell in C++ — `QListWidget` sidebar +
  `QStackedWidget` pages, all 4 pages from `dialog_pages.py` (General,
  Interface, Performance, Analysis) bound to `SettingsDialogData`.
  Defaults come from `settings_dialog_default_json`; OK runs the
  result through `settings_dialog_normalize_json`.
- [x] Toolkit expansion: `CheckBox`, `RadioButton`, `SpinBox`,
  `GroupBox` custom-painted Qt widgets in `cpp/toolkit/`, sharing the
  existing `Theme` palette with `Button` / `ComboBox`.
- [x] `application_service.py` → `SettingsApplicationService` (C++).
  Diff comes from Rust; service dispatches a Store action for the
  fields with a typed Action variant today (theme, language, ui_mode,
  debug, system_notifications, auto_crop, rhi_backend) and persists
  every changed field to `QSettings` under the legacy keys. The
  remaining typed actions will land alongside their feature ports.
- [x] i18n: `imgsli_core::i18n` walks `<root>/<lang>/**/*.json`,
  flattens to dot-separated keys, falls back to English on miss, and
  returns the key when nothing matches — same contract as
  `sli_ui_toolkit.i18n.TranslationManager`. C++ uses `imgsli::app::tr`
  over the bridge; all Settings dialog labels go through it.
- [x] Workspace tab contract (`cpp/include/imgsli/contracts/tab_contract.h`)
  and static-registration `TabRegistry`. Phase 4 skeletons:
  `MultiCompareTab`, `VideoEditorTab`, `ExportTab`. Mounted into the
  smoke shell via `QTabWidget`. Full per-tab/plugin ports land in
  Phase 5.

`manager.py` is intentionally not ported as a separate class: its
QSettings ↔ `SettingsState` mapping is now collapsed into the
`SettingsApplicationService` persistence step plus
`SettingsDialogData::apply_to_settings`. Defaults and validation live
in Rust, persistence in C++ — no orphan helper class needed.

The `phase3_contracts` ctest was extended to require the three Phase 4
tabs and still passes.

### Phase 5 — Plugins (2–3 weeks)

Choose one of:
- **`QPluginLoader`** — dynamic `.so/.dll/.dylib`. Standard, supports hot reload.
- **Static registration** — all plugins compiled into the binary, registered via macro. Simpler builds and distribution, no hot reload.

Recommended: **static registration** for v1, `QPluginLoader` later if hot reload becomes a real need.

Plugins port one at a time: `comparison` → `export` → `settings` → `video_editor`.

#### Phase 5 progress

- [x] `PluginContract` C++ interface (`cpp/include/imgsli/contracts/`)
  collapses the 5 Python `I*Plugin` markers into a single virtual
  interface. Exposes `pluginId`, `displayName`, `definition`,
  `onActivate`/`onDeactivate`, `callService`/`providesService`. The
  declarative `PluginDefinition` POD mirrors
  `core.plugin_system.contributions.PluginDefinition`.
- [x] `PluginRegistry` (static-registration `IMGSLI_REGISTER_PLUGIN` macro)
  populates a per-binary list, exposes `find` and a single
  `callService` entry point that routes to the first plugin that
  advertises the service id.
- [x] **comparison** plugin port. Owns the split/orientation/path
  commands; the smoke shell's split slider and orientation toggle now
  call through `PluginRegistry::callService` instead of dispatching
  Store actions inline.
- [x] **export** plugin port. Backs `export.save_image` (Qt
  `QImageWriter`) and `export.decode_image` (Rust core decoder) services
  — enough for the still-image side. Video export waits for the video
  editor port.
- [x] **settings** plugin port. Registers the dialog/apply commands;
  the heavy logic landed in Phase 4 (SettingsDialog,
  SettingsApplicationService, Rust view-model).
- [x] **video_editor** plugin skeleton. Registers the plugin id and a
  `video_editor.backend` service stub. The full timeline / keyframing /
  ffmpeg pipeline is the largest single subsystem in the Python source
  and ports incrementally; the skeleton keeps the registry contract
  satisfied so downstream consumers can resolve the plugin id today.

`phase3_contracts` ctest was extended again to assert all 4 plugins
are present in the registry and that `PluginRegistry::callService`
actually round-trips a comparison-plugin call through the activated
Store, and a video-editor service stub returns its expected backend
identifier.

### Phase 6 — Packaging and Cutover (2 weeks)

- AppImage / `.deb` / `windeployqt` / `.dmg`.
- Benchmarks vs Python build: render FPS, cold-start time, memory, decode throughput.
- Archive the Python repo. Update README to point at the C++ build.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| QRHI private headers needed | Link `Qt6::GuiPrivate` in CMake; keep QRHI calls in C++ only, never crossing FFI. |
| Shader pipeline (`qsb`) in build | Add `qt_add_shaders` early in Phase 0; verify on all three OSes before Phase 3. |
| `pkgutil` auto-discovery does not translate | Explicit registry from day one. Static-init macros in feature `.cpp` files. |
| Existing pytest coverage cannot run on C++/Rust | Reuse pytest **scenarios** as specifications; rewrite as `cargo test` for Rust pieces, GoogleTest for C++. |
| `cxx-qt` immaturity tempts mixing | Forbidden in v1. All Qt-touching code is C++. Revisit `cxx-qt` only if QML becomes the UI. |
| Scope creep on Phase 3 | Strict per-pass acceptance: pixel-diff vs Python build, ≤1% tolerance. |
| `QRhiWidget` + GNOME Wayland = no client-side decorations | Cosmetic, not blocking. Use `xcb` for dev sessions when frames are needed. Investigate `Qt::WA_NativeWindow`, default `QSurfaceFormat`, and per-widget `QVulkanInstance` attachment during Phase 3. Bundle `qadwaitadecorations` in release packaging. See "Smoke verification — Vulkan on Wayland" section. |

## Non-goals

- Switching UI framework (no QML, no Slint, no egui).
- Rewriting features that are not already a problem (do not "modernize" working code during the port).
- Supporting Python and C++ builds in parallel after Phase 6.

## Resolved Decisions

- Minimum Qt version is **6.7** because `QRhiWidget` is the renderer contract.
  There is no parallel `QOpenGLWidget` implementation; older Qt releases are
  unsupported instead of maintaining two GPU backends.

## Open Questions

- Single repo (`cpp/` alongside `src/`) or separate repo from the start?
- Bundle `sli-ui-toolkit` C++ port into this repo or keep it as an external library mirror?

These should be resolved before the end of Phase 0.
