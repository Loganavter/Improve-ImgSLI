# Plan: RhiCanvasRenderer decomposition (1611 → <500)

Status: `In progress` — Phase 1 fallback extracted (1240L), remaining 3 buckets parallel
Area: `src/tabs/image_compare/canvas/rhi_renderer/renderer.py:1` (1611L → 1240L), `use_cases/fallback.py:1` (364L), `residency.py:1` (548L), `resources.py:1`
Related: [CODE_PATTERNS.md](CODE_PATTERNS.md) thin owner + `use_cases/` (§When not to split), [FILE_SIZE_POLICY.md](FILE_SIZE_POLICY.md) 500L `Audit-Meta:`, [ARCHITECTURE.md](ARCHITECTURE.md) Canvas Stack, `docs/dev/rendering/tile-rendering-system.md`, `shared/rendering/fallback_lod.py:1`, `shared/rendering/tile_constants.py:1`
TODO ref: `docs/dev/TODO.md` P2 canvas file-size debt
Skills: `.cursor/skills/imgsli-devtools/SKILL.md` (tracer `IMGSLI_TRACE=1`, `IMGSLI_IC_PREVIEW_DEBUG=1`, `context --cloc-only → cloc.txt`, contracts `./launcher.sh test tests/contracts -q`, `QT_QPA_PLATFORM=offscreen pytest`), `.cursor/skills/sli-ui-toolkit-docs-first/SKILL.md` (N/A — no toolkit widgets), `improve-imgsli-internal-docs/.cursor/skills/internal-docs-hygiene/SKILL.md` (status flips in-place, mirrored paths, privacy boundary `4bcc276a`)

> **Оркестрация параллельных агентов (обязательно):** каждую фазу с независимыми бакетами запускать **в одном сообщении** `N` subagents параллельно (Cursor `parallel-execution`). В `prompt` каждого **явно указать чтение** `.cursor/skills/imgsli-devtools/SKILL.md` (tracer `IMGSLI_TRACE=1`, `context --cloc-only`, `contracts`, `offscreen pytest`, `docs_link_graph`) и, если UI, `.cursor/skills/sli-ui-toolkit-docs-first/SKILL.md` (read `API_CATALOG`→`BUTTON_API`→`FLYOUT_SYSTEM` до `grep`). Без этого — не стартовать. Верификация — через те же skills.

## 1. Goal and non-goals

**Goal:** `renderer.py` тонкий владелец `<500L` без `Audit-Meta: size=exempt`, каждый ортогональный кусок кадра — функция `func(renderer, ...)` в `use_cases/` (CODE_PATTERNS). Измеряемо:
- `wc -l src/tabs/image_compare/canvas/rhi_renderer/renderer.py` `<500` (сейчас `1240` после Phase 1, было `1611`)
- `python src/devtools/file_meta.py --report` `renderer.py` без `size=exempt`, `Audit-Meta: pattern=thin-owner`
- `python src/devtools/file_meta.py --check` + `tests/contracts/test_file_size_policy.py -q` green
- `QT_QPA_PLATFORM=offscreen pytest src/tabs/image_compare/tests/render/ -q` `211 passed` (было до плана)
- `IMGSLI_IC_PREVIEW_DEBUG=1` trace `fallback`/`coverage`/`lod_commit` идентичен до/после (throttle sigs сохранены)

**Non-goals:**
- Менять `TileTextureService`, `fallback_lod` контракт, `TiledPixelStore` — доменные (как в `tile-array-atlas-plan.md`)
- Трогать `multi_compare` renderer — отдельно
- `sli-ui-toolkit` painter/QSS — проверять `sli-ui-toolkit-docs-first` перед UI, этот план `rhi_renderer` only
- `Store` догмы — только чистка веток

**Locked decisions:**
- `RhiCanvasRenderer` остаётся единственным владельцем `rhi/resources/tile_service/_last_good_*` — `use_cases` модули не заводят свои классы, только `def func(renderer, ...)` (CODE_PATTERNS: function-taking-owner, не второй класс)
- Throttle globals (`_last_renderer_*_sig`) живут в том же `use_cases` модуле, где логика, — не в `renderer.py`
- `Audit-Meta: pattern=thin-owner` после `<500`, не `state-machine` (state-machine exempt — для неразделимого фрейма, здесь фрейм уже декомпозирован по `tile-array-atlas-plan.md`)

