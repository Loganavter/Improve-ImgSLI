"""Multi Compare slot drag → workspace tab strip (gallery-DnD parity).

Owner requirement 2026-10-25: the ordinary slot drag — previously reorder-only
inside the tab — must also hand the image to another workspace tab, exactly
like a gallery-card drag. The dedicated context-menu **Move** action is gone;
the gesture is the entry point now.

Covered here:

* the drag mime carries the slot id (intra-tab reorder) **and** the tab-path
  wire + URLs (cross-tab delivery), from one builder;
* a slot without a path stays internal-only (nothing to hand over);
* the host strip claims and parses that mime (host code cannot import a tab
  module, so the wire constant lives in ``shared/drag_mime.py``);
* a foreign-session slot id (reachable via the strip's dwell-switch) is not
  owned by this tab and falls through to the external drop path.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QPoint

from shared.drag_mime import WORKSPACE_TAB_PATHS_MIME
from tabs.multi_compare.canvas.interaction import build_internal_drag_mime
from tabs.multi_compare.models import CompareSlot, MultiCompareState
from tabs.multi_compare.ui import drag_drop
from tabs.multi_compare.ui.canvas_widget import INTERNAL_SLOT_MIME
from ui.main_window.tab_strip_drop import has_card_mime, parse_card_paths


def _image(tmp_path) -> Path:
    img = tmp_path / "slot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    return img


def test_slot_drag_mime_carries_slot_id_and_image_path(tmp_path):
    img = _image(tmp_path)
    mime = build_internal_drag_mime(3, img)

    assert bytes(mime.data(INTERNAL_SLOT_MIME)).decode("utf-8") == "3"
    assert mime.hasFormat(WORKSPACE_TAB_PATHS_MIME)
    assert [u.toLocalFile() for u in mime.urls()] == [str(img)]

    # Host strip: claims the wire and parses the paths (same code path the
    # gallery-card drag uses — no second router).
    assert has_card_mime(mime) is True
    assert parse_card_paths(mime) == [img]


def test_slot_drag_without_path_stays_internal_only():
    mime = build_internal_drag_mime(3, None)

    assert mime.hasFormat(INTERNAL_SLOT_MIME)
    assert not mime.hasFormat(WORKSPACE_TAB_PATHS_MIME)
    assert mime.urls() == []
    assert has_card_mime(mime) is False


def _widget(slot_ids=(3,)) -> SimpleNamespace:
    slots = [CompareSlot(id=sid, path=None, label=f"S{sid}") for sid in slot_ids]
    return SimpleNamespace(state=MultiCompareState(slots=slots))


def test_own_slot_id_is_owned(tmp_path):
    widget = _widget((3,))
    mime = build_internal_drag_mime(3, _image(tmp_path))

    assert drag_drop.owned_internal_source_slot_id(widget, mime) == 3


def test_foreign_slot_id_is_not_owned(tmp_path):
    """Another session's slot id must not drive this tab's internal reorder."""
    widget = _widget((3,))
    mime = build_internal_drag_mime(99, _image(tmp_path))

    assert drag_drop.owned_internal_source_slot_id(widget, mime) is None


def _enter_event(mime):
    record = SimpleNamespace(methods=[], drop_action=None)

    event = SimpleNamespace(
        position=lambda: SimpleNamespace(toPoint=lambda: QPoint(4, 4)),
        mimeData=lambda: mime,
        acceptProposedAction=lambda: record.methods.append("acceptProposedAction"),
        setDropAction=lambda action: (
            record.methods.append("setDropAction"),
            setattr(record, "drop_action", action),
        ),
        accept=lambda: record.methods.append("accept"),
        ignore=lambda: record.methods.append("ignore"),
    )
    return event, record


def test_foreign_slot_drag_enters_as_an_external_image_drop(tmp_path):
    """A drag from another Multi Compare tab lands as a new image, never a move.

    Without the ownership guard the foreign slot id would be handed to this
    session's internal-move reducer (wrong slot or no-op); with it, the enter
    is negotiated as the external URL path (CopyAction).
    """
    widget = _widget((3,))
    widget.canvas = SimpleNamespace(
        mapFrom=lambda _w, pos: pos,
        compute_drop_target=lambda _pos: (None, None, True, None),
    )
    widget.store = SimpleNamespace(dispatch=lambda _action: None)
    widget._pending_duplicate_source = None
    widget._pending_paste_paths = None
    mime = build_internal_drag_mime(99, _image(tmp_path))

    event, record = _enter_event(mime)
    drag_drop.drag_enter_event(widget, event)

    assert "acceptProposedAction" not in record.methods
    assert "setDropAction" in record.methods
    assert record.drop_action is not None
