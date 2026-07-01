# Tab Ownership Audit

Дата аудита: 2026-06-27.

Этот документ фиксирует проблему после миграции `image_compare`: часть кода
осталась в `src/ui`, `src/plugins`, `src/services`, `src/shared` и `src/core`
под видом generic/platform кода, хотя фактически обслуживает только
`tabs/image_compare`.

## Ownership Rule

Код остаётся вне `src/tabs/<tab>/` только если он действительно нужен host shell
или нескольким независимым владельцам.

Практическое правило:

- если файл нужен только `image_compare`, он живёт в `src/tabs/image_compare`;
- если файл нужен `image_compare` и `multi_compare`, он может остаться shared,
  но должен быть очищен от терминов `image1/image2`, `diff_mode`, `magnifier`,
  `divider`, `capture`, `filename_overlay` там, где это не часть generic API;
- если shared файл знает конкретное имя tab, это нарушение `docs/dev/TAB_CONTRACT.md`;
- plugins не должны быть свалкой для tab-owned logic. Plugin остаётся plugin
  только если он предоставляет самостоятельную capability нескольким tabs или
  host shell.

## Confirmed Multi-Compare Shared Surface

`multi_compare` реально использует ограниченный набор host/shared API:

- `ui.canvas_presentation.composition` для composition tree;
- `ui.canvas_presentation.plan` и generic composition-dispatch часть
  `plan_applicator` для multi export;
- `ui.widgets.canvas.rhi_backend` и `ui.widgets.canvas.runtime` для QRhi setup;
- `ui.context_menu.manager/models`;
- generic UI helpers: `ui.icon_manager`, `ui.theming`,
  `ui.widgets.form_controls`, `StartupPlaceholder`, `ZoomIndicator`,
  `FontSettingsFlyout`;
- `plugins.image_properties` как общую dialog capability;
- settings event для смены UI mode.

Что `multi_compare` не использует и поэтому не оправдывает нахождение в shared:

- `ui.canvas_presentation.plan_builder`;
- `ui.canvas_features` / `tabs.image_compare.canvas.features`;
- `ui.presenters.image_canvas`;
- `services.workflow.playlist` (removed from `src/services/workflow`);
- `plugins.comparison` (removed from `src/plugins/comparison`);
- большинство `plugins.export` image-pair pipeline;
- video-editor keyframing adapters for magnifier/splitter/diff.

## High-Severity Leaks

### Plugin discovery still scans legacy root plugins

Статус: live legacy surface, not just dead files.

Evidence:

- `core.plugin_system.registry.PluginRegistry.discover_plugins()` scans both
  top-level `plugins` and `tabs`;
- any package under `src/plugins/<name>/plugin.py` with `@plugin(...)` is still
  imported and registered on startup;
- this means migrated code left in `src/plugins` is not harmless clutter: it can
  still subscribe to events, expose capabilities, load QSS/i18n roots, and hold
  process-wide services.

Root plugins currently still registered:

- `plugins.analysis` — package deleted; pure processing moved to
  `shared.analysis`, image-pair services moved to
  `tabs.image_compare.services.analysis`.
- `plugins.export` — mixed; dialog/path shell may stay, but still-image export,
  quick-save comparison, clipboard paste image loading, recorder bootstrap, and
  image-pair export service are legacy roots after `image_compare` and
  `multi_compare` grew tab-owned export paths.
- `plugins.settings` — legitimate host plugin, but still contains migrated
  tab-owned canvas-feature controls through gateway/color-picker/application
  settings paths.
- `plugins.video_editor` — legitimate session plugin, but preview/keyframing
  adapters still include image_compare feature tracks until a render-source
  contract replaces them.
- `plugins.image_properties` — legitimate shared capability used by multiple
  image tabs.
- `plugins.help` and `plugins.layout` — likely legitimate host plugins.

Action:

- split `src/plugins` into "true host/capability plugins" vs "migrated tab
  leftovers";
- after a plugin capability is tab-owned, remove its top-level `plugin.py` so
  plugin discovery cannot register both the old and new owner;
- add a contract that top-level plugins cannot be introduced without an explicit
  owner classification (`host`, `cross-tab capability`, or `session plugin`).

### `src/plugins/comparison`

Статус: removed from `src/plugins/comparison`; ownership now lives in
`tabs/image_compare/plugin.py` and tab use-cases.

Проблемы:

- plugin still creates `session_type="image_compare"`;
- duplicates image loading/navigation/list operations;
- `session_controller.py` calls image canvas invalidation/update paths;
- lives in `plugins/`, so it bypasses tab ownership and discovery boundary.

Completed:

- `tabs/image_compare/plugin.py` registers the same `@plugin(name="comparison")`
  service and adds the `image_compare.state` session slot;
- no live imports of `plugins.comparison` remain outside this audit text;
- `src/plugins/comparison/` was deleted;
- `src/plugins/comparison/plugin.py` was removed from
  `tests/contracts/test_platform_isolation.py` allowlist.

### `src/services/workflow/playlist*`

Статус: removed from `src/services/workflow`; tab-owned implementation remains
under `tabs/image_compare/services/playlist*`.

Проблемы:

- code manipulates `store.document.image1_path`, `image2_path`,
  `preview_image1/2`, `original_image1/2`, `full_res_image1/2`;
- duplicates `src/tabs/image_compare/services/playlist*`;
- no evidence that `multi_compare` imports it.

Completed:

- `src/services/workflow/playlist.py` and
  `src/services/workflow/playlist_components/` were deleted;
- no live imports of `services.workflow` remain outside this audit text;
- `tabs/image_compare/plugin.py` imports
  `tabs.image_compare.services.playlist.PlaylistManager`.

### `src/ui/presenters/image_canvas`

Статус: removed from `src/ui/presenters/image_canvas`; implementation lives in
`tabs/image_compare/presenters/image_canvas`.

Completed:

- `src/ui/presenters/image_canvas/` was deleted;
- all direct code imports use `tabs.image_compare.presenters.image_canvas`;
- `ui.presenters.main_window.features` no longer imports or constructs
  `ImageCanvasPresenter`;
- `tabs.contract.TabContract.create_main_window_feature()` and
  `tabs.registry.TabRegistry.create_main_window_feature()` provide a transition
  hook so the host requests the legacy `"image_canvas"` feature through tab
  discovery instead of importing tab internals.

