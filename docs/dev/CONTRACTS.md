# Application Contracts

This document explains the 24+ contracts and protocols that define how different parts of the application communicate. Rather than listing every API, it focuses on *why* these contracts exist and how they solve specific architectural problems.

## Three senses of “contract”

The word **contract** is used consistently, but for three related ideas.
`contract == interface` alone is incomplete.

| Sense | Meaning | Where to read |
|---|---|---|
| **Interface** | Typed integration surface: implement these fields/methods to plug into the host (`TabContract`, `CanvasWidgetFeature`, `CanvasRenderPass`, …). | This page (why); field catalogs in [rendering/contracts.md](rendering/contracts.md), [tabs/contract.md](tabs/contract.md), [render-pass-contract.md](rendering/render-pass-contract.md) |
| **Host call sequence** | Part of an interface: the host invokes methods in a fixed order (e.g. render pass `initialize` → `prepare` → `record` → `release`). Not a separate CI suite. | [render-pass-contract.md](rendering/render-pass-contract.md) |
| **Architectural dogma** | Developer rules that keep isolation intact (“no direct feature imports in shared code”). Enforced by AST scans in CI — not a public API. | Design principles below; [TESTING.md](TESTING.md) (`tests/contracts/`) |

This page is primarily about **interface** contracts and the isolation model behind them. Architectural dogmas appear here as principles; the executable checks live under `tests/contracts/`.

## The Big Picture

The application uses **contract-based architecture** to solve a fundamental problem: how do you add visual features (magnifier, divider, guides) without scattering their logic across the renderer, state management, toolbar, settings, and export systems?

**The answer**: Instead of a feature getting hardcoded into every subsystem, it registers itself via a series of well-defined contracts. The subsystems then call features through those contracts.

Example:
- Feature doesn't know about toolbar → **ToolbarBinding** contract
- Toolbar doesn't know about feature → queries registered bindings
- Result: No direct imports, features can be deleted without crashing

## Feature Isolation Model (The Abstraction)

Each feature lives in **its own abstraction layer** — like a plugin in OpenFX. The core infrastructure handles all the complexity; the feature receives a simplified interface.

**What the feature does NOT see or handle:**
- Multiple coordinate systems (widget-px, canvas-px, image-px, screen-px)
- Zoom, pan, rotation, or any viewport transformations
- Raw Qt mouse/keyboard events
- Texture uploads, buffer management, or QRhi context state
- Serialization or deserialization details

**What the feature receives from the core:**

1. **Unified coordinate space** — all geometry in `canvas-px` (a single normalized space where zoom and pan are already applied). Feature never thinks about scale factors.
   ```python
   # Feature just works with canvas-px; transformation is handled upstream
   def on_mouse_move(canvas_x: float, canvas_y: float):
       self.position = (canvas_x, canvas_y)  # Done!
   ```

2. **Pre-processed events** — mouse clicks, drags, keyboard input are captured by the core, hit-tested, and routed to the feature as semantic commands. Feature doesn't parse Qt events.
   ```python
   # Feature receives a command, not raw QMouseEvent
   def cmd_move_overlay(store: Store, new_x: float, new_y: float):
       # Coordinates already validated, already in canvas-px
   ```

3. **Encapsulated state** — feature state lives in Redux (immutable snapshots). Feature declares properties; core handles persistence, keyframing, and export.
   ```python
   # Feature doesn't write settings to disk; core does
   @dataclass
   class MagnifierState:
       zoom: float
       position: tuple[float, float]
   ```

4. **Routed events** — when a feature needs to know what another feature is doing (e.g., divider needs magnifier offset), it queries via `CanvasFeatureStateQuery`, not by importing magnifier code.

**Why this matters**: A feature can be written without understanding the rendering pipeline, viewport math, or coordinate systems. The core guarantees that every input is pre-processed and every output is handled correctly. This is similar to how OpenFX plugins work — they operate in a simplified plugin world while the host (Nuke, etc.) handles all the complexity.

## Canvas Features (The Core Problem)

Canvas features are tools like magnifier, divider, or guides that:
1. Appear on the canvas (need scene objects and QRhi rendering)
2. React to interactions (need command handlers)
3. Have editable properties (size, color, visibility)
4. Appear in the toolbar and settings
5. Can be animated in video export
6. Need to work in live canvas AND export paths

