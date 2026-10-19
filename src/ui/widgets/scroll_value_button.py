"""Generic scroll-driven numeric control button.

A single icon region when idle, an icon+numeric-value split while hovered
(the digit shows INSIDE the button — hover does not raise the flyout), a
transient flyout mirroring the value on keyboard focus / scroll (the preview
never steals focus; Up moves the keyboard into it and Left/Right step the
value there), and an always-visible bottom underline (via the toolkit's
built-in ``show_underline``/``setUnderlineColor`` API) showing an associated
color (e.g. divider/guide color).

Enter/Return is this control's SECONDARY ACTION — it emits
``rightClicked``, exactly the signal a mouse right click emits (owner rule
2026-10-20), so keyboard users reach the divider/guides colour pickers the
consumers already wire to that channel (``multi_compare`` toolbar,
onboarding ``b_expert``). This is a reasoned exception to the app-wide
value-edit contract (plan-nav-coverage-2026-10-19): there is no Enter edit
mode here, the keyboard value path is the wheel and the Up-pill's
Left/Right, and ``is_editing()`` always reports ``False`` so
``ToolbarRowsSection`` keeps handing every arrow to ring navigation instead
of the control.

The value pill is a separate preview, entered with Up; inside it only
Left/Right change the value, a second Up leaves it upward to the control above,
and Down returns to the button. This widget carries no color editor of its own
(the color-valued control is ``ui.widgets.color.ColorSwatch``).

Used for divider width, magnifier-divider width, and magnifier-guides width
controls across multi_compare and image_compare toolbars.
Audit-Meta: pattern=state-machine reason="single custom-painted control — painter pipeline owns visuals"
"""

from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

import logging

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.ui.managers.ui_font import apply_ui_font
from sli_ui_toolkit.ui.managers.ui_font import ui_font
from sli_ui_toolkit.widgets import (
    BackgroundLayer,
    BadgeLayer,
    BaseFlyout,
    Button,
    ButtonRegion,
    ButtonRow,
    ContentLayer,
    DividerLayer,
    Layer,
    RippleLayer,
    StrikethroughLayer,
    UnderlineLayer,
    VerticalSplit,
)

from ui.host_debug import scroll_value_debug
from ui.icon_manager import themed_icon

logger = logging.getLogger("ImproveImgSLI")

_FLYOUT_HIDE_MS = 700
_WIDTH = 36
_HEIGHT = 36
_RADIUS = 6

# Padding around the digit inside the small capsule backdrop (see
# _ValueOverUnderlineLayer) — deliberately tight, not the full split region.
_CAPSULE_PAD_X = 5.0
_CAPSULE_PAD_Y = 3.0


class _ValueOverUnderlineLayer(Layer):
    """Repaints the "value" region's digit on top of UnderlineLayer, behind
    a small themed capsule sized to the digit (not the whole split region).

    Reuses the toolkit's own BackgroundLayer color resolution (so the
    capsule fill tracks the button's current state/theme for free) and
    ContentLayer for the digit itself, but draws the capsule shape by hand
    since BackgroundLayer only knows how to fill its full region rect.
    Stateless like the toolkit's own layers — reads the button instance off
    ``ctx.widget`` rather than holding any state itself, so one instance is
    shared across all ScrollValueButtons (see _LAYERS).
    """

    scope = "widget"

    def __init__(self) -> None:
        self._content_layer = ContentLayer()

    def applies(self, ctx) -> bool:
        widget = ctx.widget
        return bool(getattr(widget, "_hovered_split", False)) and not getattr(
            widget, "_is_scrolling", False
        )

    def draw(self, ctx, tm) -> None:
        iter_regions = getattr(ctx.widget, "iter_regions", None)
        if iter_regions is None:
            return
        for scoped_ctx in iter_regions(ctx):
            if scoped_ctx.region_id == "value":
                if not ctx.widget._is_at_zero():
                    self._draw_capsule(scoped_ctx, tm, str(ctx.widget._value))
                self._content_layer.draw(scoped_ctx, tm)
                return

    @staticmethod
    def _clamp_capsule(capsule: QRectF, region_rect: QRectF) -> QRectF:
        """Keep the capsule inside the value region (never over the icon)."""
        return capsule.intersected(region_rect)

    @staticmethod
    def _draw_capsule(scoped_ctx, tm, text: str) -> None:
        backgrounds, _border = BackgroundLayer._resolve(scoped_ctx, tm)
        if not backgrounds:
            return
        font = ui_font(pixel_size=14)
        fm = QFontMetrics(font)
        pad_x = scaled_px(_CAPSULE_PAD_X)
        pad_y = scaled_px(_CAPSULE_PAD_Y)
        width = fm.horizontalAdvance(text) + 2 * pad_x
        height = fm.height() + 2 * pad_y
        center = scoped_ctx.effective_rect.center()
        rect = QRectF(center.x() - width / 2, center.y() - height / 2, width, height)
        # The value split region is narrower/shorter than the digit +
        # padding for multi-digit values; clamp the capsule to the region
        # so it never bleeds into the icon region (ContentLayer clips the
        # digit itself to the same rect — clip_content=True).
        rect = _ValueOverUnderlineLayer._clamp_capsule(
            rect, QRectF(scoped_ctx.effective_rect)
        )

        p = scoped_ctx.painter
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        # Same ORDERED layer stack the region itself paints. BackgroundLayer
        # fills *every* resolved layer (e.g. base + the ambient hover/checked
        # wash); using only ``backgrounds[-1]`` made the digit capsule visibly
        # different from the button's own backdrop (the wash without the base
        # underneath it).
        for bg in backgrounds:
            p.setBrush(bg)
            p.drawRoundedRect(rect, height / 2, height / 2)
        p.restore()


