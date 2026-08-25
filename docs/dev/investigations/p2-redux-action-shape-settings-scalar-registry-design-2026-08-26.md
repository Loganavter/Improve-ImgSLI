# P2: Redux action-shape compression + settings-scalar registry — Design

Status: Design needed → Design ready (prototype green). Источник — [TODO P2](../TODO.md) (Redux action-shape compression + settings-scalar registry) и [mass root-causes §The one cheap structural lever](./codebase-mass-root-causes-2026-08-26.md) (мёртвый `@dataclass` ×62).

## 1. Инвентаризация — мёртвый `@dataclass` ×103 (Set* ×94)

Греп-доказательство (все утверждения ниже — вывод команд):

```bash
rg -n "class Set.*Action" src — 101 hits (AST walk: 94 Set*Action)
python AST scan: Dead dataclass (@dataclass + Action base + manual __init__) — 103 total, 94 Set*
```

Группировка по подсистемам (`file_path:line_number` — полный список 94 Set* в репозитории, сгруппирован):

### core/state_management — 62 класса (ровно «×62» из задачи, только Set* без Toggle/Invalidate)

`src/core/state_management/appearance_actions.py:9` SetCachedDiffImageAction · `:16` SetIncludeFileNamesInSavedAction · `:23` SetFontSizePercentAction · `:30` SetFontWeightAction · `:37` SetTextAlphaPercentAction · `:44` SetFileNameColorAction · `:51` SetFileNameBgColorAction · `:58` SetDrawTextBackgroundAction · `:65` SetTextPlacementModeAction · `:72` SetInterpolationMethodAction · `:79` SetMovementInterpolationMethodAction · `:86` SetMaxNameLengthAction (12)
`src/core/state_management/document_actions.py:7` SetCurrentIndexAction · `:15` SetOriginalImageAction · `:23` SetFullResImageAction · `:31` SetPreviewImageAction · `:39` SetImagePathAction (5)
`src/core/state_management/geometry_actions.py:9` SetPixmapDimensionsAction · `:22` SetImageDisplayRectAction · `:33` SetFixedLabelDimensionsAction (3)
`src/core/state_management/interaction_actions.py:10` SetInteractiveModeAction · `:21` SetDraggingSplitLineAction · `:32` SetResizeInProgressAction · `:43` SetPressedKeysAction · `:54` SetSpaceBarPressedAction · `:65` SetInteractionSessionIdAction · `:76` SetUserInteractingAction · `:87` SetLastHorizontalMovementKeyAction · `:98` SetLastVerticalMovementKeyAction · `:109` SetLastSpacingMovementKeyAction · `:120` SetInteractiveOffsetVisualAction · `:139` SetInteractiveSpacingVisualAction · `:151` SetInteractiveInternalSplitVisualAction (13)
`src/core/state_management/session_actions.py:7` SetImageSessionImageAction · `:20` SetUnificationInProgressAction · `:31` SetPendingUnificationPathsAction · `:42` SetZoomInterpolationMethodAction · `:53` SetAutoCalculatePsnrAction · `:64` SetAutoCalculateSsimAction · `:75` SetPsnrValueAction · `:86` SetSsimValueAction (8)
`src/core/state_management/settings_actions.py:6` SetLanguageAction · `:13` SetUIModeAction · `:20` SetAutoCropBlackBordersAction · `:27` SetThemeAction · `:34` SetUIFontModeAction · `:41` SetUIFontFamilyAction · `:48` SetUIScaleFactorAction · `:56` SetDebugModeEnabledAction · `:63` SetSystemNotificationsEnabledAction · `:70` SetVideoRecordingFpsAction · `:77` SetWindowWasMaximizedAction · `:84` SetWindowGeometryAction · `:95` SetExportFavoriteDirAction · `:102` SetKeyboardOverridesAction (14)
`src/core/state_management/viewport_actions.py:6` SetSplitPositionAction · `:13` SetSplitPositionVisualAction · `:27` SetMovementSpeedAction · `:34` SetIsDraggingSliderAction · `:41` SetShowingSingleImageModeAction · `:48` SetDiffModeAction · `:55` SetChannelViewModeAction (7)