### `src/ui/context_menu/image_compare.py`

Статус: removed from host package; tab-specific provider lives under
`tabs/image_compare/ui/context_menu.py`.

Completed:

- `src/ui/context_menu/image_compare.py` was deleted;
- `tests/contracts/test_platform_isolation.py` now fails if the old path
  reappears;
- host `ui.context_menu` keeps manager/models only.

### `src/ui/canvas_features`

Статус: removed from `src/ui`; image_compare features live under the tab.

Completed:

- feature implementations live under
  `src/tabs/image_compare/canvas/features`;
- host `ui.canvas_infra.scene.*_registry` discovers only packages registered by
  a tab hook and does not import `tabs.image_compare` directly;
- `ImageCompareTab.register_canvas_features()` registers scene/widget/render
  feature packages through the TabContract lifecycle;
- contract framework helpers now scan
  `src/tabs/image_compare/canvas/features`, not the removed
  `src/ui/canvas_features`;
- `tests/contracts/test_platform_isolation.py` now fails if the old
  `src/ui/canvas_features` directory reappears.

## Pseudo-Generic Canvas/Presentation Layer

### `src/ui/canvas_presentation/plan_builder.py`

Статус: moved to `tabs/image_compare/canvas/presentation/plan_builder.py`.

Evidence:

- builds two-image store snapshots (`image1`, `image2`);
- handles `diff_mode`, `channel_mode`, `ssim`, `capture`, `guides`,
  `divider`, `magnifier` overlay layout;
- imported by export/video-editor image-pair paths and image_compare presenter;
- not imported by `multi_compare`.

Completed:

- `src/ui/canvas_presentation/plan_builder.py` was deleted;
- image_compare presentation helpers live under
  `tabs/image_compare/canvas/presentation`;
- image-pair export plan construction moved from
  `plugins.export.services.snapshot_render_plan_builder` to
  `tabs.image_compare.services.snapshot_render_plan_builder`;
- `tests/contracts/test_platform_isolation.py` now fails if the old export
  snapshot builder path reappears.

Completed:

- `plugins.video_editor.services.video_snapshot_rendering` no longer imports
  `tabs.image_compare` directly;
- image_compare-specific snapshot frame rendering moved to
  `tabs.image_compare.services.video_snapshot_rendering`;
- the generic plugin module is now a neutral facade/factory backed by
  `TabRegistry.create_service("snapshot_frame_renderer", ...)`;
- `tabs.contract.TabContract.create_service()` provides the transition service
  hook for tab-owned integrations that legacy plugins still request.

### `src/ui/canvas_presentation/plan_applicator.py`

Статус: legacy two-image implementation moved to image_compare; shared module
is now a thin composition dispatcher + compatibility service wrappers.

Used by:

- `multi_compare` export/composition path;
- image_compare live/export path;
- video preview/export.

Completed:

- legacy texture upload / scene-only update logic moved to
  `tabs/image_compare/canvas/presentation/plan_applicator.py`;
- shared `ui.canvas_presentation.plan_applicator` resolves composition plans
  locally and routes non-composition plans through
  `TabRegistry.create_service("canvas_legacy_render_plan", ...)`;
- `apply_plan_runtime_overlays()` and `_sync_geometry_state()` remain only as
  compatibility wrappers that call image_compare tab services;
- live split sync now routes through
  `TabRegistry.create_service("canvas_plan_split_sync", ...)`;
- live runtime overlay application now routes through
  `TabRegistry.create_service("canvas_live_runtime_overlays", ...)`;
- snapshot/export guides/capture parameter application now routes through
  `TabRegistry.create_service("canvas_snapshot_overlay_params", ...)`;
- `ImageCompareTab` owns the splitter alias and live feature overlay registry
  calls plus snapshot guides/capture canvas setters behind those services;
- `tests/contracts/test_canvas_features_imports.py` now fails if
  `plan_applicator.py` reintroduces direct canvas feature command lookups,
  live overlay registry calls, snapshot guides/capture setters,
  `set_pil_layers`, texture-cache checks, source image pair references, or the
  `splitter.sync_split_position` alias.

Action:

- migrate remaining callers off the compatibility wrappers where practical;
- `multi_compare` must keep depending only on the generic composition
  applicator.

### `src/ui/canvas_presentation/render_arch.py`

Статус: cleaned; shared module now contains only generic `RenderIntent`.

Completed:

- image_compare render scene/list/style primitives moved to
  `tabs/image_compare/canvas/render_arch.py`;
- neutral filename label style moved to
  `ui/canvas_presentation/label_style.py` so `multi_compare` can keep using
  shared label rasterization without importing image_compare;
- `ui.canvas_presentation.__init__` no longer exports image_compare render
  primitives from the shared package;
- `tests/contracts/test_canvas_widget_ownership.py` now fails if
  `ui.canvas_presentation.render_arch` reintroduces split/diff/channel,
  filename/capture/guides/divider, or image-pair render-list classes.

### `src/ui/widgets/canvas`

Статус: split; shared package keeps only generic QRhi/runtime/render utilities.

Problems:

- remaining `ui.widgets.canvas` files are generic utilities:
  `render.py`, `render_common.py`, `render_executor.py`, `render_metrics.py`,
  `render_passes.py`, `rhi_backend.py`, `rhi_render.py`, `runtime.py`.

Completed:

- image_compare-owned entrypoint added at
  `tabs/image_compare/canvas/widget.py`;
- `ImageCompareTab.create_service("canvas_widget_class")` exposes the pair
  canvas class through the tab registry;
- host/export/video code now creates tab-provided canvases via
  `shared.rendering.tab_canvas_services`, not direct
  `from ui.widgets.canvas import CanvasWidget/GLCanvas`;
- pair-canvas implementation files moved to `tabs/image_compare/canvas/`,
  including `widget.py`, `state.py`, `interaction.py`, `scene.py`,
  `render_context.py`, `rhi_renderer.py`, `rhi_feature_common.py`,
  `feature_overlay_gpu.py`, `texture_parts/`, `shader_sources/`, and
  `shaders/`;
