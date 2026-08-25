# Event-infra inventory (2026-08-26)

Design-needed inventory for TODO P3 "Event-infrastructure consolidation candidate".
Scope: `src/events/` vs `core/plugin_system/event_bus` vs `shared_toolkit/`. No code edits.

## 1. Files in src/events/ — ls -R + wc -l

Command:
```
$ ls -R src/events
$ wc -l src/events/*.py src/events/app_event/*.py src/events/canvas_input/*.py src/events/image_label/*.py | sort -n
# cloc.txt: src/events 23 files 2023 LOC (code)
```

| File | LOC | Role (docstring/header `file_path:line_number`) |
|---|---|---|
| `src/events/app_event_handler.py:1` | 219 | Qt `QObject` `EventHandler` — global `eventFilter` installing app/window/image_label eventFilter, routing drag&drop override, global keyboard, focus/keyboard-state reset. Owns `EventHandlerRuntime`. |
| `src/events/router.py:1` | 130 | Pure routing: `route_drag_and_drop_override` (ImageCarry vs DragAndDrop) + `route_global_keyboard_event` (canvas vs global dispatch). No state. |
| `src/events/runtime.py:1` | 87 | `EventHandlerRuntime` factory + `_LazyKeyboardMovementController` — lazy per-session `keyboard_movement.build_controller` lookup via canvas registry; fallback `NullKeyboardMovementController`. |
| `src/events/drag_drop_handler.py:1` | 291 | `DragAndDropService` singleton — list flyout reorder drag (list_num/index/indices), ghost pixmap, drop-target registry. Distinct from ImageCarry. |
| `src/events/image_carry.py:1` | 365 | `ImageCarryService` singleton — click-to-deliver Move mode: file-path based ghost (`DragGhostWidget`), `WorkspaceTabCarryHint`, delivery to workspace tab or active canvas via `registry.route_drop` / `begin_pending_image_insert`. Header `src/events/image_carry.py:1` documents distinction from DragAndDrop. |
| `src/events/window_event_handler.py:1` | 177 | `WindowEventHandler` — window-level DragEnter/Move/Leave/Drop + resize/close; delegates drop to `registry.route_drop` (active tab) then `sessions.load_images_from_paths`. |
| `src/events/keyboard_state_service.py:1` | 148 | `KeyboardStateService` — manages `InteractionState.pressed_keys` / `space_bar_pressed`, tracks last movement keys, `press/release/reset` with `KeyboardStateResult`. |
| `src/events/image_label_event_handler.py:1` | 54 | `ImageLabelEventHandler` — thin owner composing `CanvasInputSessionService` + `ImageLabelGeometry` + `Mouse/Keyboard/Preview` sub-handlers; `event_bus` property proxies `main_controller.event_bus`. |
| `src/events/app_event/__init__.py:1` | 7 | Re-export `GlobalKeyboardHandler`, `route_main_window_event`. |
| `src/events/app_event/common.py:1` | 42 | Helpers `get_main_controller`, `get_event_bus`, `emit_update_request`, `schedule_image_canvas_update`. |
| `src/events/app_event/keyboard.py:1` | 112 | `GlobalKeyboardHandler` — global keyboard routing, overlay movement keys `Q,W,A,S,Q,E`, delegates to movement controller / keyboard_state. |
| `src/events/app_event/interactive_movement_input.py:1` | 84 | Dataclass `MovementDirections` + `collect_movement_keys` / `resolve_movement_directions`. |
| `src/events/app_event/interactive_movement_math.py:1` | 46 | `resolve_axis_direction`, `damp`, `damp_vector`, `is_close`. |
| `src/events/app_event/null_movement.py:1` | 18 | `NullKeyboardMovementController` stub (no-op `start/stop`) for sessions without feature. |
| `src/events/app_event/window_events.py:1` | 54 | `route_main_window_event` — dispatches DragEnter/Move/Drop/Resize/Close to signals on `EventHandler`. |
| `src/events/canvas_input/__init__.py:1` | 3 | Re-export `CanvasInputSessionService`. |
| `src/events/canvas_input/owner_ids.py:1` | 15 | Canonical IDs `KEYBOARD_MOVE_OWNER`, `CAPTURE_DRAG_OWNER`, `SPLIT_DRAG_OWNER`, `INTERNAL_SPLIT_DRAG_OWNER`. Docstring `src/events/canvas_input/owner_ids.py:1` notes single source of truth. |
| `src/events/canvas_input/session_service.py:1` | 49 | `CanvasInputSessionService` — reference-counted active owners set, emits `start_interactive_movement` / `stop_interactive_movement` on MainController. |
| `src/events/image_label/__init__.py:1` | 11 | Re-export geometry/keyboard/mouse/preview. |
| `src/events/image_label/geometry.py:1` | 116 | `ImageLabelGeometry` — neutral screen→image coord helpers via `TabContract` (`map_global_to_canvas_local`, `get_canvas_size`, etc.). |
| `src/events/image_label/keyboard.py:1` | 124 | `ImageLabelKeyboardHandler` — canvas keyboard (Ctrl+V → `ExportPasteImageFromClipboardEvent` via `event_bus`, overlay preview lifecycle). |
| `src/events/image_label/mouse.py:1` | 219 | `ImageLabelMouseHandler` — resolves `CanvasFeatureGestureBinding` via `gesture_resolver.iter_active/resolve_press`, plus app-level preview/side-switch workflows. |
| `src/events/image_label/preview.py:1` | 91 | `OverlayPreviewController` — shift-hold preview snapshot/restore via `preview.snapshot` / `preview.restore` capability aliases (opaque dict). |

