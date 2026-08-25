# Audit: dead code, over-engineering, silent errors, reinvented stdlib (2026-08-26)

Scope: `src/` of this repo. Method: four parallel scans (AST import graph,
wrapper/duplication scan, except-handler sweep, stdlib-reinvention scan),
then manual grep re-verification of every high-confidence item before it was
accepted here. Raw-scan findings that failed re-verification are recorded in
"Rejected findings" so a future audit does not re-litigate them.

Related backlog entries created from this audit: [TODO.md](../TODO.md)
(silent-error surfacing P2, dead-code removal P3, utility consolidation
P3, plugin-layer simplifications P2/P3 `Design needed`).

## A. Dead code (grep-verified 2026-08-26)

High confidence (0 references anywhere in `src/`, `tests/`, `launcher.sh`,
docs):

| Item | Notes |
|---|---|
| `src/ui/widgets/zoom_indicator.py` | imports nonexistent `ui.widgets.rounded_overlay` — cannot even be imported; both tabs use `ui.widgets.glass_hud.ZoomIndicator` (`tabs/image_compare/ui/layout.py:31`, `tabs/multi_compare/widget.py:31`) |
| `src/ui/widgets/canvas/rhi_backend.py` (dir lacks `__init__.py`) | legacy copy of `ui/canvas_infra/rhi/rhi_backend.py`; also holds one of the `_env_flag` copies |
| geometry converters in `src/domain/qt_adapters.py` (`point_to_qpointf`, `qpointf_to_point`, `point_to_qpoint`, `qpoint_to_point`, `rect_to_qrect`, `qrect_to_rect`) | module stays (color converters used); delete only these defs |
| `safe_rect`, `safe_point`, `truncate_text`, `get_scaled_pixmap_dimensions` in `src/utils/resource_loader.py` | 0 external hits |
| `load_pixel_store_no_crop` in `src/shared/image_processing/pixel_cache_loader.py:35` | 0 external hits |
| `on_header_prefs_changed` in `src/tabs/session_picker/recent/use_cases/refresh.py:115` | panel wires its own `_on_header_prefs_changed` (panel.py:356,399), never delegates here |
| `_begin_kind_for_end`, `_pair_durations` in `src/core/tracing/print_tree.py` | defined, never called (not even inside the module) |

Conditional (needs one coordinated change):

- `src/tabs/image_compare/presenters/connections.py` — no runtime importer,
  BUT `tests/contracts/test_no_stale_ui_widget_attrs.py:35` lists it in
  `OWNER_FILES` (AST-scans the file). Removal must update that test set.
- `src/devtools/check_translations.py` — orphan CLI tool: not wired into
  `launcher.sh`, scripts/, docs/, CI. Decide: wire it into launcher
  (`context`?) or remove.
- `src/shared/rendering/live_snapshot.py` — production uses
  `tabs.image_compare.services.live_snapshot`; this copy is imported only by
  `tabs/image_compare/tests/plugins/test_export_diff_support.py`. Move under
  tests or repoint the test.
- no-op `begin_content_scissor()` (`tabs/image_compare/canvas/render_config.py:122`)
  — QRhi-migration leftover, zero callers.
- legacy-compat exports in `shared_toolkit/__init__.py` /
  `shared_toolkit/ui/__init__.py` (`CustomGroupBuilder`,
  `MINIMAL_SCROLLBAR_WIDTH`, `get_icon_by_name`, prewarm helpers) — AGENTS.md
  forbids silent removal; needs an explicit toolkit-compat decision.

Do NOT touch (dynamic discovery keeps them alive): `plugins/*/plugin.py`,
`tabs/*/plugin.py`+`tab.py`, `plugins/settings/pages/{general,interface,performance}.py`
(pkgutil scan in `pages/__init__.py`), all `canvas/features/*/{manifest,passes,input}.py`
(pkgutil scans in `ui/canvas_infra/scene/registry.py`), `-m`-run devtools
(`core/tracing/print_tree.py` CLI entry, `devtools/compile_shaders.py`),
atexit hooks (`shared/clipboard_images.py:_cleanup_clipboard_temps`),
`canvas/features/_template/`.

