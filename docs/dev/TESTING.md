# Тесты

Гайд по структуре тестов, запуску и написанию новых.

## Запуск

```bash
# из корня репозитория
pytest                                   # весь набор (top-level tests/ + все src/tabs/*/tests/)
pytest tests/contracts                   # только общеархитектурные контракты
pytest src/tabs/image_compare/tests      # только тесты таба image_compare
pytest src/tabs/multi_compare/tests/render -q
pytest -k divider                        # все тесты со словом divider
pytest tests/runtime/test_event_bus_depth.py::TestEventBusDepth
```

`sys.path` для `src/` в top-level `tests/` добавляется автоматически из `tests/conftest.py`. Тесты внутри `src/tabs/<tab>/tests/` в этом не нуждаются: там от `src/` до файла теста — сплошная цепочка пакетов с `__init__.py`, поэтому pytest сам вставляет `src/` в `sys.path` при построении rootdir-пакета (стандартный prepend-import-mode). `sli-ui-toolkit` устанавливается как внешняя зависимость из `requirements-gui.txt`; локального fallback-пути к vendored toolkit нет. Тесты приложения проверяют только app-интеграцию с toolkit, а не публичный API самой внешней библиотеки.

Конфиг pytest в репозитории не используется (`pytest.ini` / `pyproject.toml` отсутствуют) — discovery идёт по стандартным правилам.

## Структура

Тесты разложены по двум осям: **тип проверки** (contracts/render/runtime/plugins) внутри **владельца** (общеприкладной код в `tests/`, таб-специфичный код в `src/tabs/<tab>/tests/`).

