# Investigation: cross-module review — duplication, error handling, abstractions

Date: 2026-08-25. Three-pass read-only review over `src/` (error-handling
consistency, IC↔MC semantic duplication, abstraction-rule conformance),
context-loaded from ARCHITECTURE.md / CONTRACTS.md / CODE_PATTERNS.md /
LOGGING.md / CODE_MASS_REDUCTION.md so already-fixed and deliberately-
deferred items would not be re-reported. Every finding below was verified
against source (file:line quotes); intentional-by-design spots documented
in code were excluded.

Companion entries: [TODO.md](../TODO.md) ("review 2026-08-25" sections) and
the known-bugs index for the still-open correctness items. Related:
[CODE_MASS_REDUCTION.md](../CODE_MASS_REDUCTION.md) (this review extends its
audit; Sprint-3 lesson held — every candidate duplication was re-verified,
several turned out drifted-meaningful or false positives).

---

## A. Error handling

### A1. Failed image loads never reach the user in Multi Compare (vs Image Compare)

IC surfaces load failures twice via `CoreErrorOccurredEvent`
(`tabs/image_compare/_session_controller.py:336-346`,
`use_cases/loading.py:514-521`). MC handles the *same failure class*
log-only and silently skips the file:

```python
# tabs/multi_compare/use_cases/loading.py:122-124
except Exception as e:
    logger.error("Failed to load %s: %s", path, e)
    return None
```

Callers then skip silently (`load_single_auto` :319-320, `on_images_dropped`
:343-44); full-res decode failure is also log+toast-dismiss only (:291-293).
A dropped corrupt file in MC just… doesn't appear. Same class, two policies.

### A2. Committed unconditional debug `print()` on the paint path

`ui/actions/widget_pulse.py:51,200` — stderr `print()` inside `paintEvent`
and every pulse tick, not env-gated, no `[prefix]` tag — violates
[LOGGING.md](../LOGGING.md) in production (all other `print(` hits are
devtools CLIs or the pre-logging crash handler, both justified).

### A3. Video render-loop exception swallowed mid-export

`tabs/image_compare/plugins/video_editor/services/video_export/service.py:469-471`:
`except Exception` → log only, no re-raise, execution continues to the
returncode check. If ffmpeg exits 0 after the loop crashed, a partially
written file can be reported as success. The image path re-raises correctly
(`image_export/save_flow.py:137-139`) and GPU export records into
`result_box` (`plugins/export/services/gpu_export_proxy.py:209-214`);
user-facing plumbing exists (`export_flow.py:161-163`) — this path bypasses it.

### A4. Save-flow coordinators duplicated between tabs — and already diverged

