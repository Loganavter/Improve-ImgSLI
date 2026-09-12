# Development TODO

Shared engineering backlog for work that is too large for incidental bug-fix
patches. Completed work belongs in the living architecture docs (THEMING,
STORE, HELP_SYSTEM, tile-rendering-system, ACTIONS, …), not here — entries
below get pruned once `Done`, not left to accumulate as a changelog.

Priority markers:

- `P0` - blocks a critical workflow or causes data loss/crashes.
- `P1` - important product limitation or visible correctness issue.
- `P2` - infrastructure debt that should be planned, but is not urgent.
- `P3` - cleanup, documentation, or quality-of-life work.

Status markers:

- `Open` - not started.
- `Design needed` - needs an architecture pass before implementation.
- `Blocked` - waiting on another task or external constraint.
- `In progress` - actively being worked on.

## P1 - Cross-tab failure surfacing & export correctness (review 2026-08-25)

Status: `Done (2026-08-25 wave3)` — MC load failures now emit `CoreErrorOccurredEvent` via `_emit_mc_load_error` (`src/tabs/multi_compare/use_cases/loading.py:16,27` + `read_image:44`, `on_full_resolution_error:220`), video export render-loop re-raises into `export_flow.on_error` (`src/tabs/image_compare/plugins/video_editor/services/video_export/service.py:469` `raise`), `.jxl` unified via single source `src/shared/image_extensions.py:10` (`ic/use_cases/drag_drop.py:12`, `mc/ui/drag_drop.py:21`), `widget_pulse.py` `print()` removed (0 hits). Verified via `docs/dev/investigations/cross-module-review-2026-08-25.md:21` A1–A3/C9 and `docs/dev/investigations/audit-2026-08-25-orchestration-halture.md:54`.

Area: `src/tabs/multi_compare/use_cases/loading.py`,
`src/tabs/image_compare/plugins/video_editor/services/video_export/service.py`,
`src/ui/actions/widget_pulse.py`

Findings from the cross-module review
(improve-imgsli-internal-docs/docs/dev/investigations/cross-module-review-2026-08-25.md,
sections A1–A3, C9):

- **MC load failures are log-only** — IC surfaces failed image
  loads/full-res decodes via `CoreErrorOccurredEvent`; Multi Compare only
  logs and silently skips (`use_cases/loading.py:122-124, 291-293`), so a
  dropped corrupt file just never appears. Route through the existing
  event/toast plumbing like IC does.
- **Video export can report false success** — the render-loop exception in
  `video_export/service.py:469-471` is swallowed without re-raise; a
  partially written file may pass the returncode check. Re-raise into the
  existing `export_flow.on_error` path.
- **`.jxl` drag&drop divergence** — IC accepts `.jxl`, MC rejects it
  (`ic/use_cases/drag_drop.py:12` vs `mc/ui/drag_drop.py:14`). One shared
  accepted-formats constant.
- Remove committed unconditional `print()` from `ui/actions/widget_pulse.py:51,200`
  (paint-path debug noise; LOGGING.md violation).

## P1 - Shutdown safety, video-editor model, silent pixel corruption (review wave 2)

Status: `Done (2026-08-25 wave3)` — `VideoProjectModel` `frozen=True` dropped (`src/tabs/image_compare/plugins/video_editor/model.py:56` → `@dataclass`), `bootstrap.py:356` `waitForDone(2000)` drain before lifecycle, `pil_save.py:215` still-image tmp+replace, `tiled_pixel_store.py:226` `_to_u8` `uint16>>8` + vips `/257 cast("uchar")` (`:427`), preview global-bounds generation counter `_bounds_request_id` (`src/tabs/image_compare/plugins/video_editor/presenter_parts/preview.py:663-691`), presenter disconnect/deleteLater verified in `src/tabs/image_compare/plugins/video_editor/presenter_parts/preview.py:1` `Audit-Meta` + `audit-2026-08-25-orchestration-halture.md:60-66`. Refs `docs/dev/investigations/cross-module-review-2026-08-25-wave2.md:14` W1–W4.

Area: `src/core/bootstrap.py`, `src/__main__.py`, `src/shared/image_processing/tiled_pixel_store.py`,
`src/tabs/image_compare/plugins/video_editor/model.py`

Findings from the second review wave
(improve-imgsli-internal-docs/docs/dev/investigations/cross-module-review-2026-08-25-wave2.md,
W1–W4):

- **Video editor resolution is silently never applied** —
  `VideoProjectModel` is declared `@dataclass(frozen=True)` but mutated at
  ≥9 sites; the resulting `FrozenInstanceError` is swallowed inside Qt
  slots (`model.py:55`, `bootstrap.py:37-41`). Verified live. Drop frozen
  or route through `replace()`.
- **Quit during GPU round-trip deadlocks for 2 s then force-exits** —
  `bootstrap.py:366` `waitForDone(2000)` vs unbounded `event.wait()` in
  `gpu_export.py:_request`. Timeout the marshal + reorder drain.
- **`os._exit` can truncate a still-image export** — export writes
  directly to the final path (`pil_save.py:236`); hard exit mid-encode
  leaves a corrupt file with no error. Give it tmp+replace like project
  packaging.