- `helpers.py` and `contracts.py` moved to image_compare because they expose
  pair-canvas methods like `set_pil_layers`, capture/guides, diff source, and
  split sync;
- image_compare style tokens moved to `tabs/image_compare/canvas/style_tokens.py`;
- plugins request canvas services through `shared.rendering.tab_canvas_services`
  and `ImageCompareTab.create_service()`, not by importing tab internals;
- `tests/contracts/test_canvas_widget_ownership.py` fails if app code
  reintroduces public pair-canvas imports from the shared facade or if
  pair-canvas modules return to `ui.widgets.canvas`.

## Host UI Leaks

### `src/ui/main_window/*`

Files with image_compare ownership leaks:

- `ui.py`: used to create image_compare primitive widgets/buttons/sliders
  (moved behind the tab factory);
- `layouts.py`: used to fetch `get_tab("image_compare")`, assemble tab page,
  and call `sync_session_mode("image_compare")`;
- `translations.py`: binds image_compare tooltips/labels;
- `startup.py`: image-pair startup state and magnifier button references;
- `window.py`: image_compare-specific setters for divider/diff/channel actions;
- `appearance.py`: canvas styling hooks.

Completed:

- `ui.main_window.layouts` now asks `TabRegistry.assemble_host_pages(ui)` to
  assemble legacy tab pages instead of naming `image_compare`;
- `ui.main_window.ui.sync_session_mode()` now delegates tab-specific host chrome
  state to `TabRegistry.apply_host_session_mode()` instead of checking
  `session_type == "image_compare"`;
- `ImageCompareTab` owns the transitional host-page assembly and edit-layout
  visibility hooks;
- `ImageCompareTab.assemble_host_page()` now runs
  `ImageComparePrimitivesFactory`, so image_compare buttons/sliders/canvas are
  created from `tabs/image_compare/ui/primitives.py`, not
  `ui.main_window.ui`;
- `tests/contracts/test_canvas_widget_ownership.py` now fails if
  `ui.main_window.ui` reintroduces image_compare primitive construction helpers
  or direct pair-canvas factory usage;
- `ui.main_window.translations` now binds only host window chrome and asks tabs
  to install their own translations through
  `TabRegistry.create_service("install_translations", ui)`;
- image_compare primitive labels/tooltips/placeholder bindings moved to
  `tabs.image_compare.ui.translations`;
- `tests/contracts/test_platform_isolation.py` now has an empty allowlist and
  passes with no platform file allowed to mention `image_compare`.
- `ui.main_window.window` no longer exposes `set_divider_button_color`,
  `configure_diff_mode_actions`, or `configure_channel_mode_actions`;
  callers touch `ui.btn_orientation` / `ui.btn_diff_mode` / `ui.btn_channel_mode`
  directly from tab/plugin code that already has access to `ui`.
- `ui.main_window.startup.has_initial_canvas_content()` now delegates to the
  `has_initial_canvas_content` tab service and no longer reads
  `document.image1_path` / `image2_path` / `original_image1/2` directly.
- Post-bootstrap image_compare button refresh (`btn_magnifier_color_settings*`)
  moved behind the `refresh_startup_button_visuals` tab service; the concrete
  button list lives in `tabs/image_compare/ui/startup_readiness.py`.
- `ui.main_window.appearance.update_image_label_background()` now paints only
  host chrome (`_startup_placeholder`, `_startup_cover`) and delegates
  image-label / image-container / QRhiWidget theming to the tab through
  `TabRegistry.apply_appearance(window)`; the duplicated image_compare-specific
  branch was removed.

Remaining:

- `startup.py`, `window.py`, and `appearance.py` still need follow-up ownership
  review outside the platform-literal allowlist.

Action:

- host creates only shell/workspace/tab-strip/chrome;
- image_compare tab creates and translates its own primitive widgets;
- host communicates through TabContract lifecycle/services, not `ui.btn_*`
  image_compare attributes.

### `src/ui/presenters/main_window/*` and `src/ui/presenters/toolbar/*`

Problems:

- `features.py` used to import and construct `ImageCanvasPresenter` (now moved
  behind `TabRegistry.create_main_window_feature`);
- `presenter.py` calls `features.image_canvas.*`;
- workspace defaults used to mention `image_compare` (removed from
  `core.store_workspace` and `ui.presenters.main_window.workspace`).

Completed:

- `ui.presenters.main_window.workspace` no longer hardcodes the
  `image_compare` session label or fallback active session type;
- no-active workspace fallback now uses `session_picker`;
- `src/ui/presenters/main_window/workspace.py` was removed from
  `tests/contracts/test_platform_isolation.py` allowlist.
- `ui.presenters.main_window.state` no longer checks
  `session_type == "image_compare"`; it now detects comparison-capable sessions
  through blueprint resource namespaces and was removed from the platform
  isolation allowlist.
- `ToolbarPresenter` and its `toolbar/{connections,orientation,state}.py`
  helpers moved from `ui.presenters` to
  `tabs.image_compare.presenters`;
- `ui.presenters.main_window.features` now requests the toolbar through
  `TabRegistry.create_service("toolbar_presenter", ...)` instead of importing
  the tab-owned presenter class directly;
- `tests/contracts/test_canvas_widget_ownership.py` now fails if the
  image_compare toolbar presenter source files reappear under `ui.presenters`.

Action:

- host presenter can expose `get_active_tab_feature(feature_id)` only through
  TabContract/registry;
- continue reducing host presenter calls into `features.image_canvas` and
  `features.toolbar` where they are still image_compare-specific facades.

### `src/ui/managers/*magnifier*`

Status: partially moved to image_compare feature UI.

Physical leftovers:

- `ui.managers.ui_manager_parts.bootstrap` still installs event filters on
  `btn_magnifier`, but creates the tab-owned `MagnifierVisibilityFlyout`
  through `TabRegistry`.

Completed:

- `ui.managers.transient_ui_parts.magnifier` moved to
  `tabs.image_compare.ui.transient_magnifier`;
- `ui.managers.transient_ui_parts.magnifier_instances` moved to
  `tabs.image_compare.ui.transient_magnifier_instances`;
- `TransientUIManager` now requests `magnifier_visibility_controller` and
  `magnifier_instances_popup_controller` tab services instead of importing
  feature controllers from shared managers;
