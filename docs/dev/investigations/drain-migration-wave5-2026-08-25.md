# Investigation: drain migration wave 5 — single-drain → drain_until_stable (W5)

Date: 2026-08-25. Wave 5 of `docs/dev/TODO.md:138` P2 test-deflake — migrate remaining ~35 single-drain exact-equality geometry asserts to bounded `drain_until_stable` helper (`tests/helpers/drain_until_stable.py:1`). Replaces flaky `qapp.processEvents()` + `assert geometry==expected` with poll-until-stable for 2 frames (1000 ms timeout, 10 ms poll). Keeps assert logic, only waiting.

References: `TODO.md:138` (остаток ~35 single-drain asserts, single-drain → drain-until-stable helper), `tests/helpers/drain_until_stable.py:1`, `tests/runtime/test_color_picker_dialog.py:17` (canonical usage), `docs/dev/investigations/cross-module-review-2026-08-25-wave2.md:222` W5, `tests/runtime/test_drain_until_stable_helper.py:1`.

---

## Trigger

- `TODO.md:138` P2 test suite: 85% done, remainder ~35 files low-risk single-drain exact-equality geometry asserts that flake due to deferred layout timers (`singleShot(0)` relayout, CSD polish, shelf grid recompute). Known 4 failures plus ~6 candidates, plus `src/tabs/session_picker/tests/runtime/test_recent_projects_panel.py:1` (~20 drains) where `isHidden/isVisible` still uses single drain.
- `grep -rn "processEvents" tests/runtime --include="*.py" | grep -v "drain_until_stable" | wc -l` = **35** (12 файлов: `test_dialog_auto_decoration.py`, `test_drag_ghost_ripple.py`, `test_flyout_manager_modal_deactivate.py`, `test_main_window_csd_paint_band.py`, `test_modal_keeps_flyout.py`, `test_themed_dialog.py`, `test_tooltip_interceptor.py`, `test_app_text_input_dialog_theme.py`, `test_main_window_title_bar_menus.py`, `test_rounded_window_mask.py`, `test_color_picker_dialog.py`, `test_app_message_dialog_theme.py` + остатки).
- `grep -rn "processEvents" src/tabs/session_picker/tests/runtime --include="*.py" | grep -v "drain_until_stable" | wc -l` = **26** in `test_recent_projects_panel.py` alone; many are `for _ in range(5): qapp.processEvents()` loops waiting for nested `singleShot` shelf settle.

## Root cause

- `QApplication.processEvents()` drains exactly one event-loop iteration. Deferred layout (shelf `resizeEvent -> singleShot(0) -> _rebuild_items -> singleShot(0) settle`, CSD `Polish` → `CustomTitleBar`, `ThemedDialog` `mark_theme_ui_ready` polish) needs **2** frames to settle. Single drain asserts on `grid_columns`, `scroll_area.height()`, `_csd_title_bar` existence, `flyout.isVisible()` therefore pass locally but flake on offscreen CI with different timer ordering.
- Existing wave3–4 migrated 4 known failures + `test_color_picker_dialog.py:39`, `test_app_text_input_dialog_theme.py:27`, `test_color_picker_recents.py:126`, `test_app_message_dialog_theme.py:23`, `test_ui_scale_live_apply.py:86`; remainder kept single drains for low-risk follow-up (no QRhi).
- `test_recent_projects_panel.py` mixes stable `isHidden/isVisible` (already deterministic after `refresh()` without window) with geometry (`grid_columns`, `scroll_viewport_height`, `panel.height()`) that needs drain. Previous loops `for _ in range(5): processEvents()` are ad-hoc and still timeout-prone on scale>1.0.

## Fix

**Principle:** Не менять логику asserts, только ожидание. Replace `qapp.processEvents()` + `assert geometry==expected` with `drain_until_stable(qapp, lambda: getter(), timeout_ms=1000, stable_frames=2)` as in `test_color_picker_dialog.py:17`. For visibility probes, getter returns `isVisible` tuple; for geometry, returns `(grid_columns, height)` tuple that stabilizes over 2 polls.

