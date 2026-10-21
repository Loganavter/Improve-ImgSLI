# Isolation & dependency wiring

## Tests

A tab owns its own tests, just like it owns its own resources. A test that
imports *another tab's internals* (`tabs.image_compare.canvas...`,
`tabs.multi_compare.widget`, ...) belongs under that tab's own `tests/`, not
under the top-level `tests/` tree — the top-level suite is the host-level
suite and must keep working when any single non-bootstrap tab is deleted.

`session_picker` is the exception: it is the bootstrap tab, always present, so
root tests may use it. This is enforced, not advisory:
`tests/contracts/test_root_tests_no_tab_internals_leak.py` scans every
`tests/**/test_*.py` for `tabs.<tab>.…` imports of the other tabs and fails on
any file that is not in its `ALLOWED_DEEP_TAB_IMPORTS` table (each entry carries
the reason it is a genuine host-level contract; a stale entry fails too).

```
src/tabs/<tab_name>/tests/
    __init__.py
    contracts/     # AST-scan dogmas specific to this tab's canvas features/passes
    render/        # Fake-context tests for this tab's render passes and scene
    runtime/       # Lifecycle/state contracts specific to this tab
    plugins/       # Tests for this tab's plugin-facing behavior (export, settings, ...)
    video/         # image_compare only — video editor contracts
    compare_unify/ # image_compare / multi_compare — comparison-unification parity
```

Rules:

- Mirror the type-based subfolders used by the top-level `tests/` tree
  (`contracts/`, `render/`, `runtime/`, `plugins/`, ...) — see
  [TESTING.md](../TESTING.md) for what each subfolder is for. The set is
  per-tab, not mandatory: `session_picker` ships `runtime/` only, and flat
  test modules at the tab's `tests/` root are fine for one-topic files.
- `sys.path` resolution for `src/` comes from `src/tabs/conftest.py`, which
  inserts `src/` (pytest's own rootdir insertion adds the repo root, because
  `src/__init__.py` exists). That conftest also owns the tab-suite autouse
  fixtures — a hermetic `TiledPixelStore` spill dir (so tests never write the
  user's real cache), plus language/toolkit/theme/navigation resets mirrored
  from `tests/conftest.py`. If a moved test used a `Path(__file__).parents[N]`
  trick to find the repo root, recompute `N` for the new depth
  (`src/tabs/<tab>/tests/<kind>/test_x.py` is 5 levels below repo root).
- Tests that exercise the tab **mechanism** itself — the registry, the
  `TabContract` ABC, generic drop-routing/dispose lifecycle — stay in
  `tests/contracts/` and `tests/runtime/` even if they instantiate one
  concrete tab as an example. Only tests whose assertions are actually about
  that tab's behavior move into its `tests/` folder.
- Run a single tab's suite the same way as any other pytest path:
  `pytest src/tabs/image_compare/tests/`.

Enforcement tests:

| File | What it guards |
|---|---|
| `tests/contracts/test_tabs.py` | Every tab is a filled `TabContract`; `session_type` unique |
| `tests/contracts/test_tabs_isolation.py` | No app-i18n/theme/`ui.icon_manager` imports; JSON keys in own namespace |
| `tests/contracts/test_tab_icons.py` | Tab `Icon` enum members resolve from local `resources/icons/` |
| `tests/contracts/test_root_tests_no_tab_internals_leak.py` | Root tests do not deep-import another tab's internals (allowlist with reasons) |
| `tests/contracts/test_tab_framework_lifecycle.py` | Fail-closed activation and probe isolation in the framework |
| `tests/contracts/test_tab_session_isolation.py` | Gallery slot reads pass an explicit `session_id` |
| `tests/contracts/test_tab_pixel_lifecycle_uses_release.py` | Shared pixel registry lifecycle goes through release |
| `tests/runtime/test_tabs_lifecycle.py` | Generic registry lifecycle |
| `tests/runtime/test_overlay_topology_conformity.py` | Every registered tab answers `create_service("topology_overlays", parent)` |

## Isolation rule: do not borrow app-level keys or theme tokens

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
  a styling value — including `ui.icon_manager` / `AppIcon` (use
  `tabs/<your_tab>/icons.py` instead).

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

## Intra-tab shared helpers (`tabs/_shared/`)

`src/tabs/_shared/` is a small, **import-based** package for helpers used by more
than one module *inside* `src/tabs/` — today the loading pipeline
(`loading_pipeline.py`, `overflow_summary.py`), the save flow (`save_flow.py`),
user-facing error mapping (`user_errors.py`) and canvas capability forwarding
(`canvas.py`: canvas feature aliases, snapshot bounds). `canvas.py` imports
`tabs.image_compare.canvas.registry`,
`tabs.image_compare.services.snapshot_render_plan_builder` and
`...services.video_snapshot_rendering` directly, because routing those through
`TabRegistry.create_service` made an intra-tab call look like a tab→tab
dependency and forced the producer tab to be active.

The split to keep in mind:

- **host → tab** stays on the registry (`create_service` /
  `create_startup_service` / `create_service_for`) — the host must not import tab
  internals;
- **tab → tab / intra-tab** may import from `tabs._shared` (or, as a last
  resort, from the producer's module) instead of string-dispatching through the
  registry.

That is why the "no implied lookups" rule below forbids *string-keyed* and
`getattr` side channels, not imports: an explicit import is a compile-time
dependency that a refactor can follow.

## Dependency wiring rule: no implied lookups

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

See [capability-mechanisms.md](capability-mechanisms.md) for the approved
host↔tab wiring mechanisms.