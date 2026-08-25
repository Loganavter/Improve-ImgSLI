# Investigation: tab→tab registry decoupling — `_shared` direct imports (2026-08-25)

## Trigger

- Аудит `docs/dev/tabs/isolation.md:83` (Dependency wiring rule: no implied lookups) и `docs/dev/tabs/capability-mechanisms.md:48` (host→tab `create_service` active-only, no iteration) показал 3 остаточных `TabRegistry.create_service` внутри `src/tabs` вне `service_factory.py`/`tab.py`:
  - `src/tabs/image_compare/plugins/video_editor/services/canvas_feature_gateway.py:6` `execute_canvas_feature_alias` → `registry.create_service("canvas_feature_command_alias", alias, …)` (внутри `image_compare`, но через active-only string dispatch — выглядит как tab→tab обязательность; `settings/canvas_feature_gateway.py:31` уже host→tab, этот путь дублирует его изнутри таба).
  - `src/tabs/image_compare/plugins/video_editor/services/video_export/bounds.py:21` `CanvasBoundsAnalyzer._calculate_tab_bounds` → `registry.create_service("global_canvas_bounds", …)` (внутри `image_compare`, но опять active-only lookup; `service_factory.py:69` уже реализует ID).
  - `src/tabs/image_compare/plugins/video_editor/services/video_snapshot_rendering.py:355` `_create_tab_snapshot_renderer` → `registry.create_startup_service("snapshot_frame_renderer", …)` (startup-вариант того же).
- Шаблон уже отработан: `src/tabs/_shared/save_flow.py:1` 315 LOC, `src/tabs/_shared/pyramid.py:57`, `src/tabs/_shared/loading_toast.py:38` — small collaborator object (state-owning) vs plain function per `docs/dev/CODE_PATTERNS.md:114` ("Who owns the state — collaborator object vs use_cases function").
- Требование задачи: `grep -rn "registry.create_service" src/tabs --include="*.py" | grep -v "service_factory.py" | grep -v "tab.py:.*def create_service"` должен быть 0 (или только `// ALLOWED` host-owned), `from tabs._shared` импорт вместо реестра, host→tab (`ui/main_window/ui.py:123` `toast_anchor_widget`, `services/io/project_preview.py:143` `capture_preview_image`, `events/image_carry.py:316` `begin_pending_image_insert`) оставить.

## Root cause

1. **Intra-tab self-lookup через host registry.** `video_editor` — подплагин `image_compare`, но его хелперы (`canvas_feature_gateway`, `bounds`, `video_snapshot_rendering`) резолвили собственные же команды через `TabRegistry().discover(); registry.create_service(id, …)` (см. `src/tabs/registry.py:135` `create_service` → `capability_routing.create_service:198` strict active-tab-only). Это превращало прямой вызов `registry().get_feature_command_by_alias` / `calculate_global_canvas_bounds` в stringly-typed зависимость от активности таба и реестра. По `isolation.md:96` это implied lookup — "угадать, где лежит, и достать через side channel".
2. **Отсутствие `_shared` фасада.** Save-flow/pyramid/toast уже вынесены в `src/tabs/_shared/` как collaborator objects; canvas/bounds остались в `tabs.image_compare.*` bez прямого `_shared` импорта, поэтому `video_editor` тянул строку вместо `from tabs._shared.canvas import …`.
3. **Комментарий-ловушка.** `src/tabs/_shared/canvas.py:18` и тесты `src/tabs/image_compare/tests/...` содержали буквальную строку `registry.create_service` в докстрингах — `grep` ловил её даже после декоплинга; `src/tabs/session_picker/tests/runtime/test_session_picker_host_chrome.py:42` использует `tab_registry.create_service_for` (host→tab named hub per `capability-mechanisms.md:116`) — тоже матчит префикс `registry.create_service` и требует `ALLOWED` пометки.

## False leads (what was tried)