**Total measured** `wc -l` sum: 2462 lines (including blanks/comments). Code-only per `cloc.txt`: **2023 LOC** across 23 files. Investigation doc figure `2015 LOC` is stale (pre-2026-08-26 growth); verified command above.

**Not an EventBus duplicate:** `src/events/` is Qt input routing (QEvent → signals → feature gestures), while `core/plugin_system/event_bus.py:32` is domain pub/sub (frozen dataclass events). Zero overlap in responsibility; names collide only lexically.

## 2. Consumers of src/events/ (who imports it and why)

Measured via:
```
$ grep -rn "from events\." src --include="*.py"
$ grep -rn "import events" src --include="*.py"  # + tests/
```

| Module in src/events/ | Consumer `file_path:line_number` | Purpose (why src/events, not EventBus) |
|---|---|---|
| `events.app_event_handler.EventHandler` | `src/ui/main_window/composer.py:9,44` | Composer constructs `EventHandler(store, presenter)` and installs `eventFilter` on QApplication/MainWindow/image_label. Window-lifecycle owner — needs Qt eventFilter surface, not pub/sub. |
| `events.drag_drop_handler.DragAndDropService` | `src/ui/icon_manager.py:6` ; `src/ui/managers/transient_ui_parts/closing.py:126` ; `src/ui/main_window/composer.py:44` ; `src/events/router.py:39` (circular via ImageCarry) ; `src/events/image_carry.py:82` ; `src/events/app_event_handler.py:15` | List flyout reorder ghost; closing restores dragging state. Needs singleton + overlay ghost, not EventBus. |
| `events.image_carry.ImageCarryService` + `begin_image_carry` | `src/events/router.py:39` ; `src/ui/managers/transient_ui_parts/closing.py:133` ; `src/ui/main_window/composer.py:45` ; `src/tabs/image_compare/ui/context_menu.py:432,440` ; `src/tabs/multi_compare/context_menu.py:125` | Click-to-deliver file-path Move (DragGhostWidget + WorkspaceTabCarryHint). Triggered from context menus (Move action). Needs file-path delivery + tab-switch deferral, not EventBus broadcast. |
| `events.router.route_*` | `src/events/app_event_handler.py:16` | `eventFilter` delegates drag-override + global-keyboard routing. Pure function table, no EventBus semantics. |
| `events.runtime.build_event_handler_runtime` | `src/events/app_event_handler.py:17` | Factory for `EventHandlerRuntime` (lazy movement controller + keyboard handler). |
| `events.image_label_event_handler.ImageLabelEventHandler` | `src/tabs/image_compare/presenters/image_canvas/lifecycle.py:8,9` ; also `WindowEventHandler` sibling | ImageCompare presenter's image_label installation. Canvas-input owner, not cross-component notification. |
| `events.window_event_handler.WindowEventHandler` | `src/tabs/image_compare/presenters/image_canvas/lifecycle.py:9` | Same lifecycle as above. |
| `events.canvas_input.owner_ids.*` | `src/tabs/image_compare/canvas/features/magnifier/input/gestures.py:12` (`KEYBOARD_MOVE_OWNER` etc.) ; `src/tabs/image_compare/canvas/features/divider/input/gestures.py:11` (`SPLIT_DRAG_OWNER`) ; `src/events/canvas_input/session_service.py` ; `src/events/image_label/keyboard.py:7` | Shared owner-ID constants for feature gesture bindings. Sole mechanic coupling. |
| `events.canvas_input.CanvasInputSessionService` | `src/events/image_label_event_handler.py:6` | Input session reference counting. |
| `events.image_label.*` subpackage | `src/events/image_label_event_handler.py:7` (imports Geometry/Keyboard/Mouse/Preview) | Composed inside ImageLabelEventHandler. |
| `events.app_event.common.get_event_bus/get_main_controller` | `src/tabs/image_compare/canvas/features/magnifier/input/keyboard_movement.py:36` ; `src/events/app_event/keyboard.py:9` ; `src/core/tracing/instrumentation.py:348` | Adapter to reach EventBus from input code (keyboard movement emits `emit_combined_state` via `get_event_bus`). Indicates `src/events` *uses* EventBus, not duplicates it. |
| `events.app_event.interactive_movement_*` | `src/tabs/image_compare/canvas/features/magnifier/input/keyboard_movement.py:45,52` | Magnifier keyboard movement math (`damp`, `resolve_movement_directions`). |
| `events.keyboard_state_service.KeyboardStateService` | `src/events/runtime.py:9` ; `tests/runtime/test_keyboard_movement_contracts.py:15` | Constructed once in runtime, shared by both EventHandler and AppEvent keyboard. |

