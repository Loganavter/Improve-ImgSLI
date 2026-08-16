"""Drag & drop / pending-placement orchestration for ``MultiCompareWidget``.

Split out of ``widget.py`` to keep that class down to composition/wiring --
mirrors the ``use_cases`` split applied to ``MultiCompareController``. Every
function here takes the widget as its first argument and reads/writes its
instance state (``_pending_duplicate_source``, ``_pending_paste_paths``)
directly, same calling convention as the controller's use_cases modules.

Qt calls ``dragEnterEvent``/``dragMoveEvent``/``dragLeaveEvent``/``dropEvent``/
``eventFilter`` by name on the widget itself, so those stay defined as thin
methods on ``MultiCompareWidget`` that delegate into this module.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent

from tabs.multi_compare.models import leaves, node_at_path, slot_ids_in_tree
from tabs.multi_compare.scene import actions
from tabs.multi_compare.ui.canvas_widget import INTERNAL_SLOT_MIME

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


def has_image_urls(mime) -> bool:
    if not mime.hasUrls():
        return False
    for url in mime.urls():
        path = Path(url.toLocalFile())
        if path.suffix.lower() in _IMAGE_EXTENSIONS:
            return True
    return False


def has_internal_slot(mime) -> bool:
    return mime.hasFormat(INTERNAL_SLOT_MIME)


def internal_source_slot_id(mime) -> int | None:
    if not mime.hasFormat(INTERNAL_SLOT_MIME):
        return None
    try:
        return int(bytes(mime.data(INTERNAL_SLOT_MIME)).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def grid_local_pos(widget, pos):
    return widget.canvas.mapFrom(widget, pos)


def resolve_drop_target(widget, pos, *, internal: bool):
    local = grid_local_pos(widget, pos)
    if internal:
        return widget.canvas.compute_drop_target(local, include_center=True)
    if len(slot_ids_in_tree(widget.state.root)) >= widget.state.max_slots:
        return None, None, False, None
    return widget.canvas.compute_drop_target(local)


def apply_drag_preview(widget, event, internal: bool) -> None:
    tgt_path, side, root_tgt, swap_id = resolve_drop_target(
        widget, event.position().toPoint(), internal=internal
    )
    source_id = (
        internal_source_slot_id(event.mimeData()) if internal else None
    )
    widget.store.dispatch(
        actions.set_drag_state(
            active=True,
            internal=internal,
            source_slot_id=source_id,
            target_path=tgt_path,
            target_side=side,
            target_root=root_tgt,
            target_swap_slot_id=swap_id,
        )
    )


def drag_enter_event(widget, event: QDragEnterEvent) -> None:
    cancel_pending_placements(widget)
    if has_internal_slot(event.mimeData()):
        apply_drag_preview(widget, event, internal=True)
        event.acceptProposedAction()
        return
    if has_image_urls(event.mimeData()):
        apply_drag_preview(widget, event, internal=False)
        event.acceptProposedAction()
        return
    event.ignore()


def drag_move_event(widget, event: QDragMoveEvent) -> None:
    if has_internal_slot(event.mimeData()):
        apply_drag_preview(widget, event, internal=True)
        event.acceptProposedAction()
        return
    if has_image_urls(event.mimeData()):
        apply_drag_preview(widget, event, internal=False)
        event.acceptProposedAction()
        return
    event.ignore()


def drag_leave_event(widget, event: QDragLeaveEvent) -> None:
    widget.store.dispatch(actions.set_drag_state(active=False))
    event.accept()


def drop_event(widget, event: QDropEvent) -> None:
    mime = event.mimeData()
    if has_internal_slot(mime):
        source_id = internal_source_slot_id(mime)
        tgt_path, side, _, swap_id = resolve_drop_target(
            widget, event.position().toPoint(), internal=True
        )
        widget.store.dispatch(actions.set_drag_state(active=False))
        if source_id is not None and side is not None:
            apply_internal_drop(widget, source_id, tgt_path, side, swap_id)
        event.acceptProposedAction()
        return

    tgt_path, side, root_tgt, _ = resolve_drop_target(
        widget, event.position().toPoint(), internal=False
    )
    widget.store.dispatch(actions.set_drag_state(active=False))
    paths = []
    for url in mime.urls():
        path = Path(url.toLocalFile())
        if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS:
            paths.append(path)
    if paths:
        widget.images_dropped.emit(paths, (tgt_path, root_tgt), side)
        event.acceptProposedAction()


def apply_internal_drop(
    widget,
    source_id: int,
    target_path: tuple[int, ...] | None,
    side: str,
    swap_slot_id: int | None,
) -> None:
    if side == "center" and swap_slot_id is not None and swap_slot_id != source_id:
        widget.store.dispatch(actions.swap_slots(source_id, swap_slot_id))
        return
    if target_path is None:
        return
    anchor_slot = anchor_slot_for_path(widget, target_path)
    if anchor_slot is None or anchor_slot == source_id:
        return
    widget.store.dispatch(
        actions.move_slot(
            source_slot_id=source_id,
            target_path=target_path,
            target_anchor_slot_id=anchor_slot,
            side=side,
        )
    )


def anchor_slot_for_path(widget, path: tuple[int, ...]) -> int | None:
    """Return slot_id of the first leaf inside the subtree at ``path``."""
    node = node_at_path(widget.state.root, path)
    if node is None:
        return None
    first = leaves(node)
    return first[0].slot_id if first else None


def begin_pending_duplicate(widget, source_slot_id: int) -> None:
    cancel_pending_placements(widget)
    source = next((s for s in widget.state.slots if s.id == source_slot_id), None)
    if source is None or source.image is None:
        return
    if len(widget.state.slots) >= widget.state.max_slots:
        return
    widget._pending_duplicate_source = source_slot_id
    arm_pending_placement_input(widget)
    update_pending_drag_preview(widget, canvas_cursor_pos(widget), internal=True)


def begin_pending_paste(widget, paths: list[Path]) -> None:
    """Enter external DnD placement: highlight under cursor, click to drop."""
    cancel_pending_placements(widget)
    valid = [Path(p) for p in paths if Path(p).is_file()]
    if not valid:
        return
    if len(slot_ids_in_tree(widget.state.root)) >= widget.state.max_slots:
        return
    widget._pending_paste_paths = valid
    arm_pending_placement_input(widget)
    update_pending_drag_preview(widget, canvas_cursor_pos(widget), internal=False)


def has_pending_placement(widget) -> bool:
    return (
        widget._pending_duplicate_source is not None
        or widget._pending_paste_paths is not None
    )


def cancel_pending_placements(widget) -> None:
    had = has_pending_placement(widget)
    widget._pending_duplicate_source = None
    widget._pending_paste_paths = None
    if not had:
        return
    try:
        widget.canvas.removeEventFilter(widget)
    except Exception:
        pass
    widget.canvas.unsetCursor()
    widget.store.dispatch(actions.set_drag_state(active=False))


def arm_pending_placement_input(widget) -> None:
    widget.canvas.setCursor(Qt.CursorShape.DragCopyCursor)
    widget.canvas.installEventFilter(widget)
    widget.canvas.setFocus(Qt.FocusReason.OtherFocusReason)


def canvas_cursor_pos(widget):
    from PySide6.QtGui import QCursor

    return widget.canvas.mapFromGlobal(QCursor.pos())


def update_pending_drag_preview(widget, pos, *, internal: bool) -> None:
    include_center = internal
    if internal:
        tgt_path, side, root_tgt, swap_id = widget.canvas.compute_drop_target(
            pos, include_center=include_center
        )
        widget.store.dispatch(
            actions.set_drag_state(
                active=True,
                internal=True,
                source_slot_id=widget._pending_duplicate_source,
                target_path=tgt_path,
                target_side=side,
                target_root=root_tgt,
                target_swap_slot_id=swap_id,
            )
        )
        return
    if len(slot_ids_in_tree(widget.state.root)) >= widget.state.max_slots:
        widget.store.dispatch(actions.set_drag_state(active=False))
        return
    tgt_path, side, root_tgt, _ = widget.canvas.compute_drop_target(pos)
    widget.store.dispatch(
        actions.set_drag_state(
            active=True,
            internal=False,
            target_path=tgt_path,
            target_side=side,
            target_root=root_tgt,
        )
    )


def event_filter(widget, watched, event) -> bool:
    if not has_pending_placement(widget) or watched is not widget.canvas:
        return False
    internal = widget._pending_duplicate_source is not None
    et = event.type()
    if et == QEvent.Type.MouseMove:
        pos = (
            event.position().toPoint()
            if hasattr(event, "position")
            else event.pos()
        )
        update_pending_drag_preview(widget, pos, internal=internal)
        return True
    if et == QEvent.Type.MouseButtonPress:
        button = event.button()
        if button == Qt.MouseButton.LeftButton:
            pos = (
                event.position().toPoint()
                if hasattr(event, "position")
                else event.pos()
            )
            if internal:
                tgt_path, side, root_tgt, _ = widget.canvas.compute_drop_target(
                    pos, include_center=False
                )
                finalize_pending_duplicate(widget, tgt_path, side, root_tgt)
            else:
                tgt_path, side, root_tgt, _ = widget.canvas.compute_drop_target(pos)
                finalize_pending_paste(widget, tgt_path, side, root_tgt)
            cancel_pending_placements(widget)
            return True
        if button == Qt.MouseButton.RightButton:
            cancel_pending_placements(widget)
            return True
    if et == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
        cancel_pending_placements(widget)
        return True
    return False


def finalize_pending_paste(
    widget,
    target_path: tuple[int, ...] | None,
    side: str | None,
    target_root: bool,
) -> None:
    paths = widget._pending_paste_paths
    if not paths:
        return
    # Empty canvas: compute_drop_target returns (None, None, True, None).
    # Real file dropEvent still emits; add_image_at treats target_root.
    if side is None and not target_root:
        return
    widget.images_dropped.emit(list(paths), (target_path, target_root), side)


def finalize_pending_duplicate(
    widget,
    target_path: tuple[int, ...] | None,
    side: str | None,
    target_root: bool,
) -> None:
    source_id = widget._pending_duplicate_source
    if source_id is None or side is None:
        return
    source = next((s for s in widget.state.slots if s.id == source_id), None)
    if source is None or source.image is None:
        return
    if len(widget.state.slots) >= widget.state.max_slots:
        return
    image = source.image.copy() if hasattr(source.image, "copy") else source.image
    widget.store.dispatch(
        actions.add_slot(
            path=source.path or Path(),
            image=image,
            label=source.label,
            target_path=tuple(target_path or ()),
            side=side,
            target_root=target_root,
        )
    )