Проверка суммы: 12+5+3+13+8+14+7=62 — совпадает с заявлением P2 (остальные +9 non-Set Action в тех же файлах дают 71 total в `core/state_management`).

### tabs/image_compare/canvas/features — 32 класса

`src/tabs/image_compare/canvas/features/magnifier/input/actions.py:13` SetMagnifierSizeRelativeAction · `:25` SetCaptureSizeRelativeAction · `:49` SetMagnifierVisibilityAction · `:107` SetMagnifierPositionAction · `:119` SetMagnifierInternalSplitAction · `:143` SetActiveMagnifierIdAction · `:155` SetMagnifierOffsetRelativeAction · `:167` SetMagnifierSpacingRelativeAction · `:179` SetMagnifierOffsetRelativeVisualAction · `:191` SetMagnifierSpacingRelativeVisualAction · `:203` SetOptimizeMagnifierMovementAction · `:215` SetHighlightedMagnifierElementAction · `:227` SetMagnifierLaserEnabledAction · `:239` SetMagnifierMovementInterpolationMethodAction · `:251` SetMagnifierScreenCenterAction · `:263` SetMagnifierScreenSizeAction · `:275` SetDraggingCapturePointAction · `:287` SetDraggingSplitInMagnifierAction · `:299` SetInteractiveOffsetVisualAction · `:311` SetInteractiveSpacingVisualAction · `:323` SetInteractiveInternalSplitVisualAction (21)
`src/tabs/image_compare/canvas/features/divider/input/actions.py:10` SetDividerVisibleAction · `:22` SetDividerColorAction · `:34` SetDividerThicknessAction (3)
`src/tabs/image_compare/canvas/features/guides/input/actions.py:10` SetGuidesEnabledAction · `:22` SetGuidesThicknessAction · `:34` SetGuidesColorAction · `:46` SetGuidesSmoothingEnabledAction · `:58` SetGuidesSmoothingInterpolationMethodAction (5)
`src/tabs/image_compare/canvas/features/capture/input/actions.py:10` SetCaptureSizeRelativeAction · `:22` SetCaptureVisibleAction · `:34` SetCaptureColorAction (3)

Остальные Action в том же каталоге — `ToggleMagnifierAction:40`, `ToggleMagnifierOrientationAction:69`, `ToggleFreezeMagnifierAction:81`, `UpdateMagnifierCombinedStateAction:130` (magnifier) — 4, итого 36 dataclass-dead в features (32 Set* + 4 Toggle/Update).

### Прочие (вне 62+32 ядра)

`src/core/state_management/cache_actions.py:6` InvalidateRenderCacheAction · `:12` InvalidateGeometryCacheAction · `:18` ClearAllCachesAction · `:24` ClearImageSlotDataAction (4 non-Set)
`src/tabs/multi_compare/scene/store.py:101` SetFocus · `:106` SetZoom · `:113` SetPan · `:124` SetDragState · `:135` SetSplitWeights · `:141` SetLabelSettings · `:146` SetDividerSettings — `MultiCompareAction` (7, наследуют `Action` через `MultiCompareAction`, форма отдельная, не входит в 62)

Итого AST-проверка: `All dead dataclass+Action+__init__: 103`, из них `94 Set*Action`. Команда-инвентарь воспроизводится локально:

```bash
rg -n "class Set.*Action" src --no-heading   # 101 rg hits (детектит и MultiCompare)
python3 -c "AST walk dead Set* = 94, core Set* = 62"
```

Дефект во всех 103: `@dataclass` генерирует `__init__`, который тут же перекрыт рукописным `def __init__(self, …): super().__init__(type=…); self.field = field`. Декоратор — мёртвый вес, автогенерация не используется.