# The toolkit's Painter (buttons/painter.py) always runs every region-scoped
# layer (ContentLayer among them) before any widget-scoped layer
# (UnderlineLayer is scope="widget"), regardless of where each sits in this
# list — so simply listing ContentLayer after UnderlineLayer does NOT make
# the digit paint on top; the underline (esp. the thick end of the
# thickness ramp below) still ends up covering it. _ValueOverUnderlineLayer
# below is itself widget-scoped, so its list position *does* control paint
# order relative to UnderlineLayer: it repaints just the "value" region's
# content a second time, after the underline, whenever hover-without-scroll
# should show the digit sitting on top of the line.
_LAYERS = (
    BackgroundLayer(),
    RippleLayer(),
    ContentLayer(),
    BadgeLayer(),
    UnderlineLayer(),
    _ValueOverUnderlineLayer(),
    DividerLayer(),
    StrikethroughLayer(),
)

# The underline's thickness tracks the button's own value (e.g. divider/line
# width), so a thicker configured line reads visually as a thicker indicator
# too: value=1 -> _UNDERLINE_THICKNESS_MIN, value=max_value -> _MAX. value=0
# is the separate "hidden" state (zero_icon) and isn't part of this ramp.
_UNDERLINE_THICKNESS_MIN = 1.0
_UNDERLINE_THICKNESS_MAX = 5.0