- `ui.managers.transient_ui_parts.flyouts` (image_compare pair combo/unified
  flyout logic touching `combo_image1/2`, `image_list1/2`) moved to
  `tabs.image_compare.ui.transient_flyouts`; `TransientUIManager` requests it
  through the `unified_flyout_controller` tab service;
- `ui.managers.transient_ui_manager` no longer exposes the magnifier facade
  methods (`update_magnifier_flyout_states`,
  `on_magnifier_toggle_with_hover`,
  `show/hide_magnifier_visibility_flyout`,
  `show/hide_magnifier_instances_popup`,
  `on_magnifier_instances_count_changed`); host `UIManager` private
  callbacks now route directly through `self.transient.magnifier.*` and
  `self.transient.magnifier_instances.*` tab services;
- image_compare-specific popup close/hide/focus branches moved out of
  `ui.managers.transient_ui_parts.closing` into
  `tabs.image_compare.ui.popup_closing.ImageComparePopupClosing`; the host
  `PopupClosingController` obtains it through the
  `popup_close_extension` tab service. Host `closing.py` no longer knows
  `combo_image1/2`, `btn_diff_mode`, `btn_channel_mode`, `btn_magnifier`,
  `unified_flyout`, or magnifier flyout state; only font/interpolation
  primitives and the drag/overlay hooks remain.
- `tests/contracts/test_canvas_widget_ownership.py` now fails if these
  transient controller files reappear under `ui/managers/transient_ui_parts`.

Action:

- generic `ui.managers` keeps dialog/message/tray and generic popup primitives
  only.

### `src/ui/widgets/magnifier_*`

Status: moved to image_compare tab UI.

Problems:

- completed; these are feature widgets, not generic reusable controls.

Completed:

- `ColorSettingsButton` and `MagnifierColorOptionsFlyout` moved from
  `ui.widgets.magnifier_color_controls` to
  `tabs.image_compare.ui.magnifier_color_controls`;
- `MagnifierVisibilityFlyout` moved from
  `ui.widgets.magnifier_visibility_flyout` to
  `tabs.image_compare.ui.magnifier_visibility_flyout`;
- `ImageComparePrimitivesFactory` imports the color button from the tab-owned
  module;
- host `ui.managers.ui_manager_parts.bootstrap` now creates the visibility
  flyout through `TabRegistry.create_service("magnifier_visibility_flyout", ...)`
  instead of importing the tab widget directly;
- `tests/contracts/test_canvas_widget_ownership.py` now fails if those feature
  widget files reappear under `ui/widgets`.

Action:

- continue moving magnifier transient controllers out of `ui.managers`; leave
  only generic flyout/button primitives in `sli-ui-toolkit` or `ui.widgets`.

## Plugins

### `plugins.analysis`

Status: package deleted; pure processing lives under `shared.analysis`,
image-pair services live under `tabs.image_compare.services.analysis`.

Completed:

- `plugins.analysis.plugin`, `controller`, `events`, `state`, `settings`, and
  empty `ui` package were deleted;
- image_compare analysis event dataclasses now live in
  `tabs.image_compare.events`;
- `ComparisonPlugin` subscribes to analysis metric/diff/channel events and
  routes them to `SessionController`;
- toolbar and settings emit image_compare-owned analysis events instead of
  importing `plugins.analysis.events`;
- pure processing modules (`calculate_psnr`, `calculate_ssim`,
  diff/channel/edge builders, `build_cached_diff_image`) moved from
  `plugins.analysis.processing` to `shared.analysis`;
- `MetricsService`, `CachedDiffService`, `AnalysisRuntime`,
  `CoreUpdateDispatcher`, `UIUpdateDispatcher` moved from
  `plugins.analysis.services` to `tabs.image_compare.services.analysis`;
- `src/plugins/analysis/` was deleted entirely;
- `tests/contracts/test_platform_isolation.py` now fails if any
  `plugins/analysis` sub-path reappears.

### `plugins.export`

Status: mixed, still image_compare-heavy but feature-query ownership improved.

Problems:

- still-image save/export orchestration is still initiated by the root
  `ExportPresenter`, even though image-pair context and rendering services are
  now tab-owned;
- `multi_compare` has its own export implementation under
  `tabs/multi_compare/plugins/export`.
- `ExportPlugin` is still auto-registered from `src/plugins/export/plugin.py`;
- `ExportPlugin.configure_controller()` still creates `Recorder` and video
  exporter services from the root plugin, so recording flows still enter
  through a migrated-but-live root plugin;
- paste still enters through the root export event subscription, but the
  implementation behind it is now tab-owned;

Completed:

- `plugins.export.services.snapshot_render_plan_builder` moved to
  `tabs.image_compare.services.snapshot_render_plan_builder`;
- image_compare-specific export feature queries for divider/guides/magnifier
  moved out of `plugins.export.services.gpu_export_scene` and into the
  tab-owned snapshot builder;
- `plugins.export.services.still_snapshot_bounds` was deleted; still snapshot
  bounds are calculated by `tabs.image_compare.services.snapshot_render_plan_builder`;
- `tests/contracts/test_plugins_isolation.py` now fails if
  `plugins.export` calls the canvas feature registry directly.
- `plugins.export.services.gpu_export_scene` was deleted; image_compare export
  scene construction now lives in `tabs.image_compare.services.gpu_export_scene`;
- `qimage_to_pil` moved to `shared.image_processing.qt_conversion` and is shared
  by tab export helpers instead of living in the old root export module;
- `tests/contracts/test_platform_isolation.py` now fails if the old
  `plugins/export/services/gpu_export_scene.py` path reappears.
- `ExportPlugin` no longer creates `ExportService`, exposes an `export_image`
  UI component, or handles the legacy `export_image` command directly; still
  image-pair export now enters through the window `ExportPresenter` path until
  that orchestration moves behind a tab-owned export service;
- `tests/contracts/test_plugins_isolation.py` now fails if
  `plugins.export.plugin` reintroduces the direct image-pair export command.
- `ExportContextBuilder` moved from `plugins.export.presenter_parts` to
  `tabs.image_compare.services.export_context_builder`; it now imports
  image_compare live snapshot, still snapshot bounds, and snapshot renderer
  directly from the tab-owned service package instead of assembling image-pair
  render context inside the root export plugin.