**Problem**: Each of these subsystems needs different information about the feature. But hardcoding feature names everywhere creates a tangled mess.

**Solution**: A set of contracts that let features *register* with subsystems instead of subsystems reaching into features.

### CanvasWidgetFeature

The **master contract** for any canvas feature. It declares:
- How to handle state changes → `reduce_view_state()`, `reduce_render_config()`
- What commands are available → `build_commands()`
- What properties can be animated → `build_properties()`
- How to update the toolbar → `build_toolbar_bindings()`
- How to read/write state directly → `build_state_queries()`, `build_state_commands()`

**Why it exists**: Without this contract, each feature would invent its own way to report its state and commands. The toolbar would have special cases for each feature. Settings would need custom serialization logic per feature.

**How it's used**: `widget_registry.py` auto-discovers all `CanvasWidgetFeature` instances and builds central registries of properties, commands, and toolbar bindings.

### CanvasSceneFeature

Separate from widget contract because not all features participate in scene-graph operations. Only features that need hit-testing, z-ordering, or dynamic visibility need this.

Declares:
- How to build scene objects → `build_primary()`, `build_overlay()`
- How to apply state to the viewport → `apply()`
- Hit-test implementation → `hit_test()`

**Why separate**: Some features are pure rendering (filename overlay) and don't need scene objects. Some are interaction-heavy (magnifier) and need both scene and widget contracts.

### CanvasFeatureProperty

A feature says: *"I have a property called 'size' that users can edit. Here's how to read/write it from snapshots, serialize it to settings, and describe it for the video editor."*

**Why it matters**: Properties are the ground truth for:
- Settings persistence (`serialize_setting`, `deserialize_setting`)
- Video editor keyframe tracks (`channels`)
- UI labels in settings dialogs (`label`, `group_label`)

**One place, many uses**: Instead of hardcoding size handling in settings, keyframes, and UI separately, each subsystem queries the property contract.

### CanvasFeatureStateQuery & CanvasFeatureStateCommand

Direct read/write access to feature state.

**Why**: Sometimes a feature needs to be queried or updated outside its usual command pathway. Example: the divider movement handler needs to read magnifier offset and spacing to recalculate geometry.

These allow: `query_feature_state(store, "magnifier", "active_state")` instead of `get_canvas_feature_command("magnifier", "get_active_state")`.

### CanvasFeatureToolbarBinding

Maps toolbar UI controls to feature command handlers.

Declares: *"When button 'btn_magnifier_size' slider changes, call my size command with the value."*

**Why separate**: Toolbar code doesn't know about features. Features declare their toolbar needs. The binding system wires them at runtime.

### CanvasFeatureContextMenuZone

A feature declares geometric territory where the host must not open a slot/image context menu.

Declares: *"On my combined magnifier overlay, all host context menus go away — I own RMB there."*

**How**: `WIDGET_FEATURE.build_context_menu_zones` → `CanvasFeatureContextMenuZone(zone_id, suppresses(ctx), priority)`. Shared canvas `contextMenuEvent` asks `is_context_menu_suppressed(ContextMenuHitContext)` before opening a menu. No feature literals in the canvas widget.

**Why**: Same reason as gesture bindings — RMB routing for overlays must not hard-code magnifier (or future feature) hit geometry in shared canvas code.

### CanvasFeatureCommandAlias

Maps capability names (e.g., `"render.layout_requirement"`) to features that implement them.

**Why**: Shared code needs to call features without importing them. Instead of:
```python
# Bad: requires direct feature import
from canvas_features.magnifier.commands.viewport import viewport_set_size
```

Do this:
```python
# Good: query by capability alias
cmd = get_canvas_feature_command_by_alias("magnifier.set_size")
if cmd:
    cmd(store, value)
```

### CanvasFeatureZOrder

Specifies z-ordering via `stack_role` instead of hardcoded `layer` and `priority` integers.

**Why**: Different features need different ordering rules (magnifier over divider, guides under magnifier). The stacking policy centralizes these rules instead of scattering magic numbers.

## QRhi Rendering (The Performance Problem)

Canvas features render via QRhi, not CPU. This raises questions about visibility and performance.

### CanvasRenderPass

