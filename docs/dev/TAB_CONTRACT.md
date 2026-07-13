# Tab Contract

The tab system allows adding new operation modes to the application without modifying the core codebase. Each tab is a self-contained mini-module with its own resources, translations, and state.

## File Structure

```
src/tabs/<tab_name>/
    __init__.py
    tab.py              # TabContract implementation
    controller.py       # Tab logic
    widget.py           # UI widget
    models.py           # Data models (optional)
    resources/
        i18n/
            en/<namespace>.json
            ru/<namespace>.json
        icons/          # (optional)
    tests/
        __init__.py
        contracts/      # Structural dogmas (AST-based)
        render/         # Rendering pass contracts
        runtime/        # Lifecycle and state contracts
        plugins/        # Plugin-specific contracts
        video/          # Video editor contracts (image_compare only)
        conftest.py     # Shared fixtures for this tab's tests (optional)
```

Currently registered tabs: `tabs/image_compare/` (primary two-image comparison —
full canvas, overlays, guides, capture circles, split view, video editor
integration), `tabs/multi_compare/` (grid-layout multi-image comparison,
composition-aware rendering), `tabs/session_picker/` (workspace session
browser/switcher).

## TabContract (ABC)

```python
from tabs.contract import TabContract, TabContext

class MyTab(TabContract):
    @property
    def session_type(self) -> str:
        """Unique session type identifier, e.g., 'multi_compare'."""

    @property
    def display_name(self) -> str:
        """Name used for menus and tooltips."""

    @property
    def icon(self) -> QIcon | None:
        """Icon for the session creation menu. Returns None for no icon."""

    @property
    def resources_dir(self) -> Path | None:
        """Path to tab resources. Returns None if there are no resources."""

    @property
    def i18n_namespace(self) -> str | None:
        """Translation namespace prefix. Files are located in resources/i18n/<lang>/<namespace>.json."""

    @property
    def is_bootstrap_default(self) -> bool:
        """True for exactly one tab — see "Bootstrap seam" below. Default False."""

    def create_page(self, parent: QWidget, context: TabContext) -> QWidget:
        """
        Creates the root page widget.
        Called once during application startup.
        The returned widget is added to the workspace_stack.
        """

    def on_activated(self, context: TabContext) -> None:
        """Called when switching to this tab."""

    def on_deactivated(self, context: TabContext) -> None:
        """Called when switching away from this tab."""

    def accepts_drop(self, paths: list[Path]) -> bool:
        """Returns True if the tab accepts the dropped files."""

    def handle_drop(self, paths: list[Path]) -> None:
        """Processes the drop. Called only if accepts_drop returned True."""

    def on_session_created(self, session_id: str, context: TabContext) -> None:
        """Notification that a session of this type was created."""

    def on_session_closed(self, session_id: str, context: TabContext) -> None:
        """Notification that a session of this type was closed."""

    def dispose(self) -> None:
        """Cleanup performed when the tab is unloaded."""

    def create_service(self, service_id: str, *args, **kwargs) -> Any:
        """See "Capability mechanisms" below. Base implementation returns None."""

    def create_main_window_feature(self, feature_id: str, **kwargs) -> Any:
        """Legacy, single-ID hook — see "create_main_window_feature" below."""

    def get_canvas_geometry_provider(self) -> CanvasGeometryProvider | None:
        """See "CanvasGeometryProvider" below. Base implementation returns None."""
```

`TabContract` intentionally stays small and stable: lifecycle hooks plus the
two capability-mechanism hooks above. **Nothing else gets added here.** A new
host↔tab wiring need goes through one of the two mechanisms in "Capability
mechanisms" below, never through an 11th single-purpose abstract method.

## TabContext

The context is passed to all lifecycle methods. It provides access to services without requiring direct imports:

```python
class TabContext:
    store         # Global application state
    event_bus     # Event bus
    thread_pool   # Thread pool for background tasks
    main_window   # Reference to the main window
    settings      # Application settings
    services      # dict — see "tab → host: TabContext.services" below

    def get_active_session(self) -> Any
    def tr(self, key: str, default: str | None = None) -> str
    def call_service(self, service_id: str, *args, **kwargs) -> Any
```

## TabRegistry

The registry automatically discovers all tabs at startup:

