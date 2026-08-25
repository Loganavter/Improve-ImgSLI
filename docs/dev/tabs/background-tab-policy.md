# Background tab policy

Status: `Proposed` (2026-08-25, follow-up to the deep review waves — see
[investigations/cross-module-review-2026-08-25-wave2.md](../investigations/cross-module-review-2026-08-25-wave2.md)).
This doc records how hidden workspace tabs behave today and defines the
target policy for CPU work on them. Implementation is phased and
measurement-gated (Phase 0).

Related: [session-lifecycle.md](session-lifecycle.md) ·
[isolation.md](isolation.md) ·
[THEMING.md](../THEMING.md) · [TODO.md](../TODO.md)

---

## How switching works today

The host owns a `WorkspaceTabStrip` + a plain `QStackedWidget`
(`src/ui/main_window/ui.py:35-41`). Switching runs
`on_workspace_tab_changed` → `switch_workspace_session` → store change →
`sync_session_mode` (`src/ui/presenters/main_window/ui.py:106-140`) →
`TabRegistry.activate`, which deactivates the old tab (`TabContract.
on_deactivated`) and lazily creates the new page on first activation
(`src/tabs/use_cases/pages.py:22-27`). **Once created a page lives
forever**: hidden by `setCurrentWidget`, parented to the stack, removed
only by `dispose_all()` at shutdown (`src/tabs/registry.py:292-302`).
Switching away therefore leaves the previous tab fully constructed,
subscribed, timer-armed, and RAM-resident — only Qt visibility flips.

## Inventory: what a hidden tab does today

| Subsystem | Hidden behavior | Evidence |
|---|---|---|
| GPU textures | Released automatically — Qt calls `QRhiWidget.releaseResources()` on hide; both canvases release their renderer, re-init + re-upload on show | `src/tabs/image_compare/canvas/widget.py:278-279`; `src/tabs/multi_compare/ui/canvas_widget.py:503-510` |
| Presents | None for hidden pages ("Hidden stack pages never present") | `canvas/widget.py:189`; `mc/ui/canvas_widget.py:277-284` |
| Theme / language | Already deferred via stale-flush: hidden pages marked stale (`_appearance_stale`, pending-lang), flushed on activation | `src/tabs/use_cases/appearance.py:14-56`; toolkit `i18n.py:360-391` (`defer_when_hidden`) |
| MC store subscription | Dormant — bound-mode notifications ignored unless the active session has an MC slot | `src/tabs/multi_compare/scene/store.py:558-571` |
| IC render pipeline | **Full price while hidden** — any `document`/`settings`/`viewport` dispatch schedules `update_comparison_if_needed`; gates check only UI-stability/resize/main-window-visible/minimized, never tab visibility | `chrome_sync.py:141-157` → `ui_update_batcher.py:63-64` → `presenter.py:101-110` → `render_flow.py:72-87` |
| MC composition rebuild | `_flush_composition` (texture sync + plan rebuild) has no isVisible gate; harmless while the bound store sleeps, but undo/redo of an MC session from another tab pays it | `mc/ui/canvas_widget.py:130-147,476-501` |
| Pyramid builds / full-res decodes | Continue to completion for background tabs (accidental prefetch); abort predicates know only task-id staleness / pyramid validity | `ic/use_cases/loading_pyramid.py:76-99`; `mc/use_cases/loading.py:174-190`; `_session_controller.py:295-310` |
| Metrics / SSIM auto-analysis | Triggered by load completion regardless of visible tab; cached-diff requests can be issued off-screen | `services/analysis/metrics.py:104-115`; `render_flow.py:195-213` |
| TiledPixelStore / pyramids (RAM) | Resident until slot replacement or session close; pyramids are plain memory (memmap mitigates stores only) | `docs/dev/tabs/session-lifecycle.md:41-43,102-105` |
| Pinned HUDs | Explicitly hidden in page `hideEvent`, resynced on show | `ic/widget.py:140-168`; `mc/ui/chrome.py:115-136` |

## Target policy (browser-model compromise)

Do **not** kill everything in the background — fast switch-back is part
of the product. Three tiers:

### Tier A — free while hidden (no work needed)

State subscriptions that already sleep (MC bound store), theme/language
stale-flush, GPU resource release. Keep as is.

### Tier B — continue as prefetch (deliberate, keep)

Full-res decodes and pyramid builds of a background session finish so
returning to the tab is instant. This is *declared* prefetch now, not an
accident. Cost is bounded: one decode + one pyramid build per image.

### Tier C — defer until shown (the actual work)

Anything whose output cannot be seen or whose cost is unbounded:

1. **IC comparison pipeline** (highest value): gate the
   schedule→update chain on stack-current visibility, mark the canvas
   render stale instead, flush on showEvent.
2. **Metrics / SSIM auto-recalc**: postpone trigger when the owning tab
   is hidden; recompute-on-show.
3. **MC `_flush_composition`**: skip texture sync + plan rebuild for
   non-current pages; flush on show.

## Target pattern — extend stale-flush, no new machinery

The codebase already owns the right idiom (theme/language): *while
hidden → set a stale flag; on activation/show → flush*. Reuse it rather
than inventing an idle scheduler:

```python
# shape (mirrors tabs/use_cases/appearance.py)
def _flush_stale_render(tab_page):
    if tab_page.is_current_stack_page() and tab_page._render_stale:
        tab_page.request_view_update()
        tab_page._render_stale = False
```

Wiring must go through the registry/lifecycle hooks (`on_activated`,
showEvent) — not implied widget lookups (see
[isolation.md](isolation.md)).

## Phases

0. **Measure first** (evidence-first discipline): reproduce a hidden-tab
   store churn scenario with `IMGSLI_TRACE=1` / startup trace and record
   what the IC pipeline actually spends per dispatch while hidden.
   Decides whether Phase 3's analysis deferral is worth its complexity.
1. IC pipeline visibility gate + stale-render flush-on-show.
2. MC `_flush_composition` gate.
3. Metrics/SSIM deferral-to-show (per Phase 0 evidence).

## Explicitly out of scope

- Releasing pyramids/TiledPixelStores on deactivate — intersects undo
  (closed-store snapshots, `_UNDOABLE_TYPES`) and Tier-B prefetch;
  revisit only if Phase 0 measurements show real RAM pressure.
- Unloading/deleting hidden pages (contradicts the browser model).