### `tests/runtime` (35 → 20, −15)

| File | Before | After | Getter |
|---|---|---|---|
| `tests/runtime/test_dialog_auto_decoration.py:28` | `QApplication.processEvents()` | `drain_until_stable(qapp, lambda: getattr(box, "_csd_title_bar", None), …)` | `_csd_title_bar` existence (Polish→CSD) |
| `…:43` sentinel | same | `drain_until_stable(qapp, lambda: getattr(dlg, "_csd_title_bar", None), …)` | sentinel not clobbered |
| `…:58` opt-out | same | same getter `"_csd_title_bar"` | opt-out stays None |
| `tests/runtime/test_tooltip_interceptor.py:40` | `QApplication.processEvents()` | `drain_until_stable(qapp, lambda: (bar.isVisible(), bar.tabRect(1).width()), …)` | `isVisible`+tab geometry before `sendEvent` |
| `tests/runtime/test_rounded_window_mask.py:20` | `QApplication.processEvents()` | `drain_until_stable(QApplication.instance(), lambda: (widget.isVisible(), widget.width(), widget.height()), …)` | shown before mask |
| `tests/runtime/test_drag_ghost_ripple.py:76` | `qapp.processEvents()` | `drain_until_stable(qapp, lambda: (row.isVisible(), row.width(), row.height()), …)` | row visible before ripple |
| `tests/runtime/test_themed_dialog.py:57,64` | `app.processEvents()` | `drain_until_stable(app, lambda: (polish_calls, geometry_calls, extra_calls), …)` | polish/geometry counters (≥1) |
| `tests/runtime/test_modal_keeps_flyout_open.py:25,40,70,99` | `qapp.processEvents()` | `drain_until_stable(qapp, lambda: isVisible/isModal…, …)` | modal/parent visible before `activeModalWidget` check |
| `tests/runtime/test_main_window_title_bar_menus.py:265,272,277` | `qapp.processEvents()` | `drain_until_stable(qapp, lambda: host.isVisible()/strip.isVisible()/flyout.isVisible(), …)` | overlay flyout `isVisible` after `reveal_menu_action` |

Cleanup drains after `deleteLater`/`sendPostedEvents(DeferredDelete)` intentionally **kept** as single `processEvents()` — they flush C++ deletion, not geometry, and `drain_until_stable` would timeout on dead widget.

### `src/tabs/session_picker/tests/runtime/test_recent_projects_panel.py` (26 → 15, −11)

- Added `from tests.helpers.drain_until_stable import drain_until_stable` at `test_recent_projects_panel.py:13`.
- Replaced 11 single-drain sites where geometry already stable but needs 2-frame settle; kept `isHidden/isVisible` already stable (no change where `assert not panel._empty_zone.isHidden()` after synchronous `refresh()` without window, per TODO “мигрируй где isHidden/isVisible уже stable” — those are not flaky and need no drain). Migrated:
  - `test_recent_panel_bare_panel_falls_back_to_two_rows:217,229` → `drain_until_stable(qapp, lambda: (grid_columns, scroll height), …)`
  - `test_recent_panel_viewport_uses_available_window_space:296,299` → viewport `max_h`/`height` tuple
  - `test_recent_panel_grid_uses_available_width:353,346` + `grid_shrinks_after_fullscreen_exit:402,410` → `grid_columns`
  - `test_recent_panel_shelf_height_settles_atomically:460` → `(scroll height, panel height)`; `pump()` helper `for _ in range(6): processEvents()` → `drain_until_stable(qapp, lambda: (grid_columns, scroll height, panel height), …)` (single bounded drain replaces 6-spin)
  - `test_recent_panel_resize_preserves_card_widgets:544,550` → `grid_columns`
  - `test_recent_panel_clears_orphaned_card_widgets:633` → live card count
  - `test_recent_panel_retranslate_keeps_opaque_shelf:704,709` → `card_for(...) is not None` / `isVisible && updatesEnabled`
  - `test_recent_panel_relayout_never_leaves_updates_disabled:796,800` → `grid_columns`
  - `test_recent_panel_virtualizes_large_list:1044,1057` → `live_card_count` before/after scroll