Declares: *"I have a render pass that draws on the canvas. Here's how to initialize it, detect if I have anything to draw, and clean up."*

Specifies:
- `stack_role`: Where in the render order (using central stacking policy)
- `visibility`: When to run (interactive only? export? preview?)

**Why**: Each feature can have multiple render passes (magnifier has content, border, laser). Without a contract, the renderer would need hardcoded knowledge of each pass.

### SceneVisibility & RenderPhase

Enums that avoid magic numbers and implicit assumptions.

**SceneVisibility problem solved**: Should a guide line render in video export? In preview? This flag makes it explicit instead of scattered `if` statements checking the mode.

**RenderPhase problem solved**: Instead of "render magnifier at layer 20", features declare their semantic role: `VIEW_ANNOTATION`, `IMAGE_ANNOTATION`, etc. The stacking policy owns the actual layer numbers.

## Viewport & Interaction (The Geometry Problem)

Magnifiers, dividers, and other overlays require complex geometric calculations (split position, zoom, pan).

### DisplaySplitPositionRequest & SplitPositionForViewTransformRequest

Encapsulate the inputs needed to calculate split line position under different conditions.

**Why**: Without these, code would pass 10+ scattered parameters to geometry functions. The request object documents what information is required and why.

### WheelZoomRequest & PanDragRequest

Similar: encapsulate mouse interaction parameters.

**Why**: Keeps geometry calculation pure. The canvas captures a request, passes it to handlers. Handlers return new position/zoom without side effects.

### OverlayMovementHandler

Protocol that magnifier implements for handling geometry changes.

**Why**: Divider movement needs to recalculate spacing, offset, and combined state. Rather than hardcode magnifier logic in divider code, divider requests the movement handler and calls its methods.

## Layout Contract (The Export Problem)

Magnifiers extend beyond image bounds. Dividers shift content. What should the export size be?

### NormalizedBounds & FeatureLayoutRequirement

Each feature declares: *"In normalized image coordinates (0-1), here's what space I need."*

**Why**: Export resolution depends on feature bounds. Without this contract, export code would need to know about every feature and calculate its bounds specially.

### VirtualCanvasLayout

Unions all feature requirements to get the final virtual canvas size.

**Why**: Export path, zoom/pan, and video editor all need the same layout information. This contract ensures they use the same calculation.

## Canvas Widgets (The Rendering Backend Problem)

Multiple renderers (QRhi, QPainter, export offscreen) need a common interface.

### BaseCanvasProtocol, GlLikeCanvasProtocol, ExportCanvasProtocol

(`GlLikeCanvasProtocol` names the live QRhi canvas widget protocol.)

Duck-typing protocols that let code call a canvas without knowing its concrete type.

**Why**: Presenter code, feature code, and export code all call canvas methods. Without a protocol, each canvas implementation needs to implement a large interface correctly or risk crashes.

**Example**: `set_feature_overlay_gpu_params()` is called by multiple features. The protocol ensures all canvas types implement it.

## Tabs (The Workspace Problem)

The app supports multiple tabs (image compare, video compare, future tabs).

### TabContract

Declares: *"A tab is a self-contained mini-app. Here's how to create it, handle drops, and notify it of lifecycle events."*

**Why**: Main window doesn't know about specific tabs. Tabs register themselves. Main window treats all tabs uniformly.

## Keyboard Navigation (The Focus Problem)

The app's keyboard cursor is the toolkit's section graph, not Qt focus: an
arrow key is routed to the `NavigationSection` whose `owns()` accepts the
focused widget (`src/core/navigation.py` re-exports the singleton), and a
control no section claims is unreachable by the app's own keyboard model
even when `Tab` can land on it.

### NavigationManager

Declares: *"Name the owner of each navigable surface once. Arrows route
through the registry; focus arrival is not activation."*

**Why**: arrow consumption on `QApplication` has exactly one owner, so no
widget may silently eat Up/Down and strand the keyboard cursor.

A tab participates through its lifecycle hooks:

- **Registration.** `src/tabs/image_compare/tab.py:315` and
  `src/tabs/image_gallery/tab.py:247` call
  `declare_toolbar_navigation(...)` (`src/tabs/host_helpers.py:34`) on
  activation, with toolbar *container* rows (not bare controls), then
  unregister on deactivation (`src/tabs/image_compare/tab.py:333`).