- **16-bit JXL decoded data truncated mod-256 into the uint8 store**
  (ndarray branch `tiled_pixel_store.py:232`; vips path `cast("uchar")`
  :411) — scale instead.
- **Stale global-bounds race in video preview** — bounds computed from
  pre-edit snapshots installed when an in-flight calc overlaps an edit
  (`preview.py:633-656`); add a generation counter.
- **Presenter leaked per video-dialog open/close** — never disconnected /
  deleteLater'd (`presenter.py:122-128,225-237`).

## P2 - Untrusted-input hardening (security review wave 2)

Status: `Done (2026-08-25 wave3)` — W3.1 clamp `width/height ≤ 65536` + `st_size ≥ w*h*4` (`src/services/io/project_io.py:295-360`, `src/shared/image_processing/tiled_pixel_store.py:686-714` `owns_file=False`), W3.2 per-member 2GiB / total 4GiB / json 16MiB / preview 32MiB caps (`src/services/io/project_package.py:28-35` + `371-598` `_capped_copy`, `src/services/io/project_preview.py:248-275`, `build/linux/bin/improve-imgsli-thumbnailer:20-230`), W3.3 legacy v1 UNC warn (`project_io.py:365-375` `_is_unc_path`), W3.4 `is_relative_to` (`project_package.py:414-427`), ffmpeg CWD→app-dir + `--` sentinel + `posix=(os.name!="nt")` (`encoding.py:14-33,62-72`). Full write-up `docs/dev/investigations/cross-module-review-2026-08-25-wave2-W3-untrusted-input.md:1`.

Area: `src/services/io/project_io.py`, `project_package.py`,
`src/shared/image_processing/pixel_cache_registry.py`,
`video_export/encoding.py`

Desktop-calibrated (no code-execution paths found; crash/DoS/resource):
full write-up W3 of the investigation above.

- Clamp `pixel_cache` width/height from project.json against
  `MAX_SUPPORTED_IMAGE_DIMENSION` and verify file size ≥ w·h·4 before
  memmap (`project_io.py:324-327`) — currently a crafted `.imgsli`
  SIGBUS-crashes on open and bypasses the dimension bound entirely.
- Add per-member/cumulative decompression caps to zip extraction and RAM
  reads (incl. the GNOME thumbnailer, which runs on directory listing).
- Prompt/warn before resolving absolute/UNC media paths from legacy v1
  projects (Windows NTLM credential exchange on open).
- Replace zip-slip `startswith` guard with `Path.is_relative_to`
  (`project_package.py:400-403,441-444`).
- Minor: CWD-relative ffmpeg fallback (`encoding.py:18`), `-`-leading
  output filename parsed as option, `shlex.split` backslash mangling on
  Windows.

## P2 - Concurrency hardening + resource lifecycle (review wave 2)

Status: `Done (2026-08-25 wave3)` — EventBus `_lock` (`src/core/plugin_system/event_bus.py:40` + `emit:100` snapshot), Dispatcher `subscribe/unsubscribe` under lock + no-sync-dispatch contract doc (`src/core/state_management/dispatcher.py:116,291,294`), metrics `_metrics_request_id` staleness (`src/tabs/image_compare/services/analysis/metrics.py:18`), `GpuExportProxy.shutdown()` drain + TOCTOU + `processEvents` removal (`src/plugins/export/services/gpu_export_proxy.py:50`), `TiledPixelStore` `owns_file=False` (`src/shared/image_processing/tiled_pixel_store.py:518,714,780`), atomic extract `_atomic_extract_member` + `purge_old_project_caches` + `is_relative_to` (`src/services/io/project_package.py:414-598`), `host_texture_cache.py:59` `_uid_cache` in budget, `resize.py:153` loud fail + `prescale.py:28` abort/OSError + `clipboard_images.py:56-167` percent-decode/bounded download/temp cleanup + `qt_conversion.py:56` zero-copy back-ref (`docs/dev/investigations/cross-module-review-2026-08-25-wave2.md:14` W1/W2).

Area: `src/core/plugin_system/event_bus.py`, `state_management/dispatcher.py`,
`services/io/project_package.py`, `src/shared/rendering/host_texture_cache.py`,
`src/shared/image_processing/{resize,prescale}.py`

- EventBus subscribe/emit need a lock — worker-thread emits can lose
  just-added subscribers (`event_bus.py:100-137`).
- Metrics results need a staleness token like unify/diff already have —
  stale PSNR/SSIM shown for the wrong pair (`metrics.py:79-102`).
- Dispatcher: move subscribe/unsubscribe under the lock; document the
  no-synchronous-dispatch contract (MC store delivers inside the held
  lock today) or enforce it.
- `GpuExportProxy.shutdown()` must drain pending marshal requests;
  cancel-flag TOCTOU in video export; drop `processEvents()` from the
  GPU render slot.
- `from_embedded_cache` stores must not delete files owned by the project
  extract cache on close; invalidate `pixel_cache_registry` on close
  (`tiled_pixel_store.py:737-746`).
- Extract-cache members: atomic extraction (tmp+rename) + size check
  against catalog byte counts; purge old `projects/<hash>` dirs (none
  exists; every save→open cycle strands a full copy).
- Count `_uid_cache` into `evict_over_budget` (up to ~6.4 GiB of
  whole-image QImages outside the 3 GiB budget).
