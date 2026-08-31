# Plan: Preview QImage → Unify transition — missing put, tier mismatch, uid memo

Status: `Open` — design approved, Phase 0 preflight next
Area: `src/tabs/image_compare/use_cases/image_decode.py:152` (`on_image_loaded is_preview`), `src/tabs/image_compare/state/reducer.py:33` (`DocumentReducer` no-op), `src/tabs/image_compare/pipeline/cache.py:149` (`_preview_key`/`_preview`), `src/tabs/image_compare/pipeline/pipeline.py:56` (`peek_preview`), `src/tabs/image_compare/use_cases/unify.py:61` (`_slot_sources`), `src/tabs/image_compare/presenters/image_canvas/background_parts/render_flow.py:527` (`source`/`_peek`), `src/tabs/image_compare/pipeline/cache.py:141` (`_unify_key`), `src/tabs/image_compare/state/document.py:98` (`replace` copies list)
Related: [ARCHITECTURE.md](./ARCHITECTURE.md) §State Model / Canvas Stack, [STORE.md](./STORE.md) (Transaction, `batch_changes`), [CONTRACTS.md](./CONTRACTS.md), [CODE_PATTERNS.md](./CODE_PATTERNS.md) (thin owner), `docs/dev/plan_loading_simplification.md:1` (P0 cache 8→1, P0 cancel 8→1, P1 SlotSource), `docs/dev/plan_image_pipeline.md:1` (Phase 3 preview slimmer), `improve-imgsli-internal-docs/docs/dev/investigations/codebase-mass-root-causes-2026-08-26.md:1`, `improve-imgsli-internal-docs/docs/dev/investigations/dead-code-overengineering-audit-2026-08-26.md:55`
TODO ref: `docs/dev/TODO.md` → P2 Session-state follow-ups (Done wave5), P2/P3 `tabs/_shared` consolidation, P2 preview-display-session `preview-display-session-2026-08-29.md`
Skills: `.cursor/skills/imgsli-devtools/SKILL.md` (tracer `IMGSLI_TRACE=1`, `IMGSLI_IC_PREVIEW_DEBUG=1`, `context --cloc-only → cloc.txt`, contracts `./launcher.sh test tests/contracts -q`, `QT_QPA_PLATFORM=offscreen pytest`), `.cursor/skills/sli-ui-toolkit-docs-first/SKILL.md` (N/A — no toolkit widgets, verify before adding UI), `improve-imgsli-internal-docs/.cursor/skills/internal-docs-hygiene/SKILL.md` (status flips in-place, mirrored paths, privacy boundary `4bcc276a`)

> **Executor note.** Trigger: `15:34:27` `on_image_loaded is_preview=True QImage 1017x838` → `handle_full` ok, но `set_current_image` сразу `cached=None` → `no sources`. Explore `2026-08-31` (один `explore` с `imgsli-devtools` skill) нашёл 3×P0 того же класса что `slot.py:185` detached-list и `cache.py:232` put/get `has_crop` mismatch: preview `QImage` после `load_preview_image` не попадает в `PipelineCache._preview` (`put_preview` не вызывается, `DocumentReducer` no-op), читатели `unify._slot_sources:71` и `render_flow._peek:548` смотрят только `_pixel` tier (`_preview_key:149` с `1024` никогда), `get_unified` vs `put_unified` uid mismatch (`unify.py:114` sources vs `330` results). План по шаблону `improve-imgsli-internal-docs/docs/legacy/rendering/pyvips-streaming-plan.md:1` (Problem→Decisions→Facts→Phased) и `plan_loading_simplification.md:1` (Goal→Inventory→Design→Steps). Breaking allowed — один app. При оркестрации параллельных агентов — **обязательно указывать использование `.cursor/skills`** (см. §4 преамбула).

## 1. Goal and non-goals

