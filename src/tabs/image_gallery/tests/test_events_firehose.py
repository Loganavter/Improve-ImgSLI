"""Raw input firehose (DEBUGGING.md rule 5): gated, never consumes."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtWidgets import QWidget

from tabs.image_gallery.ui.events_firehose import _EventsFirehose, install_events_firehose
from core.log_names import APP_LOGGER_NAME


def _fake_event(kind: QEvent.Type):
    return SimpleNamespace(
        type=lambda: kind,
        globalPosition=lambda: QPoint(11, 22),
        buttons=lambda: 0,
    )


def test_firehose_logs_and_never_consumes(qtbot, caplog, monkeypatch) -> None:
    import logging

    monkeypatch.setenv("IMGSLI_GALLERY_EVENTS_DEBUG", "1")
    w = QWidget()
    qtbot.addWidget(w)
    w.setObjectName("probe-host")
    filt = _EventsFirehose()
    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        assert filt.eventFilter(w, _fake_event(QEvent.Type.MouseButtonPress)) is False
        assert filt.eventFilter(w, _fake_event(QEvent.Type.Enter)) is False
    text = caplog.text
    assert "[gallery-events]" in text
    assert "MouseButtonPress" in text
    assert "probe-host" in text
    assert "(11,22)" in text


def test_firehose_off_by_default(qtbot, caplog, monkeypatch) -> None:
    import logging

    monkeypatch.delenv("IMGSLI_GALLERY_EVENTS_DEBUG", raising=False)
    w = QWidget()
    qtbot.addWidget(w)
    filt = _EventsFirehose()
    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        filt.eventFilter(w, _fake_event(QEvent.Type.Enter))
    assert "[gallery-events]" not in caplog.text


def test_installer_idempotent_and_gated(qtbot, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication

    monkeypatch.delenv("IMGSLI_GALLERY_EVENTS_DEBUG", raising=False)
    assert install_events_firehose() is False
    monkeypatch.setenv("IMGSLI_GALLERY_EVENTS_DEBUG", "1")
    assert install_events_firehose() is True
    assert install_events_firehose() is True
    app = QApplication.instance()
    assert bool(getattr(app, "_gallery_events_firehose", False)) is True