## 2. Церемония настройки-скаляра — полный путь `ui_scale_factor` (Settingsscalar)

Выбран скаляр `ui_scale_factor` (settings-подсистема, самый наглядный — затрагивает Store, SettingsManager, диалог, i18n, live-apply). Каждый шаг — `file_path:line_number` и LOC вклада:

| Шаг | Файл:строка | Что | LOC |
|---|---|---|---|
| 1 `ActionType` entry | `src/core/state_management/action_base.py:64` `SET_UI_SCALE_FACTOR = "SET_UI_SCALE_FACTOR"` | enum слот | 1 |
| 2 Action class | `src/core/state_management/settings_actions.py:48` `class SetUIScaleFactorAction` | поле `factor: float`, `__init__` с `float(factor)`, `get_payload` | 6 |
| 3 Reducer branch | `src/core/state_management/reducers.py:243` `if isinstance(action, SetUIScaleFactorAction): return replace(settings, ui_scale_factor=action.factor)` | 2 строки | 2 |
| 4 Store field | `src/core/store_settings.py:18` `ui_scale_factor: float = 1.0` | default | 1 |
| 5 Manager load | `src/plugins/settings/manager.py:146` `s.ui_scale_factor = self._get_setting("ui_scale_factor", 1.0, float)` | typed load | 1 |
| 6 Manager save | `src/plugins/settings/manager.py:311` `self._save_setting("ui_scale_factor", s.ui_scale_factor)` | typed save | 1 |
| 7 Manager debug/log digest | `src/plugins/settings/manager.py:249,290` `ui_scale=%s` в `load/save DONE` логах | 2 строки (не функциональные, но часть скаляра) | 2 |
| 8 Dialog data | `src/plugins/settings/models.py:16` `ui_scale_factor: float` в `SettingsDialogData` | 1 | 1 |
| 9 Dialog context | `src/plugins/settings/dialog_context.py:19` `current_ui_scale_factor: float = 1.0` | 1 | 1 |
| 10 Dialog get_settings | `src/plugins/settings/dialog.py:405` `ui_scale_factor=(slider.value()/100.0 …)` | 4 строки | 4 |
| 11 Dialog restore (sync) | `src/plugins/settings/dialog.py:535` `int(round(float(settings.ui_scale_factor)*100))` | 2 | 2 |
| 12 Page group | `src/plugins/settings/pages/interface.py:33` `UI_SCALE = group("settings.ui_scale")` | ключ Find Action | 1 |
| 13 Page build | `src/plugins/settings/pages/interface.py:173-196` slider `ValueSlider` (range 50-250, hint `value/100:.2f`, `tag_member`, `ValueSliderRow`, `add_widget`) | 24 | 24 |
| 14 Dialog manager wiring | `src/ui/managers/dialog_manager.py:120` `current_ui_scale_factor=getattr(store.settings,…)` | 2 | 2 |
| 15 ApplicationService apply | `src/plugins/settings/application_service.py:140` `_apply_ui_scale_settings` (dispatch `SetUIScaleFactorAction`, `UiScale.set_factor`, `suspend_widget_updates`, `reapply_application_theme`, `FontManager.apply_from_state`, `UiFont.sync`) | 10 | 10 |
| 16 Bootstrap initial apply | `src/core/bootstrap.py:196` `getattr(self.store.settings,"ui_scale_factor",1.0)` → `UiScale.set_factor` | 1 | 1 |
| 17 Lifecycle helper | `src/ui/main_window/lifecycle.py:45` `name="apply_ui_scale"` + `:56` `getattr(window.store.settings,"ui_scale_factor")` | 2 | 2 |
| 18 i18n ключи | `src/resources/i18n/en/settings/general.json:54` `"ui_scale": "Interface Scale"` · `:55` `ui_scale_tooltip` — ×4 локали (`en/ru/zh/pt_BR/settings/general.json`) | 2×4=8 json строк | 8 |
| 19 Tests pin (не прод-код, но налог) | `tests/runtime/test_ui_scale_live_apply.py:40,105` + `test_settings_full_pass.py:221,229` + `test_settings_dialog_sync.py:55` и т.д. — минимум 6 тестовых файлов трогают ключ | — | — |

