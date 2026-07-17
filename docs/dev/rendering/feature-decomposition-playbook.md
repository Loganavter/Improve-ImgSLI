# Feature Decomposition Playbook

A reproducible procedure for splitting a flat, overgrown canvas feature
package into the subpackage taxonomy described in
[package-structure.md](package-structure.md#splitting-a-large-feature-into-subpackages).
`magnifier/` (originally ~62 files at feature root) is the reference case
this playbook is extracted from. Use it whenever a feature's root directory
grows past ~15 flat files and navigating it becomes the bottleneck.

## Why not just `git mv` and fix imports by hand

Two things make this risky if done manually or with naive regex:

- Feature-internal modules use a **mix of relative import depths**
  (`.store`, `..actions`, `...scene.build`) that depend on how deep the
  importing file sits in the tree. Moving a file changes that depth, so
  every relative import touching the moved module silently starts
  resolving to the wrong place — no `ImportError`, just wrong behavior.
- Generic module names inside a feature (`state`, `actions`, `events`,
  `mode`, `geometry`) collide with unrelated names elsewhere in the
  codebase (`core.state_management.actions`, other features' `events.py`,
  etc.). A repo-wide regex keyed on the bare module name will corrupt
  unrelated code.

The fix is to do the rename in two separate, independently-verifiable
passes, each safe for a different reason.

## Step 0 — Safety net

- Confirm the feature directory is clean in `git status` (or stash/commit
  unrelated pending changes first — don't mix this refactor with other
  work).
- Make sure the feature has an existing test suite
  (`pytest src/tabs/<tab>/canvas/features/<name> ...` or wherever its tests
  live) and that it currently passes. This refactor must be a behavior
  no-op; the tests are the check.
- Take a throwaway backup copy outside the repo
  (`cp -r <feature_dir> /tmp/<name>_backup_$(date +%s)`) in case a mid-way
  `git mv` batch needs to be inspected/rolled back before it's staged.

## Step 1 — Normalize relative imports to absolute, in place

Write a small **AST-based** script (not regex — relative imports can span
multiple lines with parenthesized `from .x import (a, b, c)` lists, which
regex handles unreliably). For every `.py` file under the feature root:

1. Parse with `ast.parse`, walk for `ast.ImportFrom` nodes with
   `node.level >= 1`.
2. Compute the file's package-relative directory depth to resolve what the
   relative dots point at.
3. Rewrite the import's `module` to the fully qualified form
   `tabs.<tab>.canvas.features.<name>[.sub.path]`, replacing only the
   `from <dots><modpath> import` head — do a source-span edit (via
   `node.lineno/col_offset` → `end_lineno/end_col_offset`) so the original
   multi-line formatting and imported-name list are preserved byte-for-byte
   apart from the head.
4. Raise loudly (`SystemExit`) if a relative import would escape the
   feature package root — that indicates a real cross-feature dependency
   that needs separate handling, not silent mis-resolution.

This pass is a pure rename: no file moves yet, so nothing about the
directory tree has changed and existing relative-import resolution is
untouched — it's purely making explicit what each import already resolved
to.

**Verify before moving on:**
- `python3 -c "import ast; [ast.parse(open(f).read()) for f in ...]"` over
  every touched file (catches edit-produced syntax errors immediately).
- Clear the feature's `__pycache__` directories and re-run its test suite.
  A pass here proves the normalization changed nothing observable.

## Step 2 — Decide the subpackage buckets

Reuse the standard taxonomy from
[package-structure.md](package-structure.md#splitting-a-large-feature-into-subpackages)
unless the feature has a genuinely new concern that doesn't fit any bucket:

| Subpackage | Contents |
|---|---|
| `state/` | store, feature-local state, models, runtime state, snapshot store, mode |
| `render/` | pass implementations/helpers referenced by root `passes.py` |
| `geometry/` | bounds, layout plan, drawing coords, hit-test, generic geometry math |
| `input/` | gestures, interaction, keyboard movement, actions, events |
| `scene/` | scene apply/build/objects |

Contract files stay at the feature root, never moved: `manifest.py`,
`widget.py`, `feature.py`, `properties.py`, `settings_bindings.py`,
`constants.py`, `runtime_hooks.py`, `passes.py`, `__init__.py`. Registries
import these by hardcoded name
(`CanvasFeatureRegistry._iter_feature_modules` in
`src/ui/canvas_infra/scene/registry.py`) and silently skip the feature if
the import fails — there is no error message pointing you back here if you
move one of these by mistake, only a feature that stops loading.

Rename-on-move a module only if its bare name is ambiguous once out of
context (e.g. `magnifier/geometry.py` → `geometry/core.py`, to avoid
`geometry/geometry.py`).

Write this as an explicit map (old top-level module name → new
`subpkg.module` path) before moving anything — it's both your move script's
input and the record of what changed, useful when writing the commit
message.

## Step 3 — Create subpackages and move files

```bash
mkdir -p state render geometry input scene   # only the buckets you need
for d in state render geometry input scene; do touch "$d/__init__.py"; done
git mv old_module.py state/new_name.py
# ...repeat per the map from Step 2
```

If `git mv` fails with "not under version control" on a source path — check `git status` first. It usually means the
working tree has stray untracked files (typically `__pycache__/*.pyc`)
sitting next to the `.py` file, not that the move is unsafe. Falling back
to plain `mv` + `git add` for the affected files is fine once you've
confirmed via `git status --short` that the `.py` source itself is
tracked.

After moving, confirm the feature root now contains **only** the
root-contract files list from Step 2 — nothing else should be left flat.

## Step 4 — Rewrite absolute import paths repo-wide

Because Step 1 made every internal reference fully qualified
(`tabs.<tab>.canvas.features.<name>.<old_module>`), and that prefix is
unique to this feature, a repo-wide substitution restricted to that exact
prefix is safe — it cannot touch unrelated `store`/`state`/`actions`
modules elsewhere, because their import paths don't start with this
feature's prefix.

```python
MOVE_MAP = {"store": "state.store", "actions": "input.actions", ...}
# for each file containing "tabs.<tab>.canvas.features.<name>.<old>",
# replace with "tabs.<tab>.canvas.features.<name>.<new>"
```

Grep first for **bare re-exports** that don't match the
`from pkg.module import` pattern — dynamic/lazy imports inside
`__init__.py` (`__getattr__`-based lazy attribute access doing
`from tabs...features.<name> import old_module` with no trailing
`.attr`) are common in these features and won't be caught by an import-list
grep. Fix these by hand; there are usually only a handful.

Also grep for `Path(__file__).parent`-style lookups (shader dirs, resource
dirs) in every moved module — these silently point at the wrong directory
once a file's depth changes, with no import error to surface it. A shader
loader that now returns nothing because it's looking one directory too
shallow is easy to miss until the feature renders wrong at runtime.

## Step 5 — Verify

1. `python3 -m py_compile` / `ast.parse` every file under the feature
   directory again.
2. Repo-wide grep for the feature's pre-split import paths
   (`tabs\.<tab>\.canvas\.features\.<name>\.(old_module_1|old_module_2|...)`)
   to confirm zero remaining hits, including in tests outside the feature
   directory.
3. Clear all `__pycache__` under the feature and run its scoped test suite,
   then the full project test suite (not just the feature's) — other
   tabs/tests may import the feature's modules by absolute path.
4. Use the `run` or `verify` skill to actually launch the app and exercise
   the feature — auto-discovery failures (a silently skipped feature
   because `manifest.py`'s import chain broke) don't show up as import
   errors or test failures, only as the feature quietly not being there.

## Step 6 — Housekeeping

- Update the "Current Feature Status" table in
  [package-structure.md](package-structure.md#current-feature-status) if
  this changes a feature's decomposition state.
- Remove leftover `__pycache__` directories before committing.
- Keep the normalization (Step 1) and the move+rewrite (Steps 3-4) as
  separate commits if practical — the first is a behavior-preserving
  no-op provable by tests alone, which makes bisecting any regression in
  the second commit much faster.

## Current candidates (flat file count at feature root, `*.py` only)

All `image_compare` and `multi_compare` canvas feature packages have been
swept — every feature that had any non-contract module has been split into
subpackages. `image_compare/layer_labels`-style features that only contain
the root contract files (`manifest.py`, `widget.py`, `feature.py`,
`passes.py`, `__init__.py`, ...) have nothing to decompose and are left
flat.

| Feature | Files | Notes |
|---|---|---|
| `image_compare/magnifier` | done | reference case, see [package-structure.md](package-structure.md) |
| `image_compare/divider` | done | see [package-structure.md](package-structure.md) |
| `image_compare/guides` | done | see [package-structure.md](package-structure.md) |
| `image_compare/capture` | done | see [package-structure.md](package-structure.md) |
| `image_compare/filename_overlay` | done | see [package-structure.md](package-structure.md) |
| `image_compare/paste_overlay` | done | single module moved to `render/` |
| `multi_compare/drag_drop_overlay` | done | `gestures.py`/`interaction.py` moved to `input/` |
| `multi_compare/grid_dividers` | done | `gestures.py`/`interaction.py` moved to `input/` |
| `multi_compare/layer_labels` | n/a | root-contract-only, nothing to move |

Re-count with `find <feature_dir> -maxdepth 1 -name "*.py" | wc -l` before
treating a feature as needing this pass again — these numbers drift as
features grow. New/renamed feature packages that later grow non-contract
modules should be swept the same way.