1. Scans `src/tabs/` using `pkgutil`.
2. For each sub-package, it imports `tabs.<name>.tab`.
3. Locates subclasses of `TabContract`.
4. Creates instances and registers them by `session_type`.

Packages with a `_` prefix are ignored. The `contract` and `registry` modules are skipped.

`TabRegistry` is a **process-wide singleton** (`tabs/registry.py`, `__new__`)
— strict active-tab routing (below) only makes sense if `_active_session_type`
is a single, consistent value everywhere. `discover()` is idempotent (no-op
if tabs are already registered), so the many defensive
`TabRegistry(); registry.discover()` call sites scattered through the
codebase don't reconstruct live tab state from under the running app.

### Registry API

```python
registry = TabRegistry()
registry.discover()                                   # Auto-discovery
registry.install_pages(stack, context)                # Create pages in QStackedWidget
registry.get_page(session_type) -> QWidget             # Retrieve page by type
registry.activate(session_type)                        # Notify activation
registry.activate_default()                             # Activate the is_bootstrap_default tab
registry.deactivate(session_type)                       # Notify deactivation
registry.route_drop(session_type, paths)                # Route drag-and-drop
registry.create_service(service_id, *args, **kwargs)    # Active-tab-only dispatch
registry.create_startup_service(service_id, *a, **kw)   # Bootstrap-default-tab-only dispatch
registry.create_main_window_feature(feature_id, **kw)   # Active-tab-only, legacy single-ID hook
registry.notify_all(hook_id, *args, **kwargs)           # Broadcast to every registered tab
registry.dispose_all()                                  # Cleanup
```

## Capability mechanisms

Beyond the lifecycle hooks above, tabs and the host exchange capabilities
through a small, fixed set of mechanisms. This section is both the design
rationale and the current, verified state of each mechanism — read it before
adding a new host↔tab wiring point.

### tab → host: `TabContext.services`

A small, fixed dict, injected once at startup (`ui/main_window/layouts.py`),
identical regardless of which tabs exist:

```python
context = TabContext(
    ...,
    services={
        "list_session_blueprints":  ...,
        "create_workspace_session": ...,
        "close_workspace_session":  ...,
        "show_help_dialog":         ...,
        "show_settings_dialog":     ...,
        "open_image_export_dialog": ...,
        "workspace.transition_mask": transition_mask,
    },
)
```

A tab calls one of these via `context.call_service(service_id, *args,
**kwargs)`. `call_service` **raises** `RuntimeError` if the ID isn't in the
dict — unlike the host→tab direction, there is no "gracefully unsupported"
case here, because every entry is offered identically to every tab, including
a hypothetical new one, with zero host changes. This *is* the platform
engine, in the VS Code sense: session lifecycle and standard dialogs, offered
identically to every tab, none of it named after `image_compare` concepts.
If a tab needs a platform capability that isn't here, add it to this dict
(session lifecycle / standard dialogs only — not a tab-specific concept), not
a new ad-hoc callback threaded through some other path.

### host → tab: `create_service` (the default mechanism)

The reverse direction: host code asks the tab whether it supports a
capability, by string ID:

```python
result = get_shared_tab_registry().create_service("some_capability_id", *args, **kwargs)
```

For anything session-scoped and low-frequency (settings sync, export wiring,
popup controllers, canvas commands, ...) — this is **the default; reach for
this first.** A tab implements an ID by adding one `elif service_id ==
"...":` branch inside its own `create_service` override — zero boilerplate
for tabs that don't. The base `TabContract.create_service` returns `None`.

