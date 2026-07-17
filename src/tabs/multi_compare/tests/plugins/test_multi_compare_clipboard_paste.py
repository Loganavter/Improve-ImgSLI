"""multi_compare paste uses cursor DnD placement, not auto-add."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import tabs.multi_compare.services.clipboard as clipboard_mod
from shared.clipboard_images import _dedupe_clipboard_items
from tabs.multi_compare.services.clipboard import ClipboardService


def test_clipboard_paths_are_deduped():
    assert _dedupe_clipboard_items(
        ["/tmp/a.png", "/tmp/a.png", "/tmp/./a.png", "https://x/y"]
    ) == ["/tmp/a.png", "https://x/y"]


def test_paste_starts_pending_dnd_placement(monkeypatch, tmp_path):
    image_path = tmp_path / "a.png"
    image_path.write_bytes(b"not-a-real-png")

    monkeypatch.setattr(
        clipboard_mod,
        "collect_clipboard_image_items",
        lambda: [str(image_path)],
    )

    controller = MagicMock()
    store = SimpleNamespace(settings=SimpleNamespace(current_language="en"))
    main = SimpleNamespace(error_occurred=MagicMock(), thread_pool=None)

    service = ClipboardService(store, main, controller)
    assert service.paste_image_from_clipboard() is True

    controller.begin_paste_placement.assert_called_once_with([Path(image_path)])
    controller.load_images.assert_not_called()


def test_paste_does_not_use_direction_overlay(monkeypatch, tmp_path):
    image_path = tmp_path / "b.png"
    image_path.write_bytes(b"x")

    monkeypatch.setattr(
        clipboard_mod,
        "collect_clipboard_image_items",
        lambda: [str(image_path)],
    )

    controller = MagicMock()
    store = SimpleNamespace(settings=SimpleNamespace(current_language="en"))
    service = ClipboardService(store, None, controller)

    assert not hasattr(service, "show_paste_direction_dialog")
    assert service.paste_image_from_clipboard() is True
    controller.begin_paste_placement.assert_called_once()


def test_create_service_wires_clipboard_paste():
    from tabs.multi_compare.tab import MultiCompareTab

    tab = MultiCompareTab()
    controller = MagicMock()
    tab._controller = controller

    service = tab.create_service(
        "clipboard_paste_service",
        SimpleNamespace(settings=SimpleNamespace(current_language="en")),
        None,
    )
    assert isinstance(service, ClipboardService)
    assert service.controller is controller


def test_pending_paste_emits_images_dropped_like_file_dnd(monkeypatch):
    from tabs.multi_compare.widget import MultiCompareWidget

    widget = MultiCompareWidget.__new__(MultiCompareWidget)
    widget._pending_paste_paths = [Path("/tmp/a.png")]
    emitted: list = []
    widget.images_dropped = SimpleNamespace(
        emit=lambda *args: emitted.append(args)
    )

    widget._finalize_pending_paste((0,), "right", False)

    assert emitted == [([Path("/tmp/a.png")], ((0,), False), "right")]


def test_pending_paste_on_empty_canvas_emits_target_root():
    """Empty grid has no side; paste must still drop as target_root (like DnD)."""
    from tabs.multi_compare.widget import MultiCompareWidget

    widget = MultiCompareWidget.__new__(MultiCompareWidget)
    widget._pending_paste_paths = [Path("/tmp/a.png")]
    emitted: list = []
    widget.images_dropped = SimpleNamespace(
        emit=lambda *args: emitted.append(args)
    )

    widget._finalize_pending_paste(None, None, True)

    assert emitted == [([Path("/tmp/a.png")], (None, True), None)]


def test_pending_paste_without_side_or_root_is_ignored():
    from tabs.multi_compare.widget import MultiCompareWidget

    widget = MultiCompareWidget.__new__(MultiCompareWidget)
    widget._pending_paste_paths = [Path("/tmp/a.png")]
    emitted: list = []
    widget.images_dropped = SimpleNamespace(
        emit=lambda *args: emitted.append(args)
    )

    widget._finalize_pending_paste(None, None, False)

    assert emitted == []