## 2. Research summary (verified 2026-08-31, explore — do not re-research)

### 2.1 Inventory — where 1611 lines live

| Scope | `grep` / `rg` | Lines | Example file:line |
|---|---|---|---|
| Helpers + throttle | `_is_rekeyed_content_key` `renderer.py:123` | 47 | `renderer.py:123-169` helpers + 7 globals |
| `_resolve_fallback_plan` | `def _resolve_fallback_plan` `renderer.py:291` | 407 | `renderer.py:291-698` — atomic vs progressive, rekeyed LevelKey, first_paint_hold, narrow guard |
| `render()` — LOD commit | `resolve_lod_texture_keys` `renderer.py:862` | 90 | `renderer.py:862-951` `raw_texture_keys` → `pending` → `source_changed` → `committed` |
| `render()` — tile residency | `realize_tile_plan` `renderer.py:986` | 80 | `renderer.py:986-1065` `main_more_pending`, magnifier branch |
| `render()` — coverage | `covered_fraction` `renderer.py:1160` | 150 | `renderer.py:1160-1431` `visible1_common` → `covered1/2` → `first_paint_hold render` |
| `render()` — draw submit | `ensure_array_pipeline` `renderer.py:1473` | 130 | `renderer.py:1473-1546` `pack_array_uniforms`, `pack_array_instance`, `beginPass/draw/endPass` |
| Owner wiring | `__init__/initialize/release` `renderer.py:163` | 130 | `renderer.py:163-290` `RhiResources`, `TileTextureService`, `GlassPanelRenderer`, `feature_passes` |

### 2.2 Why it hurts

- `renderer.py:1` `Audit-Meta: state-machine` прикрывает реальное смешение забот: LOD, residency, fallback, coverage — каждая имеет свой `use_cases` тест (`test_rhi_fallback_scenarios`, `test_lod_texture_keys`, `test_realize_tile_plan_budget`, `test_array_draw_plan`), но тесты импортируют приватные функции из `renderer` (`_is_rekeyed_content_key`) — смена `renderer` ломает 4 suite.
- Рост `render()` `~900L` — каждая новая фича (SSIM diff, magnifier capture, glass panel) добавляет ветку в тот же метод, а не в `use_cases/` — нарушает `CODE_PATTERNS.md:21` `>500 lines / mixing orthogonal concerns`.
- `fallback` уже вынесен частично (`use_cases/fallback.py:1` `364L`), но `renderer.py` всё ещё `1240L` — не `<500`, `Audit-Meta: size=exempt` не снимается, `file_size_registry.json` stale.

## 3. Design

**Fallback (done Phase 1):**
```python
# use_cases/fallback.py — already landed
def resolve_fallback_plan(renderer, *, tile_service, texture_keys, diff_source_key, base_image, sampler_name, viewport_zoom, viewport_offset, main_more_pending, current_array_plan, source_changed, rekeyed, current_sources_is_same): ...
# renderer.py:291 — thin delegator
def _resolve_fallback_plan(self, ...): return resolve_fallback_plan(self, ...)
```

**LOD commit (Phase 2):**
```python
# use_cases/lod_commit.py
def commit_lod_keys(renderer, texture_keys, sources, base_image, canvas_size_px) -> tuple[tuple, bool]:
    raw = resolve_lod_texture_keys(...)
    # pending/since, source_changed via image_uid, LOD_FETCH_SETTLE_MS
    # returns (committed_keys, source_changed)
```

**Coverage + first_paint_hold (Phase 3):**
```python
# use_cases/coverage.py
def evaluate_coverage(renderer, tile_service, texture_keys, base_image, viewport_zoom, viewport_offset, array_draw_plan, main_more_pending) -> tuple[covered1, covered2, bbox_cov]:
def apply_first_paint_hold(renderer, array_draw_plan, current_array_plan, main_more_pending, covered_ok) -> list:
```

