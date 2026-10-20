"""UI-scale geometry for the gallery's segmented switch pills.

Owner report 2026-10-19 (plan-live-appearance-fixes-2026-10-19): on the
gallery page the Algorithms|AI **domain switch** (chip / sparkle segments in
one pill) and the sibling grid|list **view switch** came out the wrong size /
offset / corner radius — and a restart did not help, i.e. the defect is at
BUILD time, not a missing live re-derive.

Root cause (measured, not assumed): ``sli_ui_toolkit.widgets.Button`` scales
its ``size=`` and ``corner_radius=`` design values internally exactly once.
The toolbar passed ``size=(scaled_px(48), scaled_px(28))``, so at factor 1.5
each segment was built 108x63 inside a 159x48 pill and overflowed it
(factor^2 drift). The pill's own ``paintEvent`` radius was the literal ``8``,
which never followed the factor at all.

These tests build the REAL widgets offscreen. Because the toolbar is built
once per page, the proof is the BUILD-time path: construct at factor 1.0 and
at 1.5 and require the geometry to scale exactly once (design px * factor),
not factor^2. At factor 1.0 every assertion is a no-op, so this test is green
before and after on the default factor — it is red only at factor > 1.0
pre-fix.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import UiScale, scaled_px
from tabs.image_gallery.ui.toolbar import GalleryToolbar

#: Design px of one segment of the segmented switch (toolbar mockup).
_SEGMENT = (48, 28)
#: Design px of the pill that hosts the two segments.
_CONTAINER = (106, 32)
#: Design px of the Ask-AI include-images toggle.
_ASK_TOGGLE = (28, 28)

_SWITCH_ATTRS = (
    "domain_switch",
    "domain_switch_ai",
    "view_switch",
    "view_switch_list",
)


@pytest.fixture(autouse=True)
def _restore_ui_scale():
    """Never leak a parametrized factor into later suites (process singleton)."""
    yield
    UiScale.get_instance().set_factor(1.0)


def _build_toolbar(factor: float) -> GalleryToolbar:
    UiScale.get_instance().set_factor(factor)
    return GalleryToolbar()


def test_segments_are_design_px_at_factor_1_0(qapp) -> None:
    tb = _build_toolbar(1.0)
    try:
        for name in _SWITCH_ATTRS:
            btn = getattr(tb, name)
            assert (btn.width(), btn.height()) == _SEGMENT, (
                f"{name} at factor 1.0 is {(btn.width(), btn.height())}, "
                f"expected design {_SEGMENT}"
            )
    finally:
        tb.deleteLater()


def test_segments_fit_the_pill_and_scale_once_at_build(qapp) -> None:
    """Build at 1.5: the pill grows by the factor, segments by the factor once.

    Pre-fix red: ``size=(scaled_px(48), scaled_px(28))`` built at 1.5 gave
    108x63 per segment (48*1.5*1.5) — wider than the 159px pill, so the two
    segments plus margins overflowed the container.
    """
    tb = _build_toolbar(1.5)
    try:
        expected = (int(scaled_px(_SEGMENT[0])), int(scaled_px(_SEGMENT[1])))
        assert expected == (72, 42), f"UiScale 1.5 sanity: got {expected}"
        for name in _SWITCH_ATTRS:
            btn = getattr(tb, name)
            assert (btn.width(), btn.height()) == expected, (
                f"{name} at factor 1.5 is {(btn.width(), btn.height())}, "
                f"expected one-time-scaled {expected} (factor^2 = "
                f"{(108, 63)})"
            )
        container = tb._domain_switch_container
        assert container.minimumWidth() == int(scaled_px(_CONTAINER[0]))
        inner = (
            int(scaled_px(2)) * 3  # margins 2 + spacing 2 + margin 2
            + tb.domain_switch.width()
            + tb.domain_switch_ai.width()
        )
        assert inner <= container.minimumWidth(), (
            "segments overflow the pill at factor 1.5: content "
            f"{inner}px > pill {container.minimumWidth()}px"
        )
    finally:
        tb.deleteLater()


def test_pill_corner_radius_follows_the_scale(qapp) -> None:
    """The pill radius is painted by a plain QWidget — it must scale by hand.

    Pre-fix the paintEvent used the literal ``8``, so at factor 1.5 the pill
    still had an 8px corner on a 159x48 body (owner: "corner radius off").
    We render the container and measure the transparent corner run along its
    top row; it must grow with the factor.
    """

    def corner_reach(factor: float) -> int:
        tb = _build_toolbar(factor)
        try:
            c = tb._domain_switch_container
            c.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            c.resize(int(scaled_px(_CONTAINER[0])), int(scaled_px(_CONTAINER[1])))
            pm = QPixmap(c.size())
            pm.fill(QColor(0, 0, 0, 0))
            c.render(pm)
            img = pm.toImage()
            for x in range(img.width()):
                if img.pixelColor(x, 0).alpha() > 128:
                    return x
            return img.width()
        finally:
            tb.deleteLater()

    assert corner_reach(1.5) > corner_reach(1.0), (
        "the pill's painted corner radius did not follow UiScale — the "
        "paintEvent radius is a raw px literal"
    )


def test_ask_ai_images_toggle_scales_once_at_build(qapp) -> None:
    """The Ask-AI include-images toggle is built in the same UI family."""
    from tabs.image_gallery.ui.ask_ai import AskAiFlyout

    parent = QWidget()
    try:
        UiScale.get_instance().set_factor(1.0)
        base = AskAiFlyout(parent)
        try:
            # The ask body (and its toggle) is built on first use — one shared
            # surface per host, created lazily since the sidebar split.
            base._ensure_surface()
            # Read the 1.0 geometry BEFORE the factor moves: an alive Button
            # re-derives live on a scale change (that is correct — the bug
            # this test guards is the BUILD-time factor^2 drift).
            base_size = (base._images_toggle.width(), base._images_toggle.height())
        finally:
            base.deleteLater()
        UiScale.get_instance().set_factor(1.5)
        scaled = AskAiFlyout(parent)
        try:
            scaled._ensure_surface()
            assert base_size == _ASK_TOGGLE, (
                f"Ask-AI images toggle at factor 1.0 is {base_size}, "
                f"expected design {_ASK_TOGGLE}"
            )
            expected = (int(scaled_px(_ASK_TOGGLE[0])), int(scaled_px(_ASK_TOGGLE[1])))
            assert expected == (42, 42), f"UiScale 1.5 sanity: got {expected}"
            assert (
                scaled._images_toggle.width(),
                scaled._images_toggle.height(),
            ) == expected, (
                "the Ask-AI images toggle double-scaled: "
                f"{(scaled._images_toggle.width(), scaled._images_toggle.height())} "
                f"instead of {expected}"
            )
        finally:
            scaled.deleteLater()
    finally:
        parent.deleteLater()
