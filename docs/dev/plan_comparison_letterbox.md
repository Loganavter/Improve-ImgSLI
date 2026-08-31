# Plan: Comparison letterbox eager max — no HOLD jump 1138→1041

Status: `Open` — design approved, Phase 0 next
Area: `src/tabs/image_compare/canvas/texture_parts/base_images.py:196` (`update_common_letterbox_geometry`), `src/tabs/image_compare/presenters/image_canvas/background_parts/render_flow.py:55` (`_update_comparison_geometry`), `src/tabs/image_compare/use_cases/unify.py:127` (`wh=max`), `src/shared/rendering/tile_constants.py:111` (`UNION_LETTERBOX_HOLD_MS`), `src/tabs/image_compare/canvas/rhi_renderer/renderer.py:463` (atomic fallback)
Related: [ARCHITECTURE.md](./ARCHITECTURE.md) §Canvas Stack, [CODE_PATTERNS.md](./CODE_PATTERNS.md) Bucket A single geometry owner, `plan_loading_simplification.md:1` (Done 8→1), `docs/dev/investigations` preview-display-session, `pyvips-streaming-plan.md:1`
Skills: `.cursor/skills/imgsli-devtools/SKILL.md` (tracer, context --cloc-only, contracts, offscreen pytest), `.cursor/skills/sli-ui-toolkit-docs-first/SKILL.md` N/A

> **Trigger:** `21:36` log `IMGSLI_IC_GAP_DEBUG=1` `geometry input 2/3 2797 vs 764` `letterbox 0.201/0.596 (1180)` → `44.272 5/6 2797 vs 2797` `0.545/1080` `-8.5%` jump через `HOLD 350ms`. `predicted_unified_size` в `unify.py:195` опаздывает на 1 fps tick (ставится после `44.019 ensure_unification`, а первый `draw 44.007` уже 0,0,0,0). Best practice mismatch: `wh=max` в `unify` тире, а `Viewport bounds` должен быть eager от модели.

## 1. Goal and non-goals

**Goal:** ширина сравнения не дергается. Измеряемо:
- Первый `gap draw_plan` после второго `preview` (`44.007` `2/3`) уже `0.545/1080` (eager `max 2797`), а не `0.596/1180` → `0 jump` `bbox 0.099→0.091` стабилен до `put_unified`.
- `rg UNION_LETTERBOX_HOLD_MS` в `base_images`/`render_flow` = `0` для `predicted` пути (hold только fallback при несовпадении `predicted != final`), `more_pending` не фризит геометрию.
- `HOLD` + `atomic` остаются только для пикселей (`fallback LOD` `renderer:596`), не для `letterbox`.

**Non-goals:**
- `TiledPixelStore` memmap, `pyvips_can_stream`, `TileTextureService` budget — не трогать.
- `PipelineCache`/`AbortSignal`/`SlotSource` — уже Done `plan_loading_simplification.md`.
- `multi_compare` atlas — не трогать.

**Locked decisions:**
- `max(W),max(H)` — единственный источник `1100`/`890` rect (`wh=max(w1,w2),max(h1,h2)`).
- Пирамида ленивая `sleep 0.002` + `lod_available` — не менять.
- Диспетчер reentrant `dispatcher.py:186` — без `QTimer` для `dispatch`.

## 2. Research summary (verified 2026-08-31)

| Scope | Fact | file:line |
|---|---|---|
| Envelope сейчас | `union fitted rects` `min(x)+max(x+w)` `1138` vs `per-image 1080` | `base_images.py:308` |
| `needs_union` | `mixed_tier \|\| large_aspect>0.4 \|\| grid_mismatch` `6x5 vs 2x2` → `True` → `1138` | `base_images.py:259` |
| `predicted` опаздывает | `unify.py:195` `dispatch predicted` после `handle_full_image_loaded 44.018` → `first draw 44.007` без него | `unify.py:195`, `render_flow.py:75` |
| `HOLD` | `350ms` `tile_constants:111` `base_images:343` `render_flow:98` `renderer:1006 more_pending` | `tile_constants:111` |
| Industry | `OpenSeadragon FitBounds max`, `Figma union bounds` eager от модели, `blend` пикселей не `freeze geometry` | `pyvips-streaming-plan` |

Why `8.5%` not `1/6`: `height-limited` `nW=aspect*ch` `1.214 vs 1.326` → `1.092`, `0.596→0.545`.

## 3. Design

**Eager max in geometry (single owner):**
```python
# base_images.py:196, render_flow.py:55 — единственный владелец
def update_common_letterbox_geometry(widget, i1, i2):
    w1,h1 = get_image_dims(i1); w2,h2 = get_image_dims(i2)
    if w1 and w2:
        pw,ph = max(w1,w2), max(h1,h2)  # eager, без Store.predicted
        # fitted rect от pw,ph для обеих сторон → letterbox одинаковый → 1080 сразу
        geometry = resolve_canvas_content_geometry(cw,ch,pw,ph)
        letterbox = (ux/cw, uy/ch, uw/cw, uh/ch) for both
        # no HOLD, no more_pending
        _dispatch_store(candidate_rect); return
    # fallback old union only if one side has no size
```

`unify.py:195` `predicted` удалить (не нужен), `unify` воркер остаётся источником пикселей `BICUBIC`, не геометрии. `Store.predicted_unified_size` `models.py:61`/`reducers.py:81` — депрокетировать.

