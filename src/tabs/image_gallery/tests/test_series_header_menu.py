"""Series-header right-click menu: Ask AI / Rename / Delete + Reset/Re-cluster.

Right-click on a series header Button opens a single toolkit ``ContextMenu``:
Ask AI, Rename (session-only custom series name), Delete (remove the whole
series from the grid — files on disk stay), then Reset manual series /
Re-cluster series as the tail. The popup is parented to the header Button,
never the MainWindow (Wayland compositing trap — see the card menu).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QPoint

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _item(path: str, series_id: str | None = "series_1", rank: int | None = 1) -> GalleryItem:
    return GalleryItem(path=Path(path), mtime_ns=1, series_id=series_id, rank=rank)


def _capture_entries(monkeypatch) -> dict:
    """Capture entries + on_triggered from the manager without showing UI."""
    import ui.context_menu.manager as _mgr

    captured: dict = {}

    def _fake_open(*, source_widget, global_pos, entries, key, on_triggered=None, **_kwargs):
        captured["entries"] = tuple(entries)
        captured["on_triggered"] = on_triggered
        captured["source_widget"] = source_widget
        captured["key"] = key
        return SimpleNamespace()

    monkeypatch.setattr(_mgr, "open_context_menu_entries", _fake_open)
    return captured


def _action_ids(entries) -> list[str]:
    from sli_ui_toolkit.widgets import ContextMenuAction

    return [e.action_id for e in entries if isinstance(e, ContextMenuAction)]


def _action(entries, action_id: str):
    from sli_ui_toolkit.widgets import ContextMenuAction

    for e in entries:
        if isinstance(e, ContextMenuAction) and e.action_id == action_id:
            return e
    raise AssertionError(f"{action_id} entry missing")


def _widget(qtbot, controller=None) -> ImageGalleryWidget:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w._attached_controller = controller
    return w


def test_series_menu_has_three_actions_then_series_tools(qtbot, monkeypatch) -> None:
    captured = _capture_entries(monkeypatch)
    ctrl = SimpleNamespace(
        open_ask_ai_for_series=lambda *a, **k: None,
        reset_series_overrides=lambda: None,
        recluster_series=lambda: None,
    )
    w = _widget(qtbot, ctrl)

    w._on_series_context_menu(
        0, w, (Path("/a.png"), Path("/b.png")), "SER", "series_1", QPoint(5, 5)
    )

    ids = _action_ids(captured["entries"])
    assert ids == [
        "gallery.series.ask_ai",
        "gallery.series.rename",
        "gallery.series.delete",
        "gallery.series.reset",
        "gallery.series.recluster",
    ]
    assert captured["source_widget"] is w  # parent = content widget, not window


def test_series_menu_tail_hidden_without_controller_capability(qtbot, monkeypatch) -> None:
    captured = _capture_entries(monkeypatch)
    w = _widget(qtbot)  # bare widget: no reset/recluster capability

    w._on_series_context_menu(0, w, (Path("/a.png"),), "SER", "series_1", None)

    ids = _action_ids(captured["entries"])
    assert ids == [
        "gallery.series.ask_ai",
        "gallery.series.rename",
        "gallery.series.delete",
    ]


def test_rename_disabled_without_series_id(qtbot, monkeypatch) -> None:
    captured = _capture_entries(monkeypatch)
    w = _widget(qtbot)

    w._on_series_context_menu(0, w, (Path("/a.png"),), "SER", None, None)

    assert _action(captured["entries"], "gallery.series.rename").enabled is False


def test_delete_action_removes_whole_series_from_grid(qtbot, monkeypatch) -> None:
    from tabs.image_gallery.use_cases import triage as _triage

    captured = _capture_entries(monkeypatch)
    calls: list = []
    monkeypatch.setattr(
        _triage, "remove_paths_from_grid",
        lambda o, ps: calls.append(("batch", sorted(str(p) for p in ps))) or 2,
    )
    monkeypatch.setattr(
        _triage, "remove_from_grid",
        lambda o, p: calls.append(("single", str(p))) or True,
    )
    w = _widget(qtbot)

    # Two members → batch path.
    w._on_series_context_menu(
        0, w, (Path("/a.png"), Path("/b.png")), "SER", "series_1", None
    )
    captured["on_triggered"]("gallery.series.delete", None)
    assert calls == [("batch", ["/a.png", "/b.png"])]

    # One member → single path (no batch call).
    calls.clear()
    w._on_series_context_menu(0, w, (Path("/a.png"),), "SER", "series_1", None)
    captured["on_triggered"]("gallery.series.delete", None)
    assert calls == [("single", "/a.png")]


def test_ask_ai_action_delegates_to_controller(qtbot, monkeypatch) -> None:
    captured = _capture_entries(monkeypatch)
    got: list = []
    ctrl = SimpleNamespace(
        open_ask_ai_for_series=lambda idx, anchor, paths, label: got.append(
            (idx, tuple(paths), label)
        )
    )
    w = _widget(qtbot, ctrl)

    w._on_series_context_menu(
        2, w, (Path("/a.png"), Path("/b.png")), "MY SERIES", "series_1", None
    )
    captured["on_triggered"]("gallery.series.ask_ai", None)
    assert got == [(2, (Path("/a.png"), Path("/b.png")), "MY SERIES")]


def test_reset_and_recluster_actions_call_controller(qtbot, monkeypatch) -> None:
    captured = _capture_entries(monkeypatch)
    calls: list = []
    ctrl = SimpleNamespace(
        reset_series_overrides=lambda: calls.append("reset"),
        recluster_series=lambda: calls.append("recluster"),
    )
    w = _widget(qtbot, ctrl)

    w._on_series_context_menu(0, w, (Path("/a.png"),), "SER", "series_1", None)
    captured["on_triggered"]("gallery.series.reset", None)
    captured["on_triggered"]("gallery.series.recluster", None)
    assert calls == ["reset", "recluster"]


def test_rename_stores_session_name_and_repaints_header(qtbot, monkeypatch) -> None:
    from shared_toolkit.ui.text_input_dialog import AppTextInputDialog

    captured = _capture_entries(monkeypatch)
    monkeypatch.setattr(
        AppTextInputDialog,
        "get_text",
        classmethod(lambda cls, *a, **k: ("My Name", True)),
    )
    w = _widget(qtbot)
    a1, a2 = _item("/g/a.png", series_id="series_1"), _item("/g/b.png", series_id="series_1")
    w._series = [[a1, a2]]
    w._items = [a1, a2]

    w._on_series_context_menu(0, w, (a1.path, a2.path), "SER", "series_1", None)
    captured["on_triggered"]("gallery.series.rename", None)

    assert w._series_names["series_1"] == "My Name"
    assert w._grid_view._hub_names[0] == "My Name"


def test_rename_cancel_keeps_derived_name(qtbot, monkeypatch) -> None:
    from shared_toolkit.ui.text_input_dialog import AppTextInputDialog

    captured = _capture_entries(monkeypatch)
    monkeypatch.setattr(
        AppTextInputDialog,
        "get_text",
        classmethod(lambda cls, *a, **k: ("Ignored", False)),
    )
    w = _widget(qtbot)

    w._on_series_context_menu(0, w, (Path("/a.png"),), "SER", "series_1", None)
    captured["on_triggered"]("gallery.series.rename", None)

    assert "series_1" not in w._series_names


def test_compute_hub_names_prefers_override_and_uppercases_hub(qtbot) -> None:
    w = _widget(qtbot)
    a1, a2 = _item("/g/a.png", series_id="series_1"), _item("/g/b.png", series_id="series_1")
    b1, b2 = _item("/g/c.png", series_id="series_2"), _item("/g/d.png", series_id="series_2", rank=2)

    assert w._compute_series_hub_names([[a1, a2], [b1, b2]]) == ["A.PNG", "C.PNG"]

    w._series_names["series_1"] = "Custom"
    assert w._compute_series_hub_names([[a1, a2], [b1, b2]]) == ["Custom", "C.PNG"]