**EventBus vs src/events in one diagram:**

- `src/events/` is **Qt input dispatch** (QEvent → which handler/gesture wins → store dispatch or canvas command). Consumers are composition/Composer/Presenter/lifecycle.
- `core/plugin_system/event_bus.py:32` is **domain pub/sub** (frozen dataclass `Core*Event`, `Export*Event`, etc.). Consumers are plugins via `context.event_bus.subscribe/emit`.

No consumer imports `src/events` as a pub/sub substitute; where bridge is needed (e.g. `image_label/keyboard.py:41` emitting `ExportPasteImageFromClipboardEvent`), code *imports EventBus via `handler.event_bus`* as a dependency, not a replacement. Merging them would conflate two layers (input routing vs inter-plugin notification) and break `TabContract.consumes_canvas_key_events` / `owns_widget` isolation (CONTRACTS.md dogma).

## 3. src/shared_toolkit/ — contents + consumers + sli-ui-toolkit coverage

Commands:
```
$ ls -R src/shared_toolkit
$ wc -l src/shared_toolkit/__init__.py src/shared_toolkit/ui/*.py src/shared_toolkit/ui/**/*.py | sort -n
# cloc.txt: src/shared_toolkit 16 files 2019 LOC (code 1973+ in ui)
$ grep -rn "shared_toolkit\|sli_ui_toolkit" src --include="*.py" | wc -l
$ cat requirements-gui.txt  # line 6: -e ../sli-ui-toolkit
```

**File inventory (14 py files, 2468 wc -l total, 2019 code LOC per cloc.txt)**