**Flow:**
```
preview QImage 1017/764 → get_image_dims → max 2797 → letterbox 0.545/1080 (44.007)
full TiledStore 2797/764 → same max → stable 1080
unify 2797+2797 → pixels 2797, geometry unchanged
```

## 4. Steps

> **Оркестрация:** каждую фазу — `N` subagents параллельно в одном сообщении, каждый `prompt` явно `read .cursor/skills/imgsli-devtools/SKILL.md` + `internal-docs-hygiene` для `DOC_INDEX`.

### Phase 0 — Preflight (read-only)

Files: `base_images.py:196`, `render_flow.py:55`, `unify.py:127`, `tile_constants.py:111`, `renderer.py:463`, `tests/render/test_gap*`

1. `IMGSLI_AUTOCROP_DEBUG=1 IMGSLI_IC_GAP_DEBUG=1 ./launcher.sh run` лог `44.007 0.201/0.596 →44.307 0.226/0.545` зафиксировать.
2. `./launcher.sh test tests/contracts -q` green `1575`, `offscreen pytest tests/render -q` 211.

### Phase 1 — Eager max geometry (single owner) — P0

Files: `base_images.py:196`, `render_flow.py:55`

Parallel agents (SINGLE message, 2 subagents, `imgsli-devtools`):
- **A `base_images` eager** — `update_common_letterbox_geometry` считать `pw,ph=max` из `get_image_dims(i1/i2)` (оба `w>0`), `resolve_canvas_content_geometry(cw,ch,pw,ph)` один раз, `letterbox` оба `ux/cw`, `_dispatch_store` сразу `return`, удалить `HOLD` ветку `343-359` + `UNION_LETTERBOX_HOLD_MS` импорт + `prev_rect` `hold_until` `more_pending` для этого пути (оставить только fallback если один `w==0`).
- **B `render_flow` eager** — `_update_comparison_geometry` `size1=size2=(pw,ph)` если оба `size1/2` есть, `_fit_scale` от `pw`, `HOLD` `98-128` убрать для `both sizes` пути (оставить только если `size1 or size2 is None`), `Bucket A` `dispatcher is not None: return` сохранить.

Verification: `44.007` уже `0.545/1080` `gap draw_plan` `bbox 0.091` stable, `rg HOLD` в `base_images/render_flow` = `0` для eager пути, `contracts` green.

### Phase 2 — Deprecate predicted + atomic keep for pixels only — P1

Files: `unify.py:195,436`, `state/models.py:61`, `state/reducers.py:81`, `tile_constants.py:111`, `renderer.py:463,1006`

Parallel agents (SINGLE message, 2 subagents, `imgsli-devtools`):
- **A `unify predicted` removal** — удалить `SetPredictedUnifiedSizeAction` `dispatch` в `ensure_unification:195` и `on_unified:436` `hold_until` reset, депрокетировать `RenderCacheState.predicted_unified_size` `models:61` + reducer `81` + `ClearAllCaches`, оставить воркер только для пикселей.
- **B `renderer atomic` keep pixels** — `fallback LOD` `renderer:463 atomic` + `rekeyed` `more_pending` оставить для пикселей (`entries 36→30` стабилен), но `letterbox` уже `0.545` — убедиться `gap healthy` `covered 1.0` без `HOLD`.

Verification: `IMGSLI_IC_GAP_DEBUG` `44.007-44.272` `0 jump` `more_pending` не фризит `geometry`, `offscreen pytest tests/render -q` 211.

### Phase 3 — Docs + cloc — P2

Files: `docs/dev/DOC_INDEX.md`, `docs/dev/file_size_registry.json`, `docs/dev/ARCHITECTURE.md:51`

1. `python src/devtools/docs_link_graph.py --write-index` 0 broken.
2. `python src/devtools/file_meta.py --write-registry` 64→`~63` (удалён `predicted` + `HOLD` ~30 строк).
3. `ARCHITECTURE.md:51` добавить `eager max envelope` в §Canvas Stack.

Verification: `tests/devtools -q`, `contracts -q`, `context --cloc-only`.

## 5. Risks

- **Sliver `0.001`** — eager `max` `ph` оба одинаковы → `letterbox1==letterbox2` → `needs_union` `False` → `bbox` `0.091` без `narrow<0.01` (`renderer:544`), ок.
- **One-side missing** — если `size2 is None` — fallback старый `union`/`single` (`base_images:368`), не `max`.
- **Undo Store refs** — `PipelineCache.evict` не `close` при `undo` snapshot (`plan_loading_simplification:5`).

## 6. Progress log

| Step | Date | Result |
|---|---|---|
| 0 | 2026-08-31 | Plan landed `plan_comparison_letterbox.md:1`, `21:36` log `0.201/0.596→0.226/0.545` jump зафиксирован. |
| 1 | — | — |
| 2 | — | — |
| 3 | — | — |

## 7. References

- This: `base_images.py:196`, `render_flow.py:55`, `unify.py:127`, `tile_constants.py:111`, `renderer.py:463`
- Prior: `plan_loading_simplification.md:1`, `pyvips-streaming-plan.md:1`, `ARCHITECTURE.md:51`, `STORE.md:59`
- Logs: `21:36` `gap draw_plan 0.201→0.226`, `58.352` `0.207→0.232` earlier
- Skills: `.cursor/skills/imgsli-devtools/SKILL.md:1`, `internal-docs-hygiene`
