# Isolation & dependency wiring

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
  [TESTING.md](../TESTING.md) for what each subfolder is for. This keeps the
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

Enforcement tests (top-level `tests/contracts/`):

| File | What it guards |
|---|---|
| `test_tabs.py` | Every tab is a filled `TabContract`; `session_type` unique |
| `test_tabs_isolation.py` | No app-i18n/theme/`ui.icon_manager` imports; JSON keys in own namespace |
| `test_tab_icons.py` | Tab `Icon` enum members resolve from local `resources/icons/` |

Plus `tests/runtime/test_tabs_lifecycle.py` for generic registry lifecycle.

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
