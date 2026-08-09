"""Hover flyout mirroring a slider's current value above it.

Same shape as ``ScrollValueButton``'s ``_ScrollValueFlyout``
(``ui/widgets/scroll_value_button.py``) -- a single-purpose ``BaseFlyout``
holding one ``QLabel`` -- but shown from hovering the slider's *thumb*
specifically (via ``Slider.hoverHitTest``, not just being anywhere over the
track/widget) instead of scroll/wheel, and kept live while the value
changes (e.g. dragging the handle) instead of only updating on show.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QLabel, QWidget

from core.constants import AppConstants
from sli_ui_toolkit.managers import DelayedActionTimer
from sli_ui_toolkit.ui.managers.ui_font import apply_ui_font
from sli_ui_toolkit.widgets import BaseFlyout, Slider


class SliderHintFlyout(BaseFlyout):
    # See src/ui/flyout_policy.py's "slider_hint" group config: unconfigured
    # (the toolkit default "default" group) falls into exclusive-dismiss
    # behavior, which would close the magnifier-settings panel this hint
    # pops up *inside of* every time it showed.
    flyout_group = "slider_hint"

    SHADOW_RADIUS = 6
    CONTENT_RADIUS = 6

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._label = QLabel(self)
        # _ScrollValueFlyout's own label (the actual analogous flyout --
        # not _draw_capsule's pixel_size=12, which paints an unrelated
        # smaller in-place digit directly on the button) sets no explicit
        # font at all, just the default widget/base UI font -- match that
        # here. apply_ui_font (not a bare setFont(ui_font(...))) so this
        # stays in sync with a later real font correction -- see its
        # docstring for the stale-font bug this avoids for a widget built
        # early in assemble(), before FontManager.apply_from_state() finishes.
        apply_ui_font(self._label)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.add_widget(self._label)

    def show_value(self, text: str, anchor: QWidget) -> None:
        self._label.setText(text)
        # anchor_point="top-center" of the *anchor rect* -- for a Slider
        # that rect is its thumb (see Slider.flyoutAnchorRect), not the
        # whole track, so this already tracks the handle, not the track's
        # midpoint.
        self.show_aligned(
            anchor,
            anchor_point="top-center",
            flyout_point="bottom-center",
            offset=6,
        )

    def update_value(self, text: str) -> None:
        self._label.setText(text)
        # Re-run the last show_aligned() so the flyout's X follows the
        # thumb (see flyoutAnchorRect) as the value changes -- e.g. while
        # the user is actively dragging the handle.
        self.reposition()


_HOVER_POSITION_EVENTS = (
    QEvent.Type.HoverEnter,
    QEvent.Type.HoverMove,
    QEvent.Type.Enter,
)


class SliderHintController(QObject):
    """Hover the slider's *thumb* specifically (not the track/whole widget)
    -> show a live value flyout above it, tracking the thumb and updating
    in place while the value changes (drag).

    Hovering the flyout itself does *not* keep it open -- it isn't
    interactive, so the moment the cursor reaches it (typically while
    leaving the slider upward) it should disappear, not linger.
    """

    def __init__(self, widget: QWidget, sliders: list[Slider]) -> None:
        super().__init__(widget)
        self._flyout = SliderHintFlyout(widget)
        self._sliders = list(sliders)
        self._current_anchor: Slider | None = None
        self._hover_timer = DelayedActionTimer(self._show, parent=widget)
        self._wheel_idle_timer = DelayedActionTimer(self._on_wheel_idle, parent=widget)
        self._pending_anchor: Slider | None = None
        for slider in self._sliders:
            slider.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            slider.installEventFilter(self)
            slider.valueChanged.connect(
                lambda value, s=slider: self._on_value_changed(s, value)
            )
        self._flyout.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        et = event.type()
        if watched in self._sliders:
            if et == QEvent.Type.MouseButtonPress:
                # A drag (thumb grab or click-on-track-then-drag, both set
                # the slider's own `_pressed`) suppresses Hover* events for
                # its whole duration -- Qt delivers MouseMove instead once a
                # button is down, see Slider.mouseMoveEvent -- so the
                # hover-timer path below never fires mid-drag. Show
                # immediately here instead of waiting on hover, and skip the
                # open-delay entirely: a drag is already a deliberate
                # interaction, unlike a passing hover.
                self._hover_timer.stop()
                self._pending_anchor = None
                self._current_anchor = watched
                self._flyout.show_value(_percent_text(watched), watched)
            elif et == QEvent.Type.MouseButtonRelease:
                if self._current_anchor is watched and not self._is_cursor_over(watched):
                    self._hide()
            elif et == QEvent.Type.Wheel:
                # Wheel scrolling has no "release" event to hide on, unlike
                # a drag -- reuse the same immediate-show as MouseButtonPress
                # (updates the value itself happen after this filter runs,
                # via Slider.wheelEvent -> valueChanged -> _on_value_changed),
                # then (re)arm an idle timer since consecutive wheel ticks
                # keep landing here with no other signal of "the user
                # stopped scrolling".
                self._hover_timer.stop()
                self._pending_anchor = None
                if self._current_anchor is not watched:
                    self._current_anchor = watched
                    self._flyout.show_value(_percent_text(watched), watched)
                self._wheel_idle_timer.stop()
                self._wheel_idle_timer.start(AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS)
            elif et in _HOVER_POSITION_EVENTS:
                pos = getattr(event, "position", None)
                over_thumb = bool(watched.hoverHitTest(pos())) if pos is not None else False
                if over_thumb:
                    if self._current_anchor is not watched and self._pending_anchor is not watched:
                        self._hover_timer.stop()
                        self._pending_anchor = watched
                        self._hover_timer.start(AppConstants.TRANSIENT_HOVER_OPEN_DELAY_MS)
                else:
                    self._hover_timer.stop()
                    self._pending_anchor = None
                    if self._current_anchor is watched:
                        self._hide()
            elif et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
                self._hover_timer.stop()
                self._pending_anchor = None
                if self._current_anchor is watched:
                    self._hide()
        elif watched is self._flyout:
            if et in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
                self._hide()
        return False

    def _show(self) -> None:
        anchor = self._pending_anchor
        if anchor is None:
            return
        self._current_anchor = anchor
        self._flyout.show_value(_percent_text(anchor), anchor)

    def _hide(self) -> None:
        self._current_anchor = None
        self._flyout.hide()

    def _on_wheel_idle(self) -> None:
        anchor = self._current_anchor
        if anchor is None:
            return
        if not self._is_cursor_over(anchor):
            self._hide()

    @staticmethod
    def _is_cursor_over(slider: Slider) -> bool:
        # Whole-widget hit test, not hoverHitTest's thumb-only circle -- the
        # cursor resting anywhere on the slider (track included) after a
        # drag/scroll ends still counts as "still interacting", not just
        # landing exactly back on the thumb.
        pos = slider.mapFromGlobal(QCursor.pos())
        return slider.rect().contains(pos)

    def _on_value_changed(self, slider: Slider, value: int) -> None:
        if slider is self._current_anchor:
            self._flyout.update_value(_percent_text(slider))


def _percent_text(slider: Slider) -> str:
    """Slider position as a percentage of its own min..max span, one
    decimal place, comma as the decimal separator (e.g. "42,7%")."""
    span = slider.maximum() - slider.minimum()
    percent = 0.0 if span <= 0 else (slider.value() - slider.minimum()) / span * 100.0
    return f"{percent:.1f}".replace(".", ",") + "%"
