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

## Core Events (The Notification Problem)

### Event Protocol

Base protocol for all events. Lets code emit/listen to events without knowing concrete event types.

**Why**: Decoupling. Magnifier doesn't import video editor code. Video editor listens to magnifier events through the event bus.

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

- [QRHI_CANVAS_FEATURES.md](QRHI_CANVAS_FEATURES.md) — Detailed guide to adding new canvas features
- [ARCHITECTURE.md](ARCHITECTURE.md) — Overall app architecture
- [tabs/index.md](tabs/index.md) · [tabs/contract.md](tabs/contract.md) — workspace tabs / `TabContract`
- [rendering/contracts.md](rendering/contracts.md) — canvas feature field catalog
- [rendering/render-pass-contract.md](rendering/render-pass-contract.md) — QRhi pass lifecycle
- [TESTING.md](TESTING.md) — architectural AST dogmas vs behavior tests
- [CAPABILITY_ALIASES.md](CAPABILITY_ALIASES.md) — command/property aliases without direct imports
