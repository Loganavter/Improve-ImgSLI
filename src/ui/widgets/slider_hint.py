"""Hover value flyout for sliders + the combined ``ValueSlider`` widget.

Extracted from ``tabs/image_compare/ui/slider_hint_flyout.py`` (the
magnifier-panel integration) into the shared app widget layer so every
value slider in the app — magnifier panel, export dialog, settings,
font-settings flyout — shows the same "value above the thumb on hover"
behavior through one widget, ``ValueSlider``.

Same shape as ``ScrollValueButton``'s ``_ScrollValueFlyout``
(``ui/widgets/scroll_value_button.py``) -- a single-purpose ``BaseFlyout``
holding one ``QLabel`` -- but shown from hovering the slider's *thumb*
specifically (via ``Slider.hoverHitTest``, not just being anywhere over the
track/widget) instead of scroll/wheel, and kept live while the value
changes (e.g. dragging the handle) instead of only updating on show.
"""

from __future__ import annotations

from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QCursor, QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from core.constants import AppConstants
from sli_ui_toolkit.managers import DelayedActionTimer, UiScale, scaled_px
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
        #
        # animation="none": the app-wide default is a fade, and the fade
        # pipeline hides the flyout's children and composites a pre-rendered
        # snapshot of the (still hidden) flyout instead. The snapshot can
        # miss the freshly-set label, and even when it catches it, the box
        # shows without the digit for the whole fade — visible as an "empty
        # box" flash on every value jump (press on the track). A one-line
        # value hint has no business fading in; show it instantly like
        # MagnifierSettingsFlyout does for its panel.
        self.show_aligned(
            anchor,
            anchor_point="top-center",
            flyout_point="bottom-center",
            offset=6,
            animation="none",
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


def _percent_text(slider: Slider) -> str:
    """Slider position as a percentage of its own min..max span, one
    decimal place, comma as the decimal separator (e.g. "42,7%")."""
    span = slider.maximum() - slider.minimum()
    percent = 0.0 if span <= 0 else (slider.value() - slider.minimum()) / span * 100.0
    return f"{percent:.1f}".replace(".", ",") + "%"


SliderTextFormatter = Callable[[Slider], str]


class SliderHintController(QObject):
    """Hover the slider's *thumb* specifically (not the track/whole widget)
    -> show a live value flyout above it, tracking the thumb and updating
    in place while the value changes (drag).

    Hovering the flyout itself does *not* keep it open -- it isn't
    interactive, so the moment the cursor reaches it (typically while
    leaving the slider upward) it should disappear, not linger.

    ``hint_active_changed`` fires True while the flyout is shown (hover /
    drag / wheel) and False after it hides. (``ValueSliderRow`` used to
    subscribe to drop its persistent readout for the duration — it now
    disables the hint flyout instead and keeps its label always visible.)
    """

    hint_active_changed = Signal(bool)

    def __init__(
        self,
        widget: QWidget,
        sliders: list[Slider],
        *,
        text_formatter: SliderTextFormatter | None = None,
    ) -> None:
        super().__init__(widget)
        self._hint_active = False
        self._text_formatter = text_formatter or _percent_text
        # The flyout is parented to the slider's *window*, not the slider
        # itself: without an overlay layer the toolkit's
        # surface_available_rect falls back to the flyout's parent rect,
        # i.e. the slider's own ~22px track -- "above the thumb" then
        # overflows and the flyout gets clamped onto the slider. Parented to
        # the window (the dialog, for Settings/export), the flyout paints
        # above the dialog content like the combo dropdown; the toolkit's
        # attach_in_window_widget guard keeps it from being re-parented into
        # an ancestor window's overlay layer (which would sink it *under*
        # the dialog).
        self._flyout = SliderHintFlyout(widget.window() or widget)
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
                # The slider's own press handling (click-on-track jump via
                # setValue, or the drag grab) runs *after* this filter, so
                # showing right now would paint the flyout with the OLD
                # value at the OLD thumb position for one frame, then snap
                # it to the new state -- the visible flicker on every track
                # click. Defer by one event-loop tick: by then setValue has
                # fired and the flyout shows already in its final state.
                self._defer_show(watched)
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
                    # Same stale-frame problem as MouseButtonPress: the
                    # wheel step lands after this filter, so show one tick
                    # later, when valueChanged has already fired.
                    self._defer_show(watched)
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
        self._flyout.show_value(self._text_formatter(anchor), anchor)
        self._set_hint_active(True)

    def _defer_show(self, slider: Slider) -> None:
        """Show the flyout one event-loop tick after the triggering event.

        The slider's own press/wheel handler runs after this event filter,
        so a synchronous show paints a stale frame (old value at the old
        thumb position) before ``valueChanged`` snaps the flyout to the new
        state. One tick later the value has settled and the flyout shows
        directly in its final position.
        """

        def _run() -> None:
            if slider is not self._current_anchor:
                return
            try:
                from shiboken6 import isValid  # type: ignore[attr-defined]

                if not isValid(slider):
                    return
            except ImportError:
                pass
            assert slider is not None
            self._flyout.show_value(self._text_formatter(slider), slider)
            self._set_hint_active(True)

        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, _run)

    def _hide(self) -> None:
        self._current_anchor = None
        self._flyout.hide()
        self._set_hint_active(False)

    def _set_hint_active(self, active: bool) -> None:
        """Track flyout visibility and emit ``hint_active_changed`` only on
        transitions (show paths may run repeatedly while already shown)."""
        if active == self._hint_active:
            return
        self._hint_active = active
        self.hint_active_changed.emit(active)

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
            self._flyout.update_value(self._text_formatter(slider))