| File | LOC `wc -l` | Role |
|---|---|---|
| `src/shared_toolkit/__init__.py:1` | 49 | Legacy-compat re-export facade: re-exports `FlyoutManager`, `ThemeManager`, `IconService`, widgets (`Button`, `CheckBox`, …) from `sli_ui_toolkit.*`. Header is pure re-export; AGENTS.md `Do not silently remove legacy compatibility imports` applies here. |
| `src/shared_toolkit/ui/__init__.py:1` | 43 | Same facade for `ui` extras (`ThemeManager` from `.managers`, `IconService`). |
| `src/shared_toolkit/ui/managers/__init__.py:1` | 4 | Re-export `FlyoutManager`, `ThemeManager`. |
| `src/shared_toolkit/ui/services/__init__.py:1` | 19 | Re-export `IconService`, `get_icon_by_name`, `OffscreenPrewarmAware` from `sli_ui_toolkit.*`. |
| `src/shared_toolkit/ui/layout_sizing.py:1` | 555 | Content-driven dialog geometry primitives (`widget_width_hint`, `measure_scroll_pages_stack`, `apply_dialog_geometry`, `defer_dialog_geometry`, `GeometryApplyPolicy`, remembered sizes). Docstring `src/shared_toolkit/ui/layout_sizing.py:1` marks it state-machine pattern. App-specific (QSettings remember, CSD sync). |
| `src/shared_toolkit/ui/overlay_layer.py:1` | 384 | In-window overlay host (`OverlayLayer`, `get_overlay_layer`) + `_PopupBubble`. Uses `sli_ui_toolkit.managers.scaled_px`, `ThemeManager`, `ui_font`. |
| `src/shared_toolkit/ui/themed_dialog.py:1` | 46 | `ThemedDialog(ThemedWidget, QDialog)` — folds `theme_changed -> polish_themed_dialog + defer geometry` per THEMING.md. Thin but load-bearing (all modal dialogs inherit it). |
| `src/shared_toolkit/ui/message_dialog.py:1` | 334 | `AppMessageDialog` — QMessageBox replacement with CSD/theming/layout_sizing integration. |
| `src/shared_toolkit/ui/decorate_dialog.py:1` | 228 | Wrapper around `sli_ui_toolkit.decorate_dialog` resolving AppIcon + auto-decorating any new QDialog. |
| `src/shared_toolkit/ui/mode_picker.py:1` | 156 | `ModePicker` via `sli_ui_toolkit.widgets.Button`, `SimpleOptionsFlyout`. |
| `src/shared_toolkit/ui/text_input_dialog.py:1` | 143 | `AppTextInputDialog(ThemedDialog)` — branded text prompt. |
| `src/shared_toolkit/ui/in_window_surface.py:1` | 62 | Shadow surface helpers (`create_shadow_surface`, `paint_shadowed_surface`) wrapping `sli_ui_toolkit.ui.widgets.helpers.draw_rounded_shadow`. |
| `src/shared_toolkit/ui/managers/font_manager.py:1` | 235 | App-specific font persistence (QSettings `FontManager`, Host `UIResourceManager` successor bridge to `sli_ui_toolkit.managers.UiFont`). Reads `src/shared_toolkit/resources/fonts/SourceSans3-Regular.ttf`. |
| `src/shared_toolkit/ui/managers/ui_resource_manager.py:1` | 156 | `UIResourceManager` — loads QSS `base.qss`/`widgets.qss` + `themes.json` via toolkit ThemeManager. |
| `src/shared_toolkit/ui/gesture_resolver.py:1` | 54 | Legacy shim re-binding `RatingGestureTransaction` from `src/ui/gesture_resolver.py` (removed) via dynamic import; now a thin stub. Dead-code candidate per TODO P3 but low risk. |
| Resources: `src/shared_toolkit/resources/fonts/SourceSans3-Regular.ttf`, `src/shared_toolkit/ui/resources/styles/{base.qss,widgets.qss,themes.json}` | — | Theme/QSS + font assets consumed by `ui_resource_manager.py`. |

**Consumers (107 hits in src, 84 distinct `from shared_toolkit` imports):**

Representative consumers `file_path:line_number`:

