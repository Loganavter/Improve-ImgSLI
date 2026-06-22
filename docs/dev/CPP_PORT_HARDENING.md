# C++/Rust Port — Hardening Plan

The cross-language port of ImgSLI from Python/PySide6 to C++ Qt6 + Rust core
has shipped a working skeleton: every plugin, tab, canvas pass, recorder /
editor / export / analysis surface, and the offscreen render path are
runnable end-to-end. What's left is **bringing the port up to product
parity with the Python original** — its visual polish, its internal
architecture, and the handful of feature gaps still papered over with
scaffolding.

This document supersedes the old `CPP_RUST_MIGRATION.md` and
`QRHI_MIGRATION.md` plans. Those tracked the *initial* port and are now
fully delivered.

## State of the port (snapshot)

- C++/Rust workspace under `cpp/`. 122 cargo tests + `phase3_contracts`
  ctest pass; release smoke tools (`--snapshot`, `--video-transcode`,
  `--analysis-snapshot`) all produce valid output.
- Frameless top-level (`cpp/app/custom_window.{h,cpp}`) with our own
  Title Bar + edge-resize, because Qt-Wayland 6.11 + QRhiWidget under
  Mutter never invokes the Adwaita decoration plugin. This is a
  known-upstream issue; the custom CSD is the working solution
  Telegram Desktop and similar Qt apps use.
- 8 plugins registered through `PluginContract` + `IMGSLI_REGISTER_PLUGIN`;
  3 workspace tabs registered through `TabContract`.
- Rust core owns: settings, store / reducer / scope, render-plan POD,
  hit-test, image cache, settings-dialog model, i18n, analysis (PSNR/SSIM/
  diff), video-editor model + recording, playlist math, typed feature
  actions (`Action::SetCanvasFeature(FeatureAction)`).

What's **not** yet on par with the Python build:

| Gap | Symptom |
|---|---|
| Visual design | Toolkit surfaces and Settings pages now split; help and the remaining tab forms still need a full side-by-side visual parity pass. |
| Subscriber pattern | Typed scoped subscriptions are in place for comparison/analysis; remaining controllers and services still need migration where state ownership applies. |
| Phase 1B internals | Shared PlanBuilder ported to Rust `cpp/core/src/shared/rendering/plan_builder.rs` (single source of truth for `ComparisonController` + `MultiCompareGrid`). Primary comparison decode/scaling is asynchronous; the multi-grid import path still needs the same worker treatment. |
| Multi-compare grid | v1 ships 2×2 cells + playlist. No drag/drop transport, no per-cell composition, no large-grid renderer. |
| Drag/drop transport | Tabs accept file drops, but the rest of the workspace lacks the rich DnD wiring the Python widgets have. |
| Toolkit composites | `cpp/toolkit/` ships atomic widgets + `SectionHeader`/`Divider`/`Toolbar`/`Flyout`/`ChipGroup`/`Icon`. Declarative composites (`SectionPanel`, `InlineRow`, `FormGroup`, `PageBuilder`) the Python `sli-ui-toolkit` ships are still missing — without them tabs/dialogs fall back to inline `QFormLayout`. |

## Hardening progress log

Toolkit **polish** pass after track D landed:

- **Theme token system.** `Theme::getColor(token)` / `tryGetColor(token)`
  with a populated light/dark token map mirroring Python's tree:
  `button.{toggle,dialog.default}.background.{normal,hover,pressed,checked,
  checked.hover,disabled}` + `.border`, `accent`, `dialog.text`,
  `dialog.border`, `separator.color`. Falls back to `Palette` derivation
  on miss so callers always get a usable color.
- **Variants resolver uses the full Python cascade.** `tokenResolver(prefix)`
  factory replaces the simplified `defaultResolveBg`: disabled → pressed
  → checked(±hover) → hover → normal — every step reads via `getColor`,
  so visual output matches Python under the same theme tokens.
- **BackgroundLayer cascade.** Now follows Python: override_bg →
  custom_bg (with `deriveCustomPalette(variant)` tinting) → variant
  resolver → theme border. Replaces the local simplified resolver.
- **Multi-region paint pipeline.** `Painter::paint` detects a
  `buttonController` widget property; on hit, region-scope layers run
  per region with a `scopedTo(...)` context, then widget-scope layers
  run once. Direct Python parity with `Painter.paint` + `iter_regions`.
- **Button capability dispatch.** `Button::addCapability(...)`. Mouse
  press arms LongPressCapability; release routes through Menu/Click
  with long-press suppression; wheel forwards to ScrollCapability.
  Capability signals re-emit as `longPressed(regionId)` /
  `menuTriggered(regionId, data)` on the Button.
- **Controller exposed via dynamic property.** Button publishes its
  `ButtonController*` as `buttonController` property so the shared
  `Painter` discovers multi-region geometry without a toolkit-wide base.
- **New atomic widgets added** (closing missing Python primitives):
  - `LoadingSpinner` — conical-gradient spinner with 15ms tick.
  - `Switch` — animated track + knob with eased progress + hover halo.
  - `Slider` — `QSlider` with theme paint, hovered handle grow, animated
    inner-scale knob.
  - `Label` (text_labels) — typed typography variants
    (Body/Caption/Subhead/Heading/Display) with optional elide mode.
  - `CustomLineEdit` — rounded `QLineEdit` with focused/unfocused
    underline accent.
  - `DropZoneLabel` — dashed-border file-drop target with hover state.

Toolkit **depth** port completed during this pass (track D, all 7 phases):

- **D1 — buttons foundations.** `state.h`, `variant_spec.h`,
  `regions.{h,cpp}` (Single/Horizontal/Vertical/Grid/Custom splits +
  Divider), `content/{button_row.h, content.h}`, `specs.{h,cpp}` (ShapeSpec,
  ContentSpec, RegionStyle, BehaviorSpec + Click/Toggle/Scroll/LongPress/Menu,
  RegionSpec ↔ ButtonRegion conversion, ButtonSpec), `draw_context.h` with
  effective-* accessors and `scopedTo`.
- **D2 — state + events + controller.** `ButtonController` owns `RegionRuntimeState`
  per region: state set + ripple + scroll range/value. `recomputeRects`,
  `regionAt(pos)` with z-index ordering and disabled filtering, typed
  `behaviors(kind)` lookup.
- **D3 — painter pipeline.** `Layer` ABC + `Painter` orchestrator with the full
  Python default ordering (Background → Ripple → Content → Badge → Underline
  → Divider → Strikethrough). Each layer in its own translation unit under
  `layers/`. `Content::draw` ported for TextContent / RowsContent /
  IconContent / IconTextContent. Real `RippleEffect` with QTimer-driven
  progress/elapsed and gradient/overlay modes.