class ValueSlider(Slider):
    """Toolkit ``Slider`` with the hover value flyout built in.

    Hovering the thumb (or dragging/wheeling it) shows a small flyout above
    it mirroring the current value, tracking the handle in place. This is
    the widget the magnifier-panel sliders used to get by wiring a
    ``SliderHintController`` externally; every value slider in the app
    should be a ``ValueSlider``.

    ``hint_formatter`` maps the slider to the shown text (default: a
    percentage of the min..max span, the magnifier behavior). Pass a
    formatter for controls where the raw value reads better, e.g.
    ``lambda s: str(s.value())``.

    ``hint_active_changed`` (re-emitted from the hint controller) fires
    True while the value flyout is up and False when it hides.

    Pass ``hint_enabled=False`` (or call :meth:`set_hint_enabled`) to turn
    the flyout off — used by ``ValueSliderRow``, whose persistent
    right-hand value label replaces the hover flyout.
    """

    hint_active_changed = Signal(bool)

    def __init__(
        self,
        *args,
        hint_formatter: SliderTextFormatter | None = None,
        hint_enabled: bool = True,
        **kwargs,
    ) -> None:
        self._hint_formatter = hint_formatter or _percent_text
        self._hint_enabled = bool(hint_enabled)
        self._hint_controller: SliderHintController | None = None
        super().__init__(*args, **kwargs)

    def set_hint_enabled(self, enabled: bool) -> None:
        """Turn the hover value flyout on/off.

        Safe to call before the slider is shown (the hint controller is
        only created lazily on first show); if it already exists, its
        flyout is hidden immediately.
        """
        self._hint_enabled = bool(enabled)
        controller = self._hint_controller
        if controller is not None and not self._hint_enabled:
            try:
                controller._hide()
            except RuntimeError:
                pass

    def _ensure_hint_controller(self) -> None:
        if not self._hint_enabled:
            return
        if self._hint_controller is None:
            # Created lazily on first show: the controller parents a
            # BaseFlyout to this slider, which needs a real window. Sliders
            # are often constructed parentless and added to a dialog layout
            # later.
            controller = SliderHintController(
                self,
                [self],
                text_formatter=self._hint_formatter,
            )
            controller.hint_active_changed.connect(self.hint_active_changed)
            self._hint_controller = controller

    def showEvent(self, event) -> None:  # noqa: N802 — Qt API
        self._ensure_hint_controller()
        super().showEvent(event)


# Horizontal breathing room inside the value pad, on top of the widest
# label text (design px — scales with UiScale).
_PAD_PADDING_DESIGN_PX = 4


class _FormattedSliderSample:
    """Slider stand-in for sampling a ``SliderTextFormatter``'s output at
    min/value/max without mutating the real slider's value."""

    def __init__(self, slider: Slider, value: int) -> None:
        self._slider = slider
        self._value = value

    def minimum(self) -> int:
        return self._slider.minimum()

    def maximum(self) -> int:
        return self._slider.maximum()

    def value(self) -> int:
        return self._value