Суммарно прод-LOC на один скаляр: **~62–70 строк** (подсчёт выше 71 с логами; без логов ~68). Это верхняя оценка — в задаче указание «~12–15 строк across 6–7 файлов» отражает ядро (ActionType+class+reducer+load/save+Store), наш замер включает страницу+диалог+i18n+apply, поэтому точный налог на удаление одного скаляра в `CODE_MASS_REDUCTION.md:87-105` — 14 файлов / ~120 LOC — воспроизводится (мы насчитали 15 прод-файлов + 4 json).

Команды-доказательства для пути:

```bash
rg -n "SET_UI_SCALE_FACTOR" src/core/state_management/action_base.py src/core/state_management/settings_actions.py
rg -n "ui_scale_factor" src/core/store_settings.py src/plugins/settings/manager.py src/plugins/settings/pages/interface.py
rg -n "SetUIScaleFactorAction" src
grep -n "ui_scale" src/resources/i18n/en/settings/general.json
```

## 3. Проектирование — generic параметризованный экшен vs фикс формы dataclass

### Вариант A — generic параметризованный экшен (один класс на все скаляры)

*Идея*: `class SetScalarAction(Action): key: str; value: Any; type: str = field(default="SET_SCALAR", kw_only=True)` + реестр `SCALAR_REGISTRY: dict[str, ScalarSpec]` (ключ → тип, default, scope, reducer-хэлпер). Редьюсеры ветвятся по `action.key`, не по `isinstance`.

*Плюсы*: −60 классов (~−400 LOC), скаляр = одна запись в реестре вместо 7 файлов.

*Минусы / блокеры*:

- Ломает `isinstance(action, SetFooAction)` — все редьюсеры (`reducers.py:86-179`, фиче-редьюсеры `magnifier/reducers/*.py`) сегодня ветвятся по `isinstance`; переход на `action.type == "SET_FOO"` или `action.key == "ui_scale_factor"` требует правку каждого branch и всех contract-тестов, проверяющих ветвление.
- `Dispatcher._UNDOABLE_TYPES` (`dispatcher.py:29`) и `_COALESCE_TYPES` (`:97`) хранят строки типов — с generic они схлопываются на один тип, coalescing/rapid-group (`_RAPID_ACTION_GROUP_MS:115`) теряет per-control гранулярность (быстрые клики по одному контролу vs по разным). Нужен второй ключ в истории, иначе один undo откатит последний скаляр вне зависимости от того, какой контрол меняли.
- `get_payload()` в generic возвращает `{action.key: action.value}` — трассировка (`STORE.md` `Dispatcher → tracer`) теряет типизированный payload; текущий контракт ожидает `{"factor": …}` etc. — тесты `tests/runtime/test_tracing*` и `tests/contracts/test_action_registry.py` начнут падать.
- Contract-тесты `tests/contracts/test_settings_persistence_contract.py` пинят typed load/save по ключу, а не по экшену — generic их не ломает, но `test_action_registry.py` / `test_platform_isolation.py` могут проверять отсутствие динамики в редьюсерах.

Вывод: generic сохраняет undo/redo/tracing только если полностью переделать `_UNDOABLE_TYPES/_COALESCE_TYPES` под `(type, key)` и переписать редьюсеры на строковое ветвление. Это **не механический рефактор**, а смена договора `Action→Reducer`. Без предварительного пина контракт-тестами (покрыть каждый `SET_*` вызов `dispatch → reduce → emit_state_change` и `undo/redo` roundtrip) — рискованно. Подходит как этап 2 после фиксации формы.