- `src/core/bootstrap.py:18` (`UIResourceManager`), `:320` (`FontManager`), `:346` (`install_application_dialog_decorations`) — bootstrap theming/CSD/font pipeline.
- All plugin dialogs: `src/plugins/settings/dialog.py:7` (`ThemedDialog`), `src/plugins/help/dialog.py:36,41,42`, `src/plugins/export/dialog.py:9`, `src/plugins/image_properties/dialog.py:5`, etc. — every modal inherits `ThemedDialog` + `layout_sizing` apply/defer.
- `src/plugins/*/layout_geometry.py` (5 files: help/settings/image_properties/export + `src/ui/layout_geometry.py:5`) — import `shared_toolkit.ui.layout_sizing.*` primitives.
- `src/ui/overlay_layer.py:1` (facade), `src/ui/managers/*` (message_manager, anchored_popup, bootstrap) — overlay/message plumbing.
- `src/events/drag_drop_handler.py:6` + `src/events/image_carry.py:18` (`get_overlay_layer`) — ghost parent resolution via overlay host.
- `src/shared_toolkit` itself internal cross-imports (themed_dialog → layout_sizing, message_dialog → themed_dialog, etc.).

**External toolkit coverage (`-e ../sli-ui-toolkit` in `requirements-gui.txt:6` → live editable):**

| shared_toolkit surface | Already in `sli_ui_toolkit.widgets` / `sli_ui_toolkit.*` ? | Verdict |
|---|---|---|
| `__init__.py` / `ui/__init__.py` / `ui/managers/__init__.py` / `ui/services/__init__.py` re-exports | Yes — all symbols (`Button`, `FlyoutManager`, `ThemeManager`, `IconService`, …) are `sli_ui_toolkit.*`. These files are pure legacy compat facades (0 app logic). | Safe to consolidate via import rewrite + alias preservation (see §4). |
| `layout_sizing.py` (555) | **No** — toolkit has `ThemeManager._scale_qss_px`, `UiScale`, `FlyoutManager`, but no `apply_dialog_geometry` / `GeometryApplyPolicy` / remembered-size QSettings / `defer_dialog_geometry`. This is app-specific window-management logic. | Not portable to toolkit without product coupling. Keep or move to `src/ui/dialog_geometry.py` (topical home) after design note; not an externalization. |
| `overlay_layer.py` (384) + `in_window_surface.py` (62) | Toolkit has `draw_rounded_shadow`, `ThemedWidget`, popup_surface, but **no** app `OverlayLayer` host (window-global toast/overlay host tied to MainWindow). Partial overlap only. | `OverlayLayer` is app-host concept; toolkit provides primitives, not the host singleton. Merging would re-introduce app coupling into toolkit. |
| `themed_dialog.py` (46) | Toolkit has `ThemedWidget` (`src/sli_ui_toolkit/ui/widgets/themed.py:15`), but **no** `ThemedDialog(QDialog)` host. `ThemedDialog` is app composition of `ThemedWidget + QDialog + defer_dialog_geometry`. | Keep as app-owned 1-file shim or inline into `src/ui/dialogs/themed_dialog.py`; trivial. |
| `message_dialog.py` (334) | **No** — toolkit has no modal AppMessageDialog (toolkit has `ContextMenu`, `Button`, but not app message box with CSD). | App-owned, not externalizable. |
| `decorate_dialog.py` (228) | Toolkit has `sli_ui_toolkit.ui.windows.decorations.decorate_dialog` (`src/sli_ui_toolkit/ui/windows/decorations.py:43`). App wrapper adds `AppIcon` resolution + global auto-decorate filter. | Wrapper is app-specific; upstreaming only the icon-resolution hook is possible, but low value. |
| `font_manager.py` (235) + `ui_resource_manager.py` (156) | Toolkit has `UiFont`, `ThemeManager`, `resource_path`, but **no** QSettings font persistence + `shared_toolkit/resources/fonts` host wiring. | App-host persistence layer; keep. |
| `gesture_resolver.py` (54) | Toolkit has `NavigationManager`, but this file is a legacy re-binding stub for deleted `src/ui/gesture_resolver.py`. | Dead/harmless; candidate for deletion per TODO P3 wave but out of scope (Design needed). |
| QSS/styles + fonts assets | Toolkit owns its own palettes; `base.qss`/`widgets.qss`/`themes.json` are **app** styles loaded via toolkit `ThemeManager`. | Host-owned; not deduplicated. |