## B. Over-engineering findings

Sanctioned-by-docs shapes excluded (thin owner + `use_cases/`, Redux action
dataclasses, canvas protocols under `tests/contracts/`, ABCs with 2+
implementations). Real findings:

1. `_env_flag` — 6 identical copies (7 lines each):
   `shared/rendering/render_debug.py:18`, `shared/rendering/first_frame_debug.py:27`,
   `ui/main_window/runtime.py:22`, `ui/widgets/flyout_debug.py:19`,
   `ui/canvas_infra/rhi/rhi_backend.py:108` (+1 in dead
   `ui/widgets/canvas/rhi_backend.py`). → one topical debug-flags helper;
   the two dead/legacy copies disappear with section A cleanup.
2. `core/plugin_system/settings.py` — `PluginSettings`/`SettingsScope`/
   `auto_persist`: 0 production callers (`auto_persist` writes a flag nobody
   reads); sole consumer is `tests/runtime/test_corrupt_ini_graceful.py`.
   Decide: declared plugin API or delete with test.
3. `plugins/settings/models.py:8 SettingsDialogData` vs
   `dialog_context.py:8 SettingsDialogContext` — ~30 near-identical fields,
   both built in `dialog.py`; `get_section`/`set_section` dead in both.
   Merge locally inside the settings plugin.
4. `core/plugin_system/registry.py:24 _plugins` + `get_plugin`/`all_plugins`/
   `deferred_loaded` — write-only after discovery; lookups go through
   `PluginCoordinator → PluginLifecycleManager`. Stop storing instances.
5. `core/session_manager.py` — `list_session_types` dead;
   `switch_to_session`/`rename_session`/`close_session` are 1-caller pure
   passthroughs into Store.
6. `shared/analysis/diff_source.py:51 _align_source2` ≅ `ssim_source.py:34`;
   `_rgb_array_from_source` diff:40 ≅ ssim:26 (ssim copy has a no-op
   `if isinstance(TiledPixelStore): crop else: crop`; same-shape defect at
   `diff_source.py:34 _crop_source`). → `shared/analysis/common.py`.
7. `ui/store_bridge.py QtStoreBridge` — callback→Signal→callback double
   notification; consumers duck-type `.connect/.emit`. Give Store a real
   `Signal(str)` (check cross-thread emits first).
8. Test-compat delegators in both save_flow coordinators (~10 one-line
   methods each, documented "for tests") — sanctioned shape for now; revisit
   by migrating the tests to `._flow`.

## C. Silent errors (except-handler sweep: 771 `except Exception`, 410 empty)

Dominant pattern in the codebase is best-effort cleanup before re-raise
(narrow `OSError`/`RuntimeError`) — correct, leave alone. Genuine gaps:

HIGH:

| Site | Problem |
|---|---|
| `plugins/settings/manager.py:118` | bare `except: return default` — any failure silently resets a user setting to default; catches `KeyboardInterrupt`/`SystemExit` |
| `events/runtime.py:52` | keyboard-controller build failure → silent `NullKeyboardMovementController`; navigation dies without a trace |
| `plugins/settings/application_service.py:175–180,215` | theme/font reapply via `except Exception: pass` — user changes setting, nothing happens, nothing logged |
| `services/io/project_preview.py:244` (+`read_preview_image_bytes`) | any zip error indistinguishable from "no preview"; recent projects permanently lose previews silently |
| `video_editor/services/export_flow.py:81` | preview-frame generation `except Exception: return None` — export reports success, thumbnail silently missing |
| `core/tracing/file_sink.py:62` | tracer writes fail (disk full) with no marker — trace.jsonl ends mid-chain and misleads investigations |