class _ScrollValueFlyout(BaseFlyout):
    """Transient popup mirroring the current value above the button."""

    # Without an explicit group this falls into flyout_policy.py's
    # unconfigured "default" bucket, which resolves to the fallback
    # DISMISS_ALL policy -- every wheel-nudge on a ScrollValueButton was
    # closing every other visible flyout, including "pinned" ones like the
    # zoom-percent/info HUD chips (pinned only exempts a flyout from being
    # dismissed by *its own* passive-dismiss paths -- outside click/wheel/
    # deactivate -- not from another flyout's GroupShowPolicy dismiss set
    # naming it, or DISMISS_ALL). Same shape as "slider_hint" below.
    flyout_group = "scroll_value"

    # Declarative flyout navigation (guide §9): the pill sits ABOVE its
    # anchor, so Up out of the button enters it and Down hands the keyboard
    # back to the anchor. Declared as class metadata — the same attributes
    # PanelVisibility/ColorOptions flyouts use — instead of ad-hoc key
    # routing, so ToolbarRowsSection reads side/exit from the same registry
    # it reads them from for everyone else.
    _nav_side = "above"
    _nav_mode = "preview"
    _nav_exit = "down"

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._label = QLabel(self)
        # apply_ui_font (not a bare setFont) so the digit follows font and
        # UiScale changes live — see SliderHintFlyout for the same pattern.
        apply_ui_font(self._label)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Minimum, NOT fixed size: the flyout is cached per button and lives
        # across UiScale changes — a fixed design size computed once at
        # construction stays stale when the factor rises (digit re-resolves
        # its scaled font live, so the text overflows and clips against the
        # panel's rounded corners). A minimum keeps the compact pill for a
        # single digit while letting the sizeHint (scaled text) grow it on
        # every show (show_aligned -> adjustSize), same as SliderHintFlyout.
        self._label.setMinimumSize(scaled_px(22), scaled_px(20))
        self.add_widget(self._label)

    def focus_first_child(self, ref_x: float | None = None) -> bool:
        """Enter the pill (Up / focus grant) by focusing its own shell.

        The pill's only content is a bare ``QLabel`` (``NoFocus``), so the
        toolkit's ``BaseFlyout.focus_first_child`` — which looks for a
        ``StrongFocus`` *descendant* — reports ``False``, and
        ``ToolbarRowsSection``'s Up-into-flyout hand-off
        (``extension_below(...).focus_first_child()``) silently fell back to
        row navigation. That is exactly why Up could not enter the preview.
        Focusing the shell keeps the toolkit's own ring paint
        (``BaseFlyout.paintEvent`` → ``_keyboard_focus`` + ``hasFocus``) and
        ``_FlyoutNavigationSection.owns`` (flyout or descendant) intact.
        """
        from sli_ui_toolkit.managers import NavigationManager

        self.setFocus(NavigationManager.get_instance().current_focus_reason())
        return True

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        # While the pill owns the keyboard its preview hide-timer must not
        # yank the pill out from under the user mid-interaction.
        anchor = getattr(self, "_anchor_widget", None)
        timer = getattr(anchor, "_flyout_hide_timer", None)
        if timer is not None:
            timer.stop()

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        # Focus is leaving the pill. Down/Esc hand the keyboard back to the
        # anchor (whose focusInEvent re-arms the preview); every other
        # departure — Tab, a click on another widget, window deactivation —
        # ends the interaction. Our own focusInEvent stopped the hide
        # timer, so without this the pill would linger over an anchor that
        # keeps its hover/value split while unfocused: the stuck
        # value-display state (sv-hover-fix). Settle through the anchor's
        # own ``_hide_flyout`` so ``_is_scrolling`` resets and the digit
        # returns; the anchor's split settles only when the anchor is
        # neither hovered nor (about to be) focused — the Down/Esc paths
        # re-assert it in their focusInEvent right after this runs.
        anchor = getattr(self, "_anchor_widget", None)
        if anchor is None:
            return
        # The anchor contract (``_hide_flyout``/``_set_hover_split``) belongs
        # to ScrollValueButton; the flyout is also constructed directly with
        # a bare QWidget anchor (the live-scale reflow test), so guard both
        # calls like keyPressEvent guards ``_dismiss_preview`` — an
        # AttributeError here would raise inside Qt's event filter during
        # teardown and cascade into unrelated tests (sv-hover-fix).
        hide_flyout = getattr(anchor, "_hide_flyout", None)
        if callable(hide_flyout):
            hide_flyout()
        set_split = getattr(anchor, "_set_hover_split", None)
        if callable(set_split) and not anchor.underMouse() and not anchor.hasFocus():
            set_split(False)

    def _exit_to_anchor(self) -> None:
        """Down in preview mode: hand the keyboard back to the anchor.

        The pill stays visible (so Up can re-enter) and the anchor's own
        focus-preview path re-arms the transient hide timer.
        """
        from sli_ui_toolkit.managers import NavigationManager

        anchor = getattr(self, "_anchor_widget", None)
        if anchor is None:
            return
        anchor.setFocus(NavigationManager.get_instance().current_focus_reason())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            # Escape must dismiss the pill AND restore the anchor's own digit,
            # not merely hide this flyout: a bare self.hide() leaves the button's
            # _is_scrolling True, so its "value" region keeps painting the
            # suppressed/empty rows after the flyout is gone — the digit
            # vanishes. The pill holds focus after Up, so this is exactly the
            # path the user's Escape takes; route it through the button's
            # _hide_flyout()-based dismiss (anchor._dismiss_preview).
            anchor = getattr(self, "_anchor_widget", None)
            dismiss = getattr(anchor, "_dismiss_preview", None)
            if callable(dismiss):
                dismiss()
            else:
                self.hide()
            event.accept()
            return
        # Only Left/Right change the value inside the pill (owner rule): Up must
        # not step it, Down is the declarative way out (_nav_exit="down").
        if event.key() == Qt.Key.Key_Down:
            self._exit_to_anchor()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Up:
            # Leave the pill upward: the value changes on Left/Right only, and
            # Up must NOT be swallowed — an unaccepted key makes the flyout's
            # navigation section decline it, so NavigationManager hands focus
            # to the section above instead of the pill eating the press.
            super().keyPressEvent(event)
            return
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            anchor = getattr(self, "_anchor_widget", None)
            if anchor is not None and hasattr(anchor, "_step_value"):
                step = 1 if event.key() == Qt.Key.Key_Right else -1
                try:
                    anchor._step_value(step)  # type: ignore[attr-defined]
                    event.accept()
                    return
                except Exception:
                    pass
        super().keyPressEvent(event)

    def show_value(self, text: str, icon=None, anchor: QWidget | None = None) -> None:
        if icon is not None:
            from sli_ui_toolkit.icons import resolve_icon

            self._label.setPixmap(
                resolve_icon(icon).pixmap(scaled_px(16), scaled_px(16))
            )
            self._label.setText("")
        else:
            self._label.clear()
            self._label.setText(text)
        if anchor is not None:
            # The pill is always a preview: it never steals focus, so the ring
            # stays on the button and Up moves the keyboard into the pill.
            # Декларативный side/mode/exit заданы на классе _ScrollValueFlyout
            # (_nav_side/_nav_mode/_nav_exit, guide §9).
            self.show_aligned(
                anchor,
                anchor_point="top-center",
                flyout_point="bottom-center",
                offset=6,
                grab_focus=False,
                # Preview registers its section too (grab_focus=False,
                # register_nav_section=True — the toolkit's documented combo
                # for "reachable but must not steal focus"): without it the
                # pill is invisible to arrow routing and Up can never enter.
                register_nav_section=True,
            )
        else:
            self.show()


