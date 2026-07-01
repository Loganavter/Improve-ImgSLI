# `store.document.*` Fan-Out — Remaining Hygiene

Дата: 2026-07-01.

Этот документ фиксирует единственный незакрытый нюанс шага 8
`TAB_OWNERSHIP_AUDIT.md`: массовый прямой доступ к `store.document.*` из
платформенного и плагинного кода. Хранилище уже перенесено в
`session.state_slots["document"]` — эта работа чисто косметическая.

## Текущее положение

- `DocumentModel` / `ImageItem` живут в
  `src/tabs/image_compare/state/document.py`.
- `WorkspaceSession.document` — property-прокси на
  `session.state_slots["document"]`.
- `Store.document` — `@property`, читающий/пишущий активную сессию.
- `src/core/store_document.py` — тонкий re-export shim, единственная запись в
  ALLOWLIST в `tests/contracts/test_platform_isolation.py`.
- Каждая создаваемая workspace-сессия (включая `session_picker` и
  `multi_compare`) получает пустой `DocumentModel()` в слоте — это временная
  совместимость.

## Почему shim ещё нужен

По коду разбросано ~188 обращений вида `store.document.image1_path`,
`store.document.image_list1`, `store.document.original_image1` и т.п.
Пока они существуют, `core/store_document.py` должен продолжать
экспортировать `DocumentModel` (для типизации `store_settings`,
`store_operations`, `state_management/reducers`, `_build_worker_snapshot`),
а Store должен возвращать не-None `DocumentModel` для любой активной сессии.

Убрать shim и ограничить slot только image_compare-сессиями можно только
после fan-out.

## Что нужно сделать

Задача разбивается по слоям — от узкого к широкому:

### 1. Core reducers / dispatcher

Файлы:

- `src/core/state_management/reducers.py`
  - `DocumentReducer.reduce(document: DocumentModel, action)` — параметр
    остаётся, но должен получать document через явный tab-API,
    а не через `store.document` в `RootReducer.reduce`.
  - `new_store.document = new_document` — переписать на присваивание в slot
    активной сессии.
- `src/core/state_management/dispatcher.py`
  - `self._store.document = new_store.document`,
    `active_session.document = self._store.document` — оба присваивания
    станут no-op после того, как `Store.document` больше не будет
    атрибутом-зеркалом.
- `src/core/store_operations.py`
  - `clear_image_slot_data`, `set_current_image_data`, `swap_all_image_data`,
    `copy_for_worker` — все обращаются к `self.document.*`; должны
    получать document через явный tab-service / зарегистрированный
    action на активной вкладке.

Оценка: ~50 правок, все инкапсулированные.

### 2. Services

Файлы под `src/services/` уже почти все переехали в
`tabs/image_compare/services/` (см. audit шаги 1–7). Оставшиеся общие
сервисы не должны читать/писать `store.document.*` — если находится
такой доступ, его надо заменить на tab-owned service call.

Проверка:

```bash
grep -rn "store\.document\." src/services/ src/shared/
```

### 3. Plugins

`plugins.export`, `plugins.video_editor`, `plugins.settings`,
`plugins.image_properties` могут обращаться к `store.document.*`.
Заменять на:

- `TabRegistry.create_service("live_frame_snapshot", store)` для чтения
  текущего кадра;
- `TabRegistry.create_service("export_save_context_builder", ...)` для
  экспортных путей;
- явный tab-owned session controller для мутаций.

Ожидаемая сложность выше, чем в core: часть плагинов уже мигрирована в
tabs, часть остаётся в `src/plugins/*` (см. audit "Plugins").

### 4. UI / presenters / event handlers

Файлы:

- `src/ui/main_window/*`, `src/ui/presenters/*`, `src/events/*`, где
  осталось `store.document.*`.

После шагов 1–3 останутся преимущественно read-only обращения из UI
слоя — их можно перевести на tab-owned presenter / feature state API.

### 5. Tab-internal

Внутри `src/tabs/image_compare/` доступ к `store.document.*` допустим —
это владелец. Но и там желательно переключить на прямой
`store.get_session_state_slot("document")` (или именованный tab-API),
чтобы визуально отделить владение.

## Финализация

Когда все `store.document.*` вне `src/tabs/image_compare/` исчезнут:

1. Удалить `src/core/store_document.py`.
2. Убрать соответствующую запись из ALLOWLIST в
   `tests/contracts/test_platform_isolation.py`.
3. Убрать поле `DocumentModel` из `_build_worker_snapshot` и связанных
   типов в `core/store_settings.py` (типизация становится `Any` или
   forward-ref через registry).
4. Ограничить `session.state_slots["document"]` только для
   image_compare-сессий — прекратить создавать пустой `DocumentModel()`
   в `create_workspace_session` для остальных session_type.
5. Переименовать slot `"document"` в `"image_compare.document"` (наконец
   явно tab-owned), либо перевести на именование, диктуемое
   `SessionBlueprint.state_slots`, — сейчас имя оставлено generic
   намеренно, чтобы платформа не упоминала `image_compare`.
6. Добавить contract-тест: `store.document.*` не встречается вне
   `src/tabs/image_compare/`.

## Контрольные счётчики

Перед началом:

```bash
grep -rn "store\.document\." src/ | wc -l   # ~188
grep -rn "\.image1_path\|\.image2_path" src/ | grep -v tabs/image_compare | wc -l
```

После завершения оба должны стать ≈0 (кроме tab-internal).

## Связано

- [[TAB_OWNERSHIP_AUDIT]] шаг 8 — источник этого документа.
- [[TAB_CONTRACT]] — как правильно оформлять tab-owned session slot.
- [[STORE]] — actions/reducers/scopes.
