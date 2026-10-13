"""IC paste routes collect/split/download through ClipboardPasteCoordinator.

Direction dialog stays (overlay site), placement lands in the chosen slot.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import shared.clipboard_paste as paste_mod
import tabs.image_compare.services.clipboard as ic_clipboard_mod
from tabs.image_compare.services.clipboard import ClipboardService


def _make_service(main=None, widget=None):
    store = SimpleNamespace(
        settings=SimpleNamespace(current_language="en"),
        viewport=SimpleNamespace(view_state=SimpleNamespace(is_horizontal=True)),
    )
    if widget is None:
        widget = SimpleNamespace(image_label=MagicMock())
    return ClipboardService(store, main, widget)


def test_paste_local_file_direction_selects_slot(monkeypatch, tmp_path):
    image_path = tmp_path / "a.png"
    image_path.write_bytes(b"not-a-real-png")

    monkeypatch.setattr(
        ic_clipboard_mod, "collect_clipboard_image_items", lambda: [str(image_path)]
    )

    sessions = SimpleNamespace(load_images_from_paths=MagicMock())
    main = SimpleNamespace(
        error_occurred=MagicMock(),
        sessions=sessions,
        thread_pool=None,
        window_shell=SimpleNamespace(main_window_app=MagicMock()),
    )
    service = _make_service(main)

    captured: dict = {}

    def fake_overlay(*, on_direction, **kwargs):
        captured["on_direction"] = on_direction
        return MagicMock(isVisible=lambda: True)

    monkeypatch.setattr(
        "services.system.paste_direction_overlay.show_paste_direction_overlay",
        fake_overlay,
    )

    assert service.paste_image_from_clipboard() is True
    assert "on_direction" in captured

    captured["on_direction"]("left")
    sessions.load_images_from_paths.assert_called_once_with([str(image_path)], 1)

    captured["on_direction"]("right")
    assert sessions.load_images_from_paths.call_count == 2
    sessions.load_images_from_paths.assert_called_with([str(image_path)], 2)


def test_paste_url_download_combined_into_slot(monkeypatch, tmp_path):
    local = tmp_path / "a.png"
    local.write_bytes(b"not-a-real-png")
    downloaded = tmp_path / "url.png"
    downloaded.write_bytes(b"downloaded")

    monkeypatch.setattr(
        ic_clipboard_mod,
        "collect_clipboard_image_items",
        lambda: [str(local), "https://x/y.png"],
    )
    monkeypatch.setattr(
        paste_mod, "download_images_from_urls", lambda urls, timeout: [str(downloaded)]
    )

    sessions = SimpleNamespace(load_images_from_paths=MagicMock())
    main = SimpleNamespace(
        error_occurred=MagicMock(),
        sessions=sessions,
        thread_pool=None,
        window_shell=SimpleNamespace(main_window_app=MagicMock()),
    )
    service = _make_service(main)

    captured: dict = {}

    def fake_overlay(*, on_direction, **kwargs):
        captured["on_direction"] = on_direction
        return MagicMock(isVisible=lambda: True)

    monkeypatch.setattr(
        "services.system.paste_direction_overlay.show_paste_direction_overlay",
        fake_overlay,
    )

    assert service.paste_image_from_clipboard() is True
    captured["on_direction"]("down")

    sessions.load_images_from_paths.assert_called_once_with(
        [str(local), str(downloaded)], 2
    )
    assert main.error_occurred.emit.called  # loading toast via coordinator hook


def test_paste_empty_clipboard_emits_no_image(monkeypatch):
    monkeypatch.setattr(ic_clipboard_mod, "collect_clipboard_image_items", lambda: [])

    main = SimpleNamespace(error_occurred=MagicMock())
    service = _make_service(main)

    assert service.paste_image_from_clipboard() is False
    assert main.error_occurred.emit.called


def test_paste_delegates_split_download_to_coordinator(monkeypatch, tmp_path):
    """IC must delegate split/download to the coordinator (B2 dedup).

    Stubs out the coordinator: if the service did its own split/worker
    dance, placement would still happen and this test would fail to
    observe the delegation point (``run_with_items``).
    """
    image_path = tmp_path / "a.png"
    image_path.write_bytes(b"x")
    monkeypatch.setattr(
        ic_clipboard_mod, "collect_clipboard_image_items", lambda: [str(image_path)]
    )

    placed: list = []

    def coordinator_factory(**kwargs):
        return _RecordingCoordinator(kwargs["on_ready"], placed)

    # Patch where it is looked up (service module namespace).
    monkeypatch.setattr(ic_clipboard_mod, "ClipboardPasteCoordinator", coordinator_factory)

    sessions = SimpleNamespace(load_images_from_paths=MagicMock())
    main = SimpleNamespace(
        error_occurred=MagicMock(),
        sessions=sessions,
        thread_pool=None,
        window_shell=SimpleNamespace(main_window_app=MagicMock()),
    )
    service = _make_service(main)

    captured: dict = {}

    def fake_overlay(*, on_direction, **kwargs):
        captured["on_direction"] = on_direction
        return MagicMock(isVisible=lambda: True)

    monkeypatch.setattr(
        "services.system.paste_direction_overlay.show_paste_direction_overlay",
        fake_overlay,
    )

    assert service.paste_image_from_clipboard() is True
    captured["on_direction"]("up")
    assert placed == [[Path(str(image_path))]]


class _RecordingCoordinator:
    """Minimal stand-in proving IC delegates split/download to the coordinator."""

    def __init__(self, on_ready, placed):
        self._on_ready = on_ready
        self._placed = placed

    def run_with_items(self, items):
        local, _urls = paste_mod.split_clipboard_items(items)
        self._placed.append([Path(p) for p in local])
        self._on_ready([Path(p) for p in local])
        return True