class ScrollValueButton(Button):
    """Scroll-driven numeric control (min_value-max_value) with hover split & flyout.

    Optionally treats ``min_value`` as a "hidden" state, shown with
    ``zero_icon`` instead of the digit "0" (e.g. divider width 0 == divider
    hidden). Pass ``zero_icon=None`` (the default) to just display "0".
    """

    valueChanged = Signal(int)

    _GROUP = "scroll_value"

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        icon=None,
        toggle: bool = False,
        min_value: int = 0,
        max_value: int = 10,
        start: int = 0,
        zero_icon=None,
        **kwargs,
    ) -> None:
        self._min_value = int(min_value)
        self._max_value = int(max_value)
        self._value = max(self._min_value, min(self._max_value, int(start)))
        if isinstance(icon, (tuple, list)):
            self._svb_icon_normal = icon[0]
            self._svb_icon_checked = icon[1] if len(icon) >= 2 else icon[0]
        else:
            self._svb_icon_normal = icon
            self._svb_icon_checked = icon
        self._toggle_enabled = bool(toggle)
        # Mirrors isChecked(), tracked by hand: _build_regions() (and thus
        # _icon_region_icon()) runs once before super().__init__() below,
        # when Button's own internal state (isChecked() reads
        # self._region_states, set up by Button.__init__) doesn't exist yet.
        self._is_checked = False
        self._zero_icon = zero_icon
        self._saved_value: int | None = None
        # No value-edit mode (owner rule 2026-10-20): Enter is the secondary
        # action (``rightClicked``), so the Enter/Esc/commit state machine the
        # toolkit ``Slider`` implements is intentionally absent here.
        self._hovered_split = False
        # True only while the mouse is actually over the button
        # (enterEvent/leaveEvent) — ``_hovered_split`` also covers keyboard
        # focus, so the hover-persistency checks must read this flag.
        self._mouse_hovered = False
        self._is_scrolling = False
        self._underline_visible = False
        self._underline_qcolor = None
        self._underline_thickness_value: float | None = None
        self._flyout: _ScrollValueFlyout | None = None
        self._flyout_hide_timer = QTimer()
        self._flyout_hide_timer.setSingleShot(True)
        self._flyout_hide_timer.timeout.connect(self._on_flyout_hide_timeout)
        # Set while an exit path is handing focus back to this button, so the
        # resulting focusInEvent does not immediately re-open the preview the
        # user just left (Esc dismisses; Down returns the keyboard).
        self._suppress_focus_preview = False

        regions, split = self._build_regions()
        super().__init__(
            regions=regions,
            split=split,
            toggle=self._toggle_enabled,
            size=(_WIDTH, _HEIGHT),
            corner_radius=_RADIUS,
            content_padding=(0.0, float(scaled_px(2)), 0.0, float(scaled_px(2))),
            variant="default",
            layers=list(_LAYERS),
            parent=parent,
            **kwargs,
        )
        # Button.__init__ sets self._show_underline directly (bypassing our
        # setShowUnderline override), so a show_underline=True kwarg would
        # otherwise be silently lost the first time _sync_regions() reasserts
        # our (still-False) shadow copy on the first hover/scroll.
        self._underline_visible = bool(getattr(self, "_show_underline", False))
        super().setShowUnderline(self._underline_visible)
        self.setUnderlineThickness(self._underline_thickness_for_value(self._value))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Hover/focus now start the preview on every enter, so the hide timer
        # must not outlive the button: an unparented timer would still fire
        # after the widget's C++ side is gone and call into a deleted object.
        self._flyout_hide_timer.setParent(self)
        if self._toggle_enabled:
            self.regionClicked.connect(self._on_region_clicked)
            # A click landing directly on the icon region ("_main") is
            # handled entirely inside the toolkit's own click path — it flips
            # "_main"'s checked state and emits toggled() without ever going
            # through our setChecked() override below, so the "value" region
            # would be left out of sync in that one case. Catch it here too.
            self.toggled.connect(self._on_native_toggled)
        # RowsContent (used for the "value" region's digit) defaults to
        # splitting the region rect by row.ratio and top-aligning each row;
        # with a single row that leaves it stuck in the top half of the
        # region. compact=True instead centers the single row vertically
        # across the whole region rect, like plain text= used to.
        self._rows_compact = True

    # ---------- underline (re-applied after every region rebuild, see _sync_regions) ----------

    def setShowUnderline(self, value: bool) -> None:
        self._underline_visible = bool(value)
        super().setShowUnderline(value)

    def setUnderlineColor(self, color) -> None:
        self._underline_qcolor = color
        super().setUnderlineColor(color)

    def setUnderlineThickness(self, thickness: float) -> None:
        self._underline_thickness_value = float(thickness)
        super().setUnderlineThickness(thickness)

    def _underline_thickness_for_value(self, value: int) -> float:
        span = max(1, self._max_value - 1)
        t = (max(1, value) - 1) / span
        t = max(0.0, min(1.0, t))
        return _UNDERLINE_THICKNESS_MIN + t * (_UNDERLINE_THICKNESS_MAX - _UNDERLINE_THICKNESS_MIN)

    # ---------- checked state (kept in sync with both regions, even when the
    # caller suppresses the toggled signal) ----------

    def setChecked(self, checked: bool, emit_signal: bool = True) -> None:
        # External state sync (e.g. divider/toolbar.py's sync_toolbar_state,
        # presenter.py's viewport-change handler) always calls this with
        # emit_signal=False to avoid a feedback loop, which means the
        # `toggled` signal never fires for that path — so the rebuild below
        # is done unconditionally here rather than from a toggled.connect.
        # A full _sync_regions() (not just setRegionChecked) is required:
        # the icon region's static icon= field itself needs to switch to
        # _icon_checked/_icon_normal (see _icon_region_icon), and only
        # _sync_regions() -> _build_regions() recomputes that.
        self._is_checked = bool(checked)
        super().setChecked(checked, emit_signal=emit_signal)
        self._sync_regions()

    def _on_native_toggled(self, checked: bool) -> None:
        # A click landing directly on the icon region ("_main") is handled
        # entirely inside the toolkit's own click path (see the comment at
        # the toggled.connect above) — it never goes through our
        # setChecked() override, so _is_checked needs updating here too.
        self._is_checked = bool(checked)
        self._sync_regions()

    def _sync_region_checked_state(self, checked: bool) -> None:
        if not self._toggle_enabled:
            return
        # `group=` (see _build_regions) only mirrors hover/press across
        # regions, not the toggle/CHECKED state, so both the icon region
        # (whose icon= tuple depends on it) and the split "value" region
        # (whose darkened background depends on it) are asserted explicitly
        # rather than trusting that they already picked it up.
        # Must NOT emit toggled — this is a visual sync on hover/region rebuild,
        # not a user toggle. Emitting here caused hover (enterEvent -> _set_hover_split
        # -> _sync_regions -> this) to trigger `toggled` -> `on_magnifier_guides_toggled`
        # -> laser disable on every hover (see [laser-debug] enterEvent stack).
        self.setRegionChecked(self._icon_region_id(), checked, emit=False)
        if self._hovered_split:
            self.setRegionChecked("value", checked, emit=False)

    # ---------- backward-compat value API ----------

    def get_value(self) -> int:
        return self._value

    def set_value(self, value: int, emit: bool = True) -> None:
        clamped = max(self._min_value, min(self._max_value, int(value)))
        if clamped == self._value:
            scroll_value_debug("set_value noop %s→%s emit=%s widget=%s", self._value, clamped, emit, type(self).__name__)
            return
        old = self._value
        self._value = clamped
        scroll_value_debug("set_value %s→%s emit=%s widget=%s reason=%s", old, clamped, emit, id(self), "api")
        self.setUnderlineThickness(self._underline_thickness_for_value(clamped))
        self._sync_regions()
        if emit:
            scroll_value_debug("valueChanged emit %s widget=%s", clamped, id(self))
            if clamped == 0:
                try:
                    import traceback

                    from shared.debug_flags import env_flag as _env_flag

                    _lg = logging.getLogger("ImproveImgSLI")
                    # LOG gate (IMGSLI_LASER_DEBUG = [laser-debug] traces only).
                    # UI visibility must never read this flag — use IMGSLI_LASER_UI_DEBUG.
                    if _env_flag("IMGSLI_LASER_DEBUG"):
                        prefix = "[laser-debug]"
                        stack = "".join(traceback.format_stack(limit=15)[:-1])
                        msg = "LASER SCROLL emit value=0 widget=%s id=%s objectName=%r"
                        args = (type(self).__name__, id(self), self.objectName())
                        if _env_flag("IMGSLI_LASER_DEBUG"):
                            _lg.warning("%s %s\n%s", prefix, msg % args, stack)
                        else:
                            _lg.debug("%s %s\n%s", prefix, msg % args, stack)
                except Exception:
                    pass
            self.valueChanged.emit(clamped)

    # ---------- saved-value memory (restore previous width after hide/show) ----------

    def get_saved_value(self) -> int | None:
        return self._saved_value

    def set_saved_value(self, value: int | None) -> None:
        self._saved_value = None if value is None else int(value)

    def restore_saved_value(self) -> int | None:
        value = self._saved_value
        self._saved_value = None
        return value

    # ---------- value-edit contract query (always idle) ----------

    def is_editing(self) -> bool:
        """Always ``False``: this control has no Enter edit mode.

        Deliberate exception to the app-wide value-edit contract (owner rule
        2026-10-20): Enter is the secondary action (``rightClicked`` ->
        colour picker), the keyboard value path is the wheel and the Up-pill's
        Left/Right, so arrows never belong to this control while it is
        focused. The query stays implemented because sections/flyouts
        duck-type it (``arrow_gate_open`` in the toolkit) — returning ``False``
        is what keeps every arrow in ring navigation.
        """
        return False

    # ---------- click: value region (hover split) also toggles orientation ----------

    def _on_region_clicked(self, region_id: str) -> None:
        # When hovered, the button splits into an "icon" region (toggle=True,
        # named "_main") and a non-toggle "value" region showing the digit.
        # A left click landing on the value region would otherwise do
        # nothing, unlike the plain single-region toggle button used in
        # beginner mode. Mirror that behavior here.
        if region_id == "value":
            self.setChecked(not self.isChecked())

    # ---------- hover: single region idle, icon+value split on hover ----------

    def enterEvent(self, event) -> None:
        # Public Button hover seeding (enterEvent → group= mirror) only sees
        # the regions that already exist. Expand to the icon+value capsule
        # first so both siblings share group= when HOVERED is applied.
        self._mouse_hovered = True
        self._set_hover_split(True)
        super().enterEvent(event)
        # Hover must NOT raise the value flyout: the owner wants only the
        # digit inside the button on hover. ``_set_hover_split(True)`` above
        # paints it — ``_is_scrolling`` stays False here, so the "value"
        # region's row is not suppressed. The flyout stays an affordance of
        # the other triggers (keyboard focus, wheel, a click).
        # See _show_flyout for the suppressed-row contract.

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._mouse_hovered = False
        self._set_hover_split(False)
        self._hide_flyout()

    def _set_hover_split(self, active: bool) -> None:
        if active == self._hovered_split:
            return
        self._hovered_split = active
        self._sync_regions()

    # ---------- wheel/key-driven value stepping ----------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """A click raises the value preview (the pointer path to the pill).

        Focus alone is not enough: a button that already holds activation
        focus (the tab bootstrap lands on the first control, or the pill
        interaction just returned focus here) gets no new ``FocusIn`` on the
        click, so the focus preview would never appear and the Up key would
        have nothing to enter. A press is a deliberate interaction — show the
        pill exactly like the wheel path does (``_show_flyout`` keeps it up
        while the pointer is over the button).
        """
        self._show_flyout()
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        scroll_value_debug("wheelEvent delta=%s value=%s widget=%s", delta, self._value, id(self))
        if not delta:
            super().wheelEvent(event)
            return
        event.accept()
        self._step_value(1 if delta > 0 else -1)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        scroll_value_debug("keyPressEvent key=%s value=%s widget=%s", key, self._value, id(self))
        # Enter is this control's SECONDARY ACTION, not an edit-mode toggle
        # (owner rule 2026-10-20): emit exactly the signal a mouse right click
        # emits, so every consumer already wired to ``rightClicked`` (the
        # multi_compare divider-width -> colour picker, onboarding
        # ``b_expert`` -> colour dialog) works from the keyboard unchanged.
        # Consumed here so the toolkit Button's own Space/Enter activation
        # (``_activate_via_keyboard``) never runs: Enter must not toggle, step
        # or otherwise change the value — the keyboard value path is the wheel
        # and the Up-pill's Left/Right.
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            scroll_value_debug("Enter → rightClicked widget=%s", id(self))
            self.rightClicked.emit()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            # Escape hides the preview flyout (e.g. after wheel) and must not
            # propagate to close unrelated flyouts.
            if self._flyout is not None and self._flyout.isVisible():
                scroll_value_debug("Escape hide preview widget=%s", id(self))
                self._dismiss_preview()
                event.accept()
                return
        if key == Qt.Key.Key_Up and (self._flyout is None or not self._flyout.isVisible()):
            # No preview yet — a programmatic activation focus deliberately
            # does not raise one. Create it on demand so THIS press can enter
            # it: leave the event unaccepted, the section then finds the fresh
            # extension and focuses it.
            self._show_flyout()
        super().keyPressEvent(event)

    def _dismiss_preview(self) -> None:
        """Hide the value pill and hand the keyboard back to this button.

        The single Escape repair path: reached from the pill's own
        ``keyPressEvent`` (the pill holds focus after Up — see
        ``_ScrollValueFlyout.keyPressEvent``) and from this button's (a
        wheel/click preview never steals focus). Must go through
        ``_hide_flyout()``: it is what resets ``_is_scrolling`` and re-syncs the
        regions, without which the "value" region keeps its suppressed/empty
        rows and the digit stays blank.
        """
        self._suppress_focus_preview = True
        try:
            self._hide_flyout()
            self.update()
            # Hand the keyboard back to the button. The pill held focus after
            # Up, so without this the closing pill would leave focus nowhere
            # (Qt falls back to the window's first tab-order widget).
            try:
                from sli_ui_toolkit.managers import NavigationManager

                self.setFocus(NavigationManager.get_instance().current_focus_reason())
            except Exception:
                pass
        finally:
            self._suppress_focus_preview = False

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        scroll_value_debug(
            "focusIn widget=%s reason=%s kb=%s suppress=%s hover=%s",
            id(self), event.reason().name, getattr(self, "_keyboard_focus", None),
            self._suppress_focus_preview, self._mouse_hovered,
        )
        # Нижняя капсула (value) уже была для ховера мышкой — показываем её и для фокуса.
        # The preview shows on ANY focus, keyboard or mouse: gating it on the
        # toolkit's ``_keyboard_focus`` (keyboard modality only) left a button
        # focused the mouse way — a click, the owner's real session — with no
        # pill at all, so Up had nothing to enter (sv-hover-fix). The preview
        # never steals focus, so mouse-modality lighting it is safe; the ring
        # still follows modality.
        # Both halves of the preview (the anchor's value split and the pill)
        # are gated on the suppression flag: an exit path returning focus
        # here — Esc, or the timer dismiss below via Qt's popup focus-restore
        # — is not a NEW focus grant and must not relight the preview (that
        # relight is the "button sticks in the value-display state" the
        # owner reported, sv-hover-fix).
        if not self._suppress_focus_preview:
            # A *programmatic* focus grant is not a user preview: the new tab's
            # bootstrap lands activation focus on the first control
            # (MouseFocusReason, hover=False, keyboard=False) and the pill used
            # to pop up on its own at startup and vanish 700 ms later. Show the
            # preview only for a plausible user grant — keyboard (arrow/Tab) or
            # the pointer actually over the button (a click). Up still works
            # without a preview: keyPressEvent creates the pill on demand.
            if self._keyboard_focus or self._mouse_hovered:
                self._set_hover_split(True)
                self._show_flyout()
                # Keyboard focus: the preview must persist while the focus ring
                # is on the button (owner decision 2026-10-19) — no 700 ms
                # auto-hide, so Up can enter the pill at any time regardless of
                # how long the owner pauses. The wheel preview stays transient,
                # and the mouse/click preview keeps its own timer.
                if self._keyboard_focus:
                    self._flyout_hide_timer.stop()

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        _t = QApplication.focusWidget()
        scroll_value_debug(
            "focusOut widget=%s target=%s hover=%s",
            id(self), type(_t).__name__ if _t is not None else None, self._mouse_hovered,
        )
        # Гасим капсулу если ушли фокусом и мышка не ховерит — но НЕ когда
        # фокус ушёл в наш же флайаут значения (hover-preview → Up): капсула
        # остаётся частью той же группы, и её возврат не должен мигать при
        # входе в пилюлю и обратно.
        if self.underMouse():
            return
        target = QApplication.focusWidget()
        if (
            self._flyout is not None
            and target is not None
            and (target is self._flyout or self._flyout.isAncestorOf(target))
        ):
            return
        self._set_hover_split(False)
        if target is None:
            # clearFocus() with nowhere to hand focus: leave the preview
            # alone (an immediate hide() here re-asserts window focus and
            # fights the clear — see BaseFlyout._finish_hide).
            return
        # The keyboard preview persists while the button holds focus (no
        # auto-hide); once the focus ring moves to another widget, the pill
        # must go with it.
        self._hide_flyout()

    def _step_value(self, step: int) -> None:
        old = self._value
        new_value = max(self._min_value, min(self._max_value, self._value + step))
        scroll_value_debug("_step_value step=%s %s→%s widget=%s", step, old, new_value, id(self))
        self.set_value(new_value)
        self._show_flyout()

    # ---------- regions ----------

    def _sync_regions(self) -> None:
        regions, split = self._build_regions()
        self.set_regions(regions, split=split)
        # set_regions() rebuilds the button's internal region/paint state from
        # scratch, which drops any previously applied underline visibility/color.
        # Re-assert our last known desired state so hover/scroll/value changes
        # can't silently erase the divider-color indicator. The underline is
        # NOT tied to the value any more (owner rule 2026-10-19): the zero
        # state shows the zero_icon instead of a digit, but the line itself
        # stays visible whenever the host enabled it.
        super().setShowUnderline(self._underline_visible)
        if self._underline_qcolor is not None:
            super().setUnderlineColor(self._underline_qcolor)
        if self._underline_thickness_value is not None:
            super().setUnderlineThickness(self._underline_thickness_value)
        # set_regions() rebuilds region runtime state from scratch too (new
        # ButtonRegion objects), so re-assert checked here as well — this is
        # what makes the "value" region already show as checked/darkened the
        # moment it first appears on hover, instead of only from the next
        # setChecked() call.
        self._sync_region_checked_state(self.isChecked())

    def _is_at_zero(self) -> bool:
        return self._zero_icon is not None and self._value <= self._min_value

    def _icon_region_id(self) -> str:
        # A toggle=True region must be named "_main" — the toolkit's click
        # handler (events.py) only updates isChecked()/emits toggled() and
        # the base Button._checked state for the region literally named
        # "_main", regardless of which region the split layout renders it in.
        return "_main" if self._toggle_enabled else "icon"

    def _icon_region_icon(self):
        # The (unchecked, checked) icon-tuple convenience documented for
        # Button's own icon= constructor kwarg is Button-level sugar around
        # its single implicit "_main" region — it is not implemented for
        # ButtonRegion.icon when regions= is passed directly (as we always
        # do here), so a tuple placed there is never unpacked/switched by
        # the toolkit itself. Do the checked -> icon selection by hand,
        # baked into whichever single icon we hand to the region.
        #
        # These are stored as self._svb_icon_normal/_svb_icon_checked (not
        # self._icon_normal/_icon_checked) because Button.__init__ parses
        # its own icon= kwarg into attributes of that exact name for its
        # built-in tuple convenience; since we never forward icon= to
        # super().__init__() (we consume it ourselves), Button.__init__
        # still runs with icon=None and was clobbering ours right after
        # __init__ set them, making every rebuild after construction use a
        # None checked-icon.
        if not self._toggle_enabled:
            return self._svb_icon_normal
        # isChecked() itself isn't used here: it reads Button's internal
        # _region_states, which doesn't exist yet the first time this runs
        # (from _build_regions() in __init__, before super().__init__()).
        return self._svb_icon_checked if self._is_checked else self._svb_icon_normal

    def _build_regions(self) -> tuple[list[ButtonRegion], VerticalSplit]:
        icon_region_id = self._icon_region_id()
        if not self._hovered_split:
            regions = [
                ButtonRegion(
                    id=icon_region_id,
                    icon=self._icon_region_icon(),
                    icon_size_px=20,
                    variant="default",
                    group=self._GROUP,
                    toggle=self._toggle_enabled,
                    # group= disables the toolkit's default content clipping;
                    # re-enable so the icon stays inside its own region.
                    clip_content=True,
                ),
            ]
            return regions, VerticalSplit()

        # Per-region corner_radii is intentionally omitted: the button-level
        # corner_radius=_RADIUS (see __init__) already produces a seamless
        # capsule automatically (rounded outer ends, square inner seam) via
        # the toolkit's outer-clip contract, and stays in sync with the
        # underline arc radius, which reads the same button-level radius.
        icon_region = ButtonRegion(
            id=icon_region_id,
            icon=self._icon_region_icon(),
            icon_size_px=20,
            weight=1.1,
            variant="default",
            group=self._GROUP,
            toggle=self._toggle_enabled,
            clip_content=True,
        )
        if self._is_at_zero():
            value_region = ButtonRegion(
                id="value",
                icon=self._zero_icon,
                icon_size_px=13,
                weight=0.9,
                variant="default",
                group=self._GROUP,
                clip_content=True,
            )
        else:
            # While the scroll flyout is showing the value above the button,
            # the digit inside the button itself is suppressed (blank region)
            # so the two aren't both flashing the number at once; it reappears
            # here, drawn over the underline (see _LAYERS ordering above),
            # once hover lingers past the flyout's hide delay with no scroll.
            rows = [] if self._is_scrolling else [ButtonRow(text=str(self._value), size=12)]
            value_region = ButtonRegion(
                id="value",
                rows=rows,
                weight=0.9,
                variant="default",
                group=self._GROUP,
                clip_content=True,
            )
        # Bottom breathing room from the underline is reserved via the
        # button-level bottom-only content_padding (see __init__) rather
        # than a spacer region.
        return [icon_region, value_region], VerticalSplit()

    # ---------- flyout ----------

    def _show_flyout(self) -> None:
        try:
            from ui.canvas_infra.rhi.rhi_focus import park_keyboard_focus_off_qrhi

            park_keyboard_focus_off_qrhi()
        except Exception:
            pass
        if self._flyout is None:
            self._flyout = _ScrollValueFlyout(self.window())
            # Навигация: Up входит в флайаут сверху (bind_flyout side="above"),
            # Down возвращается к якорю (_nav_exit="down" на _ScrollValueFlyout);
            # Left/Right шагуют значение в самом флайауте.
            try:
                from sli_ui_toolkit.managers import bind_flyout

                bind_flyout(self, self._flyout, side="above")
            except Exception:
                pass
        if self._is_at_zero():
            self._flyout.show_value("", icon=themed_icon(self._zero_icon), anchor=self)
        else:
            self._flyout.show_value(str(self._value), anchor=self)
        # While the mouse is on the button the preview is persistent: leaveEvent
        # owns the hide. This matters for a button focused by a click (the
        # mouse is on it) — the pill must not be killed by the hide timer
        # before a hand can travel from mouse to keyboard and press Up (the
        # owner's value-change path). Otherwise the transient wheel/focus
        # preview arms its own timer.
        if self._mouse_hovered:
            self._flyout_hide_timer.stop()
        else:
            self._flyout_hide_timer.start(_FLYOUT_HIDE_MS)
        if not self._is_scrolling:
            self._is_scrolling = True
            self._sync_regions()
        scroll_value_debug(
            "show flyout widget=%s focus=%s timer=%s hover=%s kb=%s",
            id(self), self.hasFocus(), self._flyout_hide_timer.isActive(),
            self._mouse_hovered, getattr(self, "_keyboard_focus", None),
        )
        # Preview registers its nav section too (show_value →
        # register_nav_section=True) so Up can enter the pill without stealing
        # focus on hover.

    def _on_flyout_hide_timeout(self) -> None:
        """The transient hide (the 700 ms timer fired on its own).

        Closing the popup makes Qt restore the keyboard to the widget that
        held focus when the pill opened — the anchor. That restored focus is
        not a new focus grant: without suppression it re-triggers the anchor's
        focus preview (split relights, pill re-shows, timer re-arms), and the
        button settles into the value-display state instead of resting — the
        stuck look the owner reported after a wheel nudge (sv-hover-fix).
        Same suppression idiom as ``_dismiss_preview``.
        """
        scroll_value_debug("hide timeout widget=%s", id(self))
        self._suppress_focus_preview = True
        try:
            self._hide_flyout()
        finally:
            self._suppress_focus_preview = False

    def _hide_flyout(self) -> None:
        self._flyout_hide_timer.stop()
        scroll_value_debug("hide flyout widget=%s", id(self))
        if self._flyout is not None:
            self._flyout.hide()
        if self._is_scrolling:
            self._is_scrolling = False
            self._sync_regions()

ScrollValueButton.inspect_spec = InspectSpec(
    family="ScrollValueButton",
    state=(
        SpecField("value", "get_value"),
        SpecField("min_value", "_min_value", private=True),
        SpecField("max_value", "_max_value", private=True),
        SpecField("saved_value", "get_saved_value"),
        SpecField("checked", "isChecked"),
    ),
    regions=True,
    docs="docs/dev/widgets/scroll_value_button.md",
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
ScrollValueButton.widget_descriptor = WidgetDescriptor(
    family=ScrollValueButton.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(ScrollValueButton.inspect_spec, 'config', ()),
        state=ScrollValueButton.inspect_spec.state,
        token_family=getattr(ScrollValueButton.inspect_spec, 'token_family', ()),
        regions=getattr(ScrollValueButton.inspect_spec, 'regions', False),
        layers=getattr(ScrollValueButton.inspect_spec, 'layers', False),
        docs=getattr(ScrollValueButton.inspect_spec, 'docs', ''),
        preview_seed=getattr(ScrollValueButton.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(ScrollValueButton.inspect_spec, 'apply_config_refresh', None),
    ),
)