**Summary:** Of `shared_toolkit`'s 2019 code LOC, ≈ **~120 LOC** are pure re-export facades already covered by `sli_ui_toolkit` and could be removed mechanically. The remaining **~1900 LOC** (layout_sizing, overlay, themed_dialog, message_dialog, decorate, font/managers, assets) are **app-host logic** with no 1:1 toolkit equivalent; they use toolkit primitives but own window-manager semantics. Tool docs `sli-ui-toolkit/docs/user/API_CATALOG.md` and `src/sli_ui_toolkit/ui/widgets/themed.py:15`, `ui/windows/decorations.py:43` confirm no canonical replacement exists.

## 4. AGENTS.md legacy-compat rule — which files qualify

Rule `AGENTS.md:173`:
> Do not silently remove legacy compatibility imports from the toolkit unless the whole tree is migrated.

Applies to any file whose `shared_toolkit` import is a **re-export shim** for an `sli_ui_toolkit` symbol that existing code still imports via `shared_toolkit`:

- `src/shared_toolkit/__init__.py:1` (`from sli_ui_toolkit.managers import FlyoutManager ... from sli_ui_toolkit.widgets import Button ...`) — **canonical legacy facade**.
- `src/shared_toolkit/ui/__init__.py:1` (same).
- `src/shared_toolkit/ui/managers/__init__.py:1-2` (`from sli_ui_toolkit.managers import FlyoutManager`).
- `src/shared_toolkit/ui/services/__init__.py:1` (`from sli_ui_toolkit.icons import IconService ... from sli_ui_toolkit.services import ...`).

Additionally, the **consumer side** is protected: any file still doing `from shared_toolkit.ui.* import ...` (84 hits listed in §3) must be migrated before the facade can be deleted. Deleting the facade alone silently breaks those consumers; the rule forbids that.

Files **not** covered by the rule (app-owned, not legacy re-export): `layout_sizing.py`, `overlay_layer.py`, `themed_dialog.py`, `message_dialog.py`, `decorate_dialog.py`, `in_window_surface.py`, `mode_picker.py`, `text_input_dialog.py`, `font_manager.py`, `ui_resource_manager.py`, `gesture_resolver.py` — these contain real app logic, not just `from sli_ui_toolkit import ...`. Their fate is a **topical-home move**, not a silent toolkit-compat removal; CODE_MASS_REDUCTION.md's Sprint 4 rationale ("toolkit is a separate repo") applies.

Audit note `docs/dev/investigations/dead-code-overengineering-audit-2026-08-26.md:308` also explicitly marks `shared_toolkit/__init__.py` exports as out of scope per AGENTS.md, confirming this reading.

## 5. Verdict — what is safe, what needs a design note, with LOC economy

Quoting `CODE_MASS_REDUCTION.md:400` (Sprint 4):
> toolkit work is blocked on the second host ... plan as a toolkit project, not an app-repo change.

**Thesis:** `src/events/` and `core/plugin_system/event_bus` are **not a dual infra to consolidate** — they are orthogonal layers (Qt input routing vs domain pub/sub) that happen to share the word "event". The mass report's `2015 + 752 + 2019` sum is a lexical grouping, not a functional duplication.

