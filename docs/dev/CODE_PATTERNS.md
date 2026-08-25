# Code patterns & anti-patterns

Short rules for structuring non-rendering application code (controllers,
widgets, presenters). **No case narratives here** — only the rule and a
pointer to a real example already in the tree. For canvas/QRhi-specific
rules see `docs/dev/rendering/patterns.md` in the private
`improve-imgsli-internal-docs` repo (not in this repo); for
interface contracts between subsystems see [CONTRACTS.md](CONTRACTS.md).
This page is about internal code organization *within* one subsystem.

---

## Pattern: thin owner + `use_cases/` module

**Symptom**: a controller, session object, or `QWidget` subclass keeps
growing past ~500 lines / 40+ methods, and a `git blame` or method-name scan
shows it mixing more than one orthogonal concern — e.g. one class doing
settings sync *and* image loading *and* export *and* drag & drop. Every new
feature adds another handful of methods to the same class because that's
where the existing ones live, not because the class's own job grew.

**Rule**: split each orthogonal concern into its own module under
`use_cases/` (or `ui/` for widget-side concerns), as **plain functions that
take the owning object as their first argument** — not a second class. The
owner keeps:

- construction / wiring (signal connections, subscriptions)
- the instance state those functions read and write
  (`self._pending_paste_paths`, `self._loading_toasts`, …)
- thin delegator methods for anything Qt must find *by name* on the
  instance itself (signal handler slots, `dragEnterEvent`,
  `eventFilter`, …) — these do nothing but call straight into the
  `use_cases` function with the same arguments

```python
# widget.py — owner: state + Qt-required method names only
class MultiCompareWidget(QWidget):
    def __init__(self, ...):
        ...
        self._pending_duplicate_source: int | None = None
        self._pending_paste_paths: list[Path] | None = None

    def dropEvent(self, event: QDropEvent) -> None:   # Qt looks this up by name
        drag_drop.drop_event(self, event)

    def begin_pending_paste(self, paths: list[Path]) -> None:  # public API, keep the name
        drag_drop.begin_pending_paste(self, paths)

# ui/drag_drop.py — the actual logic, testable without a live QWidget
def drop_event(widget, event: QDropEvent) -> None:
    ...
    widget.images_dropped.emit(paths, (tgt_path, root_tgt), side)

def begin_pending_paste(widget, paths: list[Path]) -> None:
    widget._pending_paste_paths = [...]
    ...
```

**Why functions-taking-owner instead of a second class**: a second class
just relocates the coupling (it still needs the same references back into
the widget/controller) while adding a constructor, `self.`, and an import
cycle to manage. A plain function module has none of that ceremony and is
trivially unit-testable with a `SimpleNamespace`/fake object that only
implements the attributes the function actually touches — see
`src/tabs/multi_compare/tests/plugins/test_multi_compare_export.py` and
`src/tabs/image_compare/tests/render/test_document_swap_unification_race_contract.py`
for the fake-controller test pattern this enables.

**Keep the same method names when splitting** — tests and other callers
often reach into private methods/attributes directly (`controller._show_loading_toast(1)`,
`widget._pending_paste_paths = [...]`); a rename for "cleanliness" breaks
call sites for no behavioral gain. The split is about *where the body
lives*, not about renaming the public surface.

**Reference implementations** (read one before doing a new split):

| Split | Owner (thin) | use_cases module(s) |
|---|---|---|
| Image loading, pyramid build, loading toast | `tabs/image_compare/_session_controller.py` | `tabs/image_compare/use_cases/loading.py` |
| List/playlist operations (reorder, rating, rename) | `tabs/image_compare/_session_controller.py` | `tabs/image_compare/use_cases/list_ops.py` |
| Single-image-mode navigation | `tabs/image_compare/_session_controller.py` | `tabs/image_compare/use_cases/navigation.py` |
| Image loading, pyramid build, loading toast (multi-compare) | `tabs/multi_compare/controller.py` | `tabs/multi_compare/use_cases/loading.py` |
| Quick-save / export-dialog orchestration | `tabs/multi_compare/controller.py` | `tabs/multi_compare/use_cases/export.py` |
| Drag & drop / pending-placement state machine | `tabs/multi_compare/widget.py` | `tabs/multi_compare/ui/drag_drop.py` |
| Inspector Code section: preview panel | `sli-ui-toolkit` `ui/inspector/code.py` (`CodeSectionEditor` owner) | `ui/inspector/code_preview.py` (functions taking the editor) |
| Inspector Apply: class patch + config apply | same owner | `ui/inspector/code_apply.py`, shared snippet parsing in `code_config.py` |
| Inspector Code section: preview panel | `sli-ui-toolkit` `ui/inspector/code/editor.py` (`CodeSectionEditor` owner) | `ui/inspector/code/preview.py` (functions taking the editor) |
| Inspector Apply: class patch + config apply | same owner | `ui/inspector/code/apply.py`, shared snippet parsing in `code/config.py` |

