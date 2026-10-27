"""Capture path: DPR enters exactly once, and the units are NAMED.

The 2026-10-27 defect pair this module pins. Both are unit mistakes, not
rendering bugs, so an eyeball check on a DPR=1 host cannot see them:

* ``core/control/capture.compose_rhi_frames`` multiplied the canvas anchor and
  size by the DPR **and** painted into a ``QPixmap`` that already carries its
  own ``devicePixelRatio`` (a ``QPainter`` on such a pixmap works in
  device-independent coordinates). Measured on a real ``QPainter``: a canvas
  meant for device ``(200,100)-(600,300)`` at DPR=2 landed in
  ``(400,200)-(1198,598)`` — double the offset and double the size.
* ``_clip_to_visible`` sliced a *logical* rect out of a *device*-pixel grab.
  Measured: ``QPixmap(2560x1600)`` at DPR=2, ``copy(QRect(0,0,1280,700))``
  returns ``1280x700`` device px — the top-left 1/DPR² of the window.

Every assertion carries the geometry it means (device vs logical), because
"a number is a number" is exactly what produced the bug.

Falsification story: on the pre-fix tree the ``compose_rhi_frames`` test
reports red at device ``(250,150)`` (its paint starts at ``400``) and red at
``(650,350)`` (double-scaled paint reaches it), and the ``_clip_to_visible``
test reports ``1280x700`` for a crop that must be ``2560x1400``.

Run: ``QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m pytest
tests/devtools/test_capture_dpr_units.py -q -o addopts=""``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from core.control import capture as capture_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"


def _app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# compose_rhi_frames: the painter target rect is DEVICE-INDEPENDENT
# ---------------------------------------------------------------------------


class _FakeCanvas:
    """Duck-typed ``QRhiWidget``: the compositing path touches only these."""

    def __init__(self, *, anchor, size, image, visible: bool = True) -> None:
        self._anchor = anchor
        self._size = size
        self._image = image
        self._visible = visible

    def isVisible(self) -> bool:  # noqa: N802 - Qt name
        return self._visible

    def width(self) -> int:
        return self._size[0]

    def height(self) -> int:
        return self._size[1]

    def mapToGlobal(self, _point):  # noqa: N802 - Qt name
        from PySide6.QtCore import QPoint

        return QPoint(*self._anchor)

    def grabFramebuffer(self):  # noqa: N802 - Qt name
        return self._image


class _FakeTarget:
    """A widget wearing only ``findChildren`` + ``mapFromGlobal``."""

    def __init__(self, canvases) -> None:
        self._canvases = list(canvases)

    def findChildren(self, _cls):  # noqa: N802 - Qt name
        return list(self._canvases)

    def mapFromGlobal(self, point):  # noqa: N802 - Qt name
        return point


def _solid(size, color):
    from PySide6.QtGui import QColor, QImage

    image = QImage(size[0], size[1], QImage.Format.Format_RGBA8888)
    image.fill(QColor(*color))
    return image


def test_compose_rhi_frames_paints_at_the_canvas_device_rect_on_hidpi() -> None:
    """A 200x100 logical canvas at DPR=2 fills device (200,100)-(600,300).

    ``QPixmap(1200, 800)`` with dpr 2 is a 600x400 logical grab. The canvas
    sits at logical ``(100, 50)`` and is ``200x100`` logical, so its device
    rect is ``(200,100)-(600,300)``: one offset, one size, one DPR.
    """
    from PySide6.QtGui import QColor, QPixmap

    _app()
    pixmap = QPixmap(1200, 800)
    pixmap.setDevicePixelRatio(2.0)
    pixmap.fill(QColor(0, 0, 0))
    canvas = _FakeCanvas(
        anchor=(100, 50),
        size=(200, 100),
        image=_solid((400, 200), (255, 0, 0)),
    )

    assert capture_mod.compose_rhi_frames(_FakeTarget([canvas]), pixmap) == 1

    image = pixmap.toImage()

    def red(x_device: int, y_device: int) -> int:
        return image.pixelColor(x_device, y_device).red()

    # Inside the intended device rect (x offset, y offset, both slightly in).
    assert red(250, 150) > 200, "the frame did not land at the canvas anchor"
    assert red(350, 150) > 200, "the frame did not land at the canvas anchor (y)"
    # Far corner of the intended rect: proves the SIZE is the logical one.
    assert red(550, 250) > 200, "the frame is smaller than the canvas"
    # Outside the intended rect but inside the double-scaled one the pre-fix
    # code painted: 2x offset + 2x size reached device (400,200)-(1198,598).
    assert red(650, 350) < 50, "the canvas frame was scaled by DPR twice"
    assert red(1000, 700) < 50, "the canvas frame was scaled by DPR twice (far)"


def test_compose_rhi_frames_skips_a_canvas_outside_the_logical_grab() -> None:
    """The grab rect is logical too: ``deviceIndependentSize``, not ``width()``.

    A 600x400 logical grab (1200x800 device px at DPR=2). The canvas sits at
    logical x=650 — off the grab — although 650 looks "inside" a 1200-wide
    device-number rect. Counting it as painted is wrong; painting it is
    invisible only because the painter clips.
    """
    from PySide6.QtGui import QColor, QPixmap

    _app()
    pixmap = QPixmap(1200, 800)
    pixmap.setDevicePixelRatio(2.0)
    pixmap.fill(QColor(0, 0, 0))
    canvas = _FakeCanvas(
        anchor=(650, 50),
        size=(100, 100),
        image=_solid((200, 200), (0, 255, 0)),
    )

    assert capture_mod.compose_rhi_frames(_FakeTarget([canvas]), pixmap) == 0


# ---------------------------------------------------------------------------
# _clip_to_visible: a logical rect sliced out of a device-pixel grab
# ---------------------------------------------------------------------------


def test_clip_to_visible_keeps_the_visible_part_in_device_pixels() -> None:
    """A 1280x700 logical visible rect keeps 2560x1400 device px at DPR=2."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QPainter, QPixmap

    _app()
    grab = QPixmap(2560, 1600)
    grab.setDevicePixelRatio(2.0)
    grab.fill(QColor(0, 0, 0))
    # A marker at device (1300, 750) — inside the visible half, outside the
    # top-left quarter the pre-fix code cropped. Painter coords are LOGICAL on
    # a DPR-carrying pixmap, hence the logical (650, 375) -> device (1300, 750).
    painter = QPainter(grab)
    painter.fillRect(650, 375, 20, 20, QColor(255, 0, 0))
    painter.end()

    clipped = capture_mod._clip_to_visible(grab, QRect(0, 0, 1280, 700))

    assert (clipped.width(), clipped.height()) == (2560, 1400)
    assert clipped.devicePixelRatio() == 2.0
    assert clipped.deviceIndependentSize().toSize().toTuple() == (1280, 700)
    assert clipped.toImage().pixelColor(1310, 760).red() > 200, (
        "the visible half of the grab was cropped away"
    )