**Правило владения:** если тест импортирует `tabs.<tab_name>.*` (в том числе лениво, внутри тела функции) и проверяет поведение именно этого таба — тест живёт в `src/tabs/<tab_name>/tests/`, не в `tests/`. Если тест проверяет общий механизм (реестр табов, `TabContract`, Feature State API, event bus, stacking policy, плагинную изоляцию и т.п.) — он остаётся в `tests/`, даже если для примера инстанциирует конкретный таб. Подробности и структура папки — [TAB_CONTRACT.md §Tests](TAB_CONTRACT.md#tests).

| Папка | Что проверяет | Стиль |
|---|---|---|
| `tests/contracts/` | Общеархитектурные догмы, не привязанные к одному табу (см. `docs/dev/CONTRACTS.md`, `QRHI_CANVAS_FEATURES.md`). Сканирует исходники AST'ом, без запуска кода. | Статический анализ |
| `tests/runtime/` | Общие контракты при импорте/исполнении: registry, event bus, stacking policy, изоляция презентации, graceful degradation. | Импорт + assertions |
| `tests/render/` | Общее поведение composition/render-plan, не привязанное к конкретному табу. | Fake-context |
| `tests/plugins/` | Поведение плагинов (`src/plugins/*`), не завязанных на один таб: settings, help, clipboard, workspace-хром. | Юнит/интеграционные |
| `src/tabs/image_compare/tests/{contracts,render,runtime,plugins,video}/` | Всё, что специфично для таба image_compare (canvas features, magnifier, divider, video editor). | Смешанный — см. TAB_CONTRACT.md |
| `src/tabs/multi_compare/tests/{contracts,render,runtime,plugins}/` | Всё, что специфично для таба multi_compare (композиция, dividers, labels, context menu). | Смешанный — см. TAB_CONTRACT.md |

Общий хелпер для contract-тестов в `tests/` — `tests/contracts/_framework.py`: пути (`SRC`, `CANVAS_FEATURES`, `PLUGINS`), `iter_py`, `read`, `module_imports`, `list_canvas_features`, `list_plugins`, `feature_name`. Используй его вместо ручного `Path(__file__).parent…`. Таб-специфичные contract-тесты не шарят этот хелпер напрямую — `src/tabs/image_compare/tests/contracts/_framework.py` держит свою (более узкую) копию с путями, пересчитанными под глубину `src/tabs/<tab>/tests/contracts/`, чтобы папка таба оставалась самодостаточной.

## Каталог файлов

Что защищает каждый файл — чтобы не читать исходники по одному. Догма каждого
теста указана первой строкой его docstring'а. Ниже — только `tests/`
(общеархитектурные контракты). Каталог тестов конкретного таба смотри рядом
с ним: `src/tabs/image_compare/tests/`, `src/tabs/multi_compare/tests/`
(docstring первой строкой играет ту же роль — отдельного каталога-таблицы
для каждого таба здесь не дублируем).

### `contracts/` — структурные догмы (AST-скан, без запуска)

| Файл | Что защищает |
|---|---|
| `test_canvas_features_manifest.py` | Каждая фича в `ui/canvas_features/` экспортирует `WIDGET_FEATURE` с `name`; имена уникальны. |
| `test_canvas_features_imports.py` | Shared-код не импортирует `tabs.image_compare.canvas.features.<name>` напрямую. |
| `test_canvas_features_layout.py` | `canvas_presentation` без feature-именованных хелперов; фича не реинтродуцирует свой render-pipeline. |
| `test_canvas_features_render_passes.py` | Рендер-пассы объявляют `stack_role`, не хардкодят layer/priority; общий `shader_sources` без feature-шейдеров. |
| `test_canvas_widget_ownership.py` | Magnifier/toolbar-код лежит под `tabs.image_compare.*`, не в shared canvas-слое (текстовая проверка путей). |
| `test_canvas_content_geometry_single_owner.py` | Единственный владелец content-geometry вычислений; нет прямого доступа к canvas bounds в обход allowlist. |
| `test_events_no_feature_branching.py` | `mouse.py`/события не ветвятся по feature-флагам и не зовут feature-aliases напрямую. |
| `test_no_manual_theming.py` | Нет ручных вызовов темизации вне theme-инфры. |
| `test_no_system_tooltips.py` | Нет системных Qt-тултипов в обход общего tooltip-интерцептора. |
| `test_plugins_structure.py` | Каждый плагин: entry-point, декоратор+база, имя совпадает с папкой, имена уникальны. |
| `test_plugins_isolation.py` | Плагин не импортирует canvas-фичи и внутренности других плагинов. |
| `test_platform_isolation.py` | Платформенный (не таб-специфичный) код не упоминает и не импортирует конкретные табы напрямую. |
| `test_tabs.py` | Каждый таб в `src/tabs/` — заполненный `TabContract`, `session_type` уникален. |
| `test_tabs_isolation.py` | Таб не импортирует app-i18n/тему; JSON-переводы только в своём namespace. |
| `test_viewport_state_slots.py` | `ViewportState` слотирован (без `__dict__`); `overlay_clip_rect` живёт в runtime-cache, запись на ViewportState падает. |

### `runtime/` — контракты при импорте/исполнении

| Файл | Что защищает |
|---|---|
| `test_interaction_contracts.py` | Event-слой изолирован от фич; interaction-aliases резолвятся; hit-test pipeline заполнен callable. |
| `test_shared_presentation_isolation.py` | `shared/` и плагины используют только aliases; Phase-5 aliases резолвятся. |
| `test_event_bus_depth.py` | Guard глубины EventBus: циклическая цепочка останавливается на `MAX_EMIT_DEPTH`, счётчик сбрасывается между top-level emit'ами. |
| `test_plugin_graceful_degradation.py` | Пустой `plugins/` и неизвестный alias не валят bootstrap (graceful degradation). |
| `test_tabs_lifecycle.py` | Drop роутится по `accepts_drop`; `dispose()` идемпотентен (генерический registry-механизм, использует `ImageCompareTab` только как пример). |
| `test_keyboard_movement_contracts.py` | Клавиатурные жесты перемещения не завязаны на конкретный таб. |
| `test_dialog_auto_decoration.py` | Автодекорация диалогов (иконки/тайтлбар) применяется на общем host-уровне. |
| `test_main_window_resize_runtime.py` | Ресайз главного окна не привязан к конкретному табу. |
| `test_tooltip_interceptor.py` | Единый tooltip-интерцептор перехватывает подсказки для всех виджетов, включая tab bar. |
| `test_language_broadcast.py` | Смена языка транслируется всем i18n-виджетам через `resources.translations`; host выставляет `store` до `setupUi`. |

### `render/` — общее поведение composition/render-plan (fake-context)

| Файл | Что защищает |
|---|---|
| `test_composition_plan.py` | Общая сборка composition-плана не привязана к конкретному табу. |
| `test_plan_applicator_composition.py` | Applicator корректно комбинирует composition-плана независимо от таба. |
| `test_qrhi_backend_selection.py` | Выбор QRhi-бэкенда — общий механизм, не завязан на таб. |
| `test_qrhi_canvas_resize_contract.py` | Ресайз QRhi canvas делегирует в общий resize-geometry pipeline. |

### `plugins/` — поведение плагинов, не завязанных на один таб

| Файл | Что защищает |
|---|---|
| `test_settings_controller.py` | `apply_font_settings` батчит и капчит; пропускает капчу без изменений. |
| `test_clipboard_paste_shortcut.py` | Ctrl+V на canvas эмитит paste-event. |
| `test_help_dialog_anchors.py` | Help: strip anchor-суффикса, генерация heading-id, TOC из h3-секций. |
| `test_image_properties.py` | Свойства изображения читаются независимо от активного таба. |
| `test_main_window_canvas_theme_background.py` | Смена темы обновляет фон canvas-контейнера и placeholder на host-уровне. |
| `test_main_window_save_button.py` | Кнопка сохранения в главном окне — host-хром, не таб-специфична. |
| `test_settings_dialog_geometry.py` | Геометрия диалога настроек. |
| `test_workspace_session_menu_translations.py` | Меню сессий workspace использует переводы host-уровня. |
| `test_workspace_tab_close.py` | Закрытие последней вкладки workspace закрывает главное окно (host-механика workspace, не конкретный таб). |
| `test_workspace_tabs_layout.py` | Layout `workspace_tabs` (QTabBar) — host-виджет управления вкладками, не сам таб. |

## Два жанра тестов

### 1. Архитектурные контракты (`tests/contracts/`, `src/tabs/*/tests/contracts/`)

Не запускают приложение — парсят исходники и проверяют дисциплину:

- `test_canvas_features_manifest.py` — каждая фича в `src/ui/canvas_features/` экспортирует `WIDGET_FEATURE` с `name`.
- `src/tabs/image_compare/tests/contracts/test_canvas_features_aliases.py` — capability aliases объявлены и уникальны.
- `test_canvas_features_imports.py` — фичи не импортируют друг друга напрямую (общение через Store/EventBus/aliases).
- `test_canvas_features_layout.py`, `test_canvas_features_render_passes.py` — обязательные подмодули и сигнатуры passes.
- `test_plugins_structure.py`, `test_plugins_isolation.py` — то же для `src/plugins/*`.

Параметризуй такие тесты через `list_canvas_features()` / `list_plugins()` и `pytest.mark.parametrize(..., ids=...)` — тогда новая фича автоматически попадает под все правила без правки тестов.

### 2. Контракты поведения (`tests/render/`, `tests/runtime/`, `src/tabs/*/tests/{render,runtime,video}/`)

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

- Падает contract-тест после добавления фичи/плагина — фича не соответствует догме (`docs/dev/QRHI_CANVAS_FEATURES.md` или `CONTRACTS.md`). Чини фичу, не тест.
- Падает render-контракт — поменялось поведение pass. Если изменение намеренное, обнови docstring теста и сам assertion одной правкой.
- Падает на импорте — проверь, что новый код не тянет Qt/GL на верхнем уровне модуля. Lazy import внутри функции.

## Что НЕ покрыто тестами

- Реальный GL-рендеринг — пиксели из шейдеров (нужен контекст, драйверо-зависимо).
  Шов вокруг GL (render plan, `render_scene` params, fake-GPU payload) — покрыт, см.
  `src/tabs/image_compare/tests/video/test_video_export_preview_parity_matrix.py`.
- Многооконные сценарии и DnD из ОС (**транспорт**). Маршрутизация drop'а
  (`route_drop`/`accepts_drop`) — покрыта в `contracts/test_tabs.py` +
  `runtime/test_tabs_lifecycle.py`.
- **Транспорт** интерактивных жестов — доставка живых событий мыши/тачпада.
  **Резолвинг** жестов (приоритет, предикаты `matches`/`is_active`) — покрыт в
  `src/tabs/image_compare/tests/runtime/test_gesture_resolution.py`.

Для таких проверок — ручной прогон через `python -m src` или скилл `verify`.
