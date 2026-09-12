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

`create_startup_service` is a variant that, like `create_main_window_feature`
below, routes by capability across every already-discovered tab (bootstrap
before deferred, first non-`None` answer wins) instead of the active one,
for use during one-time startup shell construction (`MainWindowComposer.compose()`
builds the main-window shell — `UIManager`, toolbar, layout manager, ... —
once, synchronously, before the user's real initial session is necessarily
active). See `tabs/registry.py`'s docstring on `create_startup_service` for
the full ordering argument.

Both `create_service`/`create_startup_service` **catch and re-raise**
exceptions from the tab's implementation (logged first) — they do not
swallow errors; only an unrecognized ID silently resolves to `None`.

## host → tab: `notify_all` (broadcast, not session-scoped)

A distinct mechanism from `create_service`, for the minority of hooks that
are genuinely global broadcasts rather than session-scoped requests: every
registered tab needs its own chance to act, regardless of which one is
active. Current call sites: `install_translations` (each tab binds its
own UI's translation signals at startup, not just the active one's) and
`refresh_startup_button_visuals` (cosmetic startup refresh every tab's page
should get).  **Former** call sites `contribute_settings` /
`contribute_help` have migrated to typed collectors
(`tabs/use_cases/capability_routing.py:32`
`collect_help_contributions()` /
`collect_settings_contributions()` → `HelpContribution` /
`SettingsContribution` with `owner_tab == i18n_namespace`, per-tab
exception logged, not stopping others) and
`install_help_contributions(list[HelpContribution])` /
`install_settings_contributions(list[SettingsContribution])` immutable merge
(see [HELP_SYSTEM.md](../HELP_SYSTEM.md) and `plugins/help/tree.py:42`).

```python
registry.notify_all("install_translations", ui)
# Typed collectors (replacing notify_all for catalogs):
from tabs.use_cases.capability_routing import collect_help_contributions
contributions = collect_help_contributions(registry)  # -> list[HelpContribution]
```

Iterates every registered tab, calls `tab.create_service(hook_id, *args,
**kwargs)` on each (for `notify_all`) or collects typed return values (for
`collect_*`). One tab's hook raising is logged and does not stop the others
(`notify_all` swallows, collectors log and continue). **Do not** route anything that reads or mutates session
state through this — that must go through `create_service`, which resolves
only against the active tab. This is a deliberately different method name
from `create_service` (not a flag) so a call site can't silently pick the
wrong resolution strategy by forgetting an argument.

## host → tab: `create_service_for` (named hub tab)

Rare companion to `create_service`: resolve a service against a **specific**
`session_type`, not the active session. Legitimate when host chrome must talk
to a known hub tab that may not be active — today that is the session picker,
addressed via `core.store.INITIAL_WORKSPACE_SESSION_TYPE` (not a tab class
name and not `getattr` on the page widget).

```python
chrome = TabRegistry().create_service_for(
    INITIAL_WORKSPACE_SESSION_TYPE,
    "session_picker.host_chrome",
)
# -> SessionPickerHostChrome | None
```