- `ExportPresenter` obtains that builder through
  `TabRegistry.create_service("export_save_context_builder", ...)`, so
  `plugins.export` does not import `tabs.image_compare` directly.
- `tests/contracts/test_platform_isolation.py` now fails if the old
  `plugins/export/presenter_parts/context_builder.py` path reappears.
- `plugins.export.services.image_export` was deleted; the image-pair
  `ExportService` now lives in `tabs.image_compare.services.image_export` and
  imports tab-owned live snapshot, still bounds, and snapshot renderer services.
- `ExportPresenter` obtains that service through
  `TabRegistry.create_service("image_export_service", ...)`, keeping the root
  export plugin as a consumer of the active tab's export capability.
- `tests/contracts/test_plugins_isolation.py` and
  `tests/contracts/test_platform_isolation.py` now fail if the old root
  image-pair export service returns.
- `services.system.clipboard` was deleted; the image-slot paste implementation
  now lives in `tabs.image_compare.services.clipboard`, and `ExportPlugin`
  obtains it through `TabRegistry.create_service("clipboard_paste_service", ...)`.
- contracts now fail if the old generic clipboard service path or direct
  `services.system.clipboard` import returns.
- after `image_export` and `export_context_builder` moved into
  `tabs.image_compare`, the unused root
  `plugins.export.services.still_snapshot_bounds` facade was deleted too.
- the dead root `ExportExportRecordedVideoEvent` path was removed:
  no dataclass, no `Events.EXPORT_EXPORT_RECORDED_VIDEO`, no event-bus
  subscription, no `ExportController.export_recorded_video()` wrapper, and no
  unused `VideoExportFlow.export_recorded_video()` method remain. Video export
  continues through the video-editor `export_video_from_editor` path.
- `ExportPlugin` no longer imports or constructs
  `plugins.video_editor.services.recorder.Recorder` or
  `plugins.video_editor.services.export.VideoExporterService` directly;
  `VideoEditorPlugin.create_recording_services(...)` owns construction and the
  root export plugin consumes the returned services.
- `tests/contracts/test_plugins_isolation.py` now fails if
  `plugins.export.plugin` starts constructing video-editor services directly
  again.
- `plugins.export.services.recording_flow` and
  `plugins.export.services.video_export_flow` were deleted; the flow classes
  now live in `plugins.video_editor.services.recording_flow` and
  `plugins.video_editor.services.export_flow`, so root export no longer owns
  video-editor recording/export orchestration modules.
- removed-path contracts now fail if those root flow modules return.
- the dead root `ExportQuickSaveComparisonEvent` path was removed:
  no dataclass, no `Events.EXPORT_QUICK_SAVE_COMPARISON`, no event-bus
  subscription, and no `quick_save_comparison` command wrappers remain. The
  active quick-save button still calls the export presenter path directly.
- root `plugins.export.presenter_parts` image-pair pieces were deleted:
  `state.py` moved to `tabs.image_compare.services.export_state`,
  `save_flow.py` moved to `tabs.image_compare.services.export_save_flow`, and
  `ExportSaveContext` moved out of `plugins.export.models` into
  `tabs.image_compare.services.export_models`.
- `ExportPresenter` obtains state/save-flow/context/export service through
  tab services; root export no longer imports `plugins.export.presenter_parts`.
- the image-pair worker task that unpacks `original1_full/original2_full` moved
  from `ExportPresenter` into `tabs.image_compare.services.export_save_flow`,
  so the root presenter no longer knows the save-context payload shape.
- unused root `plugins.export.settings` and `plugins.export.state` files were
  deleted; no live imports referenced them.

Action:

- split generic export shell/dialog/path handling from image_compare renderer;
- continue moving image-pair still export orchestration to image_compare;
- keep only truly shared output path/dialog primitives in plugin/shared UI.
- move quick-save comparison, still-image pair export, clipboard paste into
  `tabs/image_compare` services or tab-contributed export actions;
- keep root `plugins.export` only as a host export dialog/capability dispatcher,
  or remove it if every tab contributes its own export plugin.

### `plugins.video_editor`

Status: cross-feature plugin, with snapshot rendering partially decoupled from
the image_compare render model.

Problems:

- snapshots are `image1_path`/`image2_path`;
- keyframing adapters know `comparison.diff_mode`,
  `comparison.channel_view_mode`, `magnifier.*`, `splitter.*`,
  `filename_overlay.*`;
- preview uses pair canvas/render plan;
- `open_image_compare()` used to hardcode the image_compare session type.

Completed:

- snapshot frame renderer construction goes through the tab service hook;
- the image_compare renderer implementation lives under
  `tabs.image_compare.services.video_snapshot_rendering`;
- video export global bounds construction now goes through
  `TabRegistry.create_service("global_canvas_bounds", ...)`; image_compare
  owns feature layout requirement evaluation and
  `plugins.video_editor.services.video_export_bounds` keeps only a featureless
  fallback;
- recorder/debug magnifier queries and dynamic magnifier keyframing adapter no
  longer import canvas feature command registries directly; they use the
  video-editor tab-service gateway;
- `tests/contracts/test_platform_isolation.py` now passes for
  `plugins.video_editor.services.video_snapshot_rendering`.
- `open_image_compare()` now resolves the comparison-capable session via the
  `"comparison"` resource namespace declared by session blueprints, instead of
  naming the image_compare tab directly;
- `src/plugins/video_editor/model.py` was removed from the platform isolation
  allowlist.

Action:

- define a render-source contract for video editor;
- continue moving image_compare-specific recorder/keyframing semantics to
  tab-owned packages;
- keep timeline/export encoding/playback generic.

### `plugins.settings`

Status: mixed, with performance page tab gating, direct feature-command
registry calls, root color-picker parts, named canvas-feature controller
wrappers, root application-service feature application, and root concrete
feature bootstrap/persist removed.

Problems:

- global settings manager persists canvas feature settings;
- performance page used to contain image rendering groups unless contributed by
  image_compare.
- `plugins.settings.manager` still owns a generic canvas-feature property sweep
  (`get_canvas_feature_properties()` serialization), which is registry-based but
  still physically lives in the root settings plugin.
