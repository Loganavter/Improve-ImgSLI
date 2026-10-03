"""Wave A gallery drag source: mime payload, dragged set, Move menu entry.

Covers the frozen Wave A/B seam (``GALLERY_PATHS_MIME`` payload + ``setUrls``,
selected-order dragged set, single-press case) and the ``Move`` menu rule —
without ever calling ``QDrag.exec`` offscreen (OS loop).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QPoint, QUrl
from PySide6.QtWidgets import QWidget

from tabs.image_gallery.ui.card import GALLERY_PATHS_MIME
from tabs.image_gallery.ui.card.context_actions import _action_targets, _ctx_move
from tabs.image_gallery.ui.grid_view import (
    build_gallery_drag_mime,
    dragged_paths_for_press,
    should_start_gallery_drag,
)


def _owner(selected, order=None, items=()):
    st = SimpleNamespace(
        selected_paths=set(selected),
        items=list(items),
    )
    if order is not None:
        st.selected_order = list(order)
    return SimpleNamespace(state=st)


def test_mime_constant_value() -> None:
    assert GALLERY_PATHS_MIME == "application/x-imgsli-gallery-paths"


def test_dragged_set_group_preserves_selected_order() -> None:
    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    owner = _owner({a, b, c}, order=[c, a, b])
    assert dragged_paths_for_press(owner, a) == [c, a, b]


def test_dragged_set_single_press_outside_selection() -> None:
    a, b = Path("/a.png"), Path("/b.png")
    owner = _owner({a}, order=[a])
    assert dragged_paths_for_press(owner, b) == [b]


def test_mime_carries_exact_set_in_order() -> None:
    paths = [Path("/c.png"), Path("/a.png"), Path("/b.png")]
    mime = build_gallery_drag_mime(paths)
    raw = bytes(mime.data(GALLERY_PATHS_MIME)).decode("utf-8")
    expect = [QUrl.fromLocalFile(str(p)).toString() for p in paths]
    assert raw.split("\n") == expect


def test_mime_set_urls_equal_same_files() -> None:
    paths = [Path("/c.png"), Path("/a.png")]
    mime = build_gallery_drag_mime(paths)
    urls = [u.toLocalFile() for u in mime.urls()]
    assert urls == [str(p) for p in paths]


def test_mime_single_press_case_is_one_path() -> None:
    (only,) = [Path("/solo.png")]
    mime = build_gallery_drag_mime([only])
    assert bytes(mime.data(GALLERY_PATHS_MIME)).decode("utf-8") == QUrl.fromLocalFile(
        str(only)
    ).toString()
    assert [u.toLocalFile() for u in mime.urls()] == [str(only)]


def test_drag_threshold_gates_kickoff(qtbot) -> None:
    _w = QWidget()
    qtbot.addWidget(_w)
    assert should_start_gallery_drag(QPoint(0, 0), QPoint(0, 0)) is False
    assert should_start_gallery_drag(None, QPoint(5, 5)) is False
    assert should_start_gallery_drag(QPoint(0, 0), QPoint(5000, 5000)) is True


def _capture_menu(monkeypatch):
    import sli_ui_toolkit.widgets as _w
    import ui.context_menu.manager as _mgr

    captured: dict = {}

    class _FakeMenu:
        def __init__(self, parent, *, entries=(), on_triggered=None, **kwargs):
            captured["entries"] = tuple(entries)
            captured["on_triggered"] = on_triggered

        def popup_at(self, pos):
            captured["popup_at"] = pos

        def show(self):
            captured["shown"] = True

    def _fake_open(*, source_widget, global_pos, entries, key, on_triggered=None):
        captured["entries"] = tuple(entries)
        captured["on_triggered"] = on_triggered
        captured["key"] = key
        return _FakeMenu(source_widget, entries=entries, on_triggered=on_triggered)

    monkeypatch.setattr(_mgr, "open_context_menu_entries", _fake_open)
    monkeypatch.setattr(_w, "ContextMenu", _FakeMenu)
    return captured


def _action_ids(entries) -> list[str]:
    from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSection

    ids: list[str] = []
    for e in entries:
        if isinstance(e, ContextMenuSection):
            ids.extend(a.action_id for a in e.entries)
        elif isinstance(e, ContextMenuAction):
            ids.append(e.action_id)
    return ids


def test_menu_move_absent_with_selection(monkeypatch) -> None:
    """Move lives in drag-only now — no menu entry even with a selection."""
    from tabs.image_gallery.ui.card.context_menu import popup_gallery_card_context_menu

    captured = _capture_menu(monkeypatch)
    owner = _owner({Path("/a.png")})
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=1,
    )
    assert "gallery.selection.move" not in _action_ids(captured["entries"])


def test_menu_move_absent_without_selection(monkeypatch) -> None:
    from tabs.image_gallery.ui.card.context_menu import popup_gallery_card_context_menu

    captured = _capture_menu(monkeypatch)
    owner = _owner(set())
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=0,
    )
    assert "gallery.selection.move" not in _action_ids(captured["entries"])


def test_menu_move_empty_selection_no_carry() -> None:
    """Empty selection → Move starts nothing (False, no exception)."""
    owner = _owner(set())
    assert _ctx_move(owner, Path("/a.png")) is False


def test_menu_move_single_missing_file_no_carry() -> None:
    owner = _owner(set())
    assert _ctx_move(owner, Path("/does/not/exist.png")) is False


def test_menu_move_group_routes_carry_selected(monkeypatch) -> None:
    from tabs.image_gallery.use_cases import carry as _carry

    seen: list = []
    monkeypatch.setattr(
        _carry, "carry_selected", lambda o, **kw: seen.append(o) or True
    )
    a, b = Path("/a.png"), Path("/b.png")
    owner = _owner({a, b}, order=[b, a])
    assert _ctx_move(owner, a) is True
    assert seen == [owner]


def test_menu_move_single_never_mutates_selection(tmp_path) -> None:
    target = tmp_path / "lone.png"
    target.write_bytes(b"fake")
    a = tmp_path / "other.png"
    before = {a}
    owner = _owner(set(before), order=[a])
    # No carry service in unit context → False, but selection must be intact.
    assert _ctx_move(owner, target) is False
    assert set(owner.state.selected_paths) == before
    assert list(owner.state.selected_order) == [a]


def test_build_card_drag_arms_single_selection(qtbot) -> None:
    """Unselected press → dispatch-only arm (controller.set_selection), then QDrag."""
    from tabs.image_gallery.ui.grid_view import GalleryGridView

    view = GalleryGridView()
    qtbot.addWidget(view)
    armed: list = []

    class _FakeOwner:
        def __init__(self):
            self.state = SimpleNamespace(
                selected_paths={Path("/a.png")},
                selected_order=[Path("/a.png")],
                items=[],
            )

        def set_selection(self, paths):
            armed.append([str(p) for p in paths])
            self.state.selected_paths = {Path(p) for p in paths}
            self.state.selected_order = [Path(p) for p in paths]

    fake_owner = _FakeOwner()
    view._gallery_widget = SimpleNamespace(_owner_for_triage=lambda: fake_owner)
    view.note_card_press(Path("/b.png"), QPoint(0, 0))
    card = QWidget()
    qtbot.addWidget(card)
    drag = view.build_card_drag(card, QPoint(5000, 5000))
    assert drag is not None
    assert armed == [["/b.png"]]
    raw = bytes(drag.mimeData().data(GALLERY_PATHS_MIME)).decode("utf-8")
    assert raw == QUrl.fromLocalFile("/b.png").toString()


def test_build_card_drag_group_press_keeps_selection(qtbot) -> None:
    """Selected press → whole selection in order, no re-arm."""
    from tabs.image_gallery.ui.grid_view import GalleryGridView

    view = GalleryGridView()
    qtbot.addWidget(view)
    armed: list = []

    class _FakeOwner:
        def __init__(self):
            self.state = SimpleNamespace(
                selected_paths={Path("/a.png"), Path("/b.png")},
                selected_order=[Path("/b.png"), Path("/a.png")],
                items=[],
            )

        def set_selection(self, paths):
            armed.append([str(p) for p in paths])

    fake_owner = _FakeOwner()
    view._gallery_widget = SimpleNamespace(_owner_for_triage=lambda: fake_owner)
    view.note_card_press(Path("/a.png"), QPoint(10, 10))
    card = QWidget()
    qtbot.addWidget(card)
    drag = view.build_card_drag(card, QPoint(9000, 9000))
    assert drag is not None
    assert armed == []
    raw = bytes(drag.mimeData().data(GALLERY_PATHS_MIME)).decode("utf-8").split("\n")
    assert raw == [
        QUrl.fromLocalFile("/b.png").toString(),
        QUrl.fromLocalFile("/a.png").toString(),
    ]


def test_build_card_drag_below_threshold_is_none(qtbot) -> None:
    from tabs.image_gallery.ui.grid_view import GalleryGridView

    view = GalleryGridView()
    qtbot.addWidget(view)
    view._gallery_widget = SimpleNamespace(
        _owner_for_triage=lambda: _owner({Path("/a.png")})
    )
    view.note_card_press(Path("/a.png"), QPoint(0, 0))
    card = QWidget()
    qtbot.addWidget(card)
    assert view.build_card_drag(card, QPoint(0, 0)) is None


def test_action_targets_mirror_reject_rule() -> None:
    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    owner = _owner({a, b}, order=[b, a])
    assert _action_targets(owner, a) == [b, a]
    assert _action_targets(owner, c) == [c]