Do **not** use this to smuggle active-session workarounds ("I'll just name
`image_compare`"). Active-session capabilities stay on `create_service`.
Do not grow a second Protocol casually — see `CanvasGeometryProvider` above;
`session_picker.host_chrome` is a small extension object with a documented
shape in `tabs/session_picker/host_chrome.py`.

## host → tab: `create_main_window_feature` (do not extend)


A narrow hook for **main-presenter-hosted features only.** Currently exactly
one ID is ever requested, `"image_canvas"` (`ui/main_window/composer.py`),
implemented only by `ImageCompareTab`. Resolves by capability (see above),
same routing as `create_startup_service`. Do not add new IDs to it — new
capabilities go through `create_service`.

`"image_canvas"` is resolved lazily — `composer.py` wraps it in
`tabs.registry.LazyTabService` (`probe_method="create_main_window_feature"`)
instead of calling `create_main_window_feature` synchronously and raising on
`None`. It is only actually built the first time some caller touches an
attribute on it, which in practice is once `image_compare`'s page is
materialized (`ImageCompareTab.create_main_window_feature` returns `None`
while `self._widget` is still unset). This is what let `image_compare` stop
being forced into existence at every boot merely because the legacy shell
depended on it. See `docs/dev/investigations/lazy-legacy-shell-plan.md` for
the full writeup, including the small set of call sites
(`ui/presenters/main_window/connections.py`,
`ui/presenters/main_window/presenter.py::schedule_canvas_update`) that had to
be made tolerant of `image_canvas` not being resolved yet.

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

## Bootstrap seam: `is_bootstrap_default` (reserved for `session_picker`)

`TabContract.is_bootstrap_default: bool` (default `False`) names the tab that
owns the app's *initial workspace session* — the tab behind
`core.store.INITIAL_WORKSPACE_SESSION_TYPE`, i.e. **`session_picker`**. The
role is reserved exclusively for that tab: `TabRegistry._bootstrap_default_tab()`
raises if any other tab claims it, and `TabRegistry.activate_default()` seeds
`_active_session_type` from it for the narrow window before the first real
`sync_session_mode()` call reconciles it. `ui/main_window/layouts.py` calls
`activate_default()` without naming any tab, and `bootstrap_default_tab()`
resolves to it.

**This flag does NOT route legacy main-window shell construction.** Legacy
shell wiring is routed by capability — see below.

## Legacy shell: routing by capability (no privileged tab)

The one-time legacy main-window shell (the `"image_canvas"` feature and the
toolbar/export/layout/magnifier startup services) is resolved by
`TabRegistry.create_startup_service`/`create_main_window_feature` **by
capability**: each registered tab is asked in registration order (bootstrap
before deferred), and the first one whose `create_service` /
`create_main_window_feature` returns a non-`None` answer provides the
service/feature. There is no flag or hardcoded session type a tab can use to
"claim" shell-hosting, and no tab has a privileged role. `image_compare`
happens to answer all of today's legacy shell capabilities purely because it
is the tab that implements them.

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
    create_service("requires_first_run_onboarding")
      -> True for image_compare / multi_compare (first-run onboarding
         fires over the first such tab opened; see plugins/onboarding.md)
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
    # Settings / Help (broadcast — every tab may own sections/help, even inactive):
    from tabs.use_cases.capability_routing import collect_help_contributions, collect_settings_contributions
    collect_help_contributions(registry) -> list[HelpContribution]  # frozen, owner_tab == i18n_namespace
    collect_settings_contributions(registry) -> list[SettingsContribution]
    # then install_*_contributions(list) immutable merge (uniq node_id / alias conflict raise)
    # Actions (active-tab chrome only):
    create_service("contribute_actions", action_registry) -> True | None
  Tabs (re)register into host SettingsRegistry / HelpTree / ActionRegistry
  (see docs/dev/ACTIONS.md, HELP_SYSTEM.md). For settings/help, collectors
  gather typed return values (per-tab exception logged, not stopping others);
  they remain browsable catalogs listing every inactive tab's contributions
  (filtered by owner_tab on display). For actions, only the active tab's
  chrome targets are live. Host callers must not import tabs.* builders by
  module path. Tab-owned label keys live under the tab i18n namespace.

Why this divergence (C10): settings/help are *browsable catalogs* — browser
must list every inactive tab's sections/help subtrees (user hasn't switched
yet), so the host broadcasts ``notify_all`` and filters by ``owner_tab`` on
display. Actions (including keymap defaults) are *active-tab chrome* — only
the live tab's widget targets exist and are hittable; inactive tabs' targets
are not in the widget tree. Hence ``contribute_actions`` / ``contribute_keymap_defaults``
resolve strictly against the active tab via ``create_service`` (``_active_session_type``),
and ``connections.py:_refresh_active_tab_actions`` re-calls it on every
``currentChanged``. Same verb prefix, opposite routing by product need.
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
  ID in the codebase was historically implemented only by `ImageCompareTab`.
  `session_picker` now implements `session_picker.host_chrome` (resolved via
  `create_service_for`); `multi_compare` implements a few contribution /
  clipboard IDs. Several call sites still treat some results as mandatory
  (`raise RuntimeError(...)` on `None`) rather than degrading gracefully —
  a policy violation per rule 1 above, not yet fully cleaned up.
  Verify, don't assume, before assuming a new ID "just works" for
  a non-`image_compare` tab.
- `multi_compare`/`session_picker` still lack several session-scoped IDs they
  could plausibly be the active tab for (`canvas_widget_class`,
  `layout_manager`, `toolbar_presenter` are the live candidates if those
  tabs are ever meant to render their own canvas chrome). Not yet started.
- **Enforced** for `contribute_*` (see `tests/contracts/test_capability_ids.py`):
  every `create_service("contribute_*")` / `notify_all("contribute_*")` literal
  must be recognized by at least one tab's `create_service` override; dangling
  IDs now fail at test time (not silently at runtime as `None`).  Other IDs
  still lack a generic enforcement test — the `contribute_*` family closed the
  biggest concrete gap (this paragraph previously documented it as missing).
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
 - Session-switch state dialects (C3): IC snapshot/restore per switch
  (``tabs/image_compare/use_cases/persistence.py``), MC slot-authoritative
  re-read (post 2026-08 unification, ``tabs/multi_compare/use_cases/persistence.py``),
  image_gallery raw ``state_slots.get`` (``tabs/image_gallery/tab.py:86``).
  All three are now documented as sanctioned — they reflect different ownership
  models (IC camera lives on host widget, MC state in Redux slot, gallery folder
  in slot dict). New tabs should pick the slot-authoritative model (MC) unless
  host-widget state forces snapshot semantics (IC).
 - `notify_all` and the `is_bootstrap_default` stopgap above are both in
  active use.