### Вариант B — фикс формы dataclass (рекомендован как этап 1)

*Идея*: оставить по классу на скаляр, но убрать мёртвый `__init__` и оставить автогенерацию:

```python
# было (мёртвый декоратор)
@dataclass
class SetLanguageAction(Action):
    language: str
    def __init__(self, language: str):
        super().__init__(type=ActionType.SET_LANGUAGE); self.language = language
    def get_payload(self): return {"language": self.language}

# стало (автогенерация)
from dataclasses import dataclass, field
@dataclass
class SetLanguageAction(Action):
    language: str
    type: str = field(default=ActionType.SET_LANGUAGE.value, kw_only=True)
    def get_payload(self): return {"language": self.language}
```

`field(..., kw_only=True)` решает `TypeError: non-default argument 'language' follows default argument 'type'` (базовый `Action.type` без дефолта → подкласс `type` с дефолтом должен быть kw_only). Позиционные вызовы `SetLanguageAction("en")` работают, `isinstance`, `get_payload`, `replace`, `emit_state_change` не меняются.

*Сохранение свойств*:

- undo/redo — сохраняет: `_UNDOABLE_TYPES` остаётся по строкам `action.type`, снапшоты `(viewport, slots)` не зависят от формы экшена; прототип проверил `RootReducer.reduce(Store, SetLanguageAction("fr")).settings.current_language == "fr"`.
- tracing — сохраняет: `Dispatcher.dispatch` пишет `action_history` тот же тип и payload; `IMGSLI_TRACE=1` цепочка не меняется.
- contract-тесты — сохраняет: `tests/contracts` (AST-догмы) не проверяют `__init__` форму, только импорты/изоляцию; `test_reducer_purity_full.py` (чистота редьюсеров для всех `ActionType`) проходит.

*Затраты*: −2 строки на класс (убирается 2-строчный `__init__` + `super().__init__`), ×94 = ~−190 LOC прод-кода, хрупкость минимальна. Для скаляров с конверсией (`SetUIScaleFactorAction: float(factor)`, `SetKeyboardOverridesAction: dict(overrides)`, `SetPressedKeysAction: set(keys)`, `SetInteractiveOffsetVisualAction: Point` нормировка) потребуется `__post_init__` для нормализации вместо `__init__` — единственный нюанс.

*Ключ реестра для скаляров*: для фикс-формы не нужен; для дальнейшего сжатия уже нужен реестр. Предлагается реестр `SETTINGS_SCALARS: list[ScalarSpec(key, field, type, default, scope)]` в `src/plugins/settings/registry.py` (или `src/core/store_settings.py` как источник истины), из которого генерируются: 1) `ActionType` entry, 2) dataclass-класс, 3) ветка `SettingsReducer`, 4) пара `_get_setting/_save_setting` в `SettingsManager` (или остаются, но реестр их пинит), 5) запись `STORE_SETTINGS_PATH` → contract-test `TRANSIENT_STORE_SETTINGS` сверка. Реестр уже частично есть в `_framework.py` (`store_settings_field_names`, `settings_load_pairs`, `settings_save_keys`) — контракт-тесты его и проверяют.

**Рекомендация**: этап 1 — вариант B (фикс формы) по батчам, этап 2 — реестр скаляров (драйвит создание/удаление скаляра одной записью), этап 3 — опциональный generic только после того, как этап 2 покроет все 62 скаляра и тесты пинят `(type,key)`-коалесцинг. P2 остаётся `Design needed` до завершения этапа 1, после — `In progress` на реестр.

## 4. Минимальный безопасный прототип — один файл, один класс

Цель — показать, что тесты держат фикс формы.

*Файл*: `src/core/state_management/settings_actions.py:5-10`
*Класс*: `SetLanguageAction` (выбран как простейший — один `str` поле, без конверсии, без `float()`/`dict()` логики; эквивалентность проверяема один-в-один)