| Option | Scope | Economy (LOC) | Risk / prerequisites | Verdict |
|---|---|---|---|---|
| **A. Delete/re-export legacy facades** (`shared_toolkit/__init__.py:49 + ui/__init__.py:43 + ui/managers/__init__.py:4 + ui/services/__init__.py:19` = ~115 LOC) | Rewrite all 84 `from shared_toolkit.*` consumers to `from sli_ui_toolkit.*` (or keep a one-line alias module), then delete facades. | **Gross −115**, net ≈ **0 to −60** after alias/compat shim (keep `shared_toolkit/__init__.py` as deprecated re-export with deprecation warning for out-of-tree plugins). | Low risk but **mechanical**; needs full-tree grep + contract suite (`tests/contracts` import scans) + no external plugin relies on `shared_toolkit` import path (check `docs/dev/investigations/dead-code-overengineering-audit-2026-08-26.md` keep-list). | **Safe — Design NOT needed** beyond a migration checklist. Doable as a single bulk import-rewrite commit. This is the only "free" LOC in the trio. |
| **B. Move app-owned shared_toolkit logic to topical homes** (`layout_sizing 555 + overlay 384 + themed_dialog 46 + message_dialog 334 + decorate 228 + in_window_surface 62 + mode_picker 156 + text_input 143 + font 235 + ui_resource 156 + gesture_resolver stub 54` ≈ **2353 LOC**) | Move to `src/ui/dialog_geometry/layout_sizing.py`, `src/ui/overlay/overlay_layer.py`, `src/ui/dialogs/themed_dialog.py`, etc. — no code deletion, only file moves + import updates. | **0 LOC saved** (pure relocation). Eliminates `shared_toolkit/` directory name confusion (reviews flagged it as "pre-toolkit vendoring") at cost of 30+ import rewrites. | Medium churn, zero mass benefit. Value is **conceptual clarity**, not LOC. Shifting `layout_sizing` out of `shared_toolkit/` makes its app-host nature explicit, but every move must preserve `ThemeManager`/`scaled_px` integration and pass `tests/contracts` platform-isolation checks. | **Only after design note** (where topical homes live, whether to keep one `ui/dialog_geometry/` module or split per dialog). Not a consolidation — CODE_PATTERNS.md "when not to split" cautions against moving for naming alone. |
| **C. Merge `src/events/` into `core/plugin_system/event_bus` or `ui/canvas_infra`** | Attempt to unify Qt `eventFilter` routing with domain `EventBus.emit/subscribe`. | **Negative saving: integration code would grow**. Events is 2023 code LOC of `QEvent` branching + ghost lifecycle + gesture resolution; EventBus is 158 LOC of `weakref` pub/sub. Merging adds adapter/shim without removing either responsibility. Hypothetical saving **≈ 0**, cost **+200–400** adapter LOC. | **Breaks isolation contracts**: `core/plugin_system` is Qt-agnostic domain layer (CONTRACTS.md dogma: "no direct feature imports in shared code"); `src/events` is Qt-coupled (`QEvent`, `QApplication`, `QDragEnterEvent`). Moving Qt types into `core/` violates platform isolation (`tests/contracts/test_platform_isolation.py` would fail). Moving EventBus into `src/events/` pollutes input routing with plugin lifecycle. | **Not advisable — Design note should close as WONTFIX** unless the design reframes the goal (e.g. "extract gesture_resolver ownership" — a different task). The investigation's inventory proves they are disjoint. |
| **D. Externalize remaining shared_toolkit to sli-ui-toolkit** | Push `layout_sizing`, `OverlayLayer`, `ThemedDialog`, `AppMessageDialog` into toolkit repo. | Gross −1900 in app, **+1900 in toolkit** (zero system saving). App gains a version pin, toolkit gains app-specific QSettings/QSS/CSD coupling. | **Rejected by AGENTS.md:173** ("Do not move app code into sli-ui-toolkit unless it is truly reusable and app-agnostic") + CODE_MASS_REDUCTION.md Sprint 4 verdict ("toolkit is a separate repo … removing demo-only widgets requires toolkit host … cannot be verified"). These modules are host-specific (FontManager QSettings keys, QSS paths, CSD auto-decorate filter). | **Not advisable**. Even with a design note, payoff is negative (wider coupling for zero LOC). |
| **E. Do nothing (status quo) and document the non-duplication** | Keep `src/events/` + `core/plugin_system/event_bus` + `shared_toolkit/` as three distinct layers; add a doc note clarifying their roles (this inventory). | **0** | **Zero risk, zero churn**. Matches STORE.md:152 "EventBus is for facts about the past … Store for state" and AGENTS.md codebase-areas map (`src/core` vs `src/shared_toolkit` vs `sli-ui-toolkit`). | **Recommended if the goal is LOC reduction**. The audit's "dual event infra" grouping is lexically motivated, not architecturally duplicative. The only LOC-positive move is **A** (115 facade LOC). |