**Goal:** preview `QImage` становится first paint через `PipelineView` без detached/mismatch, `unify` memo хит. Измеряемо:
- `put_preview` вызывается в `on_image_loaded is_preview` → `PipelineCache._preview` hit → `unify._slot_sources` и `render_flow._peek` видят preview (было `rg put_preview|peek_preview` вне определения `0`).
- `unify` memo `get_unified` vs `put_unified` на uid источников → hit на повторном `ensure_unification` (было `put` на uid результатов → never hit, каждый своп новый `GenericWorker`).
- `on_image_loaded` detached `target_list`/`Item.image` → put в `PipelineCache` + `store.transact` `SetImageSessionImageAction` с preview `QImage` (было `DocumentReducer` no-op → `doc.preview_image` всегда `None`).
- `rg "QTimer.singleShot.*preview"` в новом пути `0` (preview→full via `AbortSignal`).
- `QT_QPA_PLATFORM=offscreen pytest src/tabs/image_compare/tests/render/test_display_preview_backing* -q` и `tests/contracts -q 1575 passed`.

**Non-goals / do not touch:**
- `TiledPixelStore` memmap, `pyvips_can_stream`, `TileTextureService` — доменные (как в `plan_loading_simplification.md`).
- `sli-ui-toolkit` painter/QSS — проверять `sli-ui-toolkit-docs-first` перед UI, этот план Store/pipeline only.
- `multi_compare` atlas — отдельно (B8/B11 deferred).
- `Store` dogma — только чистка веток.

**Locked decisions (do not reopen):**
- `PipelineCache._preview` единственный для `QImage` (`_preview_key:149` `(path,mtime,size,has_crop,box,1024)`), `_pixel` для `TiledPixelStore` (`_pixel_key:117`). Preview не дублируется в `DocumentModel`/`Item.image` — `DocumentModel` остаётся `SlotSource` (`plan_loading_simplification.md:27`).
- `unify` memo ключ — uid источников (`s1,s2`), `put` тоже источники (как `pipeline.ensure_unified:133`), не результатов.
- `render_flow` source fallback — `legacy document or image_state or _peek` теперь `or _peek_preview` (preview tier), gate `unification_in_progress` proceed with `preview/full_res` остаётся (fix `2026-08-29`).

## 2. Research summary (verified 2026-08-31, explore — do not re-research)

### 2.1 Inventory — where preview→unify overhead lives

| Scope | `grep` / `rg` | Hits | Example file:line |
|---|---|---|---|
| Preview store | `rg "put_preview\|peek_preview" src/tabs/image_compare` | 0 вызовов вне `cache.py:352`/`pipeline.py:56` | `cache.py:352 put_preview`, `:323 get_preview`, `pipeline.py:56 peek_preview` — dead code |
| Preview write | `on_image_loaded is_preview` `image_decode.py:152` | 1 path | `152-175` `hasattr(is_open)` check fails for `QImage` → no `put` |
| Document preview | `DocumentReducer` `reducer.py:33` | 3 actions no-op | `SetPreview/SetFullRes/SetImagePath` → `return document`, `doc.preview_image` всегда `None` |
| Slot sources | `_slot_sources` `unify.py:71` | 1 | `pl.peek(p1)` only `_pixel` tier, `_preview` never read |
| Render peek | `render_flow._peek` `render_flow.py:548` | 1 | `pl.peek(path)` only `_pixel` |
| Unify memo | `get_unified` `unify.py:114` vs `put_unified` `330` | mismatch | `get` uid(s1,s2), `put` uid(u1,u2) → never hit |
| Detached list | `on_image_loaded` `image_decode.py:137` `target_list = document.image_list1` before dispatch | 1 | `item.image = pil_img:199` mutates detached copy, `document.py:98` `list(...)` copy in `replace` |
| Pending vs inflight | `PendingFullLoadsProxy` `session.py:68` synthetic `("__full_count__",slot)` + `image_decode.py:261` `_clear_full` only `(slot,path,"full")` | leak | `unify.py:240` `has_pending True` вечно → toast не финиширует |