### When *not* to split

A large single-responsibility state machine is not the same problem and
splitting it does not help. If every method reads and writes the *same*
tightly-coupled instance state toward *one* job (one async pipeline, one
resource lifecycle), pulling pieces into separate modules just moves state
back and forth between them without reducing coupling — it adds an import
and a parameter list, not clarity.

Signal you're looking at this case instead: you can't name the split
modules without one of them being a grab-bag ("misc", "helpers") or without
threading half the instance's fields through as parameters to every
function in the "split-off" module.

Examples already judged this way and left alone:
`tabs/image_compare/plugins/video_editor/presenter_parts/preview.py`
(`PreviewCoordinator` — one render pipeline: schedule → GPU render /
background prepare-worker → apply-to-canvas → cache, all sharing one
render-task-id race-guard), `shared/image_processing/tiled_pixel_store.py`
(one class, one storage lifecycle), `tabs/image_compare/canvas/rhi_renderer/__init__.py`
(`RhiCanvasRenderer.render()` — one frame's sequencing, see its own
module docstring), `plugins/export/dialog.py` (one `QDialog`, size is
layout/signal-wiring bulk, not mixed concerns).

### Who owns the state — collaborator object vs use_cases function

Review 2026-08-25 (B1–B3): the largest IC↔MC duplicates (save-flow ~170 LOC,
loading-toast ~75, pyramid-build ~85) are flow-shaped concerns written as
*functions over different owners* in both tabs, which made shared extraction
non-mechanical — while toast already grew a state-owning ``SaveToastMixin``
ad-hoc. Rule:

- If the concern **owns its own state/lifecycle** (toast queue, coordinator
  lifecycle, worker + abort predicate, toast bump timers) → small
  **collaborator object** (parameterizable, shareable across tabs). It holds
  its own dict/QTimer/thread state, receives the owner via constructor or
  method args, and can be reused without copying functions. Example:
  ``tabs/save_toast.py:SaveToastMixin``; future save-flow coordinator
  should be one such object parameterized by abort predicate / thread pool.

- If the concern is **widget-glue whose state genuinely lives on the owner**
  (drag & drop pending paths, list ops that mutate owner's store) → keep the
  ``use_cases`` **function-taking-owner** shape. Making a second class just
  adds ceremony and an import cycle.

Inconsistent placement today (IC drag&drop under ``use_cases/``, MC under
``ui/``) is both sanctioned: ``use_cases/`` is for controller/store-owned
logic, ``ui/`` for widget-owned logic. Pick the home that matches the owner,
not the tab.

---

## Related dogmas (already documented, cross-referenced here on purpose)

- **No implied lookups** — don't substitute one hidden lookup
  (`registry.get`, `getattr(widget, "btn_x", None)`) for an explicit
  dependency passed in. See `TAB_CONTRACT.md`'s dependency-wiring rule and
  `tests/runtime/test_no_implied_widget_lookup.py`.
- **Extension points** — before inventing a new mechanism, check
  [ARCHITECTURE.md](ARCHITECTURE.md)'s "Extension Points" table for the
  smallest viable integration point.
- **File size (canvas features only)** — files under
  `tabs/<tab>/canvas/features/<name>/` past ~400 lines need a
  `File-Size-Exempt:` marker explaining why; see
  `docs/dev/rendering/patterns.md` in `improve-imgsli-internal-docs`
  (private, not in this repo) and
  `tests/contracts/test_canvas_features_file_size.py`. This is narrower
  than the pattern above and specific to auto-discovered canvas features —
  it does not apply project-wide, and satisfying it (or being exempt from
  it) does not mean a file's *internal* organization is good; judge that
  against the "thin owner + use_cases" rule above instead.
- **File size (repo-wide)** — `src/**/*.py` past 500 lines needs `Audit-Meta:` (or `File-Size-Exempt:` for canvas) per [FILE_SIZE_POLICY.md](FILE_SIZE_POLICY.md); central registry `file_size_registry.json` is generated by `src/devtools/file_meta.py --write-registry` and checked by `tests/contracts/test_file_size_policy.py`.