class ValueSliderRow(QWidget):
    """``ValueSlider`` + an always-visible right-hand value label:
    ``[track] [label]``.

    The row replaces the hover hint flyout entirely: the slider's hint is
    disabled (``set_hint_enabled(False)``) and the right pad hosts the live
    value readout in the same format (via the slider's ``hint_formatter``)
    at all times. The pad is fixed-width — sized to the widest formatted
    value over the slider's range — so the label text never reflows the
    row or shifts the slider's geometry as the value changes. Pad width
    follows the label font through live ``UiScale`` changes.
    """

    def __init__(
        self,
        slider: Slider,
        *,
        hint_formatter: SliderTextFormatter | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._slider = slider
        self._hint_formatter = (
            hint_formatter
            or getattr(slider, "_hint_formatter", None)
            or _percent_text
        )
        self._label = QLabel(self)
        # apply_ui_font (not a bare setFont) so the value follows font and
        # UiScale changes live — see SliderHintFlyout for the same pattern.
        apply_ui_font(self._label)
        self._label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._right_pad = QWidget(self)
        right_layout = QHBoxLayout(self._right_pad)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._label)

        # The hover hint flyout is redundant next to this always-visible
        # readout — turn it off so the value shows in exactly one place.
        disable_hint = getattr(slider, "set_hint_enabled", None)
        if callable(disable_hint):
            disable_hint(False)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(slider, 1)
        row.addWidget(self._right_pad)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        slider.valueChanged.connect(self._on_value_changed)
        self._apply_label()
        self._apply_pad_width()
        UiScale.get_instance().scale_changed.connect(self._on_scale_changed)

    def _on_scale_changed(self, _factor: float | None = None) -> None:
        try:
            import shiboken6

            if not shiboken6.Shiboken.isValid(self._label):
                return
        except Exception:
            return
        apply_ui_font(self._label)
        self._apply_label()
        self._apply_pad_width()

    def _apply_label(self) -> None:
        self._label.setText(self._hint_formatter(self._slider))

    def _on_value_changed(self, _value: int) -> None:
        self._apply_label()

    def _apply_pad_width(self, _factor: float | None = None) -> None:
        try:
            import shiboken6

            if not shiboken6.Shiboken.isValid(self._right_pad):
                return
        except Exception:
            return
        self._right_pad.setFixedWidth(self._pad_width())

    def _pad_width(self) -> int:
        try:
            texts = [
                self._hint_formatter(
                    _FormattedSliderSample(self._slider, value)
                )
                for value in (
                    self._slider.minimum(),
                    self._slider.value(),
                    self._slider.maximum(),
                )
            ]
        except Exception:
            # Exotic formatters may use more of the Slider API than the
            # sample provides — size to the current text instead.
            texts = [self._hint_formatter(self._slider)]
        fm = QFontMetrics(self._label.font())
        text_width = max(fm.horizontalAdvance(text) for text in texts)
        return text_width + scaled_px(_PAD_PADDING_DESIGN_PX * 2)


__all__ = [
    "SliderHintController",
    "SliderHintFlyout",
    "SliderTextFormatter",
    "ValueSlider",
    "ValueSliderRow",
    "_percent_text",
]

ValueSlider.inspect_spec = InspectSpec(
    family="ValueSlider",
    state=(SpecField("value", "value"),),
    docs="docs/dev/widgets/value_slider.md",
)

ValueSliderRow.inspect_spec = InspectSpec(
    family="ValueSliderRow",
    state=(
        SpecField("value", lambda w: w._slider.value(), private=True),
        SpecField("minimum", lambda w: w._slider.minimum(), private=True),
        SpecField("maximum", lambda w: w._slider.maximum(), private=True),
    ),
    docs="docs/dev/widgets/value_slider.md",
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
ValueSlider.widget_descriptor = WidgetDescriptor(
    family=ValueSlider.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(ValueSlider.inspect_spec, 'config', ()),
        state=ValueSlider.inspect_spec.state,
        token_family=getattr(ValueSlider.inspect_spec, 'token_family', ()),
        regions=getattr(ValueSlider.inspect_spec, 'regions', False),
        layers=getattr(ValueSlider.inspect_spec, 'layers', False),
        docs=getattr(ValueSlider.inspect_spec, 'docs', ''),
        preview_seed=getattr(ValueSlider.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(ValueSlider.inspect_spec, 'apply_config_refresh', None),
    ),
)

ValueSliderRow.widget_descriptor = WidgetDescriptor(
    family=ValueSliderRow.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(ValueSliderRow.inspect_spec, 'config', ()),
        state=ValueSliderRow.inspect_spec.state,
        token_family=getattr(ValueSliderRow.inspect_spec, 'token_family', ()),
        regions=getattr(ValueSliderRow.inspect_spec, 'regions', False),
        layers=getattr(ValueSliderRow.inspect_spec, 'layers', False),
        docs=getattr(ValueSliderRow.inspect_spec, 'docs', ''),
        preview_seed=getattr(ValueSliderRow.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(ValueSliderRow.inspect_spec, 'apply_config_refresh', None),
    ),
)