### 2.2 Why it hurts

- First paint без backing: `load_images_from_paths` → `set_current_image` `cache miss` → worker `load_preview_image` `QImage 1017x838` → `on_image_loaded` не кладёт в `_preview` и `DocumentReducer` no-op → `store` не меняется → `render_flow` `have1/have2` via `source` `False` → `defer` или `no sources` (`15:28:23` log) до `full` (∼200ms), теряется 1024-backing.
- `unify` на stale: `_slot_sources` miss → `ensure_unification:90` `if not (s1 and s2): return` ложно → не стартует пока оба `full`, mixed-tier `QImage+TiledPixelStore` не унифицируется, small path `downscale.py:33` vs large `allocate` лишний `to_real_pil_copy:106`.
- Memo never hit → каждый своп/ресайз перезапускает `unify_pair` (дорого, логи `[Unify] task started`).

## 3. Design

**Preview write:**

```python
# image_decode.py:152 on_image_loaded is_preview=True
from shared.image_processing.tiled_pixel_store import TiledPixelStore
if isinstance(pil_img, QImage) and not pil_img.isNull():
    pl.cache.put_preview(path, pil_img)  # _preview_key with 1024
    # also publish PipelineView preview for render gate
    store.transact([SetImageSessionImageAction(slot, pil_img), InvalidateGeometryCacheAction()])
else:
    pl.cache.put_pixel(path, store=pil_img)  # TiledPixelStore
```

**Slot sources / render peek — оба tier:**

```python
# unify.py:61 _slot_sources, render_flow.py:548 _peek
def _peek_both(pl, path):
    return pl.peek(path) or pl.peek_preview(path)  # _pixel or _preview
s1 = _peek_both(pl, p1) or getattr(vp_state, "image1", None)
```

**Unify memo — uid источников:**

```python
# unify.py:114 get, on_unified_images_ready:330 put
key = (s1_uid, s2_uid, method, w, h)  # s1,s2 — источники, не u1,u2
cached = pl.cache.get_unified(*key)
...
pl.cache.put_unified(s1_uid, s2_uid, method, w, h, (u1, u2))  # same key
```

**Detached fix:**

```python
# image_decode.py:137 on_image_loaded — re-fetch after any dispatch in load path
# или put в PipelineCache + transact, не item.image
# target_list re-fetch via store.get_session_state_slot after dispatch
```

**Pending sync:**

```python
# session.py:68 PendingFullLoadsProxy — _clear_full должен чистить и synthetic count
# image_decode.py:261 _clear_full: pl._inflight.pop((slot,path,"full"), None); proxy dec count
```

## 4. Steps — breaking allowed, one app not IDE

> **Оркестрация параллельных агентов (обязательно):** каждую фазу с независимыми бакетами запускать **в одном сообщении** `N` subagents параллельно (Cursor `parallel-execution`). В `prompt` каждого **явно указать чтение** `.cursor/skills/imgsli-devtools/SKILL.md` (tracer `IMGSLI_IC_PREVIEW_DEBUG=1`, `context --cloc-only`, `contracts`, `offscreen pytest`, `docs_link_graph`) и, если UI, `.cursor/skills/sli-ui-toolkit-docs-first/SKILL.md` (read `API_CATALOG`→`BUTTON_API`→`FLYOUT_SYSTEM` до `grep`). Без этого — не стартовать. Верификация — через те же skills.

### Phase 0 — Preflight (read-only) — P0

Files: `pipeline/cache.py`, `use_cases/image_decode.py`, `use_cases/unify.py`, `presenters/.../render_flow.py`, `state/reducer.py`

