# Uncrop / Fit-Content Audit — Findings and Fix Plan

Дата аудита: 2026-07-06.

Companion к [QRHI_CANVAS_FEATURES.md](./QRHI_CANVAS_FEATURES.md), раздел "The
foundation: normalized 0.0–1.0 base-image space, and how uncrop/crop fits into
it". Та секция описывает целевую модель: uncrop-паддинг — это
`FeatureLayoutRequirement`-образное расширение виртуального канваса, а
`_content_rect_px`/`_inner_content_rect_px` — два разных rect'а, второй из
которых обязателен для семантики "где картинка", а не "где весь канвас".

Аудит кода показал, что модель реализована не так, как описана. Это не
построчный обзор всего QRhi-контракта — только uncrop/fit-content часть.

## Что подтвердилось

`FeatureLayoutRequirement` → `VirtualCanvasLayout` реально существует и
работает: `src/shared/rendering/layout_contract.py:34-85`,
`resolve_virtual_canvas_layout`. Фичи регистрируют требования через
`render.layout_requirement` (магнифир — `canvas/features/magnifier/bounds.py:174-184`,
divider — `canvas/features/divider/commands.py:127`).

Оба поля `_content_rect_px` и `_inner_content_rect_px` существуют:
`canvas/state.py:44-45`.

## Что разошлось с доком

### 1. "fit_content" в экспорте — это не uncrop-для-аспекта, а паддинг под магнифир

`calculate_still_snapshot_bounds` / `calculate_global_canvas_bounds`
(`services/snapshot_render_plan_builder.py:80-239`) действительно вызывают
`resolve_virtual_canvas_layout(requirements)`, но `requirements` собираются
только из `render.layout_requirement` — то есть из фич вроде магнифира,
которым нужно "вылезти" за границы картинки. Требования "добавить паддинг,
потому что аспект вывода не совпадает с аспектом картинки" в этот список
никогда не попадают — такого источника требований в коде нет.

Подтверждение из UI: тултип чекбокса `fit_content` берёт текст из ключа
`"magnifier.fit_mode_toggle"` (`video_editor/translations.py:47`) — то есть
исторически "fit content" в коде означает "не обрезать магнифир", а не "не
обрезать картинку при несовпадении аспекта", как написано в доке.

### 2. Реальный aspect-driven letterbox — третий, отдельный механизм

`ui/canvas_presentation/layout.py:5-38` (`compute_content_layout`) считает
центрирующий fit картинки в target по
`ratio = min(canvas_w/image_w, canvas_h/image_h)`. Именно это в реальности
"не обрезает" картинку при несовпадении аспекта — используется всегда (live
canvas, export кадра — `plan_builder.py:377-385`), независимо от флага
`fit_content`, и никак не связано с `FeatureLayoutRequirement`/
`VirtualCanvasLayout`.

Итог: в коде de facto три несвязанных механизма там, где дока описывает один
унифицированный:
- letterbox по аспекту (`compute_content_layout`) — всегда активен;
- паддинг под требования фич (`FeatureLayoutRequirement`) — активен при
  `fit_content=True`, но не про аспект;
- `_inner_content_rect_px` (см. ниже) — третий, отдельный от первых двух,
  расчёт через `overlay_clip_rect`.

### 3. `_inner_content_rect_px` считается не через `VirtualCanvasLayout`, а через отдельный `overlay_clip_rect`

`plan_applicator.py:31-77` (`_compute_inner_content_rect`) берёт
`plan.gl_scene.overlay_clip_rect` — независимое поле, не связанное с
`FeatureLayoutRequirement`/`VirtualCanvasLayout` из п.1-2. Работает, но это
четвёртый параллельный источник "где на самом деле картинка".

### 4. Потребители `_content_rect_px` без fallback на `_inner_content_rect_px`

Дока прямо предупреждает: код, который клэмпит/хит-тестит по
`_content_rect_px` безусловно, "silently drifts onto the padding" при
включённом uncrop/fit-content. Найдено:

- `canvas/interaction.py:323` — `set_capture_area` клэмпит центр и радиус
  области захвата к `_content_rect_px`, не к `_inner_content_rect_px`. При
  активном паддинге круг захвата может уехать в зону паддинга.
- `canvas/render_config.py:29` — `update_display_split_position` кормит
  `content_rect` (из `_content_rect_px`) в `compute_display_split_position`.
- `canvas/render_config.py:55` — `get_content_rect_screen_px` тоже только
  `_content_rect_px`.