- **One owner per section.** A surface may be claimed by exactly one
  section; overlapping `owns()` makes arrow routing ambiguous. A second
  surface gets its own registration — the gallery adds the grid after the
  toolbar (`src/tabs/image_gallery/tab.py:247-271`).
- **Ordering is the graph.** Registration order defines the neighbours
  `focus_first` / `focus_last` / `focus_nearest` hand off between, which is
  why the gallery documents toolbar-above / grid-below explicitly
  (`src/tabs/image_gallery/tab.py:260`). Hand-offs move the cursor only.
- **Enter activates.** Focus arrival never does: the tab strip switches on
  Enter/Space and explicitly not on a Down/Up hand-off
  (`src/core/navigation_sections.py:245`), and toolkit buttons fire on
  Space/Return/Enter. Value controls additionally gate editing behind an
  explicit Enter.
- **Canvas keys stay separate.** `TabContract.consumes_canvas_key_events()`
  (`src/tabs/contract.py:258`) defaults to `False`; a tab that opts in gets
  its canvas keys re-emitted as signals instead of routing them through the
  section graph.

**Preview flyouts are deliberately outside the graph.** Transient hover /
keyboard-peek panels open with `grab_focus=False` and
`register_nav_section=False` — see
`src/tabs/image_compare/ui/transient_magnifier.py:124` and
`src/tabs/image_compare/ui/magnifier_settings_flyout.py:369`. Do not "fix"
that `False` into `True`: it keeps Down/Up walking the parent toolbar rows
instead of entering a panel that disappears on hover-out, and the parent
section keeps ownership of the arrows. Enter is the explicit act that admits
keyboard navigation into the panel
(`src/ui/widgets/panel_visibility_flyout.py:47`). Only an interactive
opening — focus grab plus a registered flyout section — joins the graph.

Canonical long guide (sibling private docs repo, path only):
`improve-imgsli-internal-docs/docs/dev/KEYBOARD_NAVIGATION.md`.

## Core Events (The Notification Problem)

### Event Protocol

Base protocol for all events. Lets code emit/listen to events without knowing concrete event types.

**Why**: Decoupling. Magnifier doesn't import video editor code. Video editor listens to magnifier events through the event bus.

## Settings Persistence Contract (The Storage Problem)

Every value a user can change in the UI (theme, UI scale, font mode, RHI
backend, divider thickness, …) must reach the long-term config (QSettings)
with an **explicitly declared type**, and the load/save surface must be a
**full pass**: nothing saved without a typed load, nothing loaded without a
save, nothing in the store that a reducer can mutate without a persistence
path.

Enforced by:

- `tests/contracts/test_settings_persistence_contract.py` — static AST
  dogmas (no runtime).
- `tests/runtime/test_settings_full_pass.py` — behavioral full pass: every
  typed setting survives `save_all_settings -> load_all_settings` as a
  fixpoint, plus the out-of-band JSON blob and the bootstrap application of
  persisted values to the process-wide singletons.
- `src/tabs/image_compare/tests/plugins/test_settings_full_pass.py` — the
  canvas-feature half of the sweep (every property with a `setting_key`
  roundtrips `serialize -> write -> read -> deserialize` as a fixpoint).

The scanners that define the surface live in
`tests/contracts/_framework.py` (`settings_load_pairs`,
`settings_save_keys`, `settings_incremental_save_keys`,
`store_settings_field_names`) and are shared by the contract and the
runtime sweep so they cannot drift apart.

### Dogma 1 — Explicit types

Every load in `SettingsManager.load_all_settings` calls
`_get_setting(key, default, TYPE)` where `TYPE` is a literal
`str | int | float | bool`. A missing type is an implicit, guessed-format
roundtrip.

### Dogma 2 — Full-pass pairing

The keys loaded in `load_all_settings` are exactly the keys saved in
`save_all_settings` (both directions). A setting that is only saved
incrementally (or only loaded) drifts or resets between sessions.

### Dogma 3 — Store coverage and the explicit transient/persistent manifests

Every field of `SettingsState` (the only state a settings control can
mutate through reducers) must be persisted — with one of three explicit
declarations, nothing falls through implicitly:

1. **Scalar pass** — typed `_get_setting` + `_save_setting` in
   `SettingsManager` (the normal case).