- **D4 — capabilities.** `ButtonCapability` ABC + `LongPressCapability`
  (timer-driven), `MenuCapability` (with `DropdownMenu` popup, keyboard nav),
  `ScrollCapability` (wheel handler + debounced end timer, bound to
  controller's scroll runtime).
- **D5 — public Button cutover.** `Button` rewritten as thin shell over
  `ButtonController` + shared `Painter` + `Variants` registry
  (`default`/`surface`/`ghost`/`subtle` with custom `resolveBg` lambdas).
  `buildSimpleSpec(text, variant)` keeps the back-compat constructor; new
  `setSpec(ButtonSpec)` exposes the full declarative API. `ButtonGroup`
  composite (label + bordered container) shipped alongside.
- **D6 — comboboxes depth.** `comboboxes/{models, search, overlay,
  scrollable_combo_box}` ported. Search includes Unicode
  NFKD-normalize + casefold + match scoring with prefix/word/substring/gap
  penalty (same ranking as Python). `Overlay` is a popup with optional
  `QLineEdit` search; `ScrollableComboBox` is a QWidget-level combo using the
  overlay + wheel/keyboard nav.
- **D7 — unified_flyout architecture.** All 13 Python modules mirrored:
  `common` (FlyoutMode enum + `RoundedClipEffect`), `model`
  (`FlyoutListModel` with Name/Rating/Path/Index/IsCurrent roles), `style`,
  `layout` (anchor placement with above/below fallback + screen clamping),
  `delegate` (theme-aware paint), `overlay_list_view` (QListView with
  Escape signal), `panel` (composes model + delegate + view + rounded clip
  effect), `session` (open/close lifecycle + focus return), `refresh`
  (debounced reload), `dragdrop` (URL drop policy), `content` +
  `simple_adapter` (typed populate helpers), `bootstrap` (composer).

**Honest gap.** The architecture is faithful; visual fidelity needs a
token-based color system to fully match Python (currently each variant's
`resolveBg` maps to `Palette` struct members, which approximates but does
not equal the Python token tree under
`button.{toggle,dialog.default}.background.{normal,hover,pressed,checked,disabled}`).

Toolkit reorganisation completed during this pass:

- **`cpp/toolkit/` flat tree replaced with category subdirs** mirroring
  Python `sli_ui_toolkit/ui/widgets/`. Public headers now live under
  `include/sli/toolkit/{atomic,buttons,comboboxes,composite}/`; sources
  follow the same split under `src/`. `theme.{h,cpp}` stays at the root
  to mirror Python `sli_ui_toolkit/theme.py`. Mapping:
  - `atomic/`: `check_box`, `divider`, `group_box`, `icon`,
    `radio_button`, `section_header`, `spin_box`.
  - `buttons/`: `button`, `chip_group` (multi-button single-selection bar,
    analogous to Python `buttons/button_group.py`).
  - `comboboxes/`: `combo_box`.
  - `composite/`: `flyout`, `toolbar`.
  All 88 `#include "sli/toolkit/<file>.h"` sites across `cpp/app/` and
  `cpp/toolkit/src/` rewritten to the new category-prefixed paths.
  `CMakeLists.txt` updated. Build + `phase3_contracts` green.

Canvas-features decomposition completed during this pass:

- **`ui/canvas/canvas_features.cpp` + `ui/canvas/feature_passes.{h,cpp}` removed.**
  The six `*Feature` command-handler classes (divider, magnifier, guides,
  capture, paste_overlay, filename_overlay) each live in their own
  `ui/canvas_features/<name>/feature.cpp`, mirroring Python
  `src/ui/canvas_features/<name>/`. Shared GPU rasterizers split into
  `ui/canvas/passes/{background,shape,filename_overlay}_pass.{h,cpp}` —
  `passes/` is engine-side infrastructure; the 6 `ShapePass` instances
  (predicate + mode + color) are wired in `ui/canvas_features/registry.cpp`,
  which replaces the old `feature_passes.h` entry point.

Plugin and tab decomposition completed during this pass:

- **`plugins/video_editor/plugin.cpp` 672 → 128 lines.** The single
  `callService` switch over 30+ ids was split into five per-group routers
  (`services/{timeline,project,export,recorder,preview}_router.{h,cpp}`)
  sharing a `services/plugin_state.{h,cpp}` for the cross-router recorder
  and bound-canvas fields. Each router exposes a single
  `std::optional<QVariant> route…Service(id, args[, state])` and is
  composed by the plugin shell.
- **`tabs/video_editor/tab.cpp` 881 → 82 lines.** The single
  monolithic `createPage` was rewritten as five section builders
  (`sections/{project,recording,preview,timeline,export}_section.cpp`),
  each consuming/populating a typed `PageContext` instead of the
  ~30 captured locals the original used. Builder helpers (`makeSpin`,
  `makeCombo`, `makeButton`) live in a shared `sections/sections.{h,cpp}`.
- **Other plugins reviewed and left as-is.** `comparison/controller.cpp`
  (396) is 18 well-named methods, not a dump; `analysis/controller`
  (193), `export/plugin` (200), `help/dialog` (161), and
  `comparison/plugin` (132) all sit in healthy ranges and need no
  further decomposition today.
- **Toolkit composites (`SectionPanel`/`InlineRow`/`FormGroup`/`PageBuilder`)
  deferred.** These names did not actually ship in Python
  `sli-ui-toolkit` — they were proposals in the original gap analysis.
  With settings pages and video_editor sections decomposed, each
  section is self-contained inside one file; the demand for shared
  declarative composites has dropped to "nice to have, not blocking".
  Revisit when a concrete visual parity gap surfaces.

Implemented earlier during the **structural cleanup pass**:

- **`cpp/app/` reshaped to mirror `src/`.** Flat 30-file tree replaced by
  `core/`, `shell/`, `ui/canvas/`, `plugins/<name>/`, `tabs/<name>/`, `cli/`.
  Every C++ source/header has a one-to-one folder match in the Python tree.
  `#include` paths fully qualified by area. CMake reflects the new layout.
- **`cpp/core/src/` reshaped to mirror `src/`.** Flat 20-file Rust tree
  replaced by `core/` (state, store, reducer, action), `plugins/<name>/`
  (settings/model + dialog, analysis, video_editor), `ui/canvas/`
  (plan, plan_keys, virtual_layout, stacking, hit_test, image_cache),
  `tabs/multi_compare/playlist`, `workspace/session_blueprint`. `bridge.rs`,
  `domain.rs`, `i18n.rs` stay at the top. `core_py` PyO3 wrapper updated
  to the new paths. 122 cargo tests + clippy + fmt remain green.
- **`main.cpp` 1216 → 71 lines.** Bootstrap UI assembly (store, controllers,
  toolbar, theme/help/settings flyouts, workspace tabs, settings dialog
  apply path, CLI hooks) extracted to `shell/bootstrap.{h,cpp}` exposing
  `shell::buildMainUi(...)`. The `--contract-check` assertion battery
  extracted to `cli/contract_check_command.{h,cpp}` exposing
  `cli::runContractCheck(...)`. `main.cpp` now reads top-to-bottom as
  bootstrap narrative: parse options → init theme/i18n → build window/canvas
  → branch on `--contract-check` or normal UI → `app.exec()`.
- **Settings dialog decomposed by page.** `plugins/settings/dialog.cpp`
  588 → 122 lines (slim shell: sidebar/stack composition, OK/Cancel,
  Rust-normalize round-trip). Per-page widget construction + JSON
  read/write moved into `plugins/settings/pages/{general,interface,
  performance,analysis}_page.{h,cpp}`, each implementing a shared
  `SettingsPage` interface (`load(QJsonObject)`, `save(QJsonObject&)`).
  This mirrors Python `src/plugins/settings/dialog_pages.py`.
- **`AGENTS.md` rewritten** with a load-bearing C++/Rust port section:
  full `cpp/` map, src↔cpp symmetry rule as the prime directive, an
  explicit «Rust = backend, C++ = Qt shell» split with decision rule
  («Use Rust when…», «Use C++ when…»), verification commands, Wayland
  caveat. Python sections retained.

Implemented during the prior hardening pass:

- **Custom Title Bar polish**
  - maximise/restore glyph, tooltip, and accessible name follow
    `WindowStateChange`;
  - animated hover ripple on all three window controls;
  - drag-to-restore from a maximized window while preserving compositor-owned
    system movement;
  - window-scoped `Alt+F9`, `Alt+F10`, and `Alt+F4` accelerators.
- **Shared offscreen rendering**
  - one `OffscreenRenderer` plugin service owns the hidden `CanvasWidget`;
  - still export, video preview/export, and multi-compare composite export use
    the same serialized renderer;
  - multi-compare no longer resizes live grid cells while exporting;
  - batch rendering avoids one Plugin Registry round-trip per grid cell;
  - a bounded LRU caches rendered frames by complete plan, target size, and
    source image cache identities.
- **Typed Store integration**
  - C++ `StoreScope` / `StoreUpdate` and `Store::subscribe(...)` provide
    settings, viewport-tag, document, workspace, and no-op routing;
  - same-thread reducer updates are delivered synchronously, cross-thread
    updates remain queued;
  - `ComparisonController` routes split/orientation and
    magnifier/capture/guides/paste-overlay changes through typed Store methods;
  - `AnalysisController` routes diff/channel changes through the Store and
    renders from scoped reducer updates.
- **Video keyframe hardening**
  - the Rust project model persists per-feature keyframe opt-in/out;
  - C++ video editor controls expose split, divider, magnifier, capture,
    guides, filename overlay, and paste overlay policy;
  - disabled groups remain fixed to the first-snapshot baseline during
    preview/export interpolation.
- **C++ toolkit expansion**
  - public `SectionHeader`, `Divider`, and `Toolbar` primitives now structure
    the Video Editor and comparison controls;
  - public `Icon` supports standard `QIcon` sources and optional tinting;
  - exclusive keyboard-navigable `ChipGroup` replaces the stock theme combo;
  - in-window `Flyout` enforces single-active behavior and closes on Escape,
    outside click, window deactivation, or anchor movement; Settings and Help
    now use the comparison toolbar flyout.
- **CLI hardening**
  - `cpp/app/cli/startup_options.*` owns flag parsing and value validation;
  - `main.cpp` consumes typed options instead of repeated `indexOf/at` logic;
  - snapshot/smoke, benchmark, comparison startup, analysis snapshot, and
    video transcode execution live in dedicated command translation units;
  - malformed numeric, size, and missing-path arguments fail early with exit
    code 64.
- **Virtual canvas layout**
  - Rust now owns normalized-bounds union, canvas padding resolution, and
    contain/stretch content placement through `virtual_layout`;
  - the CXX bridge exposes the pure layout contracts to C++, and comparison
    image fitting consumes the Rust result instead of duplicating the math;
  - padding keeps Python-compatible ties-to-even rounding, covered by focused
    Rust tests and a C++ contract probe.
- **Session blueprints**
  - Rust owns the Python-compatible blueprint shape and hydrates workspace
    `state_slots`, resource namespaces, and metadata defaults;
  - `WorkspaceSession` now persists those plugin-owned JSON maps instead of
    dropping them at the Rust boundary;
  - `--session-blueprint <file.json>` creates the typed session and restores
    optional comparison image paths, feature toggles, split/orientation, and
    analysis modes; relative image paths resolve from the blueprint file.
- **Async comparison loading**
  - comparison image decode and contain-scaling run through QtConcurrent
    instead of blocking the GUI thread;
  - decode and scaling generations discard stale results when a newer pair is
    opened before an older worker completes;
  - fitted images are reused for render-plan updates and analysis instead of
    being synchronously rescaled on every feature toggle.

Verification completed after these changes:

- `cmake --build cpp/build -j2`;
- `ctest --test-dir cpp/build --output-on-failure -R phase3_contracts`;
- `cargo test --workspace` — 122 tests;
- `cargo fmt --check`;
- `cargo clippy --workspace --all-targets -- -D warnings`;
- real QRhi snapshot smoke for reducer-driven comparison and shared offscreen
  export;
- GPU `--contract-check`, including repeated-render cache validation and
  pixel-identical single/batch export output.
- asynchronous comparison snapshot and analysis snapshot smokes produced
  valid non-empty 512×512 RGBA PNGs.
- extracted CLI executor smokes:
  - snapshot and analysis snapshot produced valid non-empty 512×512 RGBA PNGs;
  - benchmark completed and printed measured FPS;
  - video transcode produced a verified 96×54, 10 FPS output from a local
    generated source.

## App-layer port audit (2026-06-21, second pass)

Side-by-side comparison of top-level folders revealed the C++ tree is
about half the Python tree's footprint. Most of the gap is documented
in the «Architecturally not applicable» table below; the rest is real
port work tracked here.

### `src/` → `cpp/app/` folder map (full inventory)

| `src/` | `cpp/app/` | Status |
|---|---|---|
| `__main__.py` | `shell/main.cpp` | done |
| `ui/main_window/` (12 files) | `shell/{bootstrap,custom_window}` | done |
| `ui/store_bridge.py` | integrated into `shell/bootstrap` + `Store` | done |
| `ui/theming.py` | `cpp/toolkit/theme` (token map added this pass) | done |
| `core/` | `core/` | done |
| `plugins/` | `plugins/` | done |
| `tabs/` | `tabs/` | done |
| `resources/` | consumed via `IMGSLI_I18N_ROOT` / `IMGSLI_HELP_ROOT` | done |
| `events/` | Qt signals (architectural replace) | n/a |
| `devtools/` | Qt Designer / QtCreator | n/a |
| `shared_toolkit/` | `cpp/toolkit/` | done |
| `domain/` (94 LOC) | `cpp/app/domain/` | done |
| `utils/` (237 LOC) | `cpp/app/utils/` | done |
| `ui/icon_manager.py` (100 LOC) | `cpp/app/ui/icon_manager.{h,cpp}` | done |
| `ui/gesture_resolver.py` (64 LOC) | `cpp/app/ui/gesture_resolver.{h,cpp}` | done |
| `services/system/{clipboard,notifications}` (~250 LOC) | `cpp/app/services/system/…` | done |
| `services/system/paste_direction_overlay.py` | architecturally replaced — direction picking is a comparison-plugin canvas overlay (`pasteOverlay*` signals), not a top-level service | n/a |
| `services/io/image_loader.py` (353 LOC) | sync path: `cpp/app/services/io/image_loader.{h,cpp}`; async path stays in `plugins/comparison/use_cases/loading.cpp` | done |
| `services/workflow/playlist*` (440 LOC) | Rust `tabs/multi_compare/playlist`; no Python-side glue exists to port — call sites live in tab code | n/a |
| `shared/image_processing/` (430 LOC) | `cpp/app/shared/image_processing/` (`qt_conversion`, `prescale`, `resize`, `regions`, `analysis_pair`). `progressive_loader.py` stays Python — its consumer is the QtConcurrent path | done |
| `shared/rendering/{interpolation,live_snapshot,target_surface}` (~70 LOC) | `cpp/app/shared/rendering/…` | done |
| `shared/rendering/layout_contract.py` (85 LOC) | already in Rust `virtual_layout` | done |
| `ui/canvas_features/` | `cpp/app/ui/canvas_features/` | done (track A) |
| `ui/canvas_infra/` | architecturally replaced — abstract widget contracts live inline in `ui/canvas/canvas_widget.cpp` + `core/render_pass*`; the Python module is a Python-side abstraction the Qt subclass already supplies | n/a |
| `ui/canvas_presentation/` | `layout.py` in Rust `virtual_layout`; `plan_builder.py` is tracked under track C; the remaining presentation helpers map to the canvas widget + render-plan POD already shipped | n/a |
| `ui/widgets/` (8 files) | `cpp/app/ui/widgets/{rounded_overlay,startup_placeholder,zoom_indicator,form_controls}`. Feature flyouts (`font_settings`, `magnifier_color`, `magnifier_visibility`, `video_session`) are plugin-owned and already covered by the comparison/video_editor controllers | done |
| `ui/managers/` (4 subdirs) | `cpp/app/ui/managers/{tray,message}_manager`. `dialog_manager`/`transient_ui_manager` are architecturally replaced by toolkit `Flyout` + bootstrap wiring | done |
| `ui/presenters/` | architecturally replaced — C++ wires controllers directly to views via Qt signals; the presenter intermediary is a Python-side decoupling layer with no analogous indirection here | n/a |
| `ui/onboarding/` | architecturally replaced — onboarding state lives in workspace session blueprints (Rust) + bootstrap; there is no separate `onboarding/` UI to port | n/a |

### Track E — App-layer port

Goal: every `src/` directory listed above as "pending / in progress /
partial" has a matching `cpp/app/` translation unit, with the same
behaviour the Python build relies on.

#### E1. Foundations — done

- [x] `cpp/app/domain/types.h` — `Point`, `Color`, `Rect` POD structs.
- [x] `cpp/app/domain/qt_adapters.h` — `toQPointF` / `fromQPointF`,
  `toQColor` / `fromQColor`, `toQRect` / `fromQRect`, `hexToColor`,
  `colorToHex` (inline).
- [x] `cpp/app/domain/workspace.h` — `WorkspaceSession` +
  `WorkspaceState` with `nextDefaultTitle` and UUID-backed
  `newSessionId`.
- [x] `cpp/app/utils/resource_loader.{h,cpp}` — `safeRect`, `safePoint`,
  `resourcePath`, `truncateText` (binary-search prefix + ellipsis
  cascade), `scaledPixmapDimensions`.
- [x] `cpp/app/utils/geometry.{h,cpp}` — `GeometryManager` matching
  Python: `loadAndApply` (restore `normal_rect`/`normal_geometry` +
  was-maximized from `QSettings`, set minimum 200×150), `saveOnClose`,
  `updateNormalGeometryIfNeeded`, `beginMaximizeTransition` /
  `onLeftMaximizedState` freeze toggle.
- [x] All E1 sources wired into `cpp/app/CMakeLists.txt`; build green;
  `phase3_contracts` green.

#### E2. Icon registry + gesture resolver — done

- [x] `cpp/app/ui/icon_manager.{h,cpp}` — `AppIcon` enum mirroring the
  Python registry (~40 entries) and `getAppIcon(AppIcon | QString)` loading
  themed SVGs from `<resource_root>/assets/icons/{dark,light}/`, with
  automatic theme detection from the application palette and a fallback to
  the opposite theme directory. `IMGSLI_DEFAULT_RESOURCE_ROOT` baked into
  `target_compile_definitions` so the lookup works out of the build dir
  without setting `IMGSLI_RESOURCE_ROOT`. The Python-only
  `configure_toolkit` / `configure_icon_resolver` wiring is not ported —
  those configure `sli_ui_toolkit`'s Python side, which has no C++
  counterpart.
- [x] `cpp/app/ui/gesture_resolver.{h,cpp}` — `RatingGestureTransaction`
  with `applyDelta` / `rollback` / `commit` / `hasChanges`, plus a
  `RatingGestureHandler` interface (`incrementRating`,
  `decrementRating`, `setRating`) that comparison session owners
  implement to route the events.

#### E3. System services — done

- [x] `cpp/app/services/system/clipboard.{h,cpp}` —
  `collectClipboardImageItems()` extracts paths and URLs from the system
  clipboard in the same priority order as Python (`text` lines → MIME
  URLs → raw `QImage` saved to `TempLocation/clip_<ms>.png`). The
  Python paste-direction overlay flow stays plugin-owned (see the
  deferred `paste_direction_overlay.py` row in the inventory table);
  this layer just delivers the candidate inputs.
- [x] `cpp/app/services/system/notifications.{h,cpp}` —
  `NotificationService` mirroring Python's surface: linux preference
  for `notify-send` (only outside Flatpak), fallback to a
  `QSystemTrayIcon::showMessage` bubble, `setEnabled` / `setTrayIcon`
  hooks. The D-Bus path is left out — it duplicates `notify-send` on
  every desktop we ship to and would pull a runtime dependency.

#### E4. Shared rendering helpers — done

- [x] `cpp/app/shared/rendering/interpolation.{h,cpp}` —
  `effectiveMainInterpolation` (defaults to `BILINEAR`) and
  `effectiveExportInterpolation` (substitutes `LANCZOS` for `NEAREST`),
  matching the Python helpers used by the export path.
- [x] `cpp/app/shared/rendering/live_snapshot.{h,cpp}` —
  `LiveFrameSnapshot` POD (`timestamp`, paths, names) and
  `pathAtIndex(items, index)` mirroring the Python helper. The full
  viewport/settings freeze stays in the Rust project model where it
  already lives.
- [x] `cpp/app/shared/rendering/target_surface.h` — POD mirror of
  Python `TargetSurfaceSpec` (width, height, optional fill rgba,
  output scale, preserve-zoom, clip-overlays-to-image-bounds).

#### E5. Image processing layer — done

- [x] `cpp/app/shared/image_processing/qt_conversion.{h,cpp}` —
  `toRgba8888(QImage)` + `toRgba8888Pixmap(...)`. The Python PIL→Qt
  zero-copy bridge has no C++ counterpart (every image lives as a
  `QImage` from the QtConcurrent worker onward), so the helper just
  normalises format the way the QRhi canvas pipeline consumes.
- [x] `cpp/app/shared/image_processing/prescale.{h,cpp}` —
  `sharedPrescaleSize(size1, size2, outW, outH)` and `prescalePair(...)`,
  taking the largest source dimensions and bounding to the output (the
  same logic the Python export path uses to avoid upscaling a low-res
  image after a shared-ratio shrink).
- [x] `cpp/app/shared/image_processing/resize.{h,cpp}` —
  `interpolationToTransformMode` (case-insensitive name → Qt enum) +
  `resampleImage`. Qt exposes only fast/smooth transformations, so the
  Python multi-method matrix collapses to the two stable choices.
- [x] `cpp/app/shared/image_processing/regions.{h,cpp}` —
  `ImageRegion`, `UniformTileGrid` with row-major iterator,
  `buildUniformTileGrid`, `buildSquareTileGrid`, `computeCenteredBox`.
- [x] `cpp/app/shared/image_processing/analysis_pair.{h,cpp}` —
  `prepareAnalysisPair(img1, img2, maxExtent)` aligning both images to a
  shared bounded size + `Format_RGBA8888` so PSNR/SSIM/diff metrics
  consume bit-equivalent buffers.

`progressive_loader.py` is **n/a** — its job (preview-then-full decode)
is owned by the comparison plugin's QtConcurrent path
(`plugins/comparison/use_cases/loading.cpp`), which already implements
the two-stage decode with generation guards.

#### E6. `ui/` large chunks — closed

- [x] `cpp/app/ui/widgets/{rounded_overlay,startup_placeholder,
  zoom_indicator,form_controls}` — non-feature-specific UI ported here.
  `RoundedOverlayWidget` paints its own AA rounded background (works
  over QRhi where QSS `border-radius` leaks), `StartupPlaceholder`
  mirrors a target widget's geometry and centres a label,
  `ZoomIndicator` composes both with a `Sync` icon button and a
  caller-supplied i18n prefix provider, `DialogActionBar` /
  `OutputPathSection` ship the common dialog primitives.
- [x] `cpp/app/ui/managers/{tray_manager,message_manager}`. `TrayManager`
  owns the system tray icon + context menu (toggle / open last file /
  open last folder / quit) with retranslate-able actions; `MessageManager`
  pools non-modal QMessageBox windows (`WA_DeleteOnClose`).
- [n/a] `cpp/app/ui/canvas_infra/` — abstract widget contracts already
  exist inline in `ui/canvas/canvas_widget.cpp` + `core/render_pass*`;
  the Python module is a Python-side abstraction the Qt subclass
  natively supplies.
- [n/a] `cpp/app/ui/canvas_presentation/` — `layout.py` lives in Rust
  `virtual_layout`; `plan_builder.py` is tracked under track C as
  shared work; the remaining presentation helpers map to the QRhi
  canvas widget + render-plan POD already shipped.
- [n/a] Feature flyouts (`font_settings_flyout`, `magnifier_color_controls`,
  `magnifier_visibility_flyout`, `video_session_widget`) — already
  architecturally replaced by the comparison / video_editor plugin
  controllers + the toolkit toolbar/flyout primitives.
- [n/a] `dialog_manager` / `transient_ui_manager` — superseded by the
  toolkit `Flyout` + bootstrap wiring.
- [n/a] `cpp/app/ui/presenters/` — C++ connects controllers to views
  directly via Qt signals; the presenter intermediary is a Python-side
  decoupling layer with no analogous indirection here.
- [n/a] `cpp/app/ui/onboarding/` — onboarding state is owned by Rust
  workspace session blueprints + bootstrap; there is no separate
  onboarding UI to port.

### Exit criterion for track E — **met**

Every entry in the `src/` ↔ `cpp/app/` map above is either «done» or
explicitly «n/a» with a load-bearing architectural rationale — no
«pending» / «partial» rows remain. `find cpp/app -maxdepth 1 -type d |
sort` matches the relevant subset of `find src -maxdepth 1 -type d |
sort` (modulo the architecturally-substituted dirs `events/`,
`devtools/`, `shared_toolkit/`, `presenters/`, `onboarding/`,
`canvas_infra/`, `canvas_presentation/`). Verification:
`cmake --build cpp/build` + `ctest -R phase3_contracts` green.

## Structural-cleanup audit (2026-06-21)

After the canvas-features split landed, the remaining `cpp/app/` tree was
re-walked end-to-end. The conclusion: **A1 was the last actionable structural
refactor.** Everything else either already mirrors `src/` cleanly, is shaped
by Qt-side constraints that make the Python layout a bad analogue, or is
port-gap work (Phase 1B) that belongs in its own session. The catalogue below
exists so a future pass doesn't re-investigate the same ground.

### Reviewed and OK as-is

- **`cpp/app/core/`** — 5 files, 27–280 LOC. `store.cpp` (280) is dense but
  cohesive; the four `*_registry.cpp` files are 30–60 LOC each. Python
  `src/core/{main_controller_parts, plugin_system, state_management, tracing}`
  is a Python-only split of a god-controller and a tracing harness that
  C++ replaces with Qt signals + the Rust reducer. **Action:** leave alone;
  reconsider only if `store.cpp` grows past ~500 LOC.
- **`cpp/app/ui/canvas/canvas_widget.cpp`** (450 LOC) — `QRhiWidget`
  subclass: shader init, render loop, image texture cache, mouse/wheel
  handlers, render-plan export. The Python analogue `src/ui/widgets/gl_canvas/`
  ships ~10 files (`render_context`, `render_executor`, `feature_overlay_gpu`,
  `texture_parts/`, `shader_sources/`), but in Qt this is naturally one
  QRhiWidget subclass. Dropping the split now would be cargo-culting.
  **Action:** leave alone; revisit if/when the render graph itself is
  reworked (then split `texture_parts/` and `render_context/`).
- **Plugin controllers reviewed during the prior pass** — `comparison/controller`
  (396, 18 well-named methods), `analysis/controller` (193),
  `export/plugin` (200), `help/dialog` (161), `comparison/plugin` (132).
  No further decomposition warranted.

### Architecturally not applicable

These Python modules don't map onto the C++ side at all; trying to port
their *structure* would create antipatterns.

| Python | Why it doesn't port |
|---|---|
| `src/events/{app_event,canvas_input,image_label}` | C++ uses Qt signals/slots, the native alternative to an EventBus. Layering an event bus on top of signals is cargo-cult. |
| `src/shared_toolkit/` | Python-local QSS + `ui/managers/`. C++ uses `cpp/toolkit/`. |
| `src/devtools/ui_inspector` | Runtime inspector for Python widgets. Qt Designer/QtCreator covers this on the C++ side. |
| `src/utils/` | Small helpers — either inline in C++ or covered by `<algorithm>`. |
| Per-plugin `resources/i18n/<lang>/*.json` | C++ uses one shared `IMGSLI_I18N_ROOT` over the same JSON; duplicating per-plugin would be a regression. |

### Port-gap work (separate sessions, Phase 1B)

These are real gaps, but they are *porting work*, not refactoring of what
already exists. Each one deserves a dedicated session with its own design
review; bundling them into a generic "structural cleanup" pass would lose
the per-port nuance. Tracked under track C below.

| Python | What's needed |
|---|---|
| `src/shared/rendering/plan_builder.py` (~550 LOC, 90+ feature commands) | Done — `cpp/core/src/shared/rendering/plan_builder.rs` + thin C++ shell `cpp/app/shared/rendering/plan_builder.{h,cpp}`. Canvas widget POD extended with `std::optional<OverlayLayoutPlan>` (PB-C) as a read-only mirror; the live QRhi render path keeps its per-frame mutation pipeline. |
| `src/services/{io,system,workflow}` | IO / notifications / workflow services. Partial: `playlist.rs` is in Rust; the rest is on-demand. |
| `src/plugins/export/services/{gpu_export*,recording_flow,video_export_flow}.py` | GPU-export pipeline. Partial: `offscreen_renderer` is done; remainder open. |
| `src/ui/{canvas_infra, canvas_presentation, managers, onboarding, presenters}` | Presenter pattern / scene contracts / onboarding flows. Whether C++ needs any of this should be decided per feature, not as a structural mirror. |

## Direction

Three independent tracks. They can progress in parallel by different
people; A unlocks B and C so it should go first when staffing is
single-threaded.

### A. Structural cleanup — closed

Exit criterion **met**: `main.cpp` is 71 LOC and reads top-to-bottom as
wiring narrative; every controller has a one-line dependency surface
through the typed Store. Final status of the original checklist:

- [x] **Bootstrap extracted.** `shell/bootstrap.{h,cpp}` (345 LOC) owns
  Store, plugin/tab registration, controller instantiation, bind services,
  and returns a configured `CustomWindow` to `main`.
- [x] **CLI fully split.**
  - [x] `cpp/app/cli/startup_options.{h,cpp}` is the typed parser/validator.
  - [x] Snapshot, benchmark, compare/open, analysis snapshot, and video
    transcode each live in per-command translation units under `cli/`.
  - [x] `--contract-check` extracted to `cli/contract_check_command.{h,cpp}`
    (812 LOC); `main.cpp` only branches on the parsed option.
- [x] **`StoreSubscriber` contract.** `Store::subscribe(Scope, callback)`
  delivers typed payloads for Settings / Viewport / Document / Workspace.
- [x] **Controllers route through typed Store actions.**
  - [x] `ComparisonController` — split/orientation and
    magnifier/capture/guides/paste-overlay through typed Store methods,
    consumes scoped reducer updates.
  - [x] `AnalysisController` — diff/channel through typed Store methods,
    renders only from scoped updates.
  - [x] **VideoEditor keyframe state — clarified, not Store-routed.**
    `KeyframeFeaturePolicy` lives in the Rust project model
    (`cpp/core/src/plugins/video_editor/mod.rs`) and is persisted with the
    project, not the global Store. This is the intended architecture:
    Store carries cross-plugin scopes (Settings, Viewport, Document,
    Workspace); plugin-local project state stays on the plugin. The
    original bullet conflated "typed contract" with "Store-routed" — the
    typed contract requirement is met by the Rust project model.
- [x] **Offscreen `CanvasWidget` centralised.** One `OffscreenRenderer`
  Plugin Registry service serves still export, video preview/export, and
  multi-compare composite export.
- [x] **`# moved-to-rust` cleanup.** `grep -rn 'moved-to-rust' src/`
  returns nothing — the residuals were already removed in prior passes.
- [x] **`ui/canvas_features/` per-feature split** (this pass).
  `feature_passes.{h,cpp}` + `canvas_features.cpp` replaced by
  `passes/{background,shape,filename_overlay}_pass.{h,cpp}` (engine-side
  rasterizers) + `canvas_features/<name>/feature.cpp` (per-feature command
  handlers) + `canvas_features/registry.cpp` (binding).

### B. Visual / UX parity — **re-opened.** The category-tree reorg was cosmetic; the load-bearing gap is toolkit depth.

A prior pass categorised `cpp/toolkit/` headers/sources into
`atomic/`, `buttons/`, `comboboxes/`, `composite/` to mirror the Python
tree shape. That work was **shallow**: it moved files but did not port
the architecture. Reality check:

| Folder | Python files / LOC | C++ files / LOC | Gap |
|---|---|---|---|
| `buttons/` | 24 / 4386 | 2 / 175 | ~25× LOC, layered painter + capability + state machine architecture missing |
| `comboboxes/` | 5 / 663 | 1 / 44 | ~15× LOC, overlay + search + scrollable variants missing |
| `composite/unified_flyout/` (the real flyout system) | 13 / 2702 | 1 / 165 (legacy `flyout.h`) | ~16× LOC, delegate + panel + drag/drop + session/refresh missing |

A C++ `Button` of 57 LOC is a `QAbstractButton` subclass with one
`paintEvent` and four enum variants. The Python `Button` is a 709-LOC
shell composing **declarative specs** (`specs.py` — `ShapeSpec`,
`ContentSpec`, `RegionStyle`, `BehaviorSpec` dataclasses), a **regions
model** (`regions.py` — single/horizontal/vertical/grid/custom splits),
a **controller** (`controller.py` — input/state machine), a **typed
events bus** (`events.py`), **capabilities** (`capabilities/{long_press,
menu,scroll}`), and a **layered painter** (`painter.py` +
`layers/{background,content,divider,underline,strikethrough,badge,ripple}`).
The C++ build cannot reach pixel-for-pixel visual parity with Python
until this is ported.

#### B closed during this pass

- [x] **Toolkit primitives.** `Flyout`, `Toolbar`, `SectionHeader`,
  `ChipGroup`, `Icon`, `Divider` shipped as minimum-viable atomic /
  composite widgets. Painting style approximates Python but does not
  match the Python painter pipeline.
- [x] **Toolkit category tree.** Files reorganised into
  `{atomic,buttons,comboboxes,composite}/` per Python. **Cosmetic only**
  — file shape matches, architecture does not.
- [x] **Custom Title Bar polish.**
- [x] **Help dialog Markdown rendering.**
- [x] **Open-pair + primary comparison toggles in the toolkit `Toolbar`.**

#### B reframed — original bullet did not match reality

- [x] *"Replace inline `QFormLayout` with `SectionPanel`/`Group`/`InlineRow`."*
  These declarative composites **do not exist in Python `sli-ui-toolkit`**.
- [x] *"Port Python theme tokens (`sli_ui_toolkit/theme.json`)."*
  **There is no `theme.json`** in Python — theme is `theme_manager.py`,
  already wired into the C++ toolkit.

#### B blocked on the toolkit depth port (track D, below)

- [ ] **Move diff/channel and recording controls into the toolbar.**
  Surface decision depends on toolbar widget capabilities (split buttons,
  long-press, menu) that are part of the unported `buttons/` architecture.
- [ ] **Settings dialog visual pass.** Section icons, grouping, typography
  all read from the toolkit painter pipeline; cannot match Python until
  layers/specs are ported.
- [ ] **Pixel-for-pixel parity.** Requires the layered painter (track D).

#### Exit criterion (revised)

B closes when (a) track D ports the toolkit painter pipeline +
controller + capabilities, and (b) a screenshot-driven iteration session
runs both builds side-by-side. Neither is single-session work; both are
tracked under track D.

### D. Toolkit depth port — re-opened: logic stubs found in shipped «architecture»

A bootstrap-rewrite pass (shell visual parity) discovered that several
load-bearing connectors in the toolkit port are scaffolded with the
right shape but never wired to do their work. Full catalogue:
`docs/dev/TOOLKIT_PORT_AUDIT.md`. Highlights:

- `ButtonGroup::paintEvent` painted labels in the wrong position (top
  vs Python's centred bottom). Fixed.
- `CustomWindow` / `TitleBar` bypassed `Theme` entirely with hardcoded
  dark colours. Fixed.
- `Button::paintEvent` hardcodes `TextContent` — `region.icon` is
  ignored regardless of `setSpec`. **Fixed:** widget-scope content is
  now derived from the first region via `buildContentFromRegion`.
- `Painter::paint` region-scope only emits `TextContent` for text — no
  `IconContent` / `IconTextContent` / `RowsContent` selection. **Fixed:**
  same helper is used in the region-scope branch.
- `Button` has no ergonomic ctor (Python's `Button(icon, toggle=True,
  variant="surface")` has no 1-line C++ equivalent — caller must hand-
  build a `ButtonSpec`). **Fixed:** `Button::Config` + matching ctor
  build the spec and auto-attach Scroll/LongPress/Menu capabilities.
- `region.toggle` is not propagated to `QAbstractButton::setCheckable`.
  **Fixed** in `Button::setSpec`.

The shell can now drop its `QPushButton + QSS` workarounds and use
`sli::toolkit::Button({.icon = …, .toggle = true, .variant = …})`
directly. Remaining work in track D is a smoke-test pass over the
«suspect» capabilities (badge / underline / dropdown / scroll-wheel
end-to-end) — see `TOOLKIT_PORT_AUDIT.md` follow-up item #5.

All 7 phases of D landed in one pass. The Python `buttons/`,
`comboboxes/`, and `composite/unified_flyout/` architectures are now
mirrored in C++. Build green, `phase3_contracts` green.

**Honest scope note.** The *architecture* (decomposition into specs,
controller, painter, layers, capabilities, model, delegate, panel,
session, etc.) is faithfully ported. Visual *fidelity* (pixel-for-pixel
match against Python) is a follow-up that needs theme tokens beyond the
current `Palette` struct: Python resolves colors through string tokens
(`"button.toggle.background.pressed"`) while C++ maps them onto the 10
`Palette` members. Each layer's behavior is correct; some shade/alpha
choices will need tuning when a token system lands.

#### D. Original plan — all phases delivered

### D-archive. Original plan (delivered)

**Goal.** Bring `cpp/toolkit/` up to the architectural depth of Python
`sli_ui_toolkit/ui/widgets/`. Until this lands, every "visual parity"
bullet in B will keep returning as a half-done item.

**Why a dedicated track.** ~7000 LOC of declarative Python (specs,
regions, content, layered painter, capability composition, state
machine, dropdown menu, search overlay) cannot honestly be ported in
the same session as feature work. It needs its own design pass and
multiple staged sessions.

**Order of operations (dependency order).**

#### D1. `buttons/` foundations (no widget change yet)

- [x] Port `specs.py` (227 LOC, frozen dataclasses) → POD structs:
  `ShapeSpec`, `ContentSpec`, `RegionStyle`, `BehaviorSpec`,
  `ButtonSpec`, `{Click,Toggle,LongPress,Menu,Scroll}Behavior`.
- [x] Port `regions.py` (153 LOC) → `ButtonRegion`,
  `{Single,Horizontal,Vertical,Grid,Custom}Split`, `Divider`.
- [x] Port `content.py` (272 LOC) → `ButtonRow` and content cell types.
- [x] Port `context.py` (176 LOC) → typed render context passed through
  all layers.

#### D2. State + events

- [x] Port `state.py` → button state machine (idle/hover/pressed/
  disabled/checked/focused).
- [x] Port `events.py` (259 LOC) → typed event sink: click, long-press,
  menu-request, scroll-tick.
- [x] Port `controller.py` (188 LOC) → input/state coordinator binding
  events to state transitions.

#### D3. Painter pipeline

- [x] Port `painter.py` (160 LOC) → per-frame compose-and-paint
  orchestrator.
- [x] Port `layers/` as separate translation units:
  `layers/{background,content,divider,underline,strikethrough,badge,ripple}.cpp`.
  Each layer reads spec + state + context and paints into the shared
  paint device.

#### D4. Capabilities

- [x] Port `capabilities/base.py` → capability mixin interface.
- [x] Port `capabilities/long_press.py`, `menu.py`, `scroll.py`. Each
  plugs into the controller as opt-in.
- [x] Port `_dropdown_menu.py` (308 LOC).

#### D5. Public API (the actual `Button`)

- [x] Rewrite `buttons/button.cpp` as a thin shell composing spec +
  controller + painter + layers.
- [x] Port `variants.py` (178 LOC) → variant resolution from spec.
- [x] Port `style_api.py` (391 LOC) — paint-time style resolution
  against the theme palette.
- [x] Port `button_group.py` (97 LOC) → `ButtonGroup` composite widget.

#### D6. `comboboxes/` depth port

- [ ] `_models.py` (15) → typed model.
- [ ] `_overlay.py` (341) → drop-down overlay.
- [ ] `_search.py` (78) → search filter.
- [ ] `scrollable_combobox.py` (225) → scrollable variant.
- [ ] Rebuild `combo_box.cpp` shell over the above.

#### D7. `composite/unified_flyout/` depth port

The current `composite/flyout.cpp` (165 LOC) is a placeholder — Python
ships a full flyout system: `bootstrap`, `delegate`, `panel`,
`overlay_list_view`, `dragdrop`, `session`, `refresh`, `model`,
`layout`, `style`, `content`, `simple_adapter`, `common` (13 files,
2702 LOC).

- [x] Port the 13 unified_flyout modules in this order:
  `common → model → layout → style → content → delegate → panel
   → overlay_list_view → dragdrop → session → refresh → bootstrap
   → simple_adapter`.

#### Exit criterion for D

`cpp/toolkit/` mirrors `sli_ui_toolkit/ui/widgets/` not just in file
shape but in architecture: a `Button` is a thin shell over typed spec +
controller + layered painter, capabilities plug in via the controller,
and visual output matches Python pixel-for-pixel under the same theme.

#### Honest scope note

D is ~7000 LOC of port work across 50+ files. A realistic cadence:
- D1 in one session (foundational POD types, no widget change).
- D2 + D3 in one session (state + painter pipeline).
- D4 in one session (capabilities).
- D5 in one session (cutover; visual parity test moment).
- D6 separate session.
- D7 separate session (largest by LOC).

Until D5 lands, B remains open.

This pass takes B as far as it can go without an interactive
screenshot-driven loop. Items that *can* be closed in batch are closed;
items that genuinely require running the app side-by-side with the
Python build are split into a separate "visual iteration" session.

**Closed in this pass:**

- [x] **Toolkit primitives.** `Flyout`, `Toolbar`, `SectionHeader`,
  `ChipGroup`, `Icon`, `Divider` all shipped and exercised by the live
  shell (paint style matches `Button`/`ComboBox`/`CheckBox`/`SpinBox`).
- [x] **Custom Title Bar polish.** Maximise/restore glyph + tooltip +
  accessibility from `WindowStateChange`; hover ripple; drag-to-restore
  from maximized; window-scoped `Alt+F9/F10/F4`.
- [x] **Help dialog Markdown rendering.** `plugins/help/dialog.cpp:129`
  uses `QTextBrowser::setMarkdown` — the bullet's premise («today it's
  a plain `QLabel`/`QTextBrowser`») was stale.
- [x] **Open-pair + primary comparison toggles in the toolkit `Toolbar`.**

**Reframed — original bullet did not match reality:**

- [x] *"Replace inline `QFormLayout` with `SectionPanel`/`Group`/`InlineRow`."*
  These declarative composites **do not exist in Python `sli-ui-toolkit`**
  (they were proposals, not shipped widgets — see the deferral note at the
  top of this document). The tabs already use `SectionHeader` + `Divider`
  as the panel boundary; the `QFormLayout` *inside* each section is the
  contents, which is exactly how the Python tabs are organised. There is
  no parity gap to close here.
- [x] *"Port Python theme tokens (`sli_ui_toolkit/theme.json`)."*
  **There is no `theme.json`** in `sli-ui-toolkit`; the theme system is
  `theme_manager.py` (runtime palette swaps), already wired into the C++
  toolkit through `sli::toolkit::Theme`. The bullet describes a JSON-token
  pipeline that the Python build does not have.

**Deferred — needs a screenshot-driven visual iteration session, not batch refactoring:**

- [ ] **Move diff/channel and recording controls into the toolbar.**
  Requires running both builds side-by-side to settle button order,
  separator placement, label/icon mix, and the recording state-machine
  glyphs. Not a one-shot batch change.
- [ ] **Settings dialog visual pass.** Section icons, grouping density,
  typography. Same constraint — needs visual A/B against the Python
  build, plus the per-page page contracts already exist.

These two are the only true Visual/UX items left; both require a session
with `python -m src` running next to `imgsli_app` so styling can be
tuned against live reference. They are not blocked on any code in `cpp/`.

Exit criterion (revised): structural parity is closed; pixel-for-pixel
parity on the comparison toolbar and Settings dialog is owned by a
dedicated visual-iteration session.

### C. Feature / pipeline parity

Goal: close the remaining Python-only pipelines so the C++ build does
not silently lose features users depend on.

Concrete work:

- [x] **Virtual canvas layout.** The current Python ownership in
  `src/shared/rendering/layout_contract.py` and
  `src/ui/canvas_presentation/layout.py` is ported to Rust: normalized bounds,
  padding, canvas-px → display-px scale, and contain/stretch placement.
  Multi-image grid placement remains part of the dedicated full-grid item
  below, rather than this shared canvas contract.
- [x] **Shared PlanBuilder.** Single canonical Rust builder lives in
  `cpp/core/src/shared/rendering/plan_builder.rs` (PB-A: 16 cargo
  tests covering defaults, label fallback, split clamp, texture id
  stability, overlay slot/capture/guides synthesis, JSON round-trip).
  Cxx bridge exposes both a flat `build_canvas_render_plan` and a
  JSON `build_canvas_render_plan_json` router (PB-B) carrying the rich
  `OverlayLayout`. The C++ shell at
  `cpp/app/shared/rendering/plan_builder.{h,cpp}` (PB-D) is the only
  place that touches `imgsli::CanvasPlanInputs`; both
  `ComparisonController::apply()` and `MultiCompareGrid::refreshCells()`
  now build a `PlanInputs` and call `shared::rendering::buildCanvasRenderPlan(...)`
  (PB-E). The ad-hoc 20+ field copy in `comparison/controller.cpp` is
  gone; `multi_compare/grid.cpp` no longer duplicates plan defaults.
  - **PB-C (rich POD)** — `imgsli::app::CanvasRenderPlan` extended with
    `std::optional<OverlayLayoutPlan>` mirroring Rust `OverlayLayout`
    (`OverlaySlotPlan`, `OverlayCapturePlan`, `OverlayGuideSetPlan`,
    border / channel / diff / interp modes). The C++ shell routes
    through the JSON builder when `inputs.overlay` is set and
    deserialises the layout into the POD. `ComparisonController` opts in
    to the rich payload by default. The live QRhi render path keeps
    consuming the flat magnifier/capture/guides fields — the per-frame
    `executeFeatureCommand` pipeline mutates them on drag/scroll, which
    Python's static plan_builder doesn't have an analogue for; the rich
    `overlayLayout` is the read-only mirror for non-renderer consumers
    (composition trees, snapshot/replay tools, future multi-cell
    renderers). The shader / multi-slot uniforms rework that would
    *replace* the flat pipeline is intentionally out of scope — the
    flat pipeline is already a complete and load-bearing implementation
    of the same overlay semantics, not a stub.
- [x] **Session blueprints.** Port the actual
  `core/store_workspace.py::_apply_session_blueprint` contract for state slots,
  resource namespaces, and metadata defaults. The C++ startup command accepts
  the same JSON shape plus an optional `comparison` restore block for image
  pairs, current feature toggles, split/orientation, and analysis mode.
- [ ] **Async decode / scaling workers.** Move the remaining synchronous image
  import paths onto Qt's thread pool.
  - [x] Primary comparison decode and fit-to-canvas scaling use QtConcurrent
    with stale-result generation guards.
  - [x] Analysis reuses the fitted comparison pair and no longer performs
    synchronous scaling on demand.
  - [x] Multi-compare playlist decode/import is still synchronous and must be
    converted before large-grid batch import is viable.
- [ ] **Full multi-compare grid.** Replace the v1 2×2 with a
  parametrised N×M GL grid that renders all cells through a single
  QRhi pipeline (mirrors `tabs/multi_compare/ui/gl_grid.py`). Add
  drag-and-drop reorder, per-cell composition controls, multi-image
  export to a tiled PNG / video.
- [ ] **Video editor remainder.** The recorder, preview, thumbnail
  strip, trim/delete/undo, keyframes-via-interpolation, and FFmpeg raw
  pipe are done. Still missing: per-feature opt-in/out for keyframing,
  rendered preview cache, scrub-while-playing.
  - [x] Per-feature keyframe opt-in/out is persisted in the Rust project
    model and applied against the first-snapshot baseline during export.
  - [x] Rendered preview cache: shared offscreen renders use a bounded LRU
    keyed by the complete render plan, target size, and source image cache
    identities.
  - [x] Scrub-while-playing.
- [ ] **Multi-cell offscreen renderer.** Generalise
  `OffscreenRenderer` (track A) so the multi-compare grid and the
  video editor can both request batched offscreen renders without
  fighting for the same hidden `CanvasWidget`.
  - [x] Export, video preview/export, and multi-compare composite rendering
    share one serialized hidden `CanvasWidget`; live grid cells are no longer
    resized during export.
  - [x] Multi-compare uses the batch request API, avoiding one synchronous
    Plugin Registry round-trip per cell.
  - [x] Adopt bounded batch/chunk requests for video frame sequences.

Exit criterion: opening a Python-built session blueprint in the C++
build reproduces the same visual output, no Python module imported at
runtime from `src/` is required for the C++ feature set.

## Cross-cutting

- Keep `cargo test --workspace`, `cargo fmt --check`,
  `cargo clippy --workspace --all-targets -- -D warnings`, and
  `ctest --test-dir cpp/build --output-on-failure` green on every
  change. The contract-check ctest is the single load-bearing
  integration test; extend it as new contracts are introduced.
- New cargo tests go alongside the Rust module they cover. C++
  components without an existing GoogleTest target should at minimum
  add an entry to `phase3_contracts` so the smoke binary catches
  regressions.
- The Wayland decoration issue is documented in
  `cpp/app/custom_window.cpp` and `canvas_widget.cpp`. Do not regress
  it by re-introducing `WA_NativeWindow` on top-levels or by attaching
  a `QVulkanInstance` to the top-level window.