1. `rg "put_preview|peek_preview"` → 0 вызовов, `rg "SetPreview"` → no-op, `IMGSLI_IC_PREVIEW_DEBUG=1` trace `load_images_from_paths` → `on_image_loaded is_preview QImage` → `cache miss` → `no sources`.
2. `QT_QPA_PLATFORM=offscreen pytest tests/contracts -q` green (`1575`), `tests/render/test_display_preview_backing* -q` green.

### Phase 1 — Preview write + DocumentReducer (P0)

Files: `use_cases/image_decode.py:152`, `state/reducer.py:33`, `pipeline/cache.py:352`

Parallel agents (SINGLE message, 2 subagents, each with `imgsli-devtools` skill):
- **A `put_preview` + transact:** `on_image_loaded is_preview=True` → `pl.cache.put_preview(path, pil_img)` + `store.transact([SetImageSessionImageAction(slot, pil_img)])` (preview `QImage` в `PipelineView`), удалить `item.image =` detached. `hasattr(is_open)` ветку заменить на `isinstance(pil_img, QImage)`.
- **B `DocumentReducer` preview no-op → fallback:** либо удалить `SetPreview` no-op и прокинуть в `ImageSessionReducer` как `preview_image` tier, либо оставить но добавить `put_preview` как единственный путь (выбрать A, B — no-op остаётся dead, но `render_flow` больше не читает `doc.preview_image`).

Verification: `rg "put_preview" src/tabs/image_compare/use_cases` → 1, `QT_QPA_PLATFORM=offscreen pytest src/tabs/image_compare/tests/render/test_display_preview_backing_flip_flop.py -q` green, `IMGSLI_IC_PREVIEW_DEBUG=1` → `on_image_loaded ... put_preview hit`.

### Phase 2 — Tier-aware peek (P0)

Files: `use_cases/unify.py:61`, `presenters/.../render_flow.py:548`, `pipeline/pipeline.py:56`

Parallel agents (SINGLE message, 2 subagents, `imgsli-devtools` skill):
- **A `_slot_sources`:** `pl.peek(p1) or pl.peek_preview(p1)` (helper `_peek_both`), fallback `image_state.image1` остаётся. `ensure_unification` теперь видит `QImage` preview + `TiledPixelStore` full mixed-tier.
- **B `render_flow._peek`:** `def _peek(path): return pl.peek(path) or pl.peek_preview(path)` + `source1 = ... or image_state or _peek` (уже частично `fix 2026-08-31` для `_pixel`, расширить на `_preview`), gate `unification_in_progress` proceed logic проверить с `_peek` (оба `preview` → proceed).

Verification: `RG "peek_preview" src/tabs/image_compare` → 2+ hits, `tests/render -q` still `116 passed`, `IMGSLI_TRACE=1` `ensure_unification` стартует на `preview+full`.

### Phase 3 — Unify memo uid fix + detached/pending (P1)

Files: `use_cases/unify.py:114,330`, `pipeline/cache.py:141`, `state/document.py:98`, `pipeline/session.py:68`, `use_cases/image_decode.py:137,261`

Parallel agents (SINGLE message, 3 subagents, `imgsli-devtools` skill):
- **A `uid` memo:** `get_unified(s1_uid,s2_uid)` и `put_unified(s1_uid,s2_uid, ... (u1,u2))` — оба на источниках, `cache.get_unified` `is_open` check добавить `QImage.isNull` guard.
- **B `detached list`:** `on_image_loaded:137` re-fetch `document = store.get_session_state_slot` после любого диспатча в `load_images_from_paths` пути, `item.image` detached удалить (как Phase 1A), `slot.py:185` re-fetch уже есть — распространить на `image_decode`.
- **C `pending`:** `PendingFullLoadsProxy` `__full_count__` synthetic — `_clear_full:261` декрементит count + `pop` `_inflight[(slot,path,"full")]`, `trigger_preview_unification:240` `has_pending` читает оба.

