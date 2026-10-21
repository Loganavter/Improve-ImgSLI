# TabContract & TabContext

**Interface** contract for workspace tabs. Broader glossary (interface vs host
call sequence vs architectural dogma):
[CONTRACTS.md](../CONTRACTS.md#three-senses-of-contract).

Implementation: `src/tabs/contract.py`. Three members are abstract; every other
hook below has a working default, so a tab overrides only what it needs.

## TabContract (ABC)

### Required (abstract)

```python
from tabs.contract import TabContract, TabContext

class MyTab(TabContract):
    @property
    def session_type(self) -> str:
        """Unique session type identifier, e.g., 'multi_compare'."""

    @property
    def display_name(self) -> str:
        """Name used for menus and tooltips — fallback for localized_display_name."""

    def create_page(self, parent: QWidget, context: TabContext) -> QWidget:
        """Create and return the root page widget."""
```

`create_page` is **lazy**: `TabRegistry.install_pages()` only records the tab as a
pending page, and the widget is built on the tab's *first activation*
(`tabs/use_cases/pages.py` `_ensure_page` → `_create_and_assemble_page`, called
from `tabs/use_cases/session_lifecycle.py` `activate`). The page is added to
`workspace_stack` and then kept for the app's lifetime — hidden by
`setCurrentWidget`, dropped only by `TabRegistry.dispose_all()`.

### Identity, discovery, i18n

| Member | Default | Host use |
|---|---|---|
| `localized_display_name(language)` | `display_name` | Tab-strip title (`ui/main_window/ui.py`). Tabs that own i18n override it — the host never keeps a session-type → title map |
| `icon` | `None` | Session-picker cards, through the host `get_tab_icon` service |
| `resources_dir` | `None` | Tab-owned icons/qss; its `i18n/` subtree is auto-registered by discovery |
| `i18n_namespace` | `None` | Prefix for the tab's keys; also the contribution owner id (`owner_tab`, falling back to `session_type`) for settings/help catalogs |
| `extra_i18n_roots()` | `[]` | `tabs/use_cases/discovery.py` registers each existing dir — for **nested** packages that own i18n (image_compare registers `plugins/video_editor/resources/i18n`) |
| `startup_tier` | `"deferred"` | `tabs/use_cases/discovery.py`; a typo fails at import time (`__init_subclass__` validates `bootstrap` / `deferred`) |
| `is_bootstrap_default` | `False` | Reserved exclusively for `session_picker` (`TabRegistry._bootstrap_default_tab()` raises for anyone else) |

### Transition hint

```python
@dataclass(frozen=True)
class TabTransitionHint:
    cover_on_enter: bool = True
    min_duration_ms: int = 50
    max_duration_ms: int = 300
```

`transition_hint()` is called on **every** tab switch
(`ui/presenters/main_window/workspace.py` `_cover_transition_for_session`): the
host covers the stack with `WorkspaceTransitionMask` while the new page paints.
The mask stays at least `min_duration_ms` and is hidden no later than
`max_duration_ms`. A tab that wants the cover gone as soon as its first valid
frame exists calls `context.services["workspace.transition_mask"].release()`
(image_compare does this from its widget). Missing the deadline is logged as a
contract violation, and raises `TabTransitionContractError` in strict mode
(`ui/main_window/workspace_transition_mask.py`). Tabs whose first paint is
genuinely cheap set `cover_on_enter=False` rather than racing the deadline.

### Session lifecycle

| Member | Called from |
|---|---|
| `on_activated` / `on_deactivated` | `tabs/use_cases/session_lifecycle.py` — tab **type** becomes / stops being visible |
| `on_active_session_changed` | Same-type session switch (IC→IC, MC→MC) while the tab stays visible; use for per-session apply |
| `on_session_created` / `on_session_closed` | `tabs/use_cases/session_persistence.py`, after the store changed |
| `can_close_session(session_id, context)` | **Nothing yet** — the veto point is named but no host close path consults it (`SessionManager.close_session` → `Store.close_workspace_session` still notifies post-facto via `on_session_closed`). Default `True` (fail-open); do not build a dirty-guard on it until the host is wired |
| `accepts_drop(paths)` / `handle_drop(paths, hint=)` | `TabRegistry.route_drop` from the window event handler |
| `dispose()` | `TabRegistry.dispose_all()` at shutdown |

### Host-driven repaint and teardown

These exist so the host never reaches into tab widgets by attribute name:

| Member | Called from |
|---|---|
| `apply_appearance(host_window)` | `tabs/use_cases/appearance.py` — theme flip, with the hidden-page stale-flush (`_appearance_stale`) |
| `on_window_shutdown(host_window)` | `TabRegistry.notify_window_shutdown` — stop tab-owned timers/threads |
| `on_resize_settled(viewport_state)` | `ui/main_window/runtime.py` — reposition overlays/placeholders after a resize |
| `on_host_revealed()` | `ui/main_window/startup.py` — the window became visible after startup |

### Persistence

| Member | Contract |
|---|---|
| `serialize_session(session_id, context)` | JSON-able snapshot for project save, or `None` (tab omitted from the save — `session_picker`) |
| `collect_pixel_cache_sources(session_id, context)` | `{abs source path: live TiledPixelStore}` for the opt-in embedded pixel cache — see [CONTAINER_FORMAT.md](../CONTAINER_FORMAT.md) |
| `deserialize_session(session_id, data, context)` | Restore into an already-created session (slots already hold blueprint defaults — overwrite, don't assume empty) |
| `rehydrate_session(session_id, context)` | Re-decode runtime media after `deserialize_session` |
| `duplicate_session(source_session_id, context)` | Snapshot used to clone a session; defaults to `serialize_session` |
| `create_default_session_data()` | Per-session `SessionData` factory, registered per tab during discovery (`tabs/use_cases/discovery.py`); `None` = the core comparison default |

### Canvas

`get_canvas_geometry_provider()` is the single growth point: it returns the tab's
`CanvasGeometryProvider` (`ui/canvas_infra/viewport/contract.py`) or `None`.
`owns_widget`, `get_canvas_size`, `map_global_to_canvas_local`,
`get_canvas_content_rect_px` and `get_canvas_zoom_pan` are concrete forwarders —
do not override them. `consumes_canvas_key_events()` tells the app-wide event
filter (`events/router.py`) whether to reroute key events as
`canvas_keyboard_press_event_signal` / `..._release_event_signal` instead of
normal Qt delivery (default `False`). `register_canvas_features()` runs during
discovery so a tab registers its own canvas feature packages without the host
importing them.

### Transitional host-page seam

Called while parts of the legacy main-window shell still live outside the tab
page (`tabs/use_cases/pages.py`, `ui/main_window/ui.py`):

- `assemble_host_page(ui) -> bool` — finish page assembly from host-owned
  primitives; re-run when a page is created lazily and when the host assembles
  its pages;
- `finalize_host_page(ui)` — one-time cosmetic pass over the tab's own chrome
  once the shell exists (active tab only; others on first show);
- `apply_host_session_mode(ui, session_title=None) -> bool` — apply host chrome
  state when the tab becomes active.

`image_compare` implements all three; a tab that owns no legacy primitive leaves
the defaults (`False` / no-op).

### Capability mechanisms

`create_service(service_id, *args, **kwargs)` and
`create_main_window_feature(feature_id, **kwargs)` are string-ID hooks resolved
by the registry — see [capability-mechanisms.md](capability-mechanisms.md). They
are not the whole story any more: the typed families above (transition hint,
canvas provider, extra i18n roots, session-data factory, host-page assembly)
exist precisely because a string ID would have been an untyped, easily
mis-routed answer.

### Not wired

`on_quick_save(context)` has no host caller and no implementor — the quick-save
button is tab-local (`image_compare/presenters/toolbar/connections.py`,
`multi_compare/controller.py` `_on_quick_save_requested`). Do not build on it;
it is a deletion candidate.

## TabContext

The context is passed to all lifecycle methods and to `create_page`. It provides
access to services without requiring direct imports:

```python
class TabContext:
    store         # Global application state
    event_bus     # Event bus
    thread_pool   # Thread pool for background tasks
    main_window   # Reference to the main window
    settings      # Live `store.settings` (not a bootstrap snapshot)
    services      # dict of 10 host services — see capability-mechanisms.md §TabContext.services

    def get_active_session(self) -> Any
    def _tr(self, key: str, default: str | None = None) -> str
    def _tr_lang(self, key: str, language: str) -> str
    def call_service(self, service_id: str, *args, **kwargs) -> Any
```

`_tr` translates with the **live** app language; `_tr_lang` translates for an
explicit language and is the `(key, language) -> str` shape the toolkit's
`install_translator` fan-out expects (image_gallery's widget uses it). There is
no public `tr` — `context.tr(...)` does not exist.

`settings` always reads the current `store.settings` object. The Redux settings
reducer replaces that object on language/theme/etc. changes; a one-time
reference captured at `install_pages` would freeze the startup language and break
dynamic `tr()` (e.g. Session Picker after Apply).