- `canvas/features/divider/passes.py:60-79` — вместо чтения готового
  `_inner_content_rect_px`, вручную пересчитывает тот же клип через
  `scene.overlay_clip_rect` и размеры картинки — второй owner той же логики,
  ровно тот anti-pattern, о котором дока пишет отдельно ("two owners silently
  disagreeing").

Правильно (с fallback) живёт только `plan_applicator.py:101`
(`sync_geometry_state`): `getattr(state, "_inner_content_rect_px", None) or
state._content_rect_px`.

## План исправления

Делать по шагам, каждый шаг — отдельный коммит/PR, с ручной проверкой в live
canvas (drag capture area / divider / split при zoom>1 и при включённом
fit_content) до и после.

### Шаг 1 — зафиксировать источник истины для inner rect

`_inner_content_rect_px`, как считается сейчас в
`plan_applicator._compute_inner_content_rect` (через `overlay_clip_rect`),
остаётся единственным источником "где картинка внутри паддинга". Ничего не
переписывать на `VirtualCanvasLayout` на этом шаге — это отдельная, более
рискованная работа (см. Шаг 4). Цель шага 1 — не создать новый механизм, а
перестать плодить дублирующие консюмеры старого.

### Шаг 2 — убрать безусловных потребителей `_content_rect_px`

Для каждого места из раздела "4" выше:

- `canvas/interaction.py:323` (`set_capture_area`) — заменить
  `state._content_rect_px` на
  `getattr(state, "_inner_content_rect_px", None) or state._content_rect_px`,
  как уже сделано в `plan_applicator.py:101`. Проверить вручную: включить
  fit_content с ненулевым паддингом, подвигать область захвата к краю — круг
  не должен заходить за границу самой картинки.
- `canvas/render_config.py:29,55` — то же самое: `update_display_split_position`
  и `get_content_rect_screen_px` должны сначала пробовать
  `_inner_content_rect_px`. Проверить: split-line должен визуально стоять на
  той же точке картинки при zoom>1 что и без паддинга (Split-position dual-mode
  invariant из QRHI_CANVAS_FEATURES.md).
- `canvas/features/divider/passes.py:60-79` (`_divider_clip_rect_px`) —
  удалить ручной пересчёт через `overlay_clip_rect`/`image.width/height` и
  читать `state._inner_content_rect_px` напрямую (с фолбэком на
  `_content_rect_px`, если он `None`). Это устраняет второго owner'а той же
  формулы.

Это чисто механическая правка — не меняет модель, только убирает дрейф на
паддинг в конкретных фичах. Наименее рискованный шаг, делать первым.

### Шаг 3 (решено) — не переименовывать, а сделать модель agnostic к фичам

Решение продукта (зафиксировано в этом доке): не разводить "fit_content" на
два флага/термина. Вместо этого `VirtualCanvasLayout`/`FeatureLayoutRequirement`
становится единственным резолвером паддинга и для live canvas, и для
still-export, так что новая фича, добавленная под `canvas_features`, просто
регистрирует свой `render.layout_requirement` в normalized `0.0..1.0` — и
сцена (live + still export) автоматически учитывает его в crop/uncrop, без
правки какого-либо резолвера или paths вручную под каждую фичу. Aspect-driven
letterbox в этой модели — не отдельный особый случай, а такой же участник
объединения через `resolve_feature_virtual_layout`, просто с нулевым
паддингом по умолчанию (когда ни одна фича ничего не требует).

Video export (`compute_content_layout`/`GlobalCanvasBounds`/prescale-кэши в
`SnapshotFrameRenderer`) сознательно остаётся вне первого прохода — это
самый кэш-тяжёлый и рискованный путь. Объединять его — отдельный, более
поздний PR.

### Шаг 4 — единая точка резолва (`resolve_feature_virtual_layout`)

Создан `src/ui/canvas_infra/scene/layout_requirements.py`:
`resolve_feature_virtual_layout(store, *, drawing_width, drawing_height)` —
собирает все `render.layout_requirement` команды через
`get_canvas_feature_commands_by_id` и возвращает единый `VirtualCanvasLayout`
(или `None`, если store отсутствует/размеры невалидны). Резолвер полностью
agnostic к конкретным фичам — он не знает ни про лупу, ни про divider, просто
суммирует то, что зарегистрировано под `render.layout_requirement`. Сейчас
единственная фича, которая реально отдаёт не-unit bounds — магнифир
(`divider`'s `render.layout_requirement` всегда возвращает
`NormalizedBounds.unit()`, т.е. no-op).

**Live canvas — сделано и ОТКАЧЕНО.** Было подключение
`resolve_feature_virtual_layout` в
`src/tabs/image_compare/canvas/texture_parts/base_images.py::update_letterbox_geometry`.
Найден и подтверждён баг при ручной проверке в приложении: divider теряет
правильную Y-координату (и вообще геометрию) как только включена реальная
не-unit fича (лупа с overflow). Причина — не в резолвере (он agnostic и
корректен), а в точке интеграции: `update_letterbox_geometry` вызывается из
`upload_pil_images` только когда `stored_changed` (т.е. когда реально
загружена новая картинка) — а требование лупы (bbox круга) меняется на
каждое движение мыши/каждый кадр без пересозданной картинки. В результате
`_content_rect_px`/`_inner_content_rect_px` протухали сразу после первого
кадра с паддингом, и всё, что от них зависит (divider, split position),
работало по устаревшей геометрии.

Изменение в `base_images.py` полностью откачено вручную (файл побайтово
совпадает с состоянием до этой правки, `git diff` пуст). Live canvas
letterbox по-прежнему не учитывает feature-паддинг — это осознанно
оставлено как есть до тех пор, пока не будет найден правильный per-frame
хук (место, где живая геометрия и так пересчитывается каждый кадр, а не
только при смене изображения — вероятно рядом с `render_context.py`/
`plan_applicator.py`, где уже пересчитывается `_inner_content_rect_px` через
`overlay_clip_rect`). Это отдельная, ещё не сделанная задача.

**Still export — сделано, не откачено.** `calculate_still_snapshot_bounds` и
`calculate_global_canvas_bounds` в `snapshot_render_plan_builder.py`
задедуплены на `resolve_feature_virtual_layout` вместо собственной копии
union-цикла. Здесь такой проблемы со stale-состоянием нет: обе функции
вызываются заново на каждый export/каждый снапшот, а не по признаку
"картинка изменилась" — так что нет несоответствия между моментом
пересчёта требований фич и моментом использования результата.

`plan_builder.py` (`_resolve_overlay_virtual_layout`) всё ещё содержит свою
копию того же union-цикла — не задедуплено в этом проходе.

### Проблема с Y у divider — решено, причина другая (обновление 2026-07-09)

После отката live-canvas правки баг (divider теряет Y на экспорт-превью при
активном виртуальном холсте) не исчезал, и ниже была неподтверждённая
гипотеза про рассинхронизацию `_inner_content_rect_px`/`_content_rect_px`
между циклами обновления. **Эта гипотеза проверена и опровергнута.**

Подробный лог-трейсинг (`resolve_rhi_scissor`/`_resolve_divider_state`)
показал, что `content_rect_px`, `display_split`, `position_px` и итоговый
scissor (`(0, 334, 1200, 675)` для паддинга 334px) были во всех кадрах
численно верны — рассинхрона полей не было. Реальная причина оказалась
уровнем ниже, в самом потреблении scissor'а GPU-бэкендом: `gpu_export_canvas`
— это виджет с `Qt.WidgetAttribute.WA_DontShowOnScreen` (никогда не
показывается, используется только через `grabFramebuffer()`). Такие виджеты
не проходят через обычный шаг композитинга backing-текстуры в окно, который
для видимых `QRhiWidget` незаметно компенсирует Y-конвенцию RHI-бэкенда —
поэтому `rhi.isYUpInFramebuffer()` отвечал `false`, но реально требовался
флип Y, которого не было. Divider (единственный потребитель
`resolve_rhi_scissor` с `clip_to_content=True`) рисовался с верной высотой,
но с нулевым смещением вместо смещения под паддинг; базовое изображение не
задействует scissor и потому оставалось на месте — отсюда и симптом "высота
верна, позиция нет", который выглядел как геометрический баг, а был багом
Y-конвенции на уровне записи в command buffer.

Фикс: `resolve_rhi_scissor` теперь флипает Y при `y_up OR
widget.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)`. Подробности и
общее правило — в [QRHI_CANVAS_FEATURES.md](./QRHI_CANVAS_FEATURES.md),
раздел "`isYUpInFramebuffer()` is not the whole Y-flip story for offscreen
widgets".

(Остальной анализ этого дока — про `_content_rect_px`/`_inner_content_rect_px`,
три параллельных механизма паддинга и т.д. — остаётся в силе; ошибочной была
только гипотеза в этом конкретном подразделе.)

### Шаг 5 — обновить QRHI_CANVAS_FEATURES.md

После того как шаг 4 подтверждён вручную (и, опционально, video export
объединён по той же схеме) — поправить секцию "how uncrop/crop fits into it"
так, чтобы она описывала фактическую единую точку резолва
(`resolve_feature_virtual_layout`) для live+still, и явно отметить, что video
export пока остаётся отдельным, не унифицированным путём (пока не сделан
отдельный проход).

## Итог

Шаг 2 (4 механических исправления) выполнен и проверен компиляцией. Шаг 3
решён явно: единая agnostic-к-фичам модель, без переименования `fit_content`.
Шаг 4 частично сделан: still-export задедуплен на общий
`resolve_feature_virtual_layout` (безопасно — пересчитывается каждый export).
Live canvas (`base_images.py`) — попытка сделана и откачена: интеграция в
`update_letterbox_geometry` сломала divider (устаревшая геометрия, т.к. хук
не per-frame). Live canvas unification остаётся открытой задачей — нужен
другой, per-frame хук. Video export намеренно вне scope.