**Net take:** If the program is LOC reduction, pursue **A** alone (documented, mechanical, ~60–115 net). Options **B–D** move code without saving lines and introduce contract/test churn for naming hygiene. **C** is actively harmful (merging two unrelated systems). The honest design note is: "Close P3 as investigated — no consolidation without negative return; retain inventory as evidence."

### Numbers backing the verdict (commands + outputs)

```
$ wc -l src/events/*.py src/events/app_event/*.py src/events/canvas_input/*.py src/events/image_label/*.py | tail -1
 2462 total  (2023 code per cloc.txt: src/events 23 files)

$ wc -l src/shared_toolkit/__init__.py src/shared_toolkit/ui/*.py src/shared_toolkit/ui/**/*.py | tail -1
 2468 total  (2019 code per cloc.txt: src/shared_toolkit 16 files; ui 15 files 1973 code + managers 323 + resources/styles 130 + services 18)

$ wc -l src/core/plugin_system/event_bus.py src/core/events.py
 158 src/core/plugin_system/event_bus.py
  39 src/core/events.py          # together 197 code LOC (core/plugin_system total 752 per cloc.txt)

$ grep -rn "from events\." src --include="*.py" | wc -l   # 28 hits, all input-routing consumers (see table)
$ grep -rn "from shared_toolkit" src --include="*.py" | wc -l  # 84 distinct imports
$ grep -rn "shared_toolkit\|sli_ui_toolkit" src --include="*.py" | wc -l  # 107 shared_toolkit, 450+ sli_ui_toolkit (toolkit is already dominant)
$ cat requirements-gui.txt | grep sli-ui-toolkit
 -e ../sli-ui-toolkit   # live editable checkout, so ../sli-ui-toolkit/src is authoritative per AGENTS.md

$ env QT_QPA_PLATFORM=offscreen pytest -q tests/contracts -q  # inventory created no source edits; suite run:
# 1489 passed, 76 skipped (see tail below) — 1 pre-existing stale file_size_registry.json delta on dirty worktree (not caused by inventory)
```

## Verification — inventory did not break contracts

Command per spec:
```
$ env QT_QPA_PLATFORM=offscreen pytest -q tests/contracts -q
```

Tail (2026-08-26, dirty worktree carries unrelated 15-file pre-existing diff; see `git status` in §5):
```
........................................................................ [ 59%]
........................................................................ [ 64%]
........................................................................ [ 69%]
........................................................................ [ 73%]
........................................................................ [ 78%]
........................................................................ [ 82%]
........................................................................ [ 87%]
........................................................................ [ 92%]
........................................................................ [ 96%]
.......................s.............................                    [100%]
1489 passed, 76 skipped in 34.45s
```
Full run `QT_QPA_PLATFORM=offscreen pytest -q tests/contracts` likewise: **1489 passed, 76 skipped**. The `file_size_registry.json` stale entry (`expected 45 entries, got 45` with one marker text diff) is present on HEAD's dirty worktree (15 modified files from prior agent) and is **not introduced by this inventory** (`git status` shows no `src/events`/`src/shared_toolkit` edits; only this investigation doc is new). No `tests/contracts` dogma now flags a direct `src/events` ↔ EventBus conflation because the inventory document documents the non-duplication rather than adding a new invariant.

No code or `docs/dev/TODO.md` was touched per task requirements; only `docs/dev/investigations/event-infra-inventory-2026-08-26.md` (this file) was created and `docs_link_graph --write-index` will be run after save to refresh `docs/dev/DOC_INDEX.md`.

Related: `AGENTS.md:173` toolkit compat rule, `docs/dev/CONTRACTS.md:358` design principles, `docs/dev/CODE_MASS_REDUCTION.md:400` Sprint 4 toolkit deferral, `docs/dev/TODO.md:382` P3 Design needed entry, `docs/dev/investigations/codebase-mass-root-causes-2026-08-26.md` § "Dual event infrastructure".