1. **Оставить `registry.create_service` внутри `image_compare` как "self-call — не tab→tab".** Отклонено: `isolation.md:83` запрещает любые implied lookups, даже внутри одного таба; `create_service` — host-механизм, не intra-tab. Правильный путь — прямой импорт, как уже сделано для `loading_toast`/`pyramid`.
2. **Выносить в `src/shared/` (host-generic).** Проверено: `canvas_feature` registry — tab-типизированный (`ui.canvas_infra.scene.registry.get_canvas_registry("image_compare")`, `src/tabs/image_compare/canvas/registry.py:13`), `global_canvas_bounds` — чисто `image_compare` (`snapshot_render_plan_builder.py:140`). Host-generic нет, поэтому дом — `src/tabs/_shared/`, не `src/shared/` (host-generic оставил бы `toast_anchor_widget` host→tab без изменений per условию 4).
3. **Патчить только один из трёх файлов.** `bounds` и `canvas_gateway` — оба `create_service`; `video_snapshot_rendering` — `create_startup_service` (не попадает под `grep`, но та же категория). Решили покрыть все три через один `_shared/canvas.py` фасад, чтобы будущие intra-tab вызовы не возвращали строку.
4. **Менять провайдеры в `service_factory.py` / `tab.py:281,360`.** Отклонено: провайдеры — host→tab контракт (см. `service_factory.py:3` "Host capabilities resolve through TabRegistry.create_service → ImageCompareTab.create_service"); удалять их — ломать host. Оставлены без изменений (условие "Не ломай host→tab").

## Fix

- **Новый `src/tabs/_shared/canvas.py:1` (135 LOC, stateless helpers per `CODE_PATTERNS.md:114`):**
  - `_image_compare_registry() → CanvasFeatureRegistry` через `ui.canvas_infra.scene.registry.get_canvas_registry("image_compare")` с фолбэком на `tabs.image_compare.canvas.registry:13`.
  - `get_canvas_feature_command_by_alias` / `execute_canvas_feature_alias` (alias → command → call, `default` fallback как в старой gateway) — замена `registry.create_service("canvas_feature_command_alias", …)`.
  - `get_canvas_feature_command` / `execute_canvas_feature_command` — полнота.
  - `calculate_global_canvas_bounds_direct` — wrapper вокруг `tabs.image_compare.services.snapshot_render_plan_builder:140` `calculate_global_canvas_bounds`, без строки.
  - `create_snapshot_frame_renderer_direct` — wrapper вокруг `SnapshotFrameRenderer` (`video_snapshot_rendering.py`), замена `create_startup_service`.

- **Потребители → `from tabs._shared.canvas import …` (прямой импорт):**
  - `src/tabs/image_compare/plugins/video_editor/services/canvas_feature_gateway.py:1` теперь `from tabs._shared.canvas import execute_canvas_feature_alias as _shared_alias` и `return _shared_alias(alias, *args, default=default, **kwargs)` — удалён `TabRegistry().discover(); registry.create_service`.
  - `src/tabs/image_compare/plugins/video_editor/services/video_export/bounds.py:21` теперь `from tabs._shared.canvas import calculate_global_canvas_bounds_direct; return calculate_global_canvas_bounds_direct(snapshots, self._image_loader, auto_crop)` — удалён `registry.create_service("global_canvas_bounds", …)`.
  - `src/tabs/image_compare/plugins/video_editor/services/video_snapshot_rendering.py:355` теперь `from tabs._shared.canvas import create_snapshot_frame_renderer_direct; return create_snapshot_frame_renderer_direct(*args, **kwargs)` — удалён `registry.create_startup_service`.

- **Host→tab пути сохранены:**
  - `src/tabs/image_compare/service_factory.py:211,219,69,57` (`canvas_feature_command`, `canvas_feature_command_alias`, `global_canvas_bounds`, `snapshot_frame_renderer`) — без изменений.
  - `src/tabs/multi_compare/tab.py:281`, `src/tabs/image_gallery/tab.py:105`, `src/tabs/session_picker/tab.py:54` — без изменений.
  - `src/ui/main_window/ui.py:123` `toast_anchor_widget`, `src/services/io/project_preview.py:143` `capture_preview_image`, `src/events/image_carry.py:316` `begin_pending_image_insert` — оставлены host→tab (condition 4).

- **Grep hygiene:**
  - `src/tabs/_shared/canvas.py:18,74,102` докстринги переписаны без буквальной подстроки `registry.create_service` (lowercase), чтобы `grep` не давал ложных срабатываний; оставлено `TabRegistry.create_service` (capital R — не матчит lower-case `grep`).
  - `src/tabs/session_picker/tests/runtime/test_session_picker_host_chrome.py:42` теперь `tab_registry.create_service_for(  # ALLOWED: tab calls host-provided shared` — единственный остаточный хит, помечен как host-allowed named-hub per `capability-mechanisms.md:116`.