**Tile residency (Phase 4a):**
```python
# use_cases/tile_residency.py
def realize_main_tiles(renderer, widget, texture_keys, base_image, updates, diff_key, viewport_zoom, viewport_offset, dirty_layers) -> bool: # main_more_pending
def realize_magnifier_tiles(...): ...
```

**Draw submit (Phase 4b):**
```python
# use_cases/draw.py
def submit_array_draw(renderer, widget, command_buffer, array_draw_plan, base_image, diff_ready): ...
```

Owner keeps `self.rhi/resources/tile_service/feature_passes/_last_good_*` + `initialize/release` + `render()` sequencing (~180L).

## 4. Steps — breaking allowed, one app not IDE

### Phase 0 — Preflight (read-only) — P0
Files: `rhi_renderer/renderer.py`, `use_cases/fallback.py`, `draw_plan.py`, `residency.py`, `resources.py`, `tile_constants.py`
1. `wc -l src/tabs/image_compare/canvas/rhi_renderer/renderer.py` `1240` (было `1611`), `python src/devtools/file_meta.py --report | grep renderer` `exempt`
2. `QT_QPA_PLATFORM=offscreen pytest src/tabs/image_compare/tests/render/test_rhi_fallback_scenarios.py src/tabs/image_compare/tests/render/test_content_swap_atomic_commit.py -q` `18 passed`

### Phase 1 — Fallback extracted (Done)
Files: `rhi_renderer/use_cases/fallback.py:1`, `rhi_renderer/renderer.py:291`
Parallel agents (SINGLE message, 1 subagent, `imgsli-devtools` skill):
- **A fallback:** `use_cases/fallback.py` `364L` + thin delegator `renderer.py:291` — `wc -l renderer.py` `1611→1240`, `pytest .../test_rhi_fallback_scenarios -q` green
Verification: `rg "_is_rekeyed_content_key" src/tabs/image_compare/canvas/rhi_renderer/` → 2 hits (renderer re-export + fallback impl), `tests/render -q` `211 passed`

### Phase 2 — LOD commit (P0, parallelizable)
Files: `rhi_renderer/use_cases/lod_commit.py` (new 90L), `rhi_renderer/renderer.py:862`
Parallel agents (SINGLE message, 1 subagent, `imgsli-devtools` skill):
- **A lod_commit:** extract `resolve_lod_texture_keys` + `pending/settled/source_changed` block `renderer.py:862-951` + `image_uid` + `LOD_FETCH_SETTLE_MS` into `lod_commit.commit_lod_keys(renderer, ...)`; `renderer.render` calls it; throttle `raw_sig` moves to new module
Verification: `QT_QPA_PLATFORM=offscreen pytest src/tabs/image_compare/tests/render/test_lod_texture_keys.py -q` green, `renderer.py` `1240→1150`

### Phase 3 — Coverage + first_paint_hold (P0, parallelizable)
Files: `rhi_renderer/use_cases/coverage.py` (new 150L), `rhi_renderer/renderer.py:1160`
Parallel agents (SINGLE message, 1 subagent, `imgsli-devtools` skill):
- **A coverage:** extract `covered_fraction`/`_to_common_space`/`_visible_side_image_rect` gap calc `renderer.py:1160-1250` + `first_paint_hold render` `renderer.py:1370-1431` into `coverage.evaluate_coverage` + `apply_first_paint_hold`; `renderer.render` calls them; `gap healthy/detected` logs preserved
Verification: `QT_QPA_PLATFORM=offscreen pytest src/tabs/image_compare/tests/render/test_gap_mixed_size_no_sliver.py -q` green, `renderer.py` `1150→1000`