**Resolution is strict, active-tab-only** (`TabRegistry.create_service`
resolves against `self._tabs[self._active_session_type]` — no iteration, no
fallback to another tab's answer). This was not always true: the mechanism
used to broadcast to every registered tab and return the first non-`None`
answer, which meant a tab that implemented nothing (`multi_compare`,
`session_picker`) silently fell through to `image_compare`'s implementation
— reading/mutating `image_compare`-shaped session state that doesn't exist
for other session types. One instance of this crashed outright
(`settings_viewport_application` → a reducer doing `replace(None, ...)` on a
`multi_compare` session's `render_cache=None`); others silently returned the
wrong tab's answer. Strict routing was adopted specifically to make that bug
class structurally impossible rather than relying on every tab author
remembering to add a session-type guard.

`create_startup_service` is a variant that resolves against the
**bootstrap-default** tab (`is_bootstrap_default = True`) instead of the
active one, for use during one-time startup shell construction
(`MainWindowComposer.compose()` builds the legacy shell — `UIManager`,
toolbar, layout manager, ... — once, synchronously, before the user's real
initial session is necessarily active). See `tabs/registry.py`'s docstring
on `create_startup_service` for the full ordering argument.

Both `create_service`/`create_startup_service` **catch and re-raise**
exceptions from the tab's implementation (logged first) — they do not
swallow errors; only an unrecognized ID silently resolves to `None`.

### host → tab: `notify_all` (broadcast, not session-scoped)

A distinct mechanism from `create_service`, for the minority of hooks that
are genuinely global broadcasts rather than session-scoped requests: every
registered tab needs its own chance to act, regardless of which one is
active. Two current call sites: `install_translations` (each tab binds its
own UI's translation signals at startup, not just the active one's) and
`refresh_startup_button_visuals` (cosmetic startup refresh every tab's page
should get).

```python
registry.notify_all("install_translations", ui)
```

Iterates every registered tab, calls `tab.create_service(hook_id, *args,
**kwargs)` on each. Return values are not collected — fire-and-forget by
design. One tab's hook raising is logged and swallowed per-tab; it does not
stop the others. **Do not** route anything that reads or mutates session
state through this — that must go through `create_service`, which resolves
only against the active tab. This is a deliberately different method name
from `create_service` (not a flag) so a call site can't silently pick the
wrong resolution strategy by forgetting an argument.

### host → tab: `create_main_window_feature` (legacy, do not extend)

A related, older hook for **legacy main-presenter-hosted features only.**
Currently exactly one ID is ever requested, `"image_canvas"`
(`ui/main_window/composer.py`), implemented only by `ImageCompareTab`.
Resolves active-tab-only, same as `create_service`. Do not add new IDs to
it — new capabilities go through `create_service`; this hook is transitional
and should shrink, not grow. The real fix (not yet done) is making the
`"image_canvas"` main-window feature request lazy — built on first
activation of whichever tab implements it, rather than unconditionally
during startup before any session/tab is active — which would remove the
need for a privileged bootstrap-default tab entirely. Out of scope until
someone picks up `ui/main_window/composer.py`'s startup sequence.

### host → tab: `CanvasGeometryProvider` (typed protocol, hot path)

The one exception to "everything new is a `create_service` ID": a typed
`Protocol` (`ui/canvas_infra/viewport/contract.py`), *not* on `TabContract`
itself, for the one cluster of methods that's cohesive and hot-path — called
every mouse move / key press by host-generic event routing
(`events/image_label/geometry.py`, `events/router.py`,
`events/app_event/keyboard.py`). String dispatch is unfit for a group of
methods that are always used together and need to be fast.

```python
class CanvasGeometryProvider(Protocol):
    def owns_widget(self, w) -> bool: ...
    def get_size(self) -> QSize: ...
    def map_global_to_local(self, p): ...
    def get_content_rect_px(self) -> QRect: ...
    def get_zoom_pan(self) -> tuple: ...
```

A canvas-owning tab implements the whole protocol once
(`tabs/image_compare/canvas_geometry_provider.py`,
`ImageCompareCanvasGeometryProvider`) and returns it from
`TabContract.get_canvas_geometry_provider()` — the single abstract-ish hook.
`TabContract` exposes concrete forwarding methods (`owns_widget`,
`get_canvas_size`, `map_global_to_canvas_local`, `get_canvas_content_rect_px`,
`get_canvas_zoom_pan`) that call the provider, so `geometry.py`/`router.py`/
`keyboard.py` never touch the provider directly and needed zero edits when
this mechanism was introduced. Non-canvas tabs (`session_picker`) never
implement anything: `get_canvas_geometry_provider()` returns `None` (base
default) and the 5 forwarders short-circuit to `False`/`None`/`(1.0, 0, 0)`.

**Do not add a second `Protocol` for some other cluster casually** — this
mechanism exists because canvas geometry specifically is hot-path and
cohesive. Anything else that looks reusable is `create_service` by default;
only promote to a typed protocol with an explicit decision, not by default.

### Bootstrap seam: `is_bootstrap_default`

The main-window shell is built once at startup, before any workspace session
exists for `sync_session_mode()` to `activate()`. During that narrow window
`_active_session_type` is `None`, and every `create_service`/
`create_main_window_feature` call would return `None` — which breaks the
legacy `"image_canvas"` feature the app unconditionally builds on startup.
Rather than hardcoding a tab name in generic startup code, `TabContract` has
an `is_bootstrap_default: bool` property (default `False`); exactly one tab
sets it `True`. `TabRegistry.activate_default()` finds that tab (logs an
error and no-ops if zero or more than one tab claims it) and activates it.
`ui/main_window/layouts.py` calls `activate_default()` without naming any
tab. `image_compare` currently sets `is_bootstrap_default = True` because it
is the only tab implementing `"image_canvas"`. **This is a stopgap**, not a
structural fix — see `create_main_window_feature` above for the real fix.

### Policy — when a `create_service`/`create_startup_service` ID is legitimate

A `service_id` is a real platform capability, not a smuggled tab-specific
method, only if all of these hold:

1. **The caller degrades gracefully on `None`.** `None` means "the active
   (or bootstrap) tab doesn't offer this" — a normal outcome for any tab that
   isn't the one that implemented it, not an error. `raise` on `None` is only
   legitimate for `create_startup_service` calls inherently tied to the
   bootstrap tab's *shell construction* (the shell itself doesn't exist
   without it) — and even then, that's a signal the capability probably
   belongs on `TabContract` as a real required hook, not behind a string.
2. **The shape is documented, not reverse-engineered.** If the ID returns an
   "extension object" other tabs would need to implement against, its
   expected method set must be written down next to the first call site.
3. **It answers a question or hands back one cohesive object — it is not a
   disguised setter for host-owned state.** Host code should query the tab,
   not command it to sync something host code had to already know the shape
   of.
4. **One call site per ID, or all call sites agree on the contract.** IDs
   called from exactly one place are lower risk. IDs with multiple callers
   need a documented Protocol/shape (rule 2) to stay coherent.

Two shapes satisfy this policy:

```
QUERY — "what's true right now":
    create_service("is_canvas_content_ready")
    create_service("session_has_content", store)
  Returns a primitive; None/False means "not applicable to this tab."

EXTENSION-OBJECT — "give me a small opaque controller once, I'll talk
only to it from now on" (the real contribution-point pattern):
    create_startup_service("popup_close_extension", manager)
      -> ImageComparePopupClosing(manager, widget)
         implementing: close_at_pointer(pos), hide_same_window(),
                        has_focus_inside(widget)
  Host code (ui/managers/transient_ui_parts/closing.py) never again
  mentions btn_diff_mode, btn_channel_mode, or any other button name —
  it only calls the interface it got back. This is the template for any
  new contribution-point-shaped need, not a pattern to invent from scratch.
```

Anything that exists only to let host code *push* a value or *command* a tab
to do something host code had to already know the shape of is the
anti-pattern, regardless of whether it's spelled as a method or a string ID.

### Decision rule for a new capability need

```
Is it canvas-geometry-shaped AND hot-path (called every frame/event)?
  yes -> extend CanvasGeometryProvider (rare — should almost never happen)
  no  -> is it a global broadcast (every tab needs its own chance to act,
         regardless of which is active, e.g. one-time startup wiring)?
           yes -> notify_all("new_hook_id", ...)
           no  -> does host code need to actively DO something to a
                  tab-owned widget/object (wire a signal, install an
                  event filter)?
                    yes -> create_startup_service/create_service returning
                           an EXTENSION OBJECT (policy rule 2/3)
                    no  -> create_service("new_id", ...) returning a
                           primitive/QUERY shape (policy rule 1)
```

Never add an 11th single-purpose abstract method directly on `TabContract`,
and never let host code reach into a tab's widget by attribute name
(`getattr(widget, "btn_x", None)`).

### Current status and known gaps

As of this writing:

- Every `create_service`/`create_startup_service`/`create_main_window_feature`
  ID in the codebase is implemented only by `ImageCompareTab`; `multi_compare`
  and `session_picker` implement none. Several call sites treat the result as
  mandatory (`raise RuntimeError(...)` on `None`) rather than degrading
  gracefully — a policy violation per rule 1 above, not yet fully cleaned up.
  This means the mechanism has never actually been exercised by a second
  implementor: "designed to be generic" and "proven generic" are not the same
  claim here. Verify, don't assume, before assuming a new ID "just works" for
  a non-`image_compare` tab.
- `multi_compare`/`session_picker` have no real (or deliberately-documented
  no-op) implementations for the session-scoped IDs they could plausibly be
  the active tab for (`canvas_widget_class`, `layout_manager`,
  `toolbar_presenter` are the live candidates if those tabs are ever meant to
  render their own canvas chrome). Not yet started.
- **No enforcement test exists yet** for "every `create_service(...)` call
  site's string literal is recognized by at least one tab's `create_service`
  override." A dangling/misspelled ID currently fails silently at runtime
  (`None`), not at test time. This is the biggest concrete gap in the
  mechanism as it stands today.
- `getattr(widget, "attr_name", None)` guards for tab-owned widgets have
  **not** been fully audited/removed. Confirmed still present (unaudited) in
  `tabs/image_compare/ui/popup_closing.py`,
  `tabs/image_compare/ui/transient_magnifier*.py`, and
  `ui/managers/transient_ui_parts/anchored_popup.py` /
  `closing.py`. For each: either the attribute is genuinely optional (leave
  the guard, document why) or it's a core widget attribute that must exist
  once `widget=` is correctly threaded (drop the default, let
  `AttributeError` propagate — see "No Implied Lookups" below).
  `ui/managers/ui_manager_parts/bootstrap.py`'s button-menu wiring (a
  historical instance of this same class of leak) has already been fixed —
  it no longer reaches into widgets by name; the wiring now lives in the
  tab-owned `ImageComparePopupClosing` extension object, obtained via
  `create_startup_service("popup_close_extension", ...)`.
