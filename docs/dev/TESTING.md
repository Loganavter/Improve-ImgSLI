# Тесты

Гайд по структуре `/tests`, запуску и написанию новых тестов.

## Запуск

```bash
# из корня репозитория
pytest                         # весь набор
pytest tests/contracts         # только архитектурные контракты
pytest tests/render -q         # рендер-контракты, тихий вывод
pytest -k divider              # все тесты со словом divider
pytest tests/runtime/test_feature_state_api.py::TestFeatureStateRegistry
```

`sys.path` для `src/` добавляется автоматически из `tests/conftest.py`. `sli-ui-toolkit` устанавливается как внешняя зависимость из `requirements-gui.txt`; локального fallback-пути к vendored toolkit нет. Тесты приложения проверяют только app-интеграцию с toolkit, а не публичный API самой внешней библиотеки.

Конфиг pytest в репозитории не используется (`pytest.ini` / `pyproject.toml` отсутствуют) — discovery идёт по стандартным правилам.

## Структура

Тесты разложены по типу проверяемой подсистемы, не по слою:

| Папка | Что проверяет | Стиль |
|---|---|---|
| `contracts/` | Структурные догмы (см. `docs/dev/CONTRACTS.md`, `CANVAS_FEATURES.md`). Сканирует исходники AST'ом, без запуска кода. | Статический анализ |
| `runtime/` | Контракты, которые проявляются только при импорте/исполнении: registry, Feature State API, stacking policy, изоляция презентации. | Импорт + assertions |
| `render/` | Поведение GL-passes и сцены: что и в каком порядке рисуется, что не рисуется при пустом состоянии. | Fake-context |
| `plugins/` | Поведение плагинов (`src/plugins/*`): settings, export, toast, help, clipboard. | Юнит/интеграционные |
| `video/` | Контракты видео-редактора (preview, timeline, keyframes, кэш). | Юнит |

Общий хелпер для contract-тестов — `tests/contracts/_framework.py`: пути (`SRC`, `CANVAS_FEATURES`, `PLUGINS`), `iter_py`, `read`, `module_imports`, `list_canvas_features`, `list_plugins`, `feature_name`. Используй его вместо ручного `Path(__file__).parent…`.

## Каталог файлов

Что защищает каждый файл — чтобы не читать исходники по одному. Догма каждого
теста указана первой строкой его docstring'а.

### `contracts/` — структурные догмы (AST-скан, без запуска)

| Файл | Что защищает |
|---|---|
| `test_canvas_features_manifest.py` | Каждая фича в `ui/canvas_features/` экспортирует `WIDGET_FEATURE` с `name`; имена уникальны. |
| `test_canvas_features_aliases.py` | Shared-код не хардкодит имя фичи в `get_canvas_feature_command`; каждый объявленный alias резолвится в callable. |
| `test_canvas_features_imports.py` | Shared-код не импортирует `ui.canvas_features.<name>` напрямую. |
| `test_canvas_features_layout.py` | `canvas_presentation` без feature-именованных хелперов; фича не реинтродуцирует свой render-pipeline. |
| `test_canvas_features_gl_passes.py` | GL-passes объявляют `stack_role`, не хардкодят layer/priority; общий `shader_sources` без feature-шейдеров. |
| `test_canvas_protocols.py` | `GLCanvas` реализует все методы Base/GlLike/Export-протоколов с совместимыми сигнатурами. |
| `test_events_no_feature_branching.py` | `mouse.py`/события не ветвятся по feature-флагам и не зовут feature-aliases напрямую. |
| `test_plugins_structure.py` | Каждый плагин: entry-point, декоратор+база, имя совпадает с папкой, имена уникальны. |
| `test_plugins_isolation.py` | Плагин не импортирует canvas-фичи и внутренности других плагинов. |
| `test_tabs.py` | Каждый таб в `src/tabs/` — заполненный `TabContract`, `session_type` уникален. |
| `test_tabs_isolation.py` | Таб не импортирует app-i18n/тему; JSON-переводы только в своём namespace. |
| `test_toolbar_bindings.py` | Toolbar-биндинги уникальны по `control_id`, ссылаются на callable; пример исполнения команды. |
| `test_viewport_state_slots.py` | `ViewportState` слотирован (без `__dict__`); `overlay_clip_rect` живёт в runtime-cache, запись на ViewportState падает. |

### `runtime/` — контракты при импорте/исполнении

