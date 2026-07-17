# Capability mechanisms

Beyond the lifecycle hooks on `TabContract`, tabs and the host exchange
capabilities through a small, fixed set of mechanisms. This section is both
the design rationale and the current, verified state of each mechanism — read
it before adding a new host↔tab wiring point.

## tab → host: `TabContext.services`

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
                "show_command_palette":     ...,  # Find Action / palette (query=, topic=)
                "open_image_export_dialog": ...,
                "get_tab_icon":             ...,
                "workspace.transition_mask": transition_mask,
    },
)
```

`get_tab_icon(session_type) -> QIcon` returns `TabContract.icon` for the
requested session type (empty `QIcon` if the tab has no icon). Used by
`session_picker` to render new-session cards without importing another tab's
`icons.py`. Implement `TabContract.icon` on tabs that appear in the picker
(e.g. `image_compare` → photo icon, `multi_compare` → grid icon).

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

## host → tab: `create_service` (the default mechanism)

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
fallback to another tab's answer). A missing implementation returns `None`;
it must not silently resolve to another tab's service. That keeps
session-scoped state typed to the active session type.

`create_startup_service` is a variant that resolves against the
**bootstrap-default** tab (`is_bootstrap_default = True`) instead of the
active one, for use during one-time startup shell construction
(`MainWindowComposer.compose()` builds the main-window shell — `UIManager`,
toolbar, layout manager, ... — once, synchronously, before the user's real
initial session is necessarily active). See `tabs/registry.py`'s docstring
on `create_startup_service` for the full ordering argument.

Both `create_service`/`create_startup_service` **catch and re-raise**
exceptions from the tab's implementation (logged first) — they do not
swallow errors; only an unrecognized ID silently resolves to `None`.

## host → tab: `notify_all` (broadcast, not session-scoped)

A distinct mechanism from `create_service`, for the minority of hooks that
are genuinely global broadcasts rather than session-scoped requests: every
registered tab needs its own chance to act, regardless of which one is
active. Current call sites: `install_translations` (each tab binds its
own UI's translation signals at startup, not just the active one's),
`refresh_startup_button_visuals` (cosmetic startup refresh every tab's page
should get), and `contribute_settings` (each tab may publish settings sections into the host
`SettingsRegistry`), and `contribute_help` (each tab may publish Help
subtrees into the host `HelpContributionRegistry` — see [HELP_SYSTEM.md](../HELP_SYSTEM.md)).

```python
registry.notify_all("install_translations", ui)
registry.notify_all("contribute_help", help_registry)
```

Iterates every registered tab, calls `tab.create_service(hook_id, *args,
**kwargs)` on each. Return values are not collected — fire-and-forget by
design. One tab's hook raising is logged and swallowed per-tab; it does not
stop the others. **Do not** route anything that reads or mutates session
state through this — that must go through `create_service`, which resolves
only against the active tab. This is a deliberately different method name
from `create_service` (not a flag) so a call site can't silently pick the
wrong resolution strategy by forgetting an argument.

## host → tab: `create_main_window_feature` (do not extend)

A narrow hook for **main-presenter-hosted features only.** Currently exactly
one ID is ever requested, `"image_canvas"` (`ui/main_window/composer.py`),
implemented only by `ImageCompareTab`. Resolves active-tab-only, same as
`create_service`. Do not add new IDs to it — new capabilities go through
`create_service`. Making `"image_canvas"` lazy (built on first activation of
whichever tab implements it) would remove the need for a privileged
bootstrap-default tab; out of scope until someone picks up
`ui/main_window/composer.py`'s startup sequence.

## host → tab: `CanvasGeometryProvider` (typed protocol, hot path)

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
`keyboard.py` never touch the provider directly. Non-canvas tabs
(`session_picker`) never implement anything: `get_canvas_geometry_provider()`
returns `None` (base default) and the 5 forwarders short-circuit to
`False`/`None`/`(1.0, 0, 0)`.

**Do not add a second `Protocol` for some other cluster casually** — this
mechanism exists because canvas geometry specifically is hot-path and
cohesive. Anything else that looks reusable is `create_service` by default;
only promote to a typed protocol with an explicit decision, not by default.

## Bootstrap seam: `is_bootstrap_default`

The main-window shell is built once at startup, before any workspace session
exists for `sync_session_mode()` to `activate()`. During that narrow window
`_active_session_type` is `None`, and every `create_service`/
`create_main_window_feature` call would return `None` — which breaks the
`"image_canvas"` feature the app unconditionally builds on startup.
Rather than hardcoding a tab name in generic startup code, `TabContract` has
an `is_bootstrap_default: bool` property (default `False`); exactly one tab
sets it `True`. `TabRegistry.activate_default()` finds that tab (logs an
error and no-ops if zero or more than one tab claims it) and activates it.
`ui/main_window/layouts.py` calls `activate_default()` without naming any
tab. `image_compare` currently sets `is_bootstrap_default = True` because it
is the only tab implementing `"image_canvas"`. **This is a stopgap**, not a
structural fix — see `create_main_window_feature` above for the real fix.

## Policy — when a `create_service`/`create_startup_service` ID is legitimate

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

CATALOG REFRESH — "re-publish into a host-owned registry":
    # Settings (broadcast — every tab may own sections):
    notify_all("contribute_settings", settings_registry)
    # Actions (active-tab chrome only):
    create_service("contribute_actions", action_registry) -> True | None
  Tabs (re)register into host SettingsRegistry / ActionRegistry
  (see docs/dev/ACTIONS.md). For settings, use notify_all so inactive
  tabs still publish sections filtered later by owner_tab. For actions,
  only the active tab's chrome targets are live. Host callers must not
  import tabs.*.actions / tab settings builders by module path. Tab-owned
  label keys live under the tab i18n namespace.
```

Anything that exists only to let host code *push* a value or *command* a tab
to do something host code had to already know the shape of is the
anti-pattern, regardless of whether it's spelled as a method or a string ID.

## Decision rule for a new capability need

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

## Current status and known gaps

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
  `AttributeError` propagate — see [isolation.md](isolation.md)).
  Button-menu wiring in `ui/managers/ui_manager_parts/bootstrap.py` uses the
  tab-owned `ImageComparePopupClosing` extension via
  `create_startup_service("popup_close_extension", ...)`, not widget-name
  lookups.
- `notify_all` and the `is_bootstrap_default` stopgap above are both in
  active use.