- `notify_all` (the broadcast mechanism) and the `is_bootstrap_default`
  stopgap described above are both implemented and in active use — earlier
  drafts of this document described them as future work; that is stale.

## Event Routing

- **Page Switching**: `sync_session_mode(session_type)` checks the registry. If the type is found, it displays the tab's page and calls `activate()`.
- **Drag & Drop**: `WindowEventHandler` checks the active session. If its type is registered in the registry, it calls `registry.route_drop()`.
- **Visibility Settings**: Controlled via a checkbox in Settings > Appearance. The tab bar is hidden by default.

## Translations

Each tab stores its own translations in `resources/i18n/<lang>/<namespace>.json`. Keys are accessible via `context.tr("key")` or directly through the application's translation system after the namespace is registered.

## Tests

A tab owns its own tests, just like it owns its own resources. Any test that
imports `tabs.<tab_name>.*` — directly or via a lazy import inside a test
function — belongs under `src/tabs/<tab_name>/tests/`, not under the
top-level `tests/` tree.

```
src/tabs/<tab_name>/tests/
    __init__.py
    contracts/     # AST-scan dogmas specific to this tab's canvas features/passes
    render/        # Fake-context tests for this tab's render passes and scene
    runtime/       # Lifecycle/state contracts specific to this tab
    plugins/       # Tests for this tab's plugin-facing behavior (export, settings, ...)
    video/         # image_compare only — video editor contracts
```