| Файл | Что защищает |
|---|---|
| `test_feature_onboarding.py` | Авто-дискавери: `_template` исключён, прод-фичи найдены, нет центральных списков регистрации; у каждой фичи manifest/name/reducers. |
| `test_feature_state_api.py` | Feature State API: реестр query/command, явные ошибки на missing feature/query/command, исключения хендлеров, multi-instance → `canvas_widget_state`. |
| `test_feature_property_roundtrip.py` | serialize/deserialize настроек property роундтрипится; форма `channels` соответствует `kind`. |
| `test_layout_contract.py` | `NormalizedBounds.union`; layout-requirement команды возвращают валидные bounds; пустой набор → unit-layout. |
| `test_stacking_policy.py` | Центральная политика z-порядка GL-passes/scene-objects, фильтр по visibility, сохранение нулей, отсутствие коллизий `(layer, priority)`. |
| `test_reducer_purity.py` | Редьюсеры не мутируют предыдущий store и не делают I/O. |
| `test_viewport_change_contract.py` | Store-команды фич дёргают `emit_viewport_change` ровно раз; queries — нет; storeless не требует emit. |
| `test_interaction_contracts.py` | Event-слой изолирован от фич; interaction-aliases резолвятся; hit-test pipeline заполнен callable. |
| `test_shared_presentation_isolation.py` | `shared/` и плагины используют только aliases; Phase-5 aliases резолвятся. |
| `test_event_bus_depth.py` | Guard глубины EventBus: циклическая цепочка останавливается на `MAX_EMIT_DEPTH`, счётчик сбрасывается между top-level emit'ами. |
| `test_gesture_resolution.py` | Резолвинг жестов: приоритет/фильтр по кнопке/проглатывание исключений в `matches`/`is_active`; реальные биндинги не бросают на нейтральном store. |
| `test_plugin_graceful_degradation.py` | Пустой `plugins/` и неизвестный alias не валят bootstrap (graceful degradation). |
| `test_tabs_lifecycle.py` | Drop роутится по `accepts_drop`; `dispose()` идемпотентен. |

### `render/` — поведение GL-passes и сцены (fake-context)

| Файл | Что защищает |
|---|---|
| `test_canvas_clear_state_contracts.py` | `clear` сбрасывает runtime-флаги и active display name после очистки слота. |
| `test_divider_render_contracts.py` | Divider не рисуется без двух картинок и валидного content_rect. |
| `test_single_preview_render_contracts.py` | В single-preview не рисуются divider и capture-ring. |
| `test_magnifier_overlay_order.py` | Активные magnifier-слоты рисуются последними. |
| `test_magnifier_divider_coupling.py` | Magnifier combine/separate вокруг spacing-threshold. |
| `test_magnifier_snapshot_store.py` | Нормализация capture-rect/frozen-position; virtual layout не мутирует state и не публикует clip_rect. |
| `test_paste_overlay_feature_contracts.py` | Feature-passes идут без base-картинок/на белых кадрах; paste-overlay дискаверится, использует свой shader и preview stack-role. |
| `test_scene_mode_apply_contracts.py` | Export-режим выкидывает интерактивные payloads magnifier, interactive — сохраняет. |

### `plugins/` — поведение плагинов

| Файл | Что защищает |
|---|---|
| `test_settings_controller.py` | `apply_font_settings` батчит и капчит; пропускает капчу без изменений. |
| `test_settings_roundtrip.py` | Каждая property с `setting_key` переживает save→reload (fixpoint, без Qt). |
| `test_export_diff_support.py` | Diff-режим: cached diff в GPU render-plan/preview; export-interpolation (`NEAREST`→`LANCZOS`). |
| `test_toast_and_metrics.py` | Toast-прогресс при split-rounding; SSIM-toast вне diff-режима, без дублей; export save flow. |
| `test_color_settings_button.py` | Color-кнопка сохраняет laser-сегмент при скрытых guides. |
| `test_clipboard_paste_shortcut.py` | Ctrl+V на canvas эмитит paste-event. |
| `test_help_dialog_anchors.py` | Help: strip anchor-суффикса, генерация heading-id, TOC из h3-секций. |

### `video/` — контракты видео-редактора

| Файл | Что защищает |
|---|---|
| `test_video_export_preview_parity_matrix.py` | Паритет export/preview по матрице diff/fit/interp; prescale пары к одному размеру. |
| `test_video_editor_preview_contracts.py` | Размер preview-рендера (DPR, scale, quality), main-renderer, resampler, prescale target. |
| `test_video_editor_preview_settings_contracts.py` | i18n-ключи preview-quality для всех языков; только translation-keys; persistence roundtrip. |
| `test_video_editor_preview_cache_contracts.py` | `display_cache_key` стабилен для одинаковых входов. |
| `test_keyframe_enabled_gating.py` | Per-instance keyframes не воскрешают disabled-фичу; применяются при globally enabled. |
| `test_keyframe_values.py` | Color-channels как hold; компакция color-drag; continuous scalar без step-пар. |
| `test_video_timeline_thumbnail_contracts.py` | Thumbnail: динамическая ширина, приоритетные/capped волны, координатор предпочитает viewport-индексы. |

