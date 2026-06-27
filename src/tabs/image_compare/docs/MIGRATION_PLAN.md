# image_compare → TabContract: фактический статус

Документ фиксирует состояние после аудита working tree. Старый текст
утверждал, что миграция полностью завершена серией коммитов; это уже
недостоверно для текущего дерева. Сейчас tab-side часть в основном жива, но
host-side зачистка осталась частичной и отслеживается тестом
`tests/contracts/test_platform_isolation.py`.

## 1. Что сейчас лежит в `tabs/image_compare/`

```
src/tabs/image_compare/
    __init__.py
    tab.py                      # ImageCompareTab(TabContract)
    widget.py                   # ImageCompareWidget, assemble(ui)
    models.py                   # ImageCompareState dataclass
    plugin.py                   # ComparisonPlugin + image_compare.state slot
    _session_controller.py      # tab-owned session controller
    canvas/
    events/
    presenters/image_canvas/
    services/playlist*
    state/
    ui/
        appearance.py
        context_menu.py
        layout.py
        primitives.py
        settings_performance.py
    use_cases/
    resources/i18n/{en,ru,pt_BR,zh}/image_compare.json
```

## 2. TabContract coverage

| Метод | Состояние |
|---|---|
| `session_type`, `display_name`, `resources_dir`, `i18n_namespace` | Готово |
| `localized_display_name(language)` | Через `sli_ui_toolkit.i18n`, key `image_compare.session_type` |
| `create_page` | Возвращает `ImageCompareWidget` |
| `transition_hint` | `TabTransitionHint(cover_on_enter=True, min=50, max=400)` |
| `on_activated` | snapshot/restore `image_compare.state` + focus |
| `on_deactivated` | snapshot state slot; теперь вызывается registry при смене tab |
| `accepts_drop` / `handle_drop(paths, hint)` | По расширениям; `hint["slot"]` / `hint["is_left_area"]` выбирает slot 1/2 |
| `contribute_settings` | Регистрирует `image_compare.analysis` и extras для `builtin.performance` |
| `apply_appearance` | Tab-side canvas appearance hook подключён через registry |
| `on_window_shutdown` | Registry wrapper подключён; tab пока no-op |
| `dispose` | Зануляет widget |

## 3. Что исправлено после аудита

- `TabRegistry.activate()` теперь деактивирует предыдущий tab перед активацией
  нового. Это нужно для сохранения per-session UI-only state при уходе с
  image_compare.
- `TabRegistry.route_drop()` принимает `hint` и передаёт его в
  `TabContract.handle_drop()`.
- `WindowEventHandler` больше не роутит image drop в tab до вычисления slot:
  он передаёт generic `{"slot": 1|2, "is_left_area": bool}`.
- `ImageCompareTab.handle_drop()` использует slot из hint вместо всегда slot 1.
- `SettingsRegistry` получил `add_section_extra()` / `extras_for()`.
  `plugins/settings/pages/performance.py` больше не проверяет
  `active_tab == "image_compare"`; image_compare сам добавляет свои
  performance-группы.
- `SettingsDialog` лениво загружает tab settings contributions, чтобы
  standalone создание диалога с `active_tab="image_compare"` тоже видело
  `image_compare.analysis`.
- Settings shell снова не resize-ит уже видимый диалог и очищает duplicate
  sidebar tooltips.
- `MainWindowAppearance` вызывает `TabRegistry.apply_appearance()` и больше не
  держит прямой `image_compare_widget` target в chrome background list.
- Shutdown pipeline вызывает `TabRegistry.notify_window_shutdown()` и
  `dispose_all()`.

## 4. Оставшийся host-side structural debt

Эти пункты намеренно остаются в allowlist `test_platform_isolation.py` до
отдельного refactor-а:

- `src/ui/main_window/layouts.py` всё ещё явно достаёт
  `get_tab("image_compare")`, вызывает `tab.widget.assemble(ui)` и стартует
  через `sync_session_mode("image_compare")`. Причина: primitive widgets
  (`btn_*`, sliders, `image_label`) ещё создаются host UI.
- `src/ui/main_window/ui.py` всё ещё хранит `image_compare_widget` и
  `sync_session_mode()` проверяет `session_type == "image_compare"` для
  `edit_layout_widget`.
- `src/ui/presenters/main_window/state.py` всё ещё special-case-ит active
  `image_compare` при reupload canvas state.
- `src/ui/presenters/main_window/workspace.py` и
  `src/core/store_workspace.py` всё ещё используют fallback default
  `"image_compare"` при отсутствии active session.
- `src/plugins/video_editor/model.py::open_image_compare()` остаётся
  cross-tab launch helper.
- Legacy parallel paths ещё существуют:
  `src/plugins/comparison/`, `src/ui/context_menu/image_compare.py`,
  `src/ui/widgets/gl_canvas/widget.py`.
- `src/core/state_management/reducers.py::ImageSessionReducer` остаётся
  в core. Deep step 9 (`viewport.session_data` / `render_config` named slots)
  не закрыт.

## 5. Текущий тестовый статус

Проверки, которые прошли:

```bash
python -m compileall -q src/tabs src/events src/plugins/settings src/ui/main_window \
  tests/runtime/test_tabs_lifecycle.py tests/plugins/test_settings_dialog_geometry.py
env QT_QPA_PLATFORM=offscreen pytest -q \
  tests/plugins/test_settings_dialog_geometry.py \
  tests/runtime/test_tabs_lifecycle.py \
  tests/runtime/test_context_menu_integration.py
env QT_QPA_PLATFORM=offscreen pytest -q tests/contracts/test_platform_isolation.py
```

Результаты:

- focused runtime/settings/context-menu: `12 passed`
- full runtime: `191 passed`
- platform isolation: `410 passed / 9 skipped`
- full contracts: `607 passed / 9 skipped / 2 failed`

Оставшиеся full-contract failures считаются pre-existing для этой миграции:

- `tests/contracts/test_canvas_features_imports.py`:
  `src/tabs/multi_compare/ui/layer_labels.py` импортирует
  `filename_overlay`.
- `tests/contracts/test_no_manual_theming.py`: 11 manual theming offenders.

Runtime collection blockers, найденные во время аудита, закрыты:

- `shared_toolkit.ui.decorate_dialog` снова экспортирует
  `CUSTOM_DECORATION_RESIZE_MARGIN` и
  `configure_custom_decoration_resize_margin()`.
- `tabs.multi_compare.ui.gl_grid.GLGridWidget` добавлен как compat alias на
  текущий `MultiCompareCanvasWidget`.

## 6. Manual smoke перед merge

- Создать две image_compare сессии, переключаться между ними и проверить, что
  `btn_file_names`, `edit_name1`, `edit_name2` восстанавливаются per-session.
- Drag-and-drop изображений на левую и правую половину active image_compare:
  slot должен соответствовать половине.
- Открыть Settings из image_compare: `Details` виден, image-specific
  performance groups видны.
- Открыть Settings из другого tab: `Details` скрыт, image-specific performance
  groups скрыты, render backend остаётся видимым.
- Переход image_compare → multi_compare → image_compare: transition mask
  снимается по первому canvas frame.