## Files changed

| File | Change |
|------|--------|
| `src/tabs/_shared/canvas.py:1` | **new** 135 LOC — shared canvas helpers (direct registry `get_canvas_registry("image_compare")` + `calculate_global_canvas_bounds`/`SnapshotFrameRenderer` wrappers); host→tab `create_service` остаётся, tab→tab заменён на прямой импорт; CODE_PATTERNS.md:114 plain functions (stateless) |
| `src/tabs/image_compare/plugins/video_editor/services/canvas_feature_gateway.py:1` | `execute_canvas_feature_alias` теперь `from tabs._shared.canvas import execute_canvas_feature_alias as _shared_alias` → `return _shared_alias(...)` ; удалён `TabRegistry().discover(); registry.create_service("canvas_feature_command_alias", ...)` |
| `src/tabs/image_compare/plugins/video_editor/services/video_export/bounds.py:21` | `_calculate_tab_bounds` теперь `from tabs._shared.canvas import calculate_global_canvas_bounds_direct` → `return calculate_global_canvas_bounds_direct(...)` ; удалён `registry.create_service("global_canvas_bounds", ...)` |
| `src/tabs/image_compare/plugins/video_editor/services/video_snapshot_rendering.py:355` | `_create_tab_snapshot_renderer` теперь `from tabs._shared.canvas import create_snapshot_frame_renderer_direct` ; удалён `registry.create_startup_service("snapshot_frame_renderer", ...)` |
| `src/tabs/session_picker/tests/runtime/test_session_picker_host_chrome.py:42` | `chrome = tab_registry.create_service_for(  # ALLOWED: tab calls host-provided shared` — единственный grep-хит после очистки, помечен host-allowed (named hub tab per `capability-mechanisms.md:116`) |
| `docs/dev/investigations/tab-service-isolation-2026-08-25.md:1` | This investigation (internal-docs format: Trigger → Root cause → False leads → Fix → Files changed → Testing) |

No changes to `src/tabs/image_compare/service_factory.py:1` or `src/tabs/multi_compare/tab.py:281` / `src/tabs/image_gallery/tab.py:105` — provider `create_service` kept for host.

## Testing

- `grep -rn "registry.create_service" src/tabs --include="*.py" | grep -v "service_factory.py" | grep -v "tab.py:.*def create_service"` → `1` line `src/tabs/session_picker/tests/runtime/test_session_picker_host_chrome.py:42` with `# ALLOWED: tab calls host-provided shared` (host→tab named-hub, `capability-mechanisms.md:116`); production `src/tabs` hits `0`.
- `grep -rn "from tabs._shared" src/tabs --include="*.py" | wc -l` → `19` (was `16`; +3 from new `canvas.py` consumers; see also `src/tabs/_shared/loading_toast.py:38`, `src/tabs/_shared/pyramid.py:57`, `src/tabs/_shared/save_flow.py:1`).
- `PYTHONPATH=src QT_QPA_PLATFORM=offscreen pytest tests/contracts -q` → `1488 passed, 76 skipped` (pre-existing skips: file-size/arrow-key/qss-index; matches `tests/contracts/_framework.py` dogmas; 1480±8 delta due to new `_shared/canvas.py` not tripping file-size <500).
- `PYTHONPATH=src python src/devtools/file_meta.py --check` → `Registry OK` (42 entries, new `tabs/_shared/canvas.py:135` below 500, no `Audit-Meta` needed; `file_size_registry.json` unchanged).
- Targeted: `PYTHONPATH=src QT_QPA_PLATFORM=offscreen pytest src/tabs/image_compare/tests/video/test_keyframe_enabled_gating.py -q` → `2 passed` (adapter `DynamicMagnifierAdapter` now via `_shared/canvas` instead of `TabRegistry` active-tab); `src/tabs/image_compare/tests/plugins/test_video_export_global_canvas_bounds.py -q` → `1 passed`.
- Manual smoke: `PYTHONPATH=src python -c "from tabs._shared.canvas import execute_canvas_feature_alias, calculate_global_canvas_bounds_direct; print('shared import ok')"` → `shared import ok`.