MEDIUM: `__main__.py:206` saved RHI backend silently ignored;
`core/plugin_system/settings.py:40` plugin field restore falls back silently;
`shared/image_processing/export_encoding.py:62` alpha_composite→paste fallback
wider than needed; `events/drag_drop_handler.py:78` defensive copy returns
the original on failure; `pixel_cache_loader.py:31`/`progressive_loader.py:73`
capability probes decide streaming-vs-bounded path without a trace; broad
`except Exception: pass` around focus/theme blocks
(`plugins/help/dialog.py:190,243,245,284,333,349,376`,
`tabs/image_compare/widget.py:103–111`,
`ui/managers/transient_ui_parts/closing.py:80,107,112`) should be narrowed to
`RuntimeError` where the only expected failure is deleted C++ objects.

Precedent: the 2026-08-25 waves already fixed sibling cases the same way
(TODO.md P1 "MC load failures are log-only", P3 logging sweep) — these are
the stragglers, same fix recipe (`logger.warning(..., exc_info=True)` +
narrowed exception type).

## D. Reinvented stdlib / consolidation queue (topical homes, no grab-bag)

Per CODE_PATTERNS.md ("when not to split": no misc/helpers grab-bags) each
item gets a single topical home:

| Duplicate | Live copies | Single home |
|---|---|---|
| unique-output-path generation (B7 leftover) | `image_export/state.py:22 get_unique_filepath`, `video_export/models.py:8 unique_video_path` (also hand-built f-string paths), `presenter_parts/output_paths.py:59 unique_output_filepath` | existing `pil_save.next_available_path` (B7 already done for the export service; finish the tail) |
| ffmpeg executable resolution | `export_config.py:359 _resolve_ffmpeg_executable` vs `video_export/encoding.py:15` — behaviorally diverged (CWD policy!) | one function in `export_config.py`; keep the hardened encoding.py semantics |
| ISO-timestamp parsing | `shelf/relative_time.py:12,31`, `services/io/recent_projects.py:315` | one `parse_iso_utc()` next to `relative_time.py` (justified on py3.10: `fromisoformat` rejects `Z`) |
| coalesced flush-per-tick | `ui/presenters/ui_update_batcher.py:30`, `multi_compare/ui/canvas_widget.py:238,323` hand-roll what `shared/rendering/coalesced_flush.CoalescedFlush` already does | adopt `CoalescedFlush` |
| geometric-mean magnifier size `sqrt(w*h)` | 6 sites under `magnifier/{scene,geometry,commands}` + `analysis_pair.py:63` | `magnifier/geometry/core.py` helper |
| `_size_hint` verbatim | `plugins/help/layout_geometry.py:47` ≅ `plugins/image_properties/layout_geometry.py:34` | `shared_toolkit/ui/layout_sizing.py` (already imported by both) |
| `_is_visible_magnifier_object` | `features/guides/feature.py:25` ≅ `features/capture/feature.py:25` | shared magnifier-state helper |
| local `clamp` variants | `color/value_format.py:120`, `unified_list_picker/layout.py:222`, etc., while `shared_toolkit/ui/layout_sizing.py:126` exists | adopt shared clamp where domain doesn't demand its own |
| `sqrt(dx**2+dy**2)` | `events/app_event/interactive_movement_input.py:61` | `math.hypot` (rest of the codebase already uses it) |

## Rejected raw-scan findings (verified alive — do not "clean up")

- `tabs/image_compare/canvas/texture_parts/common.py` — NOT dead:
  `canvas/widget.py:65` and `feature_overlay_gpu.py:10` import from it
  (raw AST scan missed intra-package relative imports).
- All per-tab `icons.py`, `layout_geometry.py` families, clipboard tabs —
  share real common cores already; content differs.
- `QTimer.singleShot(0, ...)` idiom (~100 sites) — idiomatic Qt defer, not
  duplication.