- Not migrated: `test_recent_panel_fills_cards_synchronously_on_show` (explicit “No processEvents / singleShot — first show fills shelf immediately” invariant), `isHidden` asserts in `test_recent_panel_empty_and_populated` (synchronous, no window).

## Files changed

| File | Change |
|---|---|
| `tests/runtime/test_dialog_auto_decoration.py:1` | import `drain_until_stable`; 3 replaces (`ensurePolished` → CSD bar) |
| `tests/runtime/test_tooltip_interceptor.py:1` | import + 1 replace (`bar.isVisible`+tabRect) |
| `tests/runtime/test_rounded_window_mask.py:1` | import + 1 replace (`widget isVisible`) |
| `tests/runtime/test_drag_ghost_ripple.py:1` | import + 1 replace (`row isVisible`) |
| `tests/runtime/test_themed_dialog.py:1` | import + 2 replaces (polish/geometry counters) |
| `tests/runtime/test_modal_keeps_flyout_open.py:1` | import + 4 replaces (modal/parent visible) |
| `tests/runtime/test_main_window_title_bar_menus.py:1` | import + 3 replaces (host/strip/flyout visible) |
| `src/tabs/session_picker/tests/runtime/test_recent_projects_panel.py:13` | import + 11 replaces (grid_columns, scroll heights, live counts, pump helper) |
| `docs/dev/investigations/drain-migration-wave5-2026-08-25.md:1` | This investigation |

No logic change to asserts; only waiting mechanism. `drain_until_stable` reuses existing helper (no QRhi, low-risk).

## Testing

- `python src/devtools/file_meta.py --check` → `Registry OK` (no size-changing edits beyond threshold; no `docs/dev/file_size_registry.json` rewrite needed).
- `QT_QPA_PLATFORM=offscreen pytest tests/runtime/test_color_picker_dialog.py tests/runtime/test_color_picker_recents.py tests/runtime/test_ui_scale_live_apply.py tests/runtime/test_app_message_dialog_theme.py -q` → `35 passed, 2 failed` (same 2 pre-existing `KeyError: 'Window'` in `test_app_message_dialog_theme.py:67,113` due to `themes.json` palette rename — not introduced by this wave; `LIGHT_THEME_PALETTE["Window"]` no longer exists, palette now `surface.background`/`WindowText`).
- `grep -rn "processEvents" tests/runtime --include="*.py" | grep -v "drain_until_stable" | wc -l` : **35 → 20** (−15). `src/tabs/session_picker/tests/runtime: 26 → 15` (−11). `tests: 61 → 46` (−15 overall). Before counts from `TODO.md:138` baseline; after from this wave.
- `QT_QPA_PLATFORM=offscreen pytest tests/contracts -q` → `1480 passed, 76 skipped, 2 failed` (`test_no_arrow_key_redirection` Up/Down grouping in `scroll_value_button.py:191,490` — pre-existing, not introduced; `test_file_size_policy` and `test_plugins_isolation` now pass; no new failures).
- Targeted: `QT_QPA_PLATFORM=offscreen pytest tests/runtime/test_dialog_auto_decoration.py tests/runtime/test_drag_ghost_ripple.py tests/runtime/test_themed_dialog.py tests/runtime/test_tooltip_interceptor.py tests/runtime/test_rounded_window_mask.py tests/runtime/test_modal_keeps_flyout_open.py tests/runtime/test_main_window_title_bar_menus.py tests/runtime/test_flyout_manager_modal_deactivate.py -q` → `27 passed`.
- `QT_QPA_PLATFORM=offscreen pytest src/tabs/session_picker/tests/runtime/test_recent_projects_panel.py -q` → `34 passed` (all grid/scale/virtualization invariants green; pump helper now bounded).