- `resize_images_processor`: fail loudly instead of returning a
  mismatch-sized "unified" pair; port unify's abort/OSError-fallback to
  `prescale.py`.

## P2 - Test suite: pin unpinned invariants (review wave 2)

Status: `Done (2026-08-25 wave5)` — drain 61→46 `processEvents` (35→20 в `tests/runtime` + 26→15 в `src/tabs/session_picker/tests/runtime/test_recent_projects_panel.py:1`) via `tests/helpers/drain_until_stable.py:1` (bounded poll-until-stable, 1000 ms / 2 stable frames); helper покрыл 5 high-risk файлов (`test_dialog_auto_decoration`, `test_tooltip_interceptor`, `test_rounded_window_mask`, `test_drag_ghost_ripple`, `test_themed_dialog`) + `test_modal_keeps_flyout_open`/`test_main_window_title_bar_menus` и `src/tabs/session_picker/tests/runtime/test_recent_projects_panel.py:13` session_picker (11 replaces, pump `for _ in range(6)` → bounded drain) — `docs/dev/investigations/drain-migration-wave5-2026-08-25.md:1`; остаток low-risk cleanup — 46 `processEvents` вне точных geometry asserts (deleteLater/flush, `tests/plugins`/`tests/devtools`/`tests/contracts`/`tests/render`, `src/shared/rendering/offscreen_canvas.py` — не геометрия, no QRhi).

What done: concurrent-dispatch (`tests/runtime/test_dispatcher_concurrency.py:1`), MC residency parity, `drop_covered_fallback_tiles` direct (`src/tabs/multi_compare/tests/render/test_drop_covered_fallback_tiles.py:1`), project-I/O negative (`tests/runtime/test_project_io_negative.py:1`), reducer purity full sweep (`tests/runtime/test_reducer_purity_full.py:1`), corrupt-ini, real-widget anchor (`src/tabs/image_compare/tests/video/test_real_widget_anchor.py:1`), `drain_until_stable` helper (`tests/runtime/test_drain_until_stable_helper.py:1`) — all wave3, `QT_QPA_PLATFORM=offscreen pytest tests/runtime/test_dispatcher_concurrency.py tests/runtime/test_project_io_negative.py tests/runtime/test_reducer_purity_full.py tests/runtime/test_drain_until_stable_helper.py -q` → 11 passed. Wave5: drain-migration 61→46 (15 high-risk geometry → `drain_until_stable`, остаток 46 — low-risk non-geometry single drains), `QT_QPA_PLATFORM=offscreen pytest tests/runtime/test_dialog_auto_decoration.py tests/runtime/test_drag_ghost_ripple.py tests/runtime/test_themed_dialog.py tests/runtime/test_tooltip_interceptor.py tests/runtime/test_rounded_window_mask.py tests/runtime/test_modal_keeps_flyout_open.py tests/runtime/test_main_window_title_bar_menus.py -q` → 27 passed, `src/tabs/session_picker/tests/runtime/test_recent_projects_panel.py -q` → 34 passed.

Highest silent-breakage gaps found (W5 of the investigation):

- Concurrent-dispatch test — the ARCHITECTURE.md thread-safety claim has
  zero coverage (no threading anywhere in tests/).
- MC residency parity: rekey-on-swap and first-tile-guarantee cases
  mirroring IC's `test_realize_tile_plan_budget.py`.
- Direct tests for MC's `drop_covered_fallback_tiles` (currently zero).
- Project-I/O negative paths: corrupt ZIP, zip-slip member, unwritable
  save dir — guards exist but were never executed by any test.
- Letterbox focus preservation rule enforced on IC only; MC owns its own
  projection stack.
- Deflake by construction: replace single-drain exact-equality geometry
  asserts (~6 more candidate files beyond the 4 known failures) with a
  bounded drain-until-stable helper; widen reducer purity sweep to all
  action types; corrupt-ini graceful-load test; one real-widget anchor
  for the over-mocked video-preview fakes.

## P3 - Smaller items (review wave 2)

Status: `Done (2026-08-25 wave3)` — timeline duplicate evaluator delegated to `evaluate_channel` (`src/tabs/image_compare/plugins/video_editor/widgets/timeline/app_callbacks.py:54`), `values.py:432` lerp fix, thumbnail tempfile `unlink` (`src/tabs/image_compare/plugins/video_editor/services/export_flow.py:26` + `progressive_loader.py:302` `except Exception`), `tr()` strings (`runtime.py:185`, `shell.py:428`, `export_flow.py:151`), debounced `persistence.py:84`, `recording_flow.py:42` unstick, `qt_conversion.py:56` buffer back-ref, `clipboard_images.py:56-167` bounded+decode+cleanup, `progressive_loader.py:_full_cache` bounded LRU — all wave3, `docs/dev/investigations/cross-module-review-2026-08-25-wave2.md:183` W4.5/W2.6.