# ---------------------------------------------------------------------------
# Which screen: the target's, not the application's primary
# ---------------------------------------------------------------------------


class _StubScreen:
    def __init__(self, geometry, pixmap=None) -> None:
        from PySide6.QtCore import QRect

        self._geometry = QRect(*geometry)
        self._pixmap = pixmap
        self.grab_calls: list[int] = []

    def availableGeometry(self):  # noqa: N802 - Qt name
        return self._geometry

    def grabWindow(self, win_id):  # noqa: N802 - Qt name
        self.grab_calls.append(win_id)
        return self._pixmap


class _StubWindowHandle:
    def __init__(self, screen) -> None:
        self._screen = screen

    def screen(self):
        return self._screen


class _PositionedTarget:
    """A widget on a specific screen: geometry + the screen it reports."""

    def __init__(self, *, geometry, origin, screen, raster=None) -> None:
        self._geometry = geometry
        self._origin = origin
        self._screen = screen
        self._raster = raster

    def width(self) -> int:
        return self._geometry[0]

    def height(self) -> int:
        return self._geometry[1]

    def mapToGlobal(self, _point):  # noqa: N802 - Qt name
        from PySide6.QtCore import QPoint

        return QPoint(*self._origin)

    def mapFromGlobal(self, point):  # noqa: N802 - Qt name
        return point

    def windowHandle(self):  # noqa: N802 - Qt name
        return _StubWindowHandle(self._screen)

    def screen(self):
        return self._screen

    def grab(self):
        return self._raster

    def winId(self):  # noqa: N802 - Qt name
        return 4242

    def findChildren(self, _cls):  # noqa: N802 - Qt name
        return []

    def window(self):
        return self


