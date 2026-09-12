"""Export paste resolves clipboard_paste_service against the active tab."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from plugins.export.controller import ExportController


def test_paste_prefers_active_tab_clipboard_service(monkeypatch):
    active = MagicMock()
    active.paste_image_from_clipboard.return_value = True
    fallback = MagicMock()

    monkeypatch.setattr(
        "tabs.registry.get_shared_tab_registry",
        lambda: SimpleNamespace(
            create_service=MagicMock(return_value=active),
        ),
    )

    controller = ExportController(
        store=object(),
        thread_pool=None,
        recorder=None,
        video_exporter=None,
        clipboard_service=fallback,
        video_editor_plugin=SimpleNamespace(
            create_control_flows=lambda _self: (MagicMock(), MagicMock())
        ),
        main_controller=object(),
    )

    assert controller.paste_image_from_clipboard() is True
    active.paste_image_from_clipboard.assert_called_once()
    fallback.paste_image_from_clipboard.assert_not_called()


def test_paste_falls_back_when_active_tab_has_no_service(monkeypatch):
    fallback = MagicMock()
    fallback.paste_image_from_clipboard.return_value = True

    monkeypatch.setattr(
        "tabs.registry.get_shared_tab_registry",
        lambda: SimpleNamespace(
            create_service=MagicMock(return_value=None),
        ),
    )

    controller = ExportController(
        store=object(),
        thread_pool=None,
        recorder=None,
        video_exporter=None,
        clipboard_service=fallback,
        video_editor_plugin=SimpleNamespace(
            create_control_flows=lambda _self: (MagicMock(), MagicMock())
        ),
        main_controller=object(),
    )

    assert controller.paste_image_from_clipboard() is True
    fallback.paste_image_from_clipboard.assert_called_once()
