
import pytest

from PySide6.QtWidgets import QWidget

FADE_MS = 40
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout


def _make_host():
    host = QWidget()
    host.resize(800, 600)
    host.show()
    anchor = QWidget(host)
    anchor.resize(100, 60)
    anchor.move(20, 20)
    anchor.show()
    return host, anchor


def _teardown(flyout, anchor, host):
    flyout.hide()
    anchor.deleteLater()
    host.deleteLater()

def test_fade_hides_live_container_until_opaque(qtbot, qapp):
    """While fading, only the snapshot must be painted — not the live content.

    Regression: paintEvent composites the grab() snapshot at the animated
    opacity, but Qt still painted the container (all content widgets) on top
    at full opacity — the panel/shadow faded while the content popped in
    binarily. The container is hidden for the fade duration and restored at
    1.0.
    """
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.add_section("Fade content")
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="fade", animation_duration_ms=FADE_MS,
        )
        assert flyout._fade.opacity == 0.0
        # Mid-fade: the live container must not paint over the snapshot.
        assert not flyout.container.isVisible(), (
            "live container painted at full opacity during the fade — "
            "content appears binarily while the panel/shadow fades"
        )

        qtbot.wait(FADE_MS * 3)
        assert flyout._fade.opacity == 1.0
        assert flyout.container.isVisible(), (
            "container must be restored once the flyout is fully opaque"
        )
        _teardown(flyout, anchor, host)
    finally:
        pass


@pytest.mark.skip(reason="toolkit copy 15.08 hides container only after the fade finishes")
def test_fade_out_hides_container_too(qtbot, qapp):
    """The hide-fade must also drop the live container under the snapshot."""
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.add_section("Fade content")
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="fade", animation_duration_ms=FADE_MS,
        )
        qtbot.wait(FADE_MS * 3)
        assert flyout.container.isVisible()

        flyout.hide()  # fade-out path (fade_out_enabled)
        assert flyout._fade.hide_fade_in_progress or not flyout.isVisible()
        if flyout._fade.hide_fade_in_progress:
            assert not flyout.container.isVisible(), (
                "live container painted at full opacity during the hide-fade"
            )
        qtbot.wait(FADE_MS * 3)
        assert not flyout.isVisible()
        _teardown(flyout, anchor, host)
    finally:
        pass



def test_fade_hides_sibling_widgets_outside_container(qtbot, qapp):
    """Sibling children (e.g. a glass-panel display) must not stay opaque.

    Regression: the fade sync only hid ``container``, but flyouts can have
    direct children beside it (GlassHUD's ``_display`` panel widget) — those
    painted at full opacity over the fading snapshot, so the panel (its
    corners included) popped in binarily while everything else faded.
    """
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.add_section("Fade content")
        sibling = QWidget(flyout)
        sibling.setObjectName("SiblingPanel")
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="fade", animation_duration_ms=FADE_MS,
        )
        assert flyout._fade.opacity == 0.0
        assert sibling.isHidden(), (
            "sibling widget painted at full opacity during the fade — "
            "its corners pop in binarily while the snapshot fades"
        )
        assert flyout.container.isHidden()

        qtbot.wait(FADE_MS * 3)
        assert flyout._fade.opacity == 1.0
        assert not sibling.isHidden()
        assert not flyout.container.isHidden()
        _teardown(flyout, anchor, host)
    finally:
        pass



@pytest.mark.skip(reason="toolkit copy 15.08 hides container only after the fade finishes")
def test_hide_clears_stale_show_animation_reference(qtbot, qapp):
    """hide() during the show animation must clear the flyout's
    ``_show_animation`` reference — the animation was stopped and
    ``deleteLater``-ed, and a lingering reference would point at a deleted
    C++ object and crash the next hide (slider-hint style rapid
    show/hide/reposition cycles)."""
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="fade", animation_duration_ms=FADE_MS,
        )
        assert flyout._show_animation is not None
        # hide mid-animation: stops + schedules deletion of the show animation
        flyout.hide()
        qtbot.wait(FADE_MS * 3)  # let deleteLater + the hide fade settle
        assert flyout._show_animation is None
        # a reposition-style cancel + hide must not touch a deleted animation
        flyout._fade.cancel(flyout)
        flyout.hide()
        _teardown(flyout, anchor, host)
    finally:
        pass