class _StubApp:
    def __init__(self, primary) -> None:
        self._primary = primary

    def primaryScreen(self):  # noqa: N802 - Qt name
        return self._primary


def _colored_pixmap(size, color):
    from PySide6.QtGui import QColor, QPixmap

    pixmap = QPixmap(*size)
    pixmap.fill(QColor(*color))
    return pixmap


def test_visible_geometry_uses_the_targets_screen_not_the_primary() -> None:
    """Window on a 640x480 display: the visible rect is 640x480-based.

    The window is 1000x900 at global ``(100, 50)``, so on a 640x480 screen its
    visible part is logical ``(0,0,540,430)``. The application's primary
    screen here is 800x600, which would report ``(0,0,700,550)`` — a window
    the primary screen calls "more visible" than it is.
    """
    from PySide6.QtCore import QRect

    _app()
    secondary = _StubScreen((0, 0, 640, 480))
    primary = _StubScreen((0, 0, 800, 600))
    target = _PositionedTarget(geometry=(1000, 900), origin=(100, 50), screen=secondary)

    visible, fully_visible = capture_mod._target_visible_geometry(
        _StubApp(primary), target
    )

    assert (visible.x(), visible.y(), visible.width(), visible.height()) == (
        0,
        0,
        540,
        430,
    )
    assert fully_visible is False
    assert primary.grab_calls == []


def test_grab_window_grabs_the_targets_screen_pixels() -> None:
    """The X grab asks the screen the window is on, not the primary one."""
    _app()
    secondary_pixmap = _colored_pixmap((40, 30), (255, 0, 0))
    primary_pixmap = _colored_pixmap((40, 30), (0, 255, 0))
    secondary = _StubScreen((0, 0, 640, 480), pixmap=secondary_pixmap)
    primary = _StubScreen((0, 0, 800, 600), pixmap=primary_pixmap)
    target = _PositionedTarget(
        geometry=(40, 30), origin=(0, 0), screen=secondary, raster=primary_pixmap
    )

    pixmap, method, _layers = capture_mod.grab_window(_StubApp(primary), target)

    assert method == "grabWindow", "the grab fell back to the widget raster"
    assert secondary.grab_calls == [4242]
    assert primary.grab_calls == [], "the primary screen was grabbed instead"
    assert pixmap.toImage().pixelColor(10, 10).red() > 200


# ---------------------------------------------------------------------------
# capture_surface: the pin is a LOGICAL frame, the PNG is DEVICE pixels
# ---------------------------------------------------------------------------


_HIDPI_GRAB_SCRIPT = """
import json
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget

from devtools.capture_surface import CaptureSession

app = QApplication.instance() or QApplication([])
widget = QWidget()
widget.setFixedSize(400, 300)
session = CaptureSession(app, Path({out!r}), width=400, height=300)
path = session.grab(widget, "hidpi.png", 400, 300, delay=0)
from PIL import Image

with Image.open(path) as image:
    png = list(image.size)
print("RESULT " + json.dumps({{"pin": session.last_pin, "size": session.last_size, "png": png}}))
"""


