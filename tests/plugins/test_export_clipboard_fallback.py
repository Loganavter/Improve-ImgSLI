"""The startup clipboard fallback is optional — its absence must not kill startup.

Red-before (2026-10-25): ``_create_clipboard_service`` raised
``RuntimeError("No tab provides clipboard_paste_service...")`` whenever no tab
could answer, which is the *normal* cold-start state — a freshly discovered tab
has no controller, so ``build_clipboard_service`` returns ``None``. The raise
aborted ``MainController.attach_deferred_plugins`` mid-loop (``help`` and
``image_properties`` never attached) and, once the deferred block moved past the
first frame (app #659), surfaced as the user-visible "Report a problem" dialog
on every cold start.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.log_names import APP_LOGGER_NAME
from plugins.export.controller import ExportController
from plugins.export.plugin import ExportPlugin


class _NoAnswerRegistry:
    """A registry whose tabs cannot answer (cold start: no tab page/controller)."""

    def discover(self, *args, **kwargs):
        return None

    def create_startup_service(self, *args, **kwargs):
        return None


def test_missing_startup_clipboard_service_warns_instead_of_raising(
    monkeypatch, caplog
):
    plugin = ExportPlugin()
    plugin.store = object()
    monkeypatch.setattr("tabs.registry.TabRegistry", _NoAnswerRegistry)

    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        service = plugin._create_clipboard_service(object())

    assert service is None
    assert "clipboard_paste_service" in caplog.text


def test_configure_controller_survives_a_cold_start(monkeypatch):
    """The exact crash path: configure_controller with no clipboard provider."""

    class _VideoEditor(SimpleNamespace):
        def create_recording_services(self, **_kwargs):
            return MagicMock(name="recorder"), MagicMock(name="video_exporter")

        def create_control_flows(self, _controller):
            return MagicMock(name="recording_flow"), MagicMock(name="video_export_flow")

    plugin = ExportPlugin()
    plugin.store = object()
    plugin.thread_pool = None
    plugin.event_bus = None
    plugin.video_editor_plugin = _VideoEditor()
    monkeypatch.setattr("tabs.registry.TabRegistry", _NoAnswerRegistry)

    plugin.configure_controller(main_controller=None, presenter=None)

    assert plugin.controller is not None
    assert plugin.clipboard_service is None


def test_paste_returns_false_when_nothing_supplies_the_service(monkeypatch):
    monkeypatch.setattr(
        "tabs.registry.get_shared_tab_registry",
        lambda: SimpleNamespace(create_service=MagicMock(return_value=None)),
    )
    controller = ExportController(
        store=object(),
        thread_pool=None,
        recorder=None,
        video_exporter=None,
        clipboard_service=None,
        video_editor_plugin=SimpleNamespace(
            create_control_flows=lambda _self: (MagicMock(), MagicMock())
        ),
        main_controller=object(),
    )

    assert controller.paste_image_from_clipboard() is False