Verification: второй `ensure_unification` с теми же `s1,s2` → `cache hit` (лог `get_unified hit`), `QT_QPA_PLATFORM=offscreen pytest tests/runtime/test_dispatcher_concurrency -q` green, `tests/contracts -q` green.

### Phase 4 — Docs + registry — P2

Files: `docs/dev/ARCHITECTURE.md:51`, `docs/dev/STORE.md`, `src/devtools/docs_link_graph.py`, `src/devtools/file_meta.py`

1. Обновить `ARCHITECTURE.md` State Model (preview tier `_preview_key 1024` vs `_pixel`, `peek_both`), `STORE.md` Transaction.
2. `python src/devtools/docs_link_graph.py --write-index` `0 broken`, `python src/devtools/file_meta.py --write-registry` `~61 entries`.

## 5. Risks

- **QImage uid `cacheKey` vs `id`**: `image_identity.py:33` `cacheKey` для `QImage`, `uid` для `TiledPixelStore` — пространства не пересекаются, `id()` fallback может реюзнуться после GC → `put_unified` на `id` рискован, использовать `image_uid` helper.
- **Mixed-tier RAM**: `QImage 1017x838 ~3.4MB` + `TiledPixelStore 764x576` → `unify_pair` large path `allocate` + `write_resampled` — проверить `tiled_pixel_store.py:619` streamed `768x576`.
- **Preview staleness**: `has_crop`/`box` в `_preview_key` и `_pixel_key` оба `stat` + `crop_service.get` → смена `auto_crop` между preview и full → miss, двойной decode (как `cache.py:232` bug).
- **Undo snapshot**: `QImage` в `image_state` попадает в `_UNDOABLE_TYPES` → `evict` не должен `close` (QImage не `close`), `TiledPixelStore` — defer close.

## 6. Progress log

| Step | Date | Result |
|---|---|---|
| 0 | 2026-08-31 | Plan landed `docs/dev/plan_preview_unify_transition_fix.md:1`, explore `QImage→unify` diagnosed 3×P0 (missing put_preview, tier mismatch, uid memo), 1×P1 detached, 1×P1 pending. `rg` baseline `put_preview 0`, `contracts 1575 passed`. |
| 1 | — | — |
| 2 | — | — |
| 3 | — | — |
| 4 | — | — |

## 7. Deviations from the plan (deliberate, recorded)

- N/A yet — follow `internal-docs-hygiene` skill: flip Status in-place, record deviation here.

## 8. References

- This session: `use_cases/image_decode.py:152`, `state/reducer.py:33`, `pipeline/cache.py:149,352`, `use_cases/unify.py:61,114,330`, `presenters/.../render_flow.py:527,548`, `pipeline/pipeline.py:56`, `state/document.py:98`, `pipeline/session.py:68`
- Prior: `docs/dev/plan_loading_simplification.md:1` (P0 cache 8→1, detached list fix `slot.py:185` re-fetch), `docs/dev/plan_image_pipeline.md:1` (preview slimmer), `improve-imgsli-internal-docs/docs/legacy/rendering/pyvips-streaming-plan.md:1`, `improve-imgsli-internal-docs/docs/dev/investigations/preview-display-session-2026-08-29.md:1` (flip-flop guard)
- Docs: `docs/dev/STORE.md:3`, `docs/dev/CONTRACTS.md:303`, `docs/dev/ARCHITECTURE.md:51`, `docs/dev/TRACING.md:30`, `docs/dev/TESTING.md:22`
- Skills: `.cursor/skills/imgsli-devtools/SKILL.md:1`, `.cursor/skills/sli-ui-toolkit-docs-first/SKILL.md:1`, `improve-imgsli-internal-docs/.cursor/skills/internal-docs-hygiene/SKILL.md:1`
- Investigations: `src/tabs/image_compare/presenters/image_canvas/background_parts/render_flow.py:246` `pick_display_with_preview_backing`, `src/shared/rendering/image_identity.py:33`