`image_compare/services/image_export/save_flow.py` (290 LOC) vs
`multi_compare/services/save_flow.py` (234 LOC, docstring: *"Mirrors
ExportSaveFlowCoordinator"*): `_create_save_toast`, worker
done/progress/error handlers, cancel-all, display-path building are
line-for-line twins despite both using `SaveToastMixin`. Meaningful drift:
MC silently falls back to a **synchronous GUI-thread save** when no thread
pool exists (:79-85); IC unconditionally requires the pool (:106). Same
failure class, two strategies.

### A5. Logging-granularity inconsistencies

- `logger.error` without `exc_info=True` where an exception is live (~15
  sites: `core/bootstrap.py:366,380,386`, both clipboard services,
  `services/analysis/metrics.py:76`, video presenter parts); a third variant
  hand-rolls `traceback.format_exc()` into the message string
  (`_session_controller.py:418`).
- Toast-update failure logged differently: shared mixin without traceback
  (`tabs/save_toast.py:43-44`) vs `logger.exception` in loading-toast modules
  (`ic/use_cases/loading_toast.py:84`, `mc/use_cases/loading.py:66`).
- Bootstrap swallows silently amid logging neighbors: UiScale apply
  (`bootstrap.py:196-198`) and FontManager.apply_from_state (~:317-324) use
  bare `except Exception: pass`.
- One zipfile-read failure class, three treatments in 40 lines
  (`services/io/project_preview.py:207-208` silent False, :221-222 logged,
  :244-245 bare `pass`).

Positive baselines to imitate: `core/plugin_system/lifecycle.py:_safe_call`
(`logger.exception` + `PluginState.ERROR`) and `event_bus.py:129-133`
(log-and-keep-listener).

### A6. Dead duplicate export dialog carrying parallel error handling

`tabs/multi_compare/plugins/export/dialog.py` (`MultiCompareExportDialog`,
~600 LOC) is referenced nowhere outside its own tests — MC routes through
the host service (`tab.py:90-91`). It duplicates the host dialog's error
handling blocks and will drift.

---

## B. IC↔MC semantic duplication

Byte-identical copies were removed in the 2026-08-17 sprints; everything
below is *drifted* mirroring. Verified against Sprint-3's lesson: several
candidates checked came out false positives (clipboard services share only
one function; divider drag differs structurally 2-way vs N-way;
placeholder-dismiss glue ~10 LOC/tab — leave alone).

| # | Duplication | Where | LOC | Risk | Status |
|---|---|---|---|---|---|
| B1 | Save-flow coordinator lifecycle | see A4 | ~170 | **Low** (no QRhi) | NEW |
| B2 | Loading-toast lifecycle (show/update/finish/bump) | `ic/use_cases/loading_toast.py` ↔ `mc/use_cases/loading.py:27-105` | ~75 | Low | NEW |
| B3 | Pyramid-build worker + progress math (identical percent pipeline; abort predicates differ meaningfully: task-id staleness vs `pyramid.valid` — parameterize) | `ic/use_cases/loading_pyramid.py` ↔ `mc/use_cases/loading.py:127-211` | ~85 | Low | NEW |
| B4 | Encoding tail of export (format/ext normalization, alpha-flatten, save_kwargs defaults, `"Save canceled by user"` magic string matched in both tabs' workers) | `ic/image_export/service.py:212-343` ↔ `mc/services/image_export.py:34-85` | ~55 | Medium (live/export parity) | NEW |
| B5 | Untested->16384px warning suppress helpers + 4 confirm call sites (dialog itself already shared) | `ic/presenters/export_presenter.py:87-101,172-184,242-254` ↔ `mc/use_cases/export.py:54-70,291-303,351-363` | ~40 | Low | NEW |
| B6 | `_img_dims` duck-typing accessor ×4 **inside IC alone** | `canvas/presentation/plan_applicator.py:50`, `canvas/texture_parts/base_images.py:143`, `canvas/render_config.py:37`, `canvas/interaction.py:44` | ~50 | Low | NEW (Batch 5 defused the cross-tab case, missed this quartet) |
| B7 | IC `_generate_unique_filepath` reimplements shared `next_available_path` | `service.py:446-465` vs `shared/image_processing/pil_save.py:43` | ~18 | Low | NEW |
| B8 | First-frame present-settle glue (render counting / settle / emit trio) | `ic/canvas/widget.py:313-377` ↔ `mc/ui/canvas_widget.py:203-256` | ~45×2 | Medium-High (present timing) | NEW, adjacent to deferred canvas work |
| B9 | Keyboard pan/zoom key sets + nudge constant (byte-identical; bodies legitimately differ) | `ic/canvas/interaction.py:500-516` ↔ `mc/canvas/interaction.py:334-351` | ~35 | Low | NEW |
| B10 | `pixel_cache_registry.lookup → from_embedded_cache/from_path` snippet ×4 (twice inside MC) | `ic/_session_controller.py:126`; `mc/use_cases/loading.py:113,275` | ~10×4 | Low | NEW |
| B11 | Residency spec-building wrappers around shared `realize_specs` (+ identical `more_tiles_pending → update()` tail) | `ic/rhi_renderer/residency.py:235-489` ↔ `mc/scene/passes/residency.py:207-410` | ~130/tab | High (QRhi) | Known-deferred ([CODE_MASS_REDUCTION.md](../CODE_MASS_REDUCTION.md) Sprint 4) |
| B12 | `_RESAMPLE` map ×4 | `shared/image_processing/{resize,prescale}.py`, `pixel_ops/unify.py`, `video_snapshot_rendering/geometry.py` | ~15×3 | Low | NEW |

**Renderer-unification Phase 4 status correction:** the `drop_covered_*`
merge flagged "still open" is **effectively complete** — the coverage
primitive lives in `shared/rendering/tile_coverage.py`, imported by both
tabs; what remains are two thin wrappers whose drift *is meaningful*
(IC letterbox-maps to common space and requires both-sides coverage, per the
Phase 9 blank-gap bug; ~20 LOC net). Recommend closing the item rather than
scheduling further work.

---

## C. Abstraction-rule violations (all NEW gaps — none caught by current `tests/contracts/`)

Existing scanners cover narrower scopes than the dogmas they encode:
implied-lookup test knows only `legacy_tab_widgets`;
platform-isolation matches only `image_compare|image_session` literals;
tab-sandbox scans `src/ui/` only. Everything below slips past all three.

| # | Violation | Location | Why it matters |
|---|---|---|---|
| C1 | Ad-hoc canvas probe reinvents `CanvasGeometryProvider`: `getattr(host, "image_label"/"canvas"/"compare_canvas")` + `findChildren` deep-walk | `services/io/project_preview.py:91-119` | IC widget name as string literal in platform code; a new canvas tab silently gets no project preview. `tabs/contract.py:210` names the provider protocol as the *only* growth point here |
| C2 | Duck-typed event-bus/window hunt: scan `topLevelWidgets()` for `.presenter` → `.event_bus` / `.main_controller` | `ui/actions/platform.py:83-90`, `ui/presenters/main_window/connections.py:104-109`, `ic/use_cases/persistence.py:26-33` | The `window.presenter ↔ window.main_controller` folk-path repeated ≥3 sites instead of one sanctioned accessor |
| C3 | Three session-switch state dialects: IC snapshot/restore per switch vs MC slot-authoritative (post 2026-08 unification) vs image_gallery raw `state_slots.get` | `ic/tab.py:268-270` vs `mc/tab.py:176-179` vs `image_gallery/tab.py:86` | Next tab picks arbitrarily; declared pattern now has two live dialects plus a third |
| C4 | Tab-name branch hardcoded in plugins layer | `plugins/settings/pages/keyboard.py:199` (`if session_type == "session_picker": continue`) | Isolation dogma eroded in an unscanned layer; should key off a registry capability |
| C5 | Tab re-fetches own page from registry + chains five getattr probes into private members (`_sync_opaque_page_fills`, `_recent_panel`, …) | `session_picker/tab.py:59,72-88` | Registry side-channel + private-API coupling inside one tab; IC/MC keep `self._widget` instead |
| C6 | Copy-pasted reach into toolkit-private `NavigationManager._sections` | `ic/tab.py:260`, `mc/tab.py:170` (byte-identical) | Breaks on toolkit update; `declare_toolbar_navigation` should return the section, or wrap in `tabs/host_helpers.py` |
| C7 | Entry point implies `window._menu_controller` | `__main__.py:366-367` | CLI open-project silently no-ops on rename |
| C8 | Zero-caller lazy re-export facade | `ui/widgets/__init__.py:11-17` | Survived the mass-reduction sprints; no importers in src/tests |
| C9 | Drag&drop accepted-extension lists diverged: IC accepts `.jxl`, MC doesn't | `ic/use_cases/drag_drop.py:12` vs `mc/ui/drag_drop.py:14`, `mc/tab.py:16` | User-visible: JXL drops work in one tab, bounce in the other |
| C10 | `contribute_*` hook family split across two routing mechanisms: `notify_all("contribute_settings"/"contribute_help"/…)` vs `create_service("contribute_actions", …)` active-tab-only | `tabs/use_cases/capability_routing.py:23,32` vs `connections.py:100`, `mc/tab.py:271` | Same verb prefix, opposite semantics; capability-mechanisms doc doesn't record why actions differ |

Not flagged (evaluated and intentional): `_ComparisonControllerProxy.__getattr__`
pass-through (borderline), `MultiCompareStore` facade and `PreviewCoordinator`
(Audit-Meta'd state machines), `notify_all` fire-and-forget shape,
reducers (no I/O confirmed), `canvas_infra/**` (no feature branches found),
TabContract abstract surface (transitional hooks documented).

---

## Resulting rules / next steps

1. Failure-policy rule to adopt: *a failed user-initiated load/export must
   reach the user through the existing event/toast plumbing in every tab*
   (A1, A3) — log-only is not a UI policy.
2. Consolidation queue = B1–B7, B9, B10, B12 (low risk, no QRhi); B4 needs
   live-vs-export parity checks per AGENTS.md; B8/B11 stay inside the
   deferred canvas-merge scope.
3. Contract-test widening: generalize implied-lookup AST scan beyond
   `legacy_tab_widgets`; extend platform-isolation literal list + directory
   scope to `src/plugins`, `src/services`; add a cross-tab lifecycle-shape
   consistency check (C3) or document the dialects as sanctioned.
4. Normalize logging per [LOGGING.md](../LOGGING.md): `exc_info=True` sweep,
   one toast-failure style, bootstrap silent-swallow audit (A5).