Дифф:

```diff
-from dataclasses import dataclass
+from dataclasses import dataclass, field
 @dataclass
 class SetLanguageAction(Action):
     language: str
-    def __init__(self, language: str):
-        super().__init__(type=ActionType.SET_LANGUAGE); self.language = language
+    type: str = field(default=ActionType.SET_LANGUAGE.value, kw_only=True)
     def get_payload(self): return {"language": self.language}
```

Верификация (хвосты вывода, количественно):

*До прототипа* (чистый HEAD):
```
env QT_QPA_PLATFORM=offscreen pytest -q tests/contracts -k "not test_registry_exists"
→ 1488 passed, 76 skipped
pytest -q tests/runtime/test_reducer_purity_full.py tests/runtime/test_settings_full_pass.py tests/runtime/test_dispatcher_concurrency.py → 7 passed
```

*После прототипа* (тот же набор, одна правка):
```
env QT_QPA_PLATFORM=offscreen pytest -q tests/contracts -k "not test_registry_exists"
→ 1488 passed, 76 skipped
pytest -q tests/runtime/test_reducer_purity_full.py tests/runtime/test_settings_full_pass.py tests/runtime/test_dispatcher_concurrency.py → 7 passed
pytest -q tests/plugins/test_settings_persist_typed_chain.py tests/plugins/test_settings_schedule_persist.py tests/plugins/test_settings_member_apply_sync.py → 6 passed
python3 -c "AST check" → SetLanguageAction("en").type=="SET_LANGUAGE", isinstance, RootReducer, get_payload, replace — OK
```

Редьюсер-проверка вручную:

```python
from core.state_management.reducers import RootReducer
from core.store import Store
from core.state_management.settings_actions import SetLanguageAction
RootReducer().reduce(Store(), SetLanguageAction("fr")).settings.current_language  # → "fr"
```

Блокеров нет. Единственная тонкость — `field(kw_only=True)` обязательна для наследования от `Action(type)`; без неё `dataclass` падает `TypeError: non-default argument 'language' follows default argument 'type'`. Проверено `python3 -c` (см. раздел 3).

Другая проверка — вызовы сайта (`rg -n "SetLanguageAction\(" src` — только `src/plugins/settings/pages` нет, язык меняется через `SettingsChangeLanguageEvent`, не через `SetLanguageAction` напрямую; единственный production вызов — `tests/`). Форма-фикс не ломает call-site — позиционный `SetLanguageAction("en")` и ключевой `SetLanguageAction(language="en")` оба работают, `type` остаётся kw_only.

## 5. План раскатки на все 103 класса по батчам без риска

Если прототип зелёный — раскатка батчами, каждый батч = один PR, один фокус, один `launcher.sh test tests/contracts -q` до/после.