### Phase 4 — Tile residency + draw submit (P1, parallelizable 2 buckets)
Files: `rhi_renderer/use_cases/tile_residency.py` (new 80L), `rhi_renderer/use_cases/draw.py` (new 130L), `rhi_renderer/renderer.py:986` + `1473`
Parallel agents (SINGLE message, 2 subagents, `imgsli-devtools` skill):
- **A residency:** extract `realize_tile_plan` main+magnifier `renderer.py:986-1065` + `fallback_protect_keys` into `tile_residency.realize_main_tiles`/`realize_magnifier_tiles`; keep `extra_protect_keys` wiring
- **B draw:** extract `ensure_array_pipeline`/`pack_array_uniforms`/`pack_array_instance`/`beginPass/draw/endPass` + `active_feature_passes` gating `renderer.py:1473-1546` + `requires_content` blank gate `renderer.py:1464` into `draw.submit_array_draw`
Verification: `QT_QPA_PLATFORM=offscreen pytest src/tabs/image_compare/tests/render/test_realize_tile_plan_budget.py src/tabs/image_compare/tests/render/test_array_draw_plan.py -q` green, `renderer.py` `1000→480` (<500)

### Phase 5 — Registry + docs (P2)
Files: `docs/dev/FILE_SIZE_POLICY.md`, `src/devtools/file_meta.py`, `src/devtools/docs_link_graph.py`
1. `python src/devtools/file_meta.py --write-registry` — `renderer.py` `480L Audit-Meta: pattern=thin-owner` (was `1611L state-machine size=exempt`)
2. `python src/devtools/docs_link_graph.py --write-index` `0 broken`, `tests/contracts/test_file_size_policy.py -q` green, `tests/contracts -q` green
3. Update `docs/dev/rendering/tile-rendering-system.md` fallback LOD ref → `use_cases/fallback.py`

## 5. Risks
- **Throttle sig divergence:** `_last_renderer_*_sig` moved to `use_cases` — `renderer` delegator must not keep stale copy; grepped `rg "_last_renderer"` before delete
- **LevelKey base mismatch:** `LevelKey(base, lvl)` where base is `_content_stash` — `fallback.py` already fixes via `.base` unwrap `fallback.py:15`, keep it
- **Requires_content gate:** `renderer.py:1464` `if not array_draw_plan: filter` — must move with `draw.py`, not lost on split
- **QImage preview stash:** `residency.py:394` `if pil_source is not None` — keep preview path (1024) in `tile_residency` bucket, not `fallback`

## 6. Progress log
| Step | Date | Result |
|---|---|---|
| 0 | 2026-08-31 | Preflight `wc -l 1240` (was 1611), `fallback.py 364L` landed, `tests/render 211 passed`, `contracts` green |
| 1 | 2026-08-31 | Phase 1 fallback extracted — `renderer.py:291` thin delegator, `1240L`, `18 passed fallback` |
| 2 | — | — |
| 3 | — | — |
| 4 | — | — |
| 5 | — | — |

## 7. Deviations from the plan (deliberate, recorded)
- N/A yet — follow `internal-docs-hygiene` skill: flip Status in-place, record deviation here.

## 8. References
- This session: `rhi_renderer/renderer.py:1` (1611L), `use_cases/fallback.py:1` (364L), `residency.py:394` (preview stash), `renderer.py:1464` (feature gate), `shared/rendering/fallback_lod.py:1`, `shared/rendering/tile_constants.py:32`
- Prior: `docs/legacy/rendering/tile-array-atlas-plan.md:1` (4-phase array atlas), `docs/legacy/rendering/renderer-unification-plan.md:1` (IC↔MC split), `docs/dev/plan_preview_unify_transition_fix.md:1` (parallel agents template), `improve-imgsli-internal-docs/docs/legacy/presenter-decoupling-plan.md:1`
- Docs: `docs/dev/CODE_PATTERNS.md:25` thin owner, `docs/dev/FILE_SIZE_POLICY.md:11` 500L, `docs/dev/ARCHITECTURE.md:130` Canvas Stack, `docs/dev/TODO.md`
- Skills: `.cursor/skills/imgsli-devtools/SKILL.md:1`, `.cursor/skills/sli-ui-toolkit-docs-first/SKILL.md:1`, `improve-imgsli-internal-docs/.cursor/skills/internal-docs-hygiene/SKILL.md:1`
- Investigations: `src/tabs/image_compare/canvas/rhi_renderer/renderer.py:700` render sequencing, `src/tabs/image_compare/docs/investigations/preview-display-session-2026-08-29.md:1`