- root `SettingsDialogData` / dialog context still expose flat image_compare
  performance fields; the section-payload mechanism is now available (see
  `SettingsRegistry.register_payload_reader/seeder` and
  `SettingsDialogData.tab_extras`) but the concrete image_compare fields are
  still populated flat for backward compatibility until each field migrates
  through the tab's payload reader.

Completed:

- `plugins.settings.pages.performance` now builds only platform render-backend
  settings and consumes tab-specific extras from `SettingsRegistry`;
- it no longer mentions `image_compare` and was removed from platform
  isolation allowlist.
- settings controller/manager/application service no longer call
  `get_canvas_feature_command*` directly; they go through
  `plugins.settings.canvas_feature_gateway`, which dispatches via
  `TabRegistry.create_service(...)`;
- `ImageCompareTab` owns execution of settings canvas-feature commands through
  the `canvas_feature_command` and `canvas_feature_command_alias` tab services;
- `tests/contracts/test_plugins_isolation.py` now fails if `plugins.settings`
  reintroduces direct canvas feature command registry calls.
- unused `plugins.settings.color_actions` was deleted; its duplicate modal
  magnifier color picker path was no longer called, while the live non-modal
  color picker path remains in the presenter coordinator until it is moved
  behind an image_compare tab service.
- `plugins.settings.presenter_parts.color_pickers` was deleted; the live canvas
  feature color picker coordinator now lives in
  `tabs.image_compare.ui.settings_color_pickers` and is requested by
  `SettingsPresenter` through
  `TabRegistry.create_service("settings_color_picker_coordinator", ...)`.
- contracts now fail if root settings presenter parts reintroduce canvas
  feature color picker ownership.
- `plugins.settings.controller` no longer exposes named image_compare canvas
  feature wrappers such as `set_magnifier_*`, `set_guides_*`, or
  `set_capture_*`; tab-owned UI calls the generic
  `execute_canvas_feature_alias(...)` gateway instead.
- contracts now fail if those image_compare feature wrappers reappear on the
  root settings controller.
- magnifier/guides viewport setting application moved from
  `plugins.settings.application_service` to
  `tabs.image_compare.ui.settings_application`, requested through
  `TabRegistry.create_service("settings_viewport_application", ...)`.
- contracts now fail if root `plugins.settings.application_service`
  reintroduces image_compare feature aliases/keys or direct canvas feature
  command registry usage.
- concrete magnifier/guides startup and persistence moved from
  `plugins.settings.manager` to
  `tabs.image_compare.ui.settings_persistence`, requested through
  `settings_canvas_feature_load` / `settings_canvas_feature_save` tab services.
- contracts now fail if root `plugins.settings.manager` reintroduces concrete
  image_compare feature aliases/keys such as `overlay.settings*`,
  `guides.set_smoothing*`, or `optimize_magnifier_movement`.
- `SettingsDialogData` / `SettingsDialogContext` now expose a
  `tab_extras: dict[str, dict[str, Any]]` section-payload dict, plus
  `SettingsRegistry.register_payload_reader/seeder` hooks. `SettingsDialog`
  seeds `context.tab_extras` on construction and reads
  `data.tab_extras` on submit — tabs can register their own field readers
  without extending the root dataclass.

Action:

- settings shell/registry stays plugin;
- tab-owned settings sections and color pickers move to image_compare via
  `TabContract.contribute_settings`;
- generic settings plugin must not mention feature IDs owned by a tab.
- decide whether the remaining generic canvas-feature property sweep belongs in
  a host extension point or in tab-owned settings contributions.
- migrate concrete image_compare performance fields
  (`optimize_magnifier_movement`, `magnifier_interpolation_method`,
  `optimize_laser_smoothing`, `laser_interpolation_method`,
  `zoom_interpolation_method`, `magnifier_intersection_highlight_enabled`,
  `magnifier_auto_color_new_instances`, `auto_calculate_psnr`,
  `auto_calculate_ssim`, `auto_crop_black_borders`) from flat
  `SettingsDialogData` fields into `tab_extras["image_compare_performance"]`
  through a payload reader in `tabs.image_compare.ui.settings_application`;
  similarly move `video_recording_fps` under
  `tab_extras["video_editor_recording"]`.

### `plugins.image_properties`, `plugins.help`, `plugins.layout`

Status:

- `image_properties` is a shared capability used by both image tabs;
- `help` appears host/plugin-level and can stay, pending normal dependency
  checks;
- `layout` is still registered as a root plugin but its definitions are
  image_compare toolbar layouts, not a tab-agnostic layout capability.

Physical leftovers in `plugins.layout`:

- `plugins.layout.definitions.LAYOUT_DEFINITIONS` lists
  `btn_diff_mode`, `btn_channel_mode`, `btn_file_names`, `btn_magnifier*`,
  `btn_divider*`, `btn_record`, `btn_pause`, and `btn_video_editor`;
- those widget IDs belong to image_compare/video-editor toolbar composition,
  not a generic host layout plugin.

Completed:

- `plugins.layout.definitions` and `plugins.layout.manager` were deleted;
- image_compare toolbar layout definitions and manager now live in
  `tabs.image_compare.ui.layout_definitions` and
  `tabs.image_compare.ui.layout_manager`;
- root `LayoutPlugin` only listens for `SettingsUIModeChangedEvent` and obtains
  the active tab-owned manager via `TabRegistry.create_service("layout_manager", ...)`;
- contracts now fail if root `plugins.layout` reintroduces image_compare toolbar
  button IDs or the old definitions/manager files.

Action:

- if a root layout plugin stays, it should manage host layout modes only and
  consume tab-contributed toolbar sections, not list tab button IDs.

## Core And Store

### `core/store_document.py`

Status: type ownership and storage relocated; `Store.document` /
`Store.viewport` are compat property proxies on the active workspace session.

Completed:

- `DocumentModel` and `ImageItem` live in
  `tabs/image_compare/state/document.py` and are the authoritative definition
  of the image-pair document model;
- `src/core/store_document.py` is a thin re-export shim retained so the
  remaining ~188 `store.document.*` platform accesses keep resolving during a
  future cosmetic fan-out; it is explicitly registered in
  `tests/contracts/test_platform_isolation.py` as a compat-bridge allowlist
  entry;