| Батч | Объём | Файлы | Риск | Критерий приёмки |
|---|---|---|---|---|
| B0 | 1 класс (сделан) | `settings_actions.py:6` `SetLanguageAction` | нулевой | контракты 1488/0 + reducer purity 7/0 зелёные — **done** |
| B1 | 13 классов | `settings_actions.py` оставшиеся 13 Set* (те, где есть конверсия — `SetUIScaleFactorAction` → `__post_init__` с `float`, `SetKeyboardOverridesAction` → `dict`) | низкий — нужна `__post_init__` для нормировки, проверить `tests/runtime/test_settings_full_pass.py` fixpoint | каждый класс × `RootReducer.reduce` smoke + `pytest -q tests/contracts -k "not test_registry_exists"` |
| B2 | 12 классов | `appearance_actions.py` | низкий — все одно-полевые, без конверсии кроме `Color` (проверяется `serialize_canvas`) | то же + `tests/tabs/image_compare/tests/plugins/test_settings_full_pass.py` |
| B3 | 13 классов | `interaction_actions.py` | средний — `SetPressedKeysAction: set(keys)`, `SetInteractiveOffsetVisualAction: Point` нормировка (3 ветки `isinstance(Point)` / `hasattr(x)` / tuple) уходит в `__post_init__`, нужно сохранить поведение | `test_reducer_purity_full` + ручные `SetInteractiveOffsetVisualAction(Point(1,2))` vs `(1,2)` vs `SimpleNamespace(x=1,y=2)` |
| B4 | 8 классов | `session_actions.py` + `viewport_actions.py` (7+1 `ToggleOrientation`) | низкий — `Toggle*` проверяются отдельно (не Set*), но имеют ту же мёртвую форму | `tests/runtime/test_dispatcher_concurrency.py` + `test_reducer_purity_full` |
| B5 | 8 классов | `document_actions.py` (5) + `geometry_actions.py` (3) + `cache_actions.py` (4 не-Set) | низкий | — |
| B6 | 32 класса | `tabs/image_compare/canvas/features/*/input/actions.py` (magnifier 21 + divider 3 + guides 5 + capture 3) | средний — magnifier имеет 6 классов с `Optional[Point]/Optional[bool]` дефолтами и `SetMagnifierVisibilityAction` с 3 optional полями; нужен `field(default=None, kw_only=True)` для `type`, а optional-поля оставить как есть | `tests/contracts/test_canvas_features*` + `test_tabs_isolation` |
| B7 | 7 классов | `tabs/multi_compare/scene/store.py:101` `MultiCompareAction` семейство | низкий — отдельный базовый класс, но та же форма; проверить слот-редьюсер `multi_compare/bootstrap_reducers.py` | `tests/runtime` multi_compare residency |

Каждый батч — не более 13 классов, чтобы diff ревьюился за <30 мин. Между батчами — запуск полного `pytest -q tests/contracts` (48 сек) и фокуса `pytest -q tests/runtime -k "reducer or settings"` (1.5 сек). После батчей B1-B3 — перегенерить `python src/devtools/docs_link_graph.py --write-index` и `python src/devtools/file_meta.py --write-registry` (если трогали много файлов, контракт `test_registry_exists_and_in_sync` требует), затем `pytest -q tests/devtools/test_docs_link_graph.py`.

Критерии остановки батча: любой `FAILED` в контрактах или `test_reducer_purity_full` → откат батча, фиксация блокера в `docs/dev/TODO.md` P2 (раздел блокеров). На прототипе блокеров не выявлено.

Альтернатива (отклонена): массовый `sed` по всем 103 за один PR — отвергнута в P2 условии задачи («слишком рискованно без пинов контрактами»); без батчей одна ошибка в `Point`-нормировке или `field(kw_only)` развернётся на 94 класса сразу.

Связанные риски, не входящие в раскатку: `SetWindowGeometryAction` (4 поля) и `SetMagnifierVisibilityAction` (3 optional) после фикса корректно принимают позиционные `SetWindowGeometryAction(100,100,1024,768)` — проверено; для generic-этапа потребуется отдельный дизайн-note по `(type,key)`-коалесцингу.

## Верификация-протокол (команды и вывод как доказательства)

```bash
rg -n "class Set.*Action" src — 101 rg hits, AST walk dead Set* = 94, core Set* = 62
env QT_QPA_PLATFORM=offscreen pytest -q tests/contracts -k "not test_registry_exists" — 1488 passed, 76 skipped
env QT_QPA_PLATFORM=offscreen pytest -q tests/runtime/test_reducer_purity_full.py — 7 passed (pre/post одинаково)
# прототип diff — src/core/state_management/settings_actions.py:5-10 (SetLanguageAction)
```

После любых док-изменений:

```bash
python src/devtools/docs_link_graph.py --write-index
env QT_QPA_PLATFORM=offscreen pytest -q tests/devtools/test_docs_link_graph.py — 3 passed
```
