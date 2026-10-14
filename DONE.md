# DONE — gallery-kbd2 (Image Gallery keyboard navigation)

## STATUS
Done. Branch `agent/gallery-kbd2/work`, committed, pushed. No GUI run
(offscreen/headless only). Only keyboard/navigation/focus logic touched; no
color/hex/token/theme line changed (disjoint from `gallery-dark-theme`).

## TESTS
```
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m pytest -q src/tabs/image_gallery/tests tests/contracts -p no:cacheprovider
```
Result: **3191 passed, 68 skipped** (green).

New focused cases in `src/tabs/image_gallery/tests/test_gallery_keyboard.py`
(9 new, 18 total). Red-before/green-after verified in a detached worktree at
pre-fix `HEAD` (copied the final test file in): **9 failed, 9 passed** pre-fix,
**18 passed** post-fix.

Extra: `tests/test_navigation_manager.py tests/test_app_shell_navigation.py
tests/contracts/test_no_arrow_key_redirection.py
tests/contracts/test_navigation_graph.py` → 73 passed.

## INTERFACE
- `GalleryGridView.focus_card(card, reason=None)`, `focus_first_card(reason=None)`,
  `focus_last_card(reason=None)` — `reason` is an optional `NavigationSection`
  grant; otherwise `NavigationManager.current_focus_reason()` (never a literal
  `OtherFocusReason`).
- `GalleryGridView.move_focus(key)` — returns `False` at an edge (yields) instead
  of consuming.
- `GalleryGridView.nav_section` (property) → `GalleryGridNavSection`:
  `owns` live cards only, `extra_keys={Left, Right}`, `navigate` →
  `move_focus`, `focus_first/focus_last(ref_x=None, *, reason)`.
- `GalleryGridView._focus_snapshot()` / `_restore_focus(snapshot)` replace
  `_capture_focus_path` / `_restore_focus_path` (path **+ order index**, nearest
  live card on removal).
- `ImageGalleryTab._toolbar_rows()` returns container rows
  `[widget.toolbar, widget.stats_strip]`; `_register_nav_section()` registers
  the toolbar section then the grid section; `on_deactivated`/`dispose`
  unregister both.
- `triage_ui.handle_key` no longer re-interprets arrows as a selection move.

## SELF-REVIEW
- All binding constraints checked: edges yield (`event.ignore`), no
  Down→Right/Up→Left grouping, focus grants via `current_focus_reason()`, cards
  keep real Qt focus (no second index ring), key semantics preserved
  (Enter=Quick Look, Space/Delete/Backspace=remove-from-view before Button
  activation, Menu=context menu, Home/End, Ctrl+A, B, Esc), focus survives
  rebuild/recycle, grid is not a toolbar row, keyboard filters are separate
  `QObject`s below the scroll viewport, order from layout geometry, sections
  registered on activate / unregistered on deactivate.
- Residual risk: the grid section opts into Left/Right, so the manager consumes
  a row-edge Left/Right (nothing happens) rather than moving selection — chosen
  over the old linear selection jump.
- `triage_ui` arrow branch removed rather than kept as a fallback (see SUMMARY
  §Steer D) — it is unreachable once the grid section owns all four arrows.
- File-size registry regenerated (`grid_view.py`, `tab.py` grew).

## SUMMARY

### RECON — how the other tabs do it (file:line)
- **Accepted sibling for card focus nav** `src/tabs/session_picker/recent/items_view.py`:
  real Qt focus on pooled `Button`s; `navigate_focus` (`:216`), `activate_focused_card`
  (`:250`), `_ensure_index_visible` (`:198`), focus-preserving recycle
  `_focused_record_index` (`:614`) / `_restore_focus_after_recycle` (`:630`) —
  nearest live card, never teleport to 0; `eventFilter` → `_handle_key_press`
  for KeyPress on the host (`:349`–`:373`).
- `src/tabs/session_picker/recent/header_bar.py`: explicit section handoff in
  `keyPressEvent` — Down → first shelf card (`:141`), Up → create-cards (`:115`).
- `src/core/navigation_sections.py`: `SessionPickerSection.owns` deliberately
  excludes the recent panel (`:63`) so its own filter owns arrows; `navigate`
  yields (returns `False`) at the first/last item (`:78`–`:119`); `TabStripSection`
  yields Up/Down (`:199`–`:207`).
- `tests/test_navigation_manager.py`: trial-dispatch Down/Up to the next/prev
  section (`:192`–`:237`), Left/Right pass through unless `extra_keys` opts in
  (`:240`, `:455`).
- `src/plugins/settings/pages/keyboard.py:339`–`:355`: NavigationManager owns
  arrow consumption on `QApplication`; a widget-level filter never sees the key
  when a registered section owns the focused widget.
- `src/core/app_shell_navigation.py:11`–`:20`: section registration order is the
  vertical hierarchy `_neighbor()` relies on.
- Tab toolbar registration pattern: `image_compare/tab.py:303`–`:324`,
  `multi_compare/tab.py:211`–`:216` via `declare_toolbar_navigation`.

### Breakages found and fixed
1. **Toolbar nav section was INERT** — `tab.py:_toolbar_rows` passed bare
   controls (`_filter_edit`, `_pick_button`); `ToolbarRowsSection` searches a
   row's StrongFocus descendants, so `focus_first/focus_last` returned `False`
   (verified) and Up/Down never left the filter. Fixed → container rows.
2. **The grid was not a registered section** — no `NavigationManager._neighbor`
   handoff; an edge arrow was swallowed and focus stayed put. Fixed →
   `GalleryGridNavSection` + `move_focus` yields at edges. Verified: Up at the
   first card → toolbar, Down from toolbar/filter → first card.
3. **Host KeyPress swallowed** — `GalleryGridView.eventFilter` handled
   marquee/RMB but not KeyPress, so a bare arrow on the host/viewport never
   entered the grid. Fixed (session-picker parity).
4. **Two overlapping arrow implementations** — `move_focus`/`_CardKeyFilter`
   vs `triage_ui.handle_key`'s selection-by-index arrows. Fixed → single path.
5. **Focus lost when the focused card was removed** (Space/Delete) — the rebuild
   recycled it and the ring dropped to the hosting widget. Fixed →
   `_focus_snapshot`/`_restore_focus` (path, else nearest live card).
6. **Literal `OtherFocusReason` focus grants** — bare `setFocus()` in
   `_rebuild_series` and a literal fallback in `focus_card`. Fixed → routed
   through `_focus_reason()` / `current_focus_reason()`.

### Steer D note
The supervisor suggested keeping `triage_ui`'s arrow branch as a selection-only
fallback "invoked only when focus nav declined". I removed it entirely: once the
grid section owns all four arrows (`extra_keys={Left,Right}`) the fallback is
unreachable dead code, and the task's binding constraint says NavigationManager
owns arrows exclusively. Restorable guarded on request.