def test_capture_session_reports_the_logical_frame_on_hidpi(tmp_path) -> None:
    """At ``QT_SCALE_FACTOR=2`` a 400x300 pin grabs an 800x600 PNG, not a lie.

    ``QWidget.grab()`` returns DEVICE pixels (800x600) while ``last_pin`` is
    the LOGICAL request (400x300); comparing the two raw numbers reported
    "pin not honoured: requested 400x300, window settled at 400x300, grabbed
    800x600" and made every HiDPI capture look like a refused pin. Real DPR=2
    is produced here by a real ``QApplication`` in a child process (the QPA
    scale comes from ``QT_SCALE_FACTOR`` at app creation).
    """
    import json

    out_dir = tmp_path / "hidpi"
    out_dir.mkdir()
    script = _HIDPI_GRAB_SCRIPT.format(out=out_dir.as_posix())
    env = dict(os.environ)
    env.update(
        QT_QPA_PLATFORM="offscreen",
        QT_SCALE_FACTOR="2",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=str(SRC_ROOT),
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.split("RESULT ", 1)[1].strip())

    assert result["pin"] == [400, 300], "the pin is a logical frame"
    assert result["size"] == [400, 300], (
        f"the grabbed frame was reported in device px: {result['size']}"
    )
    assert result["png"] == [800, 600], "the PNG really is the device-pixel raster"
    assert "pin not honoured" not in proc.stderr, proc.stderr


# ---------------------------------------------------------------------------
# Resize shield: ``setFixedColorBufferSize`` takes a PIXEL size
# ---------------------------------------------------------------------------


class _StubRhiWidget:
    """``QRhiWidget`` stand-in for the freeze path (no GPU init offscreen)."""

    def __init__(self, *, logical, dpr, render_target=None) -> None:
        from PySide6.QtCore import QSize

        self._logical = QSize(*logical)
        self._dpr = dpr
        self._render_target = render_target
        self._fixed = QSize()
        self.pinned: list[tuple[int, int]] = []

    def objectName(self):  # noqa: N802 - Qt name
        return "stub-rhi"

    def isVisible(self) -> bool:  # noqa: N802 - Qt name
        return True

    def size(self):
        return self._logical

    def devicePixelRatioF(self) -> float:  # noqa: N802 - Qt name
        return self._dpr

    def renderTarget(self):  # noqa: N802 - Qt name
        return self._render_target

    def fixedColorBufferSize(self):  # noqa: N802 - Qt name
        return self._fixed

    def setFixedColorBufferSize(self, *args):  # noqa: N802 - Qt name
        from PySide6.QtCore import QSize

        size = args[0] if len(args) == 1 else QSize(args[0], args[1])
        self._fixed = size
        self.pinned.append((size.width(), size.height()))

    def update(self) -> None:
        return None

    def parentWidget(self):  # noqa: N802 - Qt name
        return None


class _StubWindow:
    def __init__(self, widgets) -> None:
        self._widgets = list(widgets)

    def findChildren(self, _cls):  # noqa: N802 - Qt name
        return list(self._widgets)


def test_freeze_pins_the_device_pixel_buffer_on_hidpi() -> None:
    """``size()`` is logical, ``setFixedColorBufferSize`` takes ``pixelSize``.

    A 400x300 logical canvas at DPR=2 must pin 800x600 device px; pinning
    400x300 asks Qt for a half-resolution buffer that it then upscales — the
    exact blur the shield is meant to avoid.
    """
    from ui.main_window.runtime import _freeze_rhi_surfaces

    rhi = _StubRhiWidget(logical=(400, 300), dpr=2.0)

    _freeze_rhi_surfaces(_StubWindow([rhi]))

    assert rhi.pinned == [(800, 600)], f"pinned {rhi.pinned} instead of device px"


def test_freeze_prefers_the_render_targets_pixel_size() -> None:
    """The render target's own ``pixelSize()`` is the truth when it exists."""
    from PySide6.QtCore import QSize

    from ui.main_window.runtime import _freeze_rhi_surfaces

    class _Target:
        def pixelSize(self):  # noqa: N802 - Qt name
            return QSize(1600, 1200)

    rhi = _StubRhiWidget(logical=(400, 300), dpr=2.0, render_target=_Target())

    _freeze_rhi_surfaces(_StubWindow([rhi]))

    assert rhi.pinned == [(1600, 1200)]