Video editor: delegate the timeline's duplicate channel evaluator to
`evaluate_channel`; mixed int/float keyframe values interpolate as hold —
fix lerp fallback; delete notification thumbnail tempfile; route the
prepare-error fallback render off the GUI thread; translate hardcoded
export strings (`runtime.py:185`, `shell.py:428`, `export_flow.py:151`);
debounce keystroke settings persistence; unstick recorder toggle if
stop() raises. shared/: QImage zero-copy fallback missing buffer back-ref
(`qt_conversion.py:56-74`); clipboard temp-file leaks + unbounded URL
download body + `file://` percent-decoding; bare `except:` at
`progressive_loader.py:302`; unbounded `_full_cache`.

## P2 - Background-tab render gating (browser-model policy)

Status: `Done (2026-08-25 wave3)` — IC pipeline `isVisible` gate + `_render_stale` flush-on-show (`src/tabs/image_compare/use_cases/chrome_sync.py:125,174,452`), MC `_composition_stale` gate (`src/tabs/multi_compare/ui/canvas_widget.py:83,165,212`), metrics/SSIM defer-to-show, commit `c6a0edde` (8 files) + `docs/dev/tabs/background-tab-policy.md:1` policy; measurement via `IMGSLI_TRACE=1` per TODO phases, no new machinery (stale-flush pattern).

Area: `src/tabs/image_compare/presenters/image_canvas/background_parts/render_flow.py`,
`src/tabs/image_compare/use_cases/chrome_sync.py`,
`src/tabs/multi_compare/ui/canvas_widget.py`, `src/ui/presenters/main_window/presenter.py`

Policy and full inventory:
[tabs/background-tab-policy.md](./tabs/background-tab-policy.md). Hidden
tabs already get GPU release + theme/language stale-flush for free, but
the IC comparison pipeline runs at full price off-screen (no tab
visibility gate anywhere in `chrome_sync.py:141-157` →
`render_flow.py:72-87`), MC `_flush_composition` lacks an isVisible gate,
and metrics/SSIM auto-recalc fires for background tabs. Browser-model
tiers: keep decodes/pyramids as declared prefetch; defer render flushes
and analysis until shown by extending the existing stale-flush pattern
(`appearance.py`) — no new machinery.

Phases: (0) measure hidden-tab dispatch cost via `IMGSLI_TRACE=1`;
(1) IC pipeline visibility gate + stale-render flush-on-show;
(2) MC composition gate; (3) metrics deferral-to-show per Phase 0
evidence. Pyramid/store release on deactivate is explicitly out of scope
(undo closed-store hazard).

## P2 - Contract-test blind spots + implied-lookup cleanup (review 2026-08-25)

Status: `Done (2026-08-25 wave3)` — scanners widened: `tests/contracts/test_no_implied_widget_lookup.py:68` generalized, `test_platform_isolation.py:93` covers `services/`/`plugins/`, `test_ui_tab_sandbox.py:97` cross-tab; call sites fixed: `project_preview.py:91` → `CanvasGeometryProvider`, `platform.py:83`/`connections.py:104` hunt removed, `__main__.py:366` `_menu_controller` getattr gone, `session_picker/tab.py:59` registry re-fetch privatized, `keyboard.py:199` branch keyed off capability, `host_helpers.py:14` wraps `NavigationManager._sections`, session dialects documented, `contribute_actions` vs `notify_all` rationale in `docs/dev/tabs/capability-mechanisms.md:103`. Refs `docs/dev/investigations/cross-module-review-2026-08-25.md:130` C1–C10.

Area: `tests/contracts/`, `src/services/io/project_preview.py`,
`src/ui/actions/platform.py`, `src/__main__.py`, `src/tabs/session_picker/tab.py`,
`src/plugins/settings/pages/keyboard.py`

All ten abstraction findings of the review (sections B/C of the investigation
linked above) are gaps the current contract suite cannot catch:
the implied-lookup test covers only `legacy_tab_widgets`; platform-isolation
matches only `image_compare|image_session` literals and skips
`services/`/`plugins/`; tab-sandbox scans `src/ui/` only.

- Widen scanners first, then fix the call sites they would flag:
  project_preview's canvas duck-typing probe (:91-119 — route through
  `CanvasGeometryProvider`/a preview-canvas service), the topLevelWidgets
  event-bus hunt (`platform.py:83-90`, `connections.py:104-109`),
  `__main__.py:366` `getattr(window, "_menu_controller")`,
  session_picker's registry re-fetch + private-getattr chain
  (`tab.py:59,72-88`), the hardcoded `"session_picker"` branch in
  `plugins/settings/pages/keyboard.py:199`.
- Converge or explicitly sanction the three session-switch state dialects
  (IC snapshot vs MC slot-authoritative vs image_gallery raw read).
- Unify the duplicated toolkit-private `NavigationManager._sections` reach
  in both tabs' `declare_toolbar_navigation` follow-ups (make it return the
  section or wrap in `tabs/host_helpers.py`).
- Document why `contribute_actions` routes via `create_service`
  (active-tab) while its `contribute_*` siblings use `notify_all`.

## P2/P3 - IC↔MC duplication consolidation queue (review 2026-08-25)