- tab-internal callers (`plan_builder`, `video_snapshot_rendering`,
  `use_cases/loading`, canvas clear-state test) import `ImageItem` from the
  tab-owned path, not `core.store`;
- `WorkspaceSession.document` and `WorkspaceSession.viewport` are no longer
  dataclass fields; they are compat properties backed by
  `session.state_slots["document"]` / `session.state_slots["viewport"]`,
  so image-pair document *and* viewport state live in the generic session
  slot mechanism;
- `Store.document` and `Store.viewport` are `@property` proxies that read /
  write the active session's slot (with a pre-session fallback used only
  during `Store.__init__` before the initial workspace session exists);
- `create_workspace_session()` populates both slots via property assignment
  instead of dataclass constructor args; the platform never carries these
  fields as first-class Store attributes.

Remaining (cosmetic fan-out, tracked in
[`DOCUMENT_ACCESS_FANOUT.md`](DOCUMENT_ACCESS_FANOUT.md)):

- rewrite the ~188 `store.document.*` accesses across core/services/plugins
  to reach the slot through `TabRegistry.create_service(...)` or a dedicated
  tab API, so `Store.document` can be dropped entirely;
- limit slot population to image_compare sessions only (blueprint-driven);
  today every session still gets an empty `DocumentModel` for backward
  compatibility with those platform accesses;
- once the fan-out lands, delete `src/core/store_document.py` and remove it
  from the platform isolation allowlist.

Action:

- fan-out is now purely a hygiene sweep — storage is already in
  `session.state_slots`, so callers can migrate incrementally without
  changing behaviour;
- export/video/editor should consume snapshots from tab services, not global
  image-pair fields.

### `core/store_viewport.py` and reducers

Status: mixed.

Problems:

- viewport state includes comparison fields (`diff_mode`, channel mode,
  split position, feature data);
- reducers import canvas widget feature registry.

Action:

- keep generic viewport primitives only if multi_compare also needs them;
- move image_compare feature state/reducers to
  `tabs/image_compare/state`;
- core reducers should not import UI feature registries.

### `core/store_workspace.py`

Status: default session-type leak removed.

Problem:

- defaults to `session_type="image_compare"`.

Completed:

- `WorkspaceStoreMixin.create_workspace_session()` no longer defaults to
  `image_compare`; callers must pass a session type or receive a `ValueError`;
- `Store` explicitly creates the initial `session_picker` workspace session;
- `src/core/store_workspace.py` was removed from
  `tests/contracts/test_platform_isolation.py` allowlist.

Remaining:

- startup policy still lives close to `Store` initialization and should be
  moved fully into startup/session-picker orchestration when the host-created
  primitive widget migration is complete.

## Events

### `events/image_label/*`

Status: image_compare canvas input path under generic events.

Problems:

- feature command aliases for canvas features;
- old comments reference `ui/canvas_features`;
- image label naming reflects old single canvas.

Action:

- move image_compare label/canvas event handlers to
  `tabs/image_compare/events`;
- keep host `WindowEventHandler` only for generic drag/drop/window lifecycle
  routing into active tab.

### `events/app_event/common.py`

Status: image_compare presenter helper.

Problem:

- `get_image_canvas_presenter(presenter)` and
  `schedule_image_canvas_update()` are tab-specific helpers outside the tab.

Action:

- move to `tabs/image_compare/events` or replace with tab registry service.

## Services And Shared

### `services/io` and `services/system`

Status: cleaned for the old root image loader; `services/system` is mostly
generic and remaining pair behavior should be audited separately.

Problems:

- `ImageLoaderService.on_full_image_loaded()` writes
  `store.document.image_list1/2`, `original_image1/2`, `full_res_image1/2`,
  `preview_image1/2`, and `image1_path/image2_path`;
- it owns pair-image unification, display-cache generation, pending
  unification path checks, and metrics triggering;
- `tabs.image_compare.plugin.ComparisonPlugin` and `plugins.export.ExportPlugin`
  both instantiate this root service, so a migrated tab still depends on a
  root service for its document mutation path.

Completed:

- `src/services/io/image_loader.py` was deleted;
- image_compare loading/unification now uses the existing tab-owned
  `tabs.image_compare._session_controller` + `tabs.image_compare.use_cases.loading`
  path;
- `ComparisonPlugin` no longer creates a root `ImageLoaderService`;
- `ExportPlugin` no longer creates or passes a root `ImageLoaderService`;
- clipboard paste implementation moved from `services.system.clipboard` to
  `tabs.image_compare.services.clipboard`;
- `tests/contracts/test_platform_isolation.py` now fails if
  `src/services/io/image_loader.py` or `src/services/system/clipboard.py`
  reappears.

Action:

- add a contract that `src/services` cannot write `store.document.image1/2` or
  `store.viewport.session_data.image_state.image1/2`.

### `services/workflow`

Status: image_compare-only; see high-severity section.

### `shared/image_processing`

Status: mixed but mostly acceptable as pure functions.

Notes:

- pair helpers (`resize_images_processor`, `analysis_pair`) can remain shared
  only if they are pure image utilities with no store/tab imports;
- naming can stay pair-oriented if the API is genuinely reusable by analysis,
  export, video, and tabs.

### `shared/rendering`

Status: mixed, with live snapshot pair construction moved behind tab service.

Problems:

- layout/target surface contracts are generic enough.
- `shared.rendering.canvas_widget_factory` used to be a compatibility facade
  with image_compare-specific function names; it has been replaced by neutral
  `shared.rendering.tab_canvas_services`.

Completed:

- `shared.rendering.live_snapshot.build_live_frame_snapshot()` now delegates to
  `TabRegistry.create_service("live_frame_snapshot", store)`;
- image-pair path/name extraction lives in
  `tabs.image_compare.services.live_snapshot`;
- `tests/contracts/test_platform_isolation.py` now fails if shared
  `live_snapshot.py` reintroduces image-pair fields or `FrameSnapshot`
  construction.
- `shared.rendering.canvas_widget_factory.py` was deleted;
- `plugins.export` and `plugins.video_editor` now request tab canvas widgets
  through neutral `shared.rendering.tab_canvas_services`;
- `tests/contracts/test_platform_isolation.py` now fails if the old
  `shared/rendering/canvas_widget_factory.py` path reappears.