Rules:

- Mirror the type-based subfolders (`contracts/`, `render/`, `runtime/`,
  `plugins/`, ...) used by the top-level `tests/` tree — see
  [TESTING.md](TESTING.md) for what each subfolder is for. This keeps the
  "one file — one topic" discipline even though tests are now split by tab.
- `sys.path` resolution for `src/` still comes from pytest's own rootdir
  package-insertion (every directory down to `tests/` has an `__init__.py`),
  not from `tests/conftest.py` — that conftest only applies to the top-level
  `tests/` tree. If a moved test used a `Path(__file__).parents[N]` trick to
  find the repo root, recompute `N` for the new depth
  (`src/tabs/<tab>/tests/<kind>/test_x.py` is 5 levels below repo root).
- Tests that exercise the tab **mechanism** itself — the registry, the
  `TabContract` ABC, generic drop-routing/dispose lifecycle — stay in
  `tests/contracts/` and `tests/runtime/` even if they instantiate one
  concrete tab as an example. Only tests whose assertions are actually about
  that tab's behavior move into its `tests/` folder.
- Run a single tab's suite the same way as any other pytest path:
  `pytest src/tabs/image_compare/tests/`.

## Isolation Rule: Do Not Borrow App-Level Keys or Theme Tokens

A tab is a self-contained module. Treat the host application's resource
namespaces as **private to the host** — they can be renamed, removed, or
restructured at any major update without warning to tabs.

