# Background tab policy

Status: **as-is map, verified** (originally proposed 2026-08-25, as a follow-up
to the deep review waves in the private docs repo:
the internal notes on cross-module-review-2026-08-25-wave2).
The three deferral phases proposed here have since shipped (see § Tier C); what
remains below is current behaviour, not a plan.

Related: [session-lifecycle.md](session-lifecycle.md) ·
[isolation.md](isolation.md) ·
[THEMING.md](../THEMING.md) · [TODO.md](../TODO.md)

---

## How switching works today

The host owns a `WorkspaceTabStrip` + a plain `QStackedWidget`
(`src/ui/main_window/ui.py`, `_create_static_widgets`). Switching runs
`on_workspace_tab_changed` → `switch_workspace_session` → store change →
`sync_session_mode` (`ui/presenters/main_window/workspace.py`, reached through
the presenter delegate) → `TabRegistry.activate`, which deactivates the old tab
(`TabContract.on_deactivated`) and lazily creates the new page on first
activation (`src/tabs/use_cases/pages.py`, `_ensure_page`). **Once created a page
lives forever**: hidden by `setCurrentWidget`, parented to the stack, removed
only by `dispose_all()` at shutdown (`src/tabs/registry.py`). Switching away
therefore leaves the previous tab fully constructed, subscribed, timer-armed,
and RAM-resident — only Qt visibility flips.

## Inventory: what a hidden tab does today

| Subsystem | Hidden behavior | Evidence |
|---|---|---|
| GPU textures | Released automatically — Qt calls `QRhiWidget.releaseResources()` on hide; both canvases override it to release their renderer, re-init + re-upload on show | `src/tabs/image_compare/canvas/widget.py` `releaseResources`; `src/tabs/multi_compare/ui/canvas_widget.py` `releaseResources` |
| Presents | None for hidden pages — the view-update flush returns when the widget is not visible, and a frame only counts once a pass actually completed | `multi_compare/ui/canvas_widget.py` `_flush_view_update`; `image_compare/canvas/widget.py` `render` |
| Theme / language | Already deferred via stale-flush: hidden pages are marked stale (`_appearance_stale`, pending-lang), flushed on activation | `src/tabs/use_cases/appearance.py`; toolkit `install_translations(..., defer_when_hidden=…)` |
| MC store subscription | Dormant — bound-mode notifications are ignored unless the active session has an MC slot | `src/tabs/multi_compare/scene/store.py` (`_on_core_change`, bound-mode plumbing) |
| IC render pipeline | **Deferred while hidden** — the schedule→update chain checks tab visibility (`ImageCompareChromeSync._is_visible` compares `stack.currentWidget()`), sets `_render_stale` instead of rendering, and the page's `showEvent` flushes it (`_flush_stale_render` → `chrome_sync.flush_stale_render`) | `image_compare/use_cases/chrome_sync.py` `_is_visible` / `flush_stale_render`; `image_compare/widget.py` `showEvent` |
| MC composition rebuild | **Deferred while hidden** — `_flush_composition` and its scheduler record `render.mc.deferred`, set `_composition_stale` and return for a non-current page; `flush_stale_composition` runs on show | `multi_compare/ui/canvas_widget.py` `_flush_composition`, `flush_stale_composition`, `is_current_stack_page` |
| Pyramid builds / full-res decodes | Continue to completion for background tabs (accidental prefetch); abort predicates know only task-id staleness / pyramid validity | `image_compare/use_cases/loading_pyramid.py`; `multi_compare/use_cases/loading.py`; `image_compare/_session_controller.py` |
| Metrics / SSIM auto-analysis | **Deferred while hidden** — the trigger marks `_metrics_stale` and records `metrics.deferred` instead of computing; the page's `showEvent` flushes it (`_flush_stale_metrics`) | `image_compare/use_cases/metrics_trigger.py` (`trigger_metrics_calculation_if_needed`, `trigger_full_diff_generation`) |
| TiledPixelStore / pyramids (RAM) | Resident until slot replacement or session close; pyramids are plain memory (memmap mitigates stores only) | see [session-lifecycle.md](session-lifecycle.md) § `state_slots` / § Project I/O |
| Pinned HUDs | Explicitly hidden in the page's `hideEvent`, resynced on show | `image_compare/widget.py` `hideEvent` → `_hide_pinned_huds_on_tab_switch`; `multi_compare/ui/chrome.py` |

## Policy: keep switch-back instant (browser model)

Do **not** kill everything in the background — fast switch-back is part of the
product. Three tiers:

### Tier A — free while hidden (nothing to do)

State subscriptions that already sleep (MC bound store), theme/language
stale-flush, GPU resource release. Keep as is.

### Tier B — continue as prefetch (deliberate)

Full-res decodes and pyramid builds of a background session finish so returning
to the tab is instant. This is *declared* prefetch now, not an accident. Cost is
bounded: one decode + one pyramid build per image.

### Tier C — defer until shown (shipped)

Anything whose output cannot be seen or whose cost is unbounded:

1. **IC comparison pipeline** — shipped: `chrome_sync._is_visible` gates the
   schedule→update chain, `_render_stale` flushes on show.
2. **Metrics / SSIM auto-recalc** — shipped: `metrics_trigger` marks
   `_metrics_stale` while hidden; the page flushes on show.
3. **MC `_flush_composition`** — shipped: texture sync + plan rebuild are skipped
   for non-current pages (`_composition_stale`), flushed on show.

## Pattern used — extend stale-flush, no new machinery

The codebase reuses the idiom it already owned (theme/language): *while hidden →
set a stale flag; on activation/show → flush*. No idle scheduler was added:

```python
# shape (mirrors tabs/use_cases/appearance.py and IC's chrome_sync)
def _flush_stale_render(tab_page):
    if tab_page.is_current_stack_page() and tab_page._render_stale:
        tab_page.request_view_update()
        tab_page._render_stale = False
```

Wiring goes through the page's `showEvent`/`hideEvent` and the tab's own sync
object — not through implied widget lookups from the host (see
[isolation.md](isolation.md)).

## Explicitly out of scope

- Releasing pyramids/TiledPixelStores on deactivate — intersects undo
  (closed-store snapshots, `_UNDOABLE_TYPES`) and Tier-B prefetch; revisit only
  if measurements show real RAM pressure.
- Unloading/deleting hidden pages (contradicts the browser model).