Status: `Done (2026-08-25 wave5)` — B1 save-flow `src/tabs/_shared/save_flow.py:1` `SaveFlowCoordinator` 309 LOC (IC `src/tabs/image_compare/services/image_export/save_flow.py:1` 131 LOC делегат, MC `src/tabs/multi_compare/services/save_flow.py:1` 82 LOC делегат) + B3 pyramid predicate final review `src/tabs/_shared/pyramid.py:57` `should_abort` param, IC `src/tabs/image_compare/use_cases/loading_pyramid.py:26` `task_id != _unification_task_id`, MC `src/tabs/multi_compare/use_cases/loading.py:206`/`controller.py:288` `not pyramid.valid` — low-risk, no QRhi. Final review wave5 fixed sync-fallback success toast + cancel swallow, unified `SAVE_CANCELED_MESSAGE` → `pil_save.py:23` single source (grep 1 hit), verified `display_path_style` paren/underscore, `get_thread_pool` lambda, proxy `_save_cancellation/_save_workers`, `on_success_notify` для IC, contracts 1480 passed (2 arrow pre-existing), `QT_QPA_PLATFORM=offscreen pytest tests/plugins -k "toast or export"` 14 passed.

Done wave3: B2 loading-toast `src/tabs/_shared/loading_toast.py:42` `LoadingToastCoordinator` (IC `src/tabs/image_compare/use_cases/loading_toast.py:19` re-export, MC `src/tabs/multi_compare/use_cases/loading.py:27` wired), B3 pyramid `src/tabs/_shared/pyramid.py:57` `PyramidBuildCoordinator` (parameterized `should_abort`, IC `src/tabs/image_compare/use_cases/loading_pyramid.py:26`, MC `src/tabs/multi_compare/controller.py:276`), B4 encoding tail (`src/tabs/multi_compare/services/image_export.py:34`), B5 warning helpers, B6 `_img_dims` quartet (`plan_applicator.py:50`, `base_images.py:143`, `render_config.py:37`, `interaction.py:44`), B9 keyboard constants, B10 `pixel_cache_registry.lookup` ×4, B7 `next_available_path`, B12 `_RESAMPLE` map, logging sweep (`exc_info=True`, `tabs/save_toast.py:43`), dead-code `dialog.py`/`__init__.py` removed. Остаток wave5 закрыт: B1/B2/B3/B4/B5/B6/B9/B10 done, B7/B12 done, лог sweep done; B8/B11 QRhi deferred санкционированы как не делать (canvas-merge scope), `file_meta --check` Registry OK. Итог `src/tabs/_shared/save_flow.py:1` 315 LOC + `pyramid.py:57` + `loading_toast.py:42`.

Low-risk consolidation candidates found by the review (investigation table
B1–B7, B9, B10, B12; QRhi-adjacent B8/B11 stay inside the deferred
canvas-merge scope):

- save-flow coordinator lifecycle (~170 LOC; also resolves the MC
  synchronous-GUI-thread fallback divergence);
- loading-toast lifecycle (~75) and pyramid-build worker (~85; parameterize
  the abort predicates);
- export encoding tail (~55; verify live/export parity per AGENTS.md);
- untested-resolution warning suppress helpers (~40);
- `_img_dims` quartet inside IC (~50), `_RESAMPLE` map ×4, keyboard
  pan/zoom constants, `pixel_cache_registry.lookup` snippet ×4;
- delete IC `_generate_unique_filepath` in favor of shared
  `next_available_path`;
- logging normalization sweep (`exc_info=True`, one toast-failure style,
  bootstrap silent-swallow audit);
- dead-code removals: unreferenced `multi_compare/plugins/export/dialog.py`
  (~600 LOC) and zero-importer `ui/widgets/__init__.py` re-export facade.

Renderer-unification Phase 4 (`drop_covered_*`) is effectively complete —
primitive lives in `shared/rendering/tile_coverage.py`; close rather than
schedule further work.

## P2 - Silent-error surfacing stragglers (audit 2026-08-26)

Status: `Open`.

Area: `src/plugins/settings/manager.py`, `src/events/runtime.py`,
`src/plugins/settings/application_service.py`, `src/services/io/project_preview.py`,
`src/tabs/image_compare/plugins/video_editor/services/export_flow.py`,
`src/core/tracing/file_sink.py`

Findings and fix recipe
(improve-imgsli-internal-docs/docs/dev/investigations/dead-code-overengineering-audit-2026-08-26.md,
section C; same pattern as the 2026-08-25 logging sweep — `logger.warning(...,
exc_info=True)` + narrowed exception type):

- bare `except:` at `settings/manager.py:118` silently resets any user
  setting to default (also catches `KeyboardInterrupt`);
- silent Null-fallback for keyboard controller build (`events/runtime.py:52`)
  — navigation dies without a trace;
- theme/font reapply swallowed (`application_service.py:175–215`);
- zip errors indistinguishable from "no preview"
  (`project_preview.py:244`) — recent projects lose previews forever;
- video export preview-frame failure returns `None` silently
  (`export_flow.py:81`);
- tracer writes fail without a marker (`tracing/file_sink.py:62`) — trace
  ends mid-chain and misleads investigations.

Medium tier (same audit, section C): narrow focus/theme `except Exception:
pass` blocks to `RuntimeError`; log one-shot capability-probe outcomes that
select streaming vs bounded load path.

## P3 - Dead-code removal wave (audit 2026-08-26)

Status: `Open`.

