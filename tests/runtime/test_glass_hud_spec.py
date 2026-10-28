"""The glass HUD registers its radii in DEVICE px — all of them.

Regression (board ``task-glass-hud-blur-dpr-2026-10-28``): ``_refresh_backdrop``
multiplied the corner radius and the border width by ``dpr`` but passed the blur
radius as the raw logical constant. The blur pass renders into a viewport sized
from ``device_size`` (``engine/gpu/glass_panel.py``), so at DPR=2 the corner
looked right while the blur was half as strong — visible only side by side with a
100 % reference.

The stub below is deliberately NOT a Qt HUD: ``_refresh_backdrop`` only reads a
handful of attributes, and building a real HUD would drag the whole overlay
machinery into a unit test of one multiplication.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from engine.gpu.glass_panel import GlassPanelRegistry
from ui.widgets.glass_hud.hud import _BLUR_RADIUS_PX, GlassHUD


def _register(qtbot, dpr: float):
    """Run the HUD's registration with a chosen device pixel ratio."""

    class _Target(QWidget):
        glass_panels = GlassPanelRegistry()

    target = _Target()
    qtbot.addWidget(target)
    box = QWidget(target)
    qtbot.addWidget(box)
    box.resize(160, 48)

    class _Stub:
        _target_widget = target
        container = box
        CONTENT_RADIUS = GlassHUD.CONTENT_RADIUS

        def isVisible(self) -> bool:  # noqa: N802 - Qt naming
            return True

        def devicePixelRatioF(self) -> float:  # noqa: N802 - Qt naming
            return dpr

        def _border_highlight_color(self) -> QColor:
            return QColor(255, 255, 255, 200)

        def _glass_tint(self) -> QColor:
            return QColor(20, 24, 30, 90)

    GlassHUD._refresh_backdrop(_Stub())
    specs = list(_Target.glass_panels._specs.values())
    assert len(specs) == 1, "the stub registered exactly one panel"
    return specs[0]


@pytest.mark.parametrize("dpr", [1.0, 1.5, 2.0])
def test_every_radius_is_converted_to_device_px(qtbot, dpr):
    spec = _register(qtbot, dpr)

    assert spec.dpr == dpr
    assert spec.corner_radius_px == pytest.approx(GlassHUD.CONTENT_RADIUS * dpr), (
        "the corner radius is a device-space quantity"
    )
    assert spec.border_width_px == pytest.approx(2.0 * dpr)
    assert spec.blur_radius_px == pytest.approx(_BLUR_RADIUS_PX * dpr), (
        "the blur radius is consumed by a DEVICE-px pass (its viewport comes from "
        "device_size); leaving it in logical px makes the blur half as strong at "
        "DPR 2 while the corner stays correct"
    )
