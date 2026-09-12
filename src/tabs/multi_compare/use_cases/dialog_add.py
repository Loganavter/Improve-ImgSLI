"""Toolbar "Add images" dialog entry for the Multi Compare tab (P8).

Split out of ``use_cases/loading.py`` (file-size policy per
``docs/dev/CODE_PATTERNS.md``): ``loading.py`` keeps the sync decode
primitives, toast lifecycle, pyramid builds and the full-res second
stage; this module owns the dialog-add shape — validate like the
DnD/chrome/carry entries, imageless slot + loading toast synchronously,
preview in a ``GenericWorker`` (``preview_decode.load_preview_async``),
error-toast via the shared EventBus/toast plumbing whenever a
dialog-confirmed file yields no slot. Every function here takes the
controller as its first argument, same calling convention as
``loading.py``.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("ImproveImgSLI")


def _coerce_dialog_path(raw: Path | str) -> Path:
    return raw if isinstance(raw, Path) else Path(raw)


def _is_loadable_image(path: Path) -> bool:
    """Dialog-entry validation shared with DnD/chrome/carry (P8 suspect 3).

    Single source stays ``shared.image_extensions``; ``is_file`` mirrors
    ``ui/drag_drop.drop_event`` and ``loading.load_external_paths`` so the
    button cannot offer-then-drop files the other entries reject.
    """
    from shared.image_extensions import is_accepted_image_path

    return is_accepted_image_path(path) and path.is_file()


def _grid_full_reason(controller) -> str:
    try:
        max_slots = controller.widget.state.max_slots
    except Exception:
        max_slots = None
    default = (
        f"Comparison grid is full ({max_slots} images max)"
        if max_slots is not None
        else "Comparison grid is full"
    )
    try:
        return controller.translate("msg.compare_grid_full", default)
    except Exception:
        return default


def load_images(controller, paths) -> int:
    """Toolbar-dialog entry (P8 invariant).

    Dialog confirm with ≥1 valid file → slot + preview/error-toast, never
    a silent 0 slots: valid files go through a single ``store.transact``
    of planned ``AddSlot`` actions (A3: 1 dispatch / 1 emit for the whole
    confirm — same end state as N sequential ``load_single_auto`` calls);
    loading toast + preview worker stay per created slot, and files past
    capacity surface one error-toast each via the bus like the single-add
    path does. A grid that is already full short-circuits to a single
    error-toast instead of one per file.

    Returns the number of slots created synchronously.

    Multi-file chaining (B2, DnD parity): only file 0 resolves its auto
    target against the live canvas — files 1..N chain beside the previously
    added slot via ``find_path`` on the scratch state (same rule as
    ``loading.on_images_dropped``). Re-resolving every file against the
    live widget reads the pre-confirm tree (the ``transact`` commits only
    after the loop), so files 1..N re-targeted file 0's anchor and each
    ``((), side)`` re-hit wrapped the whole root instead of sibling-chaining
    (``S(h,[S(h,[L0,L1]),L2])`` — uneven panes vs DnD's flat chain).
    """
    from tabs.multi_compare.models import find_path
    from tabs.multi_compare.scene import actions as mc_actions
    from tabs.multi_compare.scene.store import reduce as mc_reduce
    from tabs.multi_compare.use_cases import loading as _loading
    from tabs.multi_compare.use_cases import preview_decode as _preview
    from tabs.multi_compare.use_cases.loading import resolve_auto_triple

    valid: list[Path] = []
    for raw in paths or []:
        path = _coerce_dialog_path(raw)
        if not _is_loadable_image(path):
            logger.debug("load_images: skipped non-image/missing file %s", path)
            continue
        valid.append(path)
    if not valid:
        return 0
    try:
        full = len(controller.widget.state.slots) >= controller.widget.state.max_slots
    except Exception:
        full = False
    if full:
        logger.warning("load_images: grid full, rejecting %d file(s)", len(valid))
        _loading._emit_mc_load_error(controller, valid[0], _grid_full_reason(controller))
        return 0
    widget = controller.widget
    scratch = widget.state
    built: list = []
    planned: list[tuple[int, Path]] = []
    overflow: list[Path] = []
    file0_side: str | None = None
    last_added: int | None = None
    for i, path in enumerate(valid):
        if len(scratch.slots) >= scratch.max_slots:
            overflow.append(path)
            continue
        if i == 0:
            auto_path, auto_side, auto_root = resolve_auto_triple(widget, scratch)
            file0_side = auto_side
            action = mc_actions.add_slot(
                path=path,
                label=path.stem,
                target_path=auto_path,
                side=auto_side,
                target_root=auto_root,
            )
        else:
            next_side = "right" if file0_side in ("left", "right") else "bottom"
            next_path: tuple[int, ...] | None = None
            if last_added is not None:
                found = find_path(scratch.root, last_added)
                next_path = tuple(found) if found is not None else None
            if next_path is None:
                auto_path, auto_side, auto_root = resolve_auto_triple(widget, scratch)
                action = mc_actions.add_slot(
                    path=path,
                    label=path.stem,
                    target_path=auto_path,
                    side=auto_side,
                    target_root=auto_root,
                )
            else:
                action = mc_actions.add_slot(
                    path=path,
                    label=path.stem,
                    target_path=next_path,
                    side=next_side,
                    target_root=False,
                )
        before = len(scratch.slots)
        scratch = mc_reduce(scratch, action)
        if len(scratch.slots) <= before:
            overflow.append(path)
            continue
        built.append(action)
        last_added = scratch.slots[-1].id
        planned.append((scratch.slots[-1].id, path))
    if not built:
        for path in overflow:
            _loading._emit_mc_load_error(controller, path, _grid_full_reason(controller))
        return 0
    store = widget.store
    transact = getattr(store, "transact", None)
    if callable(transact):
        store.transact(built)
    else:  # headless fakes pre-dating the batch API: same end state, N dispatches
        for sub in built:
            store.dispatch(sub)
    live_ids = {s.id for s in widget.state.slots}
    created = 0
    for sid, path in planned:
        if sid not in live_ids:
            continue
        created += 1
        _loading.show_loading_toast(controller, sid)
        _preview.load_preview_async(controller, path, sid)
    for path in overflow:
        logger.warning("load_images: no slot created for %s (grid full?)", path)
        _loading._emit_mc_load_error(controller, path, _grid_full_reason(controller))
    return created


def load_single_auto(controller, path: Path | str) -> int | None:
    # P2: slot first (imageless), decode in a worker — the dialog-add path
    # shares the drop path's async shape instead of stalling the GUI inside
    # load_initial_image.
    #
    # P8: never silently drops. ``sid is None`` (grid full or the reducer
    # grew nothing) used to bare-``return`` — dialog-confirmed files
    # vanished with no slot, no toast, no bus event while DnD of the same
    # file worked. A no-slot outcome now surfaces through the shared
    # EventBus/toast plumbing like every other load failure; invalid
    # entries (wrong suffix, missing file) are skipped like the
    # DnD/chrome/carry entries skip them.
    from tabs.multi_compare.use_cases import loading as _loading
    from tabs.multi_compare.use_cases import preview_decode as _preview

    path = _coerce_dialog_path(path)
    if not _is_loadable_image(path):
        logger.debug("load_single_auto: skipped non-image/missing file %s", path)
        return None
    sid = controller.widget.add_image_auto(path, path.stem)
    if sid is None:
        logger.warning("load_single_auto: no slot created for %s (grid full?)", path)
        _loading._emit_mc_load_error(controller, path, _grid_full_reason(controller))
        return None
    _loading.show_loading_toast(controller, sid)
    _preview.load_preview_async(controller, path, sid)
    return sid
