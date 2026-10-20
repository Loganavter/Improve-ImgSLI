"""``capture_surface`` devtool: import and ``--list`` need no X display.

The tool drives production widgets on a private X display; simply importing
it or asking for the surface catalogue must not open a display (agents call
``--list`` to discover names). Falsification: the module is new — a base
checkout has no ``src/devtools/capture_surface.py`` to import.
"""

from __future__ import annotations

import importlib

import pytest

EXPECTED_SURFACES = {
    "settings",
    "settings-keyboard",
    "gallery",
    "gallery-populated",
    "multi",
    "multi-populated",
    "session-picker",
    "onboarding",
}


@pytest.fixture
def _no_display(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)


def test_import_does_not_need_display(_no_display):
    module = importlib.import_module("devtools.capture_surface")
    assert EXPECTED_SURFACES <= set(module.SURFACES)
    # QRhi/GL surfaces are isolated (run in an offscreen child) so a hard
    # QRhi exit cannot take the tool down.
    assert module.SURFACES["multi"].isolated
    assert module.SURFACES["multi-populated"].isolated


def test_list_enumerates_surfaces_without_display(_no_display, capsys):
    from devtools.capture_surface import main

    assert main(["--list"]) == 0
    out = capsys.readouterr().out
    for name in EXPECTED_SURFACES:
        assert name in out, f"{name} missing from --list output"


def test_missing_display_errors_clearly(_no_display, capsys):
    from devtools.capture_surface import main

    with pytest.raises(SystemExit) as exc:
        main(["settings"])
    assert exc.value.code == 2
    assert "Xvfb" in capsys.readouterr().err


def test_unknown_surface_needs_no_display(_no_display, capsys):
    from devtools.capture_surface import main

    # Unknown-surface validation happens before the display check.
    assert main(["no-such-surface"]) == 2
    assert "unknown surface" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Size pins (offscreen Qt — no display needed; grab only rasterizes the widget)
# ---------------------------------------------------------------------------


def _app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _image_size(path):
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def test_grab_reapplies_the_pin_after_the_show_path_shrinks_the_window(tmp_path):
    """``resize`` before ``show`` is a request; the show path can undo it.

    Mirrors the live onboarding overlay (pinned 1000x684, grabbed 1000x648):
    its show path returns a shorter frame, so the pin must be applied again
    once the window is up — without resampling pixels afterwards.
    """
    from PySide6.QtWidgets import QWidget

    from devtools.capture_surface import CaptureSession

    class Shrinking(QWidget):
        def showEvent(self, event):  # noqa: N802 - Qt API
            super().showEvent(event)
            self.resize(320, 200)

    session = CaptureSession(_app(), tmp_path / "out", width=400, height=300)
    shot = session.grab(Shrinking(), "pin.png", 10, 10, delay=0)

    assert _image_size(shot) == (400, 300)
    assert session.last_pin == (400, 300)
    assert session.last_size == (400, 300)


def test_pin_application_reports_the_size_a_fixed_surface_keeps(tmp_path):
    """A surface that refuses the pin reports its own size instead of faking."""
    from PySide6.QtWidgets import QWidget

    from devtools.capture_surface import CaptureSession

    widget = QWidget()
    widget.setFixedSize(120, 90)
    session = CaptureSession(_app(), tmp_path / "out")

    assert session.apply_size(widget, 400, 300, delay=0) == (120, 90)


def test_pin_application_corrects_a_shells_constant_frame_margin(tmp_path):
    """The pin names the grabbed frame, not the shell's content box.

    CSD dialogs resize their content and keep their own margins, so the frame
    lands a constant offset off the request (the settings dialog: +16 px per
    axis). The measured offset must be corrected once — and only kept when the
    frame really equals the pin.
    """
    from PySide6.QtWidgets import QWidget

    from devtools.capture_surface import CaptureSession

    class Chromed(QWidget):
        MARGIN = 8

        def resize(self, width, height=None):
            if height is None:
                width, height = width.width(), width.height()
            super().resize(width + 2 * self.MARGIN, height + 2 * self.MARGIN)

    widget = Chromed()
    session = CaptureSession(_app(), tmp_path / "out")

    assert session.apply_size(widget, 400, 300, delay=0) == (400, 300)
    assert (widget.width(), widget.height()) == (400, 300)


def test_grab_records_a_refused_pin_instead_of_resampling(tmp_path):
    from PySide6.QtWidgets import QWidget

    from devtools.capture_surface import CaptureSession

    widget = QWidget()
    widget.setFixedSize(120, 90)
    session = CaptureSession(_app(), tmp_path / "out", width=400, height=300)

    shot = session.grab(widget, "fixed.png", 10, 10, delay=0)

    assert _image_size(shot) == (120, 90), "the grab must stay the surface's real frame"
    assert session.last_pin == (400, 300)
    assert session.last_size == (120, 90)