## Два жанра тестов

### 1. Архитектурные контракты (`tests/contracts/`)

Не запускают приложение — парсят исходники и проверяют дисциплину:

- `test_canvas_features_manifest.py` — каждая фича в `src/ui/canvas_features/` экспортирует `WIDGET_FEATURE` с `name`.
- `test_canvas_features_aliases.py` — capability aliases объявлены и уникальны.
- `test_canvas_features_imports.py` — фичи не импортируют друг друга напрямую (общение через Store/EventBus/aliases).
- `test_canvas_features_layout.py`, `test_canvas_features_gl_passes.py` — обязательные подмодули и сигнатуры passes.
- `test_plugins_structure.py`, `test_plugins_isolation.py` — то же для `src/plugins/*`.

Параметризуй такие тесты через `list_canvas_features()` / `list_plugins()` и `pytest.mark.parametrize(..., ids=...)` — тогда новая фича автоматически попадает под все правила без правки тестов.

### 2. Контракты поведения (`tests/render/`, `tests/runtime/`, `tests/video/`)

Импортируют рантайм-классы и собирают минимальный контекст вручную — без Qt-приложения, без OpenGL. Паттерн — `SimpleNamespace` вместо моков:

```python
from types import SimpleNamespace

def _build_ctx(*, show_divider, thickness, images_uploaded, content_rect):
    return SimpleNamespace(
        widget=SimpleNamespace(width=lambda: 100, height=lambda: 100, runtime_state=None),
        images_uploaded=list(images_uploaded),
        scene_frame=SimpleNamespace(
            feature_payloads={"show_divider": show_divider, "divider_thickness": thickness},
            is_horizontal=False,
            content_rect_px=content_rect,
        ),
    )
```

Проверяй *что* pass делает (вызвал ли painter, какие команды записал), а не *как* — без Qt-окна и реального GL.

## Правила написания новых тестов

1. **Тест на каждый контракт, а не на каждую фичу.** Если правило применимо ко всем фичам — пиши параметризованный тест в `tests/contracts/`, который автоматически покроет будущие фичи.
2. **Один файл — одна тема.** Имя в стиле `test_<thing>_contracts.py` для контрактных, `test_<feature>.py` для поведенческих.
3. **Никакого Qt/GL в юнитах.** Если тесту нужен `QApplication` — это уже интеграция; вынеси в app-level тест рядом с проверяемой подсистемой и явно создавай `QApplication.instance() or QApplication([])` в фикстуре.
4. **`SimpleNamespace` вместо `MagicMock`.** Mock ловит ошибки только когда падает, namespace — на этапе AttributeError. Тесты должны падать на отсутствующих полях контракта, а не молча проходить.
5. **Документируй догму в docstring.** Первой строкой — ссылка на раздел в `docs/dev/`, чтобы при изменении правила было понятно, какой документ обновить вместе с тестом.
6. **Не мокай Store.** Если нужно проверить редьюсер — диспатчь реальный action в реальный store; если pass — собирай `scene_frame` вручную.

## Когда тесты ломаются

- Падает contract-тест после добавления фичи/плагина — фича не соответствует догме (`docs/dev/CANVAS_FEATURES.md` или `CONTRACTS.md`). Чини фичу, не тест.
- Падает render-контракт — поменялось поведение pass. Если изменение намеренное, обнови docstring теста и сам assertion одной правкой.
- Падает на импорте — проверь, что новый код не тянет Qt/GL на верхнем уровне модуля. Lazy import внутри функции.

## Что НЕ покрыто тестами

- Реальный GL-рендеринг — пиксели из шейдеров (нужен контекст, драйверо-зависимо).
  Шов вокруг GL (render plan, `gl_scene` params, fake-GPU payload) — покрыт, см.
  `video/test_video_export_preview_parity_matrix.py`.
- Многооконные сценарии и DnD из ОС (**транспорт**). Маршрутизация drop'а
  (`route_drop`/`accepts_drop`) — покрыта в `contracts/test_tabs.py` +
  `runtime/test_tabs_lifecycle.py`.
- **Транспорт** интерактивных жестов — доставка живых событий мыши/тачпада.
  **Резолвинг** жестов (приоритет, предикаты `matches`/`is_active`) — покрыт в
  `runtime/test_gesture_resolution.py`.

Для таких проверок — ручной прогон через `python -m src` или скилл `verify`.