**Do not, under any circumstances:**

- Reference i18n keys from the main app namespace (e.g. `app.*`, `main.*`,
  `common.*`, `settings.*`, anything outside your tab's own `<namespace>`).
  Even if a string looks identical to one in the host — copy it into your
  own JSON.
- Read QSS classes, theme colors, design tokens, or icon names from
  `src/shared_toolkit/` or the host's theming layer. If you need a color
  or icon, vendor it in `resources/icons/` or define it locally.
- Import constants, enums, or labels from `src/plugins/settings/`,
  `src/ui/...`, or any host-side UI module purely to reuse a string or
  a styling value.

**Why this matters.** The host app evolves on its own schedule:
translation keys get split, theme tokens get renamed, settings namespaces
get restructured. Nothing in the build or runtime guarantees that a
borrowed key still resolves after an upgrade — and the breakage is
silent (missing label shows the key string; missing color falls back to
black/transparent). Nobody on the host side will notice that a tab quietly
broke, because the host's own tests pass.

**The rule of thumb:** if you delete `src/resources/` and `src/shared_toolkit/`
entirely, your tab must still render its UI correctly (modulo the host
chrome around it). Everything visual or textual that your tab needs lives
under `src/tabs/<your_tab>/resources/`.

This isolation is part of the tab contract and is enforced by
`tests/contracts/test_tabs.py`, `tests/contracts/test_tabs_isolation.py` and
`tests/runtime/test_tabs_lifecycle.py` (see [TESTING.md](TESTING.md) §Каталог).
These three stay in the top-level `tests/` tree because they check the
registry/contract mechanism itself, not a specific tab's behavior — see
§Tests above.

## Dependency Wiring Rule: No Implied Lookups

When code needs a reference it doesn't already hold (a widget, a presenter,
a controller), there are exactly two acceptable ways to get it:

1. **It is passed in explicitly** by the code that owns/creates it — as a
   constructor argument, a method parameter, or an attribute set once by the
   owner at construction time.
2. **It is `self`'s own state**, set by `self` in its own `__init__`.

**It is never acceptable to reach for it indirectly** — i.e. to guess where
it lives and pull it out through a side channel:

- `some_registry.get("string_key")` / `legacy_tab_widgets.get("image_compare")`
  — a string-keyed lookup into a dict that some unrelated piece of code
  populated. The reader has no way to know the key is still valid, or that
  the dict still gets populated at all, six months from now.
- `getattr(obj, "attr_name", None)` used as a *substitute* for a real
  parameter, rather than as a genuine "this field is optional" check.
- Walking up through unrelated objects to find something
  (`self._widget._context.main_window.ui.some_attr`) instead of being handed
  that object directly by whoever constructed `self`.

**Why this matters.** A lookup-by-name or a walk-through-unrelated-objects
*looks* like a fix — it makes the immediate `AttributeError` go away — but it
just replaces one hidden dependency with another hidden dependency. The
reader (and the next refactor) still cannot tell, from the call site alone,
who is actually responsible for providing that value, or what breaks if the
provider changes shape. It is a "responsibility dump": passing the problem
of finding the right object from the true owner onto whichever piece of code
happens to need it later.

**The fix is always to trace real ownership.** Find the object that actually
creates/holds the thing you need (e.g. a tab's `self._widget` inside its own
`tab.py`), and have it hand that reference explicitly to whatever it
constructs or calls — through a constructor parameter or method argument —
all the way down the call chain. If that means threading a parameter through
several layers, that is the correct amount of code, not a sign to look for a
shortcut.

This applies everywhere in this codebase, not just to tabs — it is called
out here because tab/host wiring (`TabContract.create_page`, `TabContext`,
presenter construction via `create_service`) is exactly where the temptation
to "just grab it from the registry" comes up most often.

## How to Add a New Tab

1. Create a package in `src/tabs/<name>/`.
2. Implement the `TabContract` in `tab.py`.
3. Create the widget and controller.
4. Add translation files to `resources/i18n/`.
5. Add tests under `tests/` in the new tab's own `src/tabs/<name>/tests/` (see §Tests).
6. Done — the registry will pick it up automatically.

No changes are required in `main_window_ui.py`, `window_event_handler.py`, or other core files.
