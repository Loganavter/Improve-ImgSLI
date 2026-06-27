# image_compare → TabContract: текущее состояние

Документ заменяет прежний поэтапный план. Миграция завершена тремя
коммитами на ветке `migrate/qrhi`:

- `96429e6 refactor(image_compare): TabContract skeleton + extract page builder`
- `4e5a2af refactor(image_compare): drop image_session_page wrapper, wire tab lifecycle`
- `23d6ab3 feat(image_compare): finish TabContract migration — slot state, i18n, settings`

## 1. Что сейчас лежит в `tabs/image_compare/`

```
src/tabs/image_compare/
    __init__.py
    tab.py                # ImageCompareTab(TabContract)
    widget.py             # ImageCompareWidget, assemble(ui), firstVisualFrameReady→mask.release
    models.py             # ImageCompareState dataclass
    plugin.py             # ComparisonPlugin + SessionSlotBlueprint('image_compare.state')
    events.py
    session_controller.py
    use_cases/
    ui/
        __init__.py
        layout.py         # ImageCompareLayoutBuilder
    resources/i18n/{en,ru,pt_BR,zh}/image_compare.json
    docs/MIGRATION_PLAN.md
```

## 2. Покрытие TabContract

| Метод | Состояние |
|---|---|
| `session_type`, `display_name`, `resources_dir`, `i18n_namespace` | Полноценно |
| `localized_display_name(language)` | Резолвится через `workspace.session_types.image_compare` |
| `create_page` | Возвращает `ImageCompareWidget` |
| `transition_hint` | `TabTransitionHint(cover_on_enter=True, min=50, max=400)` |
| `on_activated` | snapshot/restore state slot + `setFocus` |
| `on_deactivated` | snapshot state slot |
| `on_session_created` | no-op (слот создаётся blueprint'ом) |
| `on_session_closed` | сбрасывает `_active_session_id` |
| `accepts_drop` / `handle_drop` | По расширениям; роутит в `main_controller.sessions.load_images_from_paths` |
| `contribute_settings` | Регистрирует `image_compare.analysis` (бывшая `builtin.analysis`) |
| `dispose` | Зануляет widget |

## 3. Архитектурные перемены в хосте

- `ui.image_session_page` больше нет — `workspace_stack` напрямую содержит
  `ImageCompareWidget`. `sync_session_mode` единым путём идёт через
  `_tab_registry.get_page`.
- `LayoutComposer` отдал всю image_compare сборку в
  `tabs/image_compare/ui/layout.py::ImageCompareLayoutBuilder`.
- `plugins/settings/pages/analysis.py` — только `build()`; регистрация
  секции уехала в `ImageCompareTab.contribute_settings`.
- `appearance._apply_widget_background` теперь работает с
  `image_compare_widget`, не с пропавшим `image_session_page`.
- `CanvasWidget.firstVisualFrameReady` подписан в `ImageCompareWidget` —
  маска transition'а снимается по факту первого валидного кадра.

## 4. Per-session state

`SessionSlotBlueprint("image_compare.state", factory=ImageCompareState)`
зарегистрирован в `ComparisonPlugin.get_session_blueprints()`. Tab при
переключении сессий вызывает `store.set_session_state_slot` /
`ensure_session_state_slot`.

`ImageCompareState` сейчас покрывает только UI-only поля, которые не
живут в `viewport`:

- `show_file_names`
- `edit_name_1`
- `edit_name_2`

Всё остальное (paths, divider position, magnifier params, метрики)
уже было per-session через `workspace_session.viewport`/`.document` —
это инфраструктура хоста, не требующая дублирования.

## 5. Что НЕ закоммичено и осталось в working tree

Изменения в `src/ui/main_window/ui.py`, сделанные в этой сессии, в
коммит не попали — файл слишком плотно перепачкан pre-existing
рефакторингом, который смешать с миграцией нельзя без потери авторства.
В working tree уже лежит:

- Удаление `"image_compare"` ключа из `_SESSION_TYPE_KEYS`.
- Удаление `@property image_session_page` (proxy).
- `_localized_session_type_label` сначала спрашивает
  `_tab_registry.get_tab(session_type).localized_display_name(lang)`.

Тесты проходят с этим working tree. Эти строчки должны попасть в
следующий же коммит по `ui.py` (вместе с pre-existing dirty work, у
которого свой автор).

## 6. Регрессии и smoke-чек

Все проверки выполняются под `QT_QPA_PLATFORM=offscreen` и проходят:

- `Ui_ImageComparisonApp().setupUi(mw)` собирается.
- `workspace_stack.count() == 4` (image_compare + multi_compare +
  session_picker + video_session_page).
- `sync_session_mode("image_compare")` показывает `ImageCompareWidget`.
- `_localized_session_type_label("image_compare", "ru")` → «Сравнение
  изображений».
- `get_settings_registry()` содержит `image_compare.analysis` и НЕ
  содержит `builtin.analysis`.
- `ImageCompareTab.accepts_drop([Path("x.png")]) is True`,
  `accepts_drop([Path("x.txt")]) is False`.
- `transition_hint().max_duration_ms == 400`.
- `SessionBlueprint.state_slots` содержит `image_compare.state`.
- `image_label.firstVisualFrameReady` существует и подключён в виджете.

Runtime-проверки, которые надо прогнать вручную перед мержем:

- Открыть две image_compare сессии, переключаться между ними —
  убедиться, что `btn_file_names`/`edit_name1`/`edit_name2`
  восстанавливаются per-session.
- Drag-and-drop изображения на окно при активной image_compare сессии.
- Открыть диалог настроек, проверить, что страница «Detail» появляется
  только в image_compare.
- Переход image_compare → multi_compare → image_compare: маска
  transition'а должна сниматься по первому кадру, без чёрной паузы.
- `video_editor` всё ещё трогает `main_window.ui.image_label` напрямую —
  убедиться, что этот путь не сломался от смены родителей.

## 7. Известные хрупкости

- `image_label` (`CanvasWidget`) остаётся атрибутом `MainWindowUI`, не
  свойством `ImageCompareWidget`. Это сознательно: его читает
  `plugins/video_editor/presenter_parts/preview.py`. Переезд канваса
  внутрь image_compare потребует отдельного канала для video_editor.
- `SessionController` и связанные сервисы (`MetricsService`,
  `PlaylistManager`, `CachedDiffService`) живут глобально на плагине,
  а не per-session. Состояние, которое они держат, для image_compare
  редко между-сессионное — но если такие баги вылезут, фикс там же
  через `image_compare.state` слот.
- Имя плагина в metadata осталось `"comparison"` —
  `main_controller._get_plugin("comparison")` ожидает именно это.
  Переименование плагина — отдельная мелкая зачистка.