2. **Out-of-band blob** — a dedicated `_load_<name>` / `_save_<name>`
   helper pair wired into both master passes. Current manifest:
   - `keyboard_overrides` — `action_id -> chord` map, saved as JSON.
3. **Explicitly transient** — declared in `TRANSIENT_STORE_SETTINGS` in
   `tests/contracts/_framework.py` **with a reason**, because the value is
   session-scoped by design. Current manifest:
   - `export_resolution_scale` — per-export resolution scale, recomputed
     from the export dialog for each export; not a user preference.

Adding a store field without wiring one of these three paths fails the
contract — this is the "no implicit controls" guarantee: a control that
changes a value it never persists is structurally impossible.

### Dogma 4 — Apply path uses a single full-snapshot writer

The settings file is only ever written as a **coherent snapshot of the
Store**: `SettingsApplicationService.apply()` mutates the store via
`Set*Action` dispatches and ends by calling `_schedule_persist()`, which
debounces a full `save_all_settings(store)` (typed loads ⇄ full save stay
paired — see the persistence-contract tests). **No apply-path method may
call the incremental `_save_setting`**: a partial write derived from
dialog-widget state can silently overwrite good values with the widget's
defaults (observed reset: `ui_mode` → beginner, `ui_scale_factor` → widget
default, `rhi_backend` → default, written on a settings OK with no log).
The low-level `_save_setting` remains only for direct single-key writers
outside the apply path (video-editor dirs/favorites, first-run flag) whose
value is simultaneously stored in the Store. Full mechanics and a
troubleshooting guide: [SETTINGS_PERSISTENCE.md](SETTINGS_PERSISTENCE.md).

### Dogma 5 — Mutation service requires a key

Every call site of `set_viewport_value` / `set_settings_value` /
`set_viewport_color` must pass an explicit `setting_key`. A mutation
without one changes state that never reaches the config.

### Dogma 6 — Canvas-feature properties

Every canvas-feature property declaring a `setting_key` declares its kind
(`bool` / `scalar` / `color` / `enum`) and must be a
save->load fixpoint: the raw value written into QSettings comes back out
unchanged, for defaults and mutations alike. A drift means the declared
kind does not match the real serializer format.

**Range discipline**: values a control can produce must survive the full
pass. When a load path clamps (e.g. `text_alpha_percent` — the font flyout
opacity slider and the feature property both clamp to `5..100`), the
saving side must clamp to the same range so save->load is a fixpoint;
`tests/runtime/test_settings_full_pass.py` keeps an explicit
`_RANGE_SAFE_VALUES` manifest for such fields.

## Store→Widget Sync Contract (The Restart Problem)

Every Store flag a user can flip (toolbar toggles, label switches, …) must
reach **every** widget projection (panel visibility, button state, …) on
**every** sync path: live dispatch, deferred/background-tab branch, tab
switch, and post-restore. A Store flip that moves the panel but not the
button (observed: labels on after restart while the toolbar button stayed
off) is a desync, not a cosmetic lag.

Sync vocabulary convention (what the dogmas scan — use these names so any
tab is covered automatically, no per-tab special cases):

- entry points: `handle_store_domain` / `apply_initial_state` /
  `apply_host_session_mode`;
- visibility moves: `setVisible` or `toggle_*_visibility`;
- toolbar fanout: `update_toolbar_states` (toolbar-presenter fanout entry),
  `sync_state` / `get_feature_toolbar_bindings` (shared binding API),
  `refresh_*toolbar` (post-restore re-sync, must return `bool`).

Rules:

1. **Fanout symmetry** — a branch that moves one projection moves all of
   them. No visible-branch-moves-panel / deferred-branch-moves-both splits.
2. **No silent swallow** — sync helpers never `except Exception: pass` /
   `return None` around a sync decision. A missed sync (no presenter
   reachable during early-bootstrap restore, dispatch failure) logs a
   warning and reports `False`; narrow guards (`except RuntimeError` for
   torn-down widgets, probes) are out of scope.
3. **Store-first reveal** — code that reveals chrome (Find Action, flyouts)
   flips the SSOT flag via `dispatch(Set*Action)` first; direct widget
   forcing is last-resort only and self-heals on the next emit.

Enforced by:

- `tests/contracts/test_store_projection_symmetry_contracts.py` — static AST.
- `tests/contracts/test_sync_no_silent_swallow_contracts.py` — static AST.
- `tests/contracts/test_render_config_roundtrip_contracts.py` — every
  `RenderConfig` field has a reducer branch and a persistence roundtrip.
- `tests/contracts/test_deferred_restore_close_loop_contracts.py` — every
  deferred restore callback carries retry/re-sync.
- `src/tabs/image_compare/tests/runtime/test_store_projection_roundtrip.py` —
  behavioral roundtrip (dispatch → both branches → post-restore).

## UI Scale Contract (The DPI Problem)

Chrome geometry (widget sizes, minimums, margins, spacings, icons placed by
layout) is authored in **design px** and multiplied by `UiScale` at exactly
one boundary — `scaled_px(...)` or `UiFont` — so a live scale change moves
every surface together. A raw literal that never reaches that boundary, or a
value that reached it too early, keeps the old design size while the rest of
the UI rescales (the "plain px instead of `scaled_px`" class: chips, flyouts
and dialogs stranded at design px after a scale change).

Rules:

1. **Per site, not per file** — a module that scales one geometry does not
   license raw literals elsewhere in it. The gate scans each site; there is no
   whole-file skip for files that merely mention `scaled_px`/`ui_font`.
2. **No import-time bake** — a module/class-level constant or a default
   argument that calls `scaled_px(...)` is evaluated once at import and frozen
   at that factor. Resolve geometry at call time (a helper that reads the
   current factor) instead.
3. **No double scaling** — toolkit APIs whose `size=` is already a design-px
   channel (`Button(size=...)`, overlay `show_popup(size=...)`, bubble
   `show(size=...)`) scale internally; pass plain design px, never
   `scaled_px(...)`. `scaled_px(scaled_px(x))` and helper-mediated repeats
   drift with `factor^2`.
4. **Sentinels are not design px** — `0`, `1` and `16777215`
   (`QWIDGETSIZE_MAX`) are structural layout values and are never flagged.
5. **Exceptions carry a reason** — image-space geometry (canvas widget
   minimums, QIcon raster requests) is listed per site in the gate's
   `EXEMPTED_SITES`/`EXEMPTIONS` with a reason. The counts are exact: a new
   identical literal fails the gate, and a fixed site fails until its
   allowance is lowered in the same commit.

Enforced by:

- `tests/contracts/test_no_raw_chrome_px.py` — per-site AST ratchet over
  import-time `scaled_px` bakes, raw literals in
  `setFixed*`/`setMinimum*`/`setMaximum*`/`resize`/`QSize`/
  `setContentsMargins`/`setSpacing`, and `scaled_px` into self-scaling
  `size=` kwargs, with seeded exact-count exemptions and falsification tests.
- `tests/contracts/test_no_double_scaled_px.py` — nested `scaled_px(...)`
  calls in one expression.

## Design Principles Behind These Contracts

These are the **architectural** sense of contract — isolation rules that
interface registration alone does not enforce. CI encodes many of them as
AST dogmas in `tests/contracts/` (see [TESTING.md](TESTING.md)).

1. **No direct imports of features in shared code** — Use contracts/aliases instead
2. **Auto-discovery** — Features register, subsystems discover them
3. **Graceful degradation** — Missing feature? The app still works, just doesn't respond to that feature's commands
4. **Immutable contracts** — Contracts are frozen dataclasses, can't be modified at runtime
5. **Composition over inheritance** — Features build combinations of contracts, not inherit from a base class

## Related Documentation

- [rendering/index.md](rendering/index.md) — Detailed guide to adding new canvas features
- [ARCHITECTURE.md](ARCHITECTURE.md) — Overall app architecture
- [tabs/index.md](tabs/index.md) · [tabs/contract.md](tabs/contract.md) — workspace tabs / `TabContract`
- [rendering/contracts.md](rendering/contracts.md) — canvas feature field catalog
- [rendering/render-pass-contract.md](rendering/render-pass-contract.md) — QRhi pass lifecycle
- [TESTING.md](TESTING.md) — architectural AST dogmas vs behavior tests
- [CAPABILITY_ALIASES.md](CAPABILITY_ALIASES.md) — command/property aliases without direct imports