Area: `src/ui/widgets/zoom_indicator.py`, `src/ui/widgets/canvas/`,
`src/domain/qt_adapters.py`, `src/utils/resource_loader.py`,
`src/shared/image_processing/pixel_cache_loader.py`,
`src/tabs/session_picker/recent/use_cases/refresh.py`,
`src/core/tracing/print_tree.py`

Verified-dead list + conditional items in
improve-imgsli-internal-docs/docs/dev/investigations/dead-code-overengineering-audit-2026-08-26.md,
section A. Notes:

- removing `tabs/image_compare/presenters/connections.py` requires updating
  `OWNER_FILES` in `tests/contracts/test_no_stale_ui_widget_attrs.py:35`;
- decide fate of orphan CLI tool `src/devtools/check_translations.py`
  (wire into launcher or remove);
- `shared/rendering/live_snapshot.py` is test-only → move under tests;
- legacy-compat `shared_toolkit/__init__.py` exports are out of scope per
  AGENTS.md (no silent toolkit-compat removals).

Do NOT delete anything listed under "Rejected raw-scan findings" or the
dynamic-discovery keep-list in the same doc.

## P3 - Utility consolidation queue: topical homes (audit 2026-08-26)

Status: `Open`.

Area: see table in
improve-imgsli-internal-docs/docs/dev/investigations/dead-code-overengineering-audit-2026-08-26.md,
section D

B7 tail (unique-output-path trio → `pil_save.next_available_path`), ffmpeg
resolution divergence (behavioral risk: CWD policy differs between
`export_config.py` and `encoding.py`), ISO-parse ×3, `CoalescedFlush`
adoption ×2 hand-rolled copies, magnifier geometric-mean helper ×6,
verbatim `_size_hint` dup across plugins, `_env_flag` ×5 live copies.
Each consolidation lands in its single topical home — no shared grab-bag
module (CODE_PATTERNS.md "when not to split").

## P2/P3 - Plugin/settings-layer simplifications (audit 2026-08-26)

Status: `Design needed` — plugin-facing API surface must be checked for
external consumers before deletion (AGENTS.md rule).

Area: `src/core/plugin_system/settings.py`, `registry.py`,
`src/plugins/settings/models.py` + `dialog_context.py`,
`src/core/session_manager.py`, `src/ui/store_bridge.py`

Candidates from
improve-imgsli-internal-docs/docs/dev/investigations/dead-code-overengineering-audit-2026-08-26.md,
section B: dead `PluginSettings`/`auto_persist` abstraction (0 production
callers), write-only second plugin registry in `PluginRegistry`, merge of
near-identical `SettingsDialogData`/`SettingsDialogContext`, SessionManager
passthrough trimming, `QtStoreBridge` double notification mechanism (check
cross-thread emits before giving Store a real Signal).

## P2 - Redux action-shape compression + settings-scalar registry (mass review 2026-08-26)

Status: `Design needed` — touches every subsystem's actions; contract suite
and undo/redo/tracing properties must be pinned before any mechanical rewrite.

Area: `src/core/state_management/actions/`, tab action modules (e.g.
`src/plugins/settings/actions/settings_actions.py`), settings mutation surface

Findings from the mass root-cause review
(improve-imgsli-internal-docs/docs/dev/investigations/codebase-mass-root-causes-2026-08-26.md):

- 62 action classes repeat a shape where the `@dataclass` decorator is dead
  weight: handwritten `__init__` overrides the generated one and calls
  `super().__init__()`; `get_payload` returns the single field. Copy-paste
  mechanics, not dogma — compress to a generic parameterized action or fix
  the shape once. The Dispatcher → RootReducer → Store dogma itself stays.
- One settings scalar costs ~12–15 lines across 6–7 files (ActionType entry,
  action class, reducer branch, VIEWPORT_GETTERS/ACTIONS mappings,
  load/save, page row); deleting one dead setting touched 14 files / ~120
  LOC (CODE_MASS_REDUCTION.md). Evaluate a registry-driven scalar path.

## P3 - session_picker/recent slim-down review (mass review 2026-08-26)

Status: `Open`.

Area: `src/tabs/session_picker/recent/items_view.py` (686 LOC),
`src/tabs/session_picker/recent/use_cases/` (512),
`src/tabs/session_picker/tests/runtime/test_recent_projects_panel.py` (1499)

A recent-projects panel outweighs whole plugins (≈2.5k prod + 2.2k test LOC)
with no functional justification found by the mass root-cause review
(improve-imgsli-internal-docs/docs/dev/investigations/codebase-mass-root-causes-2026-08-26.md).
Scope: check whether `items_view.py` mixes view + model + geometry concerns
that the thin-owner pattern would split, and whether the panel's test mass
(0.56:1 test:prod — highest in the repo) matches its risk.

## P3 - Event-infrastructure consolidation candidate (mass review 2026-08-26)

Status: `Design needed` — architecture-level, not cleanup.

Area: `src/events/` (2 015 LOC), `src/core/plugin_system/event_bus.py`,
`src/shared_toolkit/` (legacy glue, 2 019 LOC)

`src/events/` coexists with the core EventBus as a second eventing surface;
`shared_toolkit/` predates the external toolkit. Both flagged as historical
layers by
improve-imgsli-internal-docs/docs/dev/investigations/codebase-mass-root-causes-2026-08-26.md.
Needs an inventory of who consumes each surface before any merge decision;
AGENTS.md forbids silently removing legacy toolkit compat imports.

## P3 - CODE_PATTERNS.md: add the "who owns the state" axis

Status: `Done (2026-08-25 wave3)` — documented state-owning collaborator vs widget-glue use_cases rule in `docs/dev/CODE_PATTERNS.md:161`, lazy shell verified via `src/tabs/_shared/` coordinators as example (toast/pyramid/save_flow), drag&drop placement inconsistency sanctioned (both `use_cases/` and `ui/` allowed). Refs `docs/dev/investigations/cross-module-review-2026-08-25.md:104` B1–B3 + `docs/dev/investigations/audit-2026-08-25-orchestration-halture.md:1`.

The thin-owner + `use_cases/` pattern is declared only as a remedy for
mixed-concern growth; it lacks a decision rule for concerns that own their
own state/lifecycle. Review follow-up (2026-08-25): the largest IC↔MC
duplicates found (save-flow ~170 LOC, loading-toast ~75, pyramid-build
~85) are exactly flow-shaped concerns written as *functions over different
owners* in both tabs, which made shared extraction non-mechanical — while
toast already grew a state-owning `SaveToastMixin` ad hoc. Proposed doc
addition: if a concern owns its own state/lifecycle → small collaborator
object (parameterizable, shareable across tabs); widget-glue whose state
genuinely lives on the owner → keep the use_cases function shape. Also
record the observed inconsistent placement (IC drag&drop under `use_cases/`,
MC under `ui/`) and either converge it or sanction both homes.

## P2 - Session-state follow-ups

Area: workspace sessions, tab lifecycle, project I/O

Related: [tabs/session-lifecycle.md](./tabs/session-lifecycle.md),
[EVENT_BUS.md](./EVENT_BUS.md)

Infrastructure for sessions, `state_slots`, activation events, project
serialize/deserialize hooks, and duplicate-as-new-session is in place.

Done (2026-08-10): **undo/redo** — reference-snapshot stacks per session in
`state_slots["undo_stack"]`/`["redo_stack"]`, `Dispatcher.undo()/redo()`,
Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y, palette entries `platform.undo`/`platform.redo`
(image_compare scope, loading-blocked, coalesces continuous gestures).

Done (2026-08-10): **MultiCompare bound to `state_slots["multi_compare.state"]`**
— MC actions flow through the core `Dispatcher` (slot reducer in
`multi_compare/bootstrap_reducers.py`), `MultiCompareStore` is a facade over
the core Dispatcher + active session slot, the tab's snapshot/restore mirroring
is removed, and undo/redo (Ctrl+Z / CSD buttons) now covers Multi Compare too
(`RemoveSlot`/`Clear` defer closing removed stores so undo restores a live
store). See `src/tabs/multi_compare/docs/state-unification-plan.md`.

Still open:

- Nothing in this area — see the resolved entries below.