Action:

- keep `target_surface.py`, `layout_contract.py`, interpolation helpers;
- continue moving remaining image-pair render construction out of shared
  presentation/export helpers.
- continue replacing remaining tab-specific render-source concepts with
  explicit active-tab/render-source services.

### `ui.widgets.canvas.render_passes`

Status: dead QRhi migration shim.

Evidence:

- `ui.widgets.canvas.render_passes.paint_canvas()` is documented as a no-op
  shim retained for legacy callers;
- `ui.widgets.canvas.render` only re-exports that no-op;
- real rendering goes through image_compare `RhiCanvasRenderer` and shared
  `render_executor`.

Action:

- search for remaining symbolic imports;
- remove `ui.widgets.canvas.render` and `render_passes.py` once no tests or
  instrumentation need the old name.

## Test And Contract Gaps

Current tests still allow some structural debt:

- `test_platform_isolation.py` now has an empty allowlist for literal
  `image_compare` / `image_session` mentions in platform/shared files;
- removed-path regressions cover `src/ui/canvas_features`,
  `src/ui/presenters/image_canvas`, `src/ui/widgets/gl_canvas`,
  `src/ui/context_menu/image_compare.py`,
  `src/ui/canvas_presentation/plan_builder.py`, and old plugin/service paths;
- canvas feature contract helpers now scan the tab-owned feature root and
  plugin/shared import scans forbid direct imports of
  `tabs.image_compare.canvas.features.*`;
- no repo-wide ownership test answers: "who imports this shared file?"
- generic plugin checks now fail on any direct canvas feature command registry
  call under `src/plugins`; remaining video-editor debt is semantic ownership
  of magnifier keyframing/recorder concepts, not registry coupling.
- no contract classifies root `src/plugins/<name>` packages; migrated plugin
  packages can keep registering on startup unless manually removed;
- no contract fails on image_compare widget IDs inside root plugins such as
  `plugins.layout.definitions`;
- no contract fails on no-op compatibility modules such as
  `ui.widgets.canvas.render_passes`.

Latest focused verification:

- `tests/contracts/test_platform_isolation.py`,
  `test_canvas_features_imports.py`, `test_plugins_isolation.py`,
  `test_canvas_features_manifest.py`, `test_canvas_features_layout.py`,
  `test_canvas_features_gl_passes.py`, `test_canvas_protocols.py`, and
  `tests/render/test_paste_overlay_feature_contracts.py`: `368 passed`;
- multi_compare label/refactor coverage after removing the cross-tab label
  import: `23 passed`;
- plugin/platform isolation after export/video/settings/live-snapshot and
  plan-applicator hook cleanup: `634 passed`;
- export/video render-plan coverage after moving export and video bounds
  feature queries: `41 passed`;
- settings-focused coverage after moving settings command execution behind tab
  services: `68 passed`;
- video keyframing/export coverage after moving recorder/keyframing command
  lookup behind tab services: `35 passed`;
- render/export/video plan-applicator coverage after moving live/snapshot
  feature hooks and legacy plan application behind tab services: `44 passed`;
- focused canvas-feature/platform/plugin isolation contracts after the same
  split: `634 passed`;
- canvas widget ownership contract after moving pair-canvas selection behind
  tab services: `1 passed`;
- render_arch/canvas split focused coverage:
  `tests/contracts/test_canvas_widget_ownership.py`,
  `tests/runtime/test_stacking_policy.py`, and focused canvas render tests:
  `65 passed`;
- export/video/main-window coverage after the physical canvas split:
  `53 passed`;
- full `tests/contracts`: `780 passed / 1 failed`; remaining failure is
  `tests/contracts/test_no_manual_theming.py`, the existing manual-theming
  offender list.

Needed tests:

- fail if `src/ui`, `src/core`, `src/services`, or generic `src/plugins`
  import `tabs.image_compare` directly, except explicit registry hooks;
- fail if `src/ui` contains files/dirs with tab-specific names
  (`image_compare`, `image_canvas`, `magnifier`, `divider`, etc.) outside
  approved generic contracts;
- owner-map contract for selected shared files:
  `ui.canvas_presentation.plan_builder`-style regressions should fail when a
  shared file has only one tab owner;
- plugin isolation rule: generic plugins must not call canvas feature command
  registries directly.
- root plugin registry contract: every `src/plugins/<name>/plugin.py` must be
  explicitly allowed as host/cross-tab/session plugin; migrated tab-owned
  plugins must live under `src/tabs/<tab>`;
- legacy-shim contract: files that advertise themselves as no-op/compatibility
  wrappers must be listed in an expiry table or removed.

## Recommended Migration Order

1. [done] Finish already obvious removals:
   `src/ui/canvas_features`, `src/ui/presenters/image_canvas`,
   `src/ui/widgets/gl_canvas`, `src/ui/context_menu/image_compare.py`.
2. [done] Remove `plugins/comparison` after confirming tab plugin service parity.
3. [done] Move `services/workflow/playlist*` to image_compare or delete duplicates.
4. [done] Move `ui.canvas_presentation.plan_builder` and related image-pair export
   builder code to image_compare.
5. [done] Split `plan_applicator` into generic composition applicator and
   image_compare overlay applicator.
6. [done] Split `ui.widgets.canvas` into generic QRhi backend plus image_compare pair
   canvas widget.
7. [done] Move host-created image_compare primitive widgets/toolbars/transient
   managers from `ui.main_window`, `ui.presenters`, and `ui.managers` into the
   tab.
8. [done] Move image-pair document/viewport state out of core store into
   image_compare session slots. Type ownership for `DocumentModel`/`ImageItem`
   lives in `tabs/image_compare/state/document.py`; `WorkspaceSession.document`
   and `WorkspaceSession.viewport` are `state_slots`-backed properties;
   `Store.document` / `Store.viewport` are `@property` proxies onto the
   active session's slot. `core/store_document.py` remains as an allowlisted
   compat re-export until the ~188 `store.document.*` platform accesses are
   fanned out — tracked as hygiene since storage is already relocated.
9. [partial] Rework export/video_editor/settings/analysis integrations to consume
   tab-provided capabilities instead of importing image_compare internals.
10. Tighten contracts so new pseudo-generic files cannot appear.