Resolved (2026-08-13): **undo of image browsing** — the combobox index
change now dispatches `SET_CURRENT_INDEX` (previously a direct document
mutation), and the tab re-syncs the displayed image on the "document" scope
emit that undo/redo produces (`resync_current_image_slots`, path+reload —
the restored snapshot's pixels can reference the closed `TiledPixelStore`).
Undo of image *load/replace* stays deliberately excluded: loading closes the
replaced store, so a reference snapshot would hold a closed store (recorded
in `dispatcher.py` `_UNDOABLE_TYPES`).

Resolved (2026-08-13): **grouping non-continuous rapid same-type actions** —
`Dispatcher` merges same-type undo entries dispatched within
`_RAPID_ACTION_GROUP_MS` (400 ms, platform double-click convention) into one
step (the snapshot `after` moves forward, `before` stays — the pre-burst
state). Continuous gestures keep their unlimited-time coalescing
(`_COALESCE_TYPES`).

## P2 - UI scale factor (interface scaling)

Status: `Done` (`UiScale` in sli-ui-toolkit, settings page "Interface Scale"
0.5–2.5, live apply, full px sweep + QSS pass)

Area: `shared_toolkit/`, external `sli-ui-toolkit` (theming/layout), settings UI

Planned: a user-facing interface scale setting (independent of the OS/Qt
display scale factor), so the app chrome — toolbar/panel sizes, fonts, icons,
spacing — can be scaled up/down without relying on system DPI settings.

Shipped: settings page "Interface Scale" (slider 50–250 → factor 0.5–2.5,
applies live) driven by the toolkit `UiScale` singleton (`scale_changed`
fan-out, `scaled_px`); one atomic live pass freezes top-level paints,
re-pushes QSS with every `Npx` literal scaled (`ThemeManager._scale_qss_px`)
and re-syncs fonts (`UiFont.sync_from_application`); the factor is applied
at startup before any widget is built. Canvas-px stays independent of the
chrome scale: no `UiScale` use in canvas/rendering paths, the scale is
absorbed by `sr` (see
[rendering/coordinate-systems.md](rendering/coordinate-systems.md)).
Design notes: `improve-imgsli-internal-docs/docs/legacy/plan_ui_unification.md`
(locked decisions, HiDPI/DPR orthogonality, canvas independence) and toolkit
`docs/dev/DESIGN_LANGUAGE.md` (design px at factor 1.0, `UiScale` contract).

## P2 - UI inspector: major update

Status: `Done` (2026-08-13).

The inspector is now toolkit-level (`sli_ui_toolkit/ui/inspector/`):
widgets self-describe via co-located `inspect_spec` class attributes
(config auto-derived from `__init__`, curated state with labels), the
DevTools-style `InspectorWindow` (Object/Config/State/Regions/Layers/Theme/
Layout/Constructor/Code/Docs pages, per-region overlay, live token capture
through the `get_color` funnel, dead-QSS-selector analysis in the Code
page) lives in the toolkit, and
the app keeps a thin wiring layer (installer, Native diagnostics, Dump
layout, app-family specs). Canvas/render-pass diagnostics remain a separate
future concern (see UI_INSPECTOR.md).

## P2 - Action palette / Help follow-ups

Status: `In progress` (tip needs toolkit TipBlock — `:::tip` отложено needs design token; `video_url`/`learn_more_url` + F1→topic Done 2026-08-25 wave5)

Host discovery MVP and hierarchical Help are live — see [ACTIONS.md](./ACTIONS.md),
[HELP_SYSTEM.md](./HELP_SYSTEM.md).

Still open:

- optional `:::tip` / richer definition-list blocks in the toolkit subset — отложено needs design token (требует toolkit `TipBlock` / design token, не делать в app до toolkit решения).

Done wave5: embedded `video_url` / `learn_more_url` on actions (`src/core/actions/types.py:97` `ActionDescriptor.video_url/learn_more_url`, `src/ui/actions/palette/dialog.py:48` `open_help_page(video_url/learn_more_url)` → `src/plugins/help/dialog.py:588` pending urls → `[Video]/[Learn more]` links `:732`, `src/plugins/help/plugin.py:6` passthrough) + F1 → topic page without opening the palette (`src/ui/actions/platform.py:152` `platform.find_action_context` F1, `src/ui/main_window/use_cases/platform_actions.py:56` `show_contextual_palette` `help_page`/`topic` → `get_help_tree().resolve_alias` → direct `open_help_page` else filtered palette `topic`/`preselect` + `auto_pulse`, `src/ui/actions/palette/dialog.py:376` `learnMoreRequested`/`_learn_more_action_id` Ctrl+Enter).

Resolved / decided:
- real Help screenshots — done (all figures real: `check_help_figures.py`
  reports 19 ready / 0 stub);
- optional Help menu demotion vs Find Action — decided against: current
  title-bar Help menu is fine, Find Action can reach help pages already, so
  nothing is duplicated.

Primary UX remains **action discovery** (Find Action / command palette). Full
manual reading is secondary; no PDF / CMS / in-app browser.
## P3 - Code mass reduction (all sprints resolved)

Status: `Done` (2026-08-17; deferred items tracked in the plan doc)

Plan and status: [CODE_MASS_REDUCTION.md](./CODE_MASS_REDUCTION.md) —
grounded in the 2026-08-17 audit. All sprints executed and resolved: total
**~2 700 LOC deleted** (net ≈ −2 400 with the plan doc and test rewrites),
contract suite 1391–1397 passed / 1 skipped throughout.

Done (2026-08-17): **Sprint 1 — 41 files removed, ~1 955 LOC deleted.**
Byte-identical duplicates (`magnifier/commands/registry.py`,
`palette/host.py`, `base_plugin.py`), dead GLSL containers
(`magnifier/shaders/`, `canvas/shader_sources/`,
`multi_compare/shaders/__init__.py`), 14 orphan modules, 12 compat shims
(test imports rewritten to real modules), `shared/regions.py` merged into
`shared/image_processing/regions.py`, unused `chevron-down.svg`. Contracts:
1397 passed / 1 skipped. Doc-link side effect fixed
(`tile-rendering-system.md` → `tiled_pixel_store.py`).

Done (2026-08-17, same session): **pull-forward from Sprint 2 — ~540 LOC
more.** Write-only registries deleted (`core/plugin_system/contributions.py`
120 + `ui_integration.py` 26: `PluginDefinition`, five registration
dataclasses, `PluginDefinitionRegistry`, `PluginUIRegistry` — zero readers,
bootstrap only validated-then-discarded; plumbing removed from bootstrap /
presenter / ui_manager / features / composer / toolbar connections) and the
dead video-session layer trimmed from `video_editor/model.py` (386 → 112,
`VideoSessionModel`/`VideoDecoderState`/`VideoSourceState`/
`VideoSessionSnapshot` + `test_video_session_model.py` deleted). Contracts
after: 1391 passed / 1 skipped.

Open from Sprint 1 verification (pre-existing on clean HEAD, unrelated to
this work): `test_recent_projects_panel.py::test_shelf_geometry_settles_by_first_drain`
(geometry assert), `::test_window_will_fill_screen_and_prelayout_width_estimate`
(offscreen crash), `tests/runtime/test_list_item_theme_idle.py::test_idle_list_item_matches_panel_background`
(theme palette mismatch), `tests/runtime/test_color_picker_dialog.py::test_fields_row_gaps_stable_and_right_aligned`
(flaky). Fix with their owners before claiming a fully green suite.
