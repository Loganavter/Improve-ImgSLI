from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

from typing import Callable

from PySide6.QtCore import QEvent, QRect, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from resources.translations import tr
from sli_ui_toolkit.i18n import translatable_tooltip
from sli_ui_toolkit.ui.in_window_surface import (
    clamp_surface_rect,
    surface_anchor_rect,
    surface_available_rect,
)
from sli_ui_toolkit.managers import UiFont, scaled_px
from sli_ui_toolkit.ui.managers.ui_font import apply_ui_font
from sli_ui_toolkit.widgets import Button

from ui.icon_manager import AppIcon
from ui.widgets.glass_hud.hud import GlassHUD, caller_str
from ui.widgets.flyout_debug import (
    flyout_debug,
    flyout_debug_elapsed_ms,
    flyout_debug_enabled,
    flyout_debug_timer,
)

_MARGIN = 8


class ZoomIndicator(GlassHUD):
    """Pinned corner flyout showing the current zoom percent with a reset button.

    Same glassmorphism chip construct as ``InfoHUD`` (see
    ``ui/widgets/glass_hud/info.py`` and the shared ``ui/widgets/glass_hud/hud.py``):
    a persistent, always-on-top HUD inset into a corner of the canvas
    rather than a dismissible popup, so it survives outside clicks/wheel/
    window deactivate and other flyouts opening. It tracks its anchor's
    resize/move itself (see ``GlassHUD._watch_target``), so the host
    doesn't need to wire that up; `sync_position()` remains for hosts that
    want to force a resync eagerly (mirrors `InfoHUD.reposition()`).

    Self-contained: takes a `lang_provider` callback to localize its
    prefix. The owning UI is responsible for connecting
    `btn_zoom_reset.clicked`.
    """

    flyout_group = "zoom_indicator"

    def __init__(
        self,
        parent: QWidget,
        *,
        lang_provider: Callable[[], str] = lambda: "en",
        target_widget: QWidget | None = None,
        reset_icon: AppIcon | QIcon | None = None,
    ):
        super().__init__(parent)
        # Purely informational HUD: its only control (btn_zoom_reset) is
        # deliberately NoFocus (see below), so there is nothing here for
        # keyboard navigation to reach. Skip BaseFlyout.show()'s focus grab
        # and NavigationSection registration -- without this, every resync
        # while zoom/pan is non-default steals keyboard focus from whatever
        # the user was actually doing and inserts a dead-end nav section.
        self._skip_focus_grab = True
        self._lang_provider = lang_provider
        if target_widget is not None:
            self._connect_zoom_refresh(target_widget)
            self._watch_target(target_widget)
        self._target_widget = target_widget

        self.setObjectName("ZoomIndicator")

        row = QWidget(self.container)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(scaled_px(4), 0, 0, 0)
        layout.setSpacing(scaled_px(4))

        self._label = QLabel("100%", row)
        self._label.setContentsMargins(0, 0, scaled_px(6), 0)
        if flyout_debug_enabled():
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if not isinstance(app, QApplication):
                app = None
            flyout_debug(
                "zoom_indicator: __init__ calling apply_ui_font() self=%#x "
                "label=%#x app.font=(family=%r pointSizeF=%.2f) caller=%s",
                id(self),
                id(self._label),
                app.font().family() if app is not None else None,
                app.font().pointSizeF() if app is not None else -1.0,
                caller_str(),
            )
        # point_size override (not the bare app default) -- keeps this
        # readable at the same larger size as InfoHUD's own labels (see
        # _INFO_HUD_LABEL_PIXEL_SIZE in primitives.py). Persists across
        # future UiFont.font_changed resyncs too (the toolkit's `apply()`
        # closure captures these same kwargs each call).
        apply_ui_font(self._label, point_size=14)
        if flyout_debug_enabled():
            self._label.installEventFilter(self)
        # `UiFont.apply()` (what `apply_ui_font()` calls) now keeps
        # `self._label`'s *font itself* in sync with any future real
        # `font_changed` on its own (see that method's docstring for the
        # startup-ordering bug this fixes -- a plain QLabel constructed
        # before the host's own startup font correction finishes used to
        # bake in a stale fallback font forever). What it can't do for us
        # is re-run *this* flyout's own layout: a font-size change can
        # grow/shrink `self._label`'s sizeHint, which needs
        # `_reflow_container()`/`_position()` to actually resize the glass
        # panel around it -- see docs/dev/rendering/glass-panel-text-vibrancy-plan.md
        # Phase 3 for the full investigation.
        UiFont.get_instance().font_changed.connect(self._on_ui_font_changed)
        layout.addWidget(self._label)
        self.btn_zoom_reset = Button(reset_icon or AppIcon.SYNC, parent=row)
        self.btn_zoom_reset.setFixedSize(scaled_px(22), scaled_px(22))
        # Hiding this overlay after a reset (zoom back to 1.0) would otherwise
        # hand keyboard focus back to whatever QLineEdit had it before the
        # button stole it, since Qt restores prior focus when a focused
        # widget's ancestor is hidden. Keep the button out of the focus chain.
        self.btn_zoom_reset.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        translatable_tooltip(self.btn_zoom_reset, "tooltip.reset_zoom")
        layout.addWidget(self.btn_zoom_reset)

        self.add_widget(row)
        self.update_zoom(1.0)

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._label and event.type() == QEvent.Type.FontChange:
            flyout_debug(
                "zoom_indicator: self._label FontChange self=%#x label=%#x "
                "new_font=(family=%r pointSizeF=%.2f) caller=%s",
                id(self),
                id(self._label),
                self._label.font().family(),
                self._label.font().pointSizeF(),
                caller_str(),
            )
        return super().eventFilter(obj, event)

    def _on_ui_font_changed(self) -> None:
        # `self._label`'s own font is already re-synced by this point --
        # `UiFont.apply()`'s internal `font_changed` connection (see
        # `apply_ui_font(self._label)` above) fires before this one, same
        # signal, connected first. This handler only needs to catch up the
        # surrounding layout to whatever sizeHint that resync produced.
        if self.isVisible():
            self._position()

    def set_target(self, target: QWidget):
        if target is not self._target_widget:
            self._connect_zoom_refresh(target)
        self._watch_target(target)
        self._target_widget = target

    def update_zoom(self, zoom: float, pan_x: float = 0.0, pan_y: float = 0.0):
        percent = int(round(float(zoom) * 100))
        prefix = tr("label.zoom", self._lang_provider())
        self._label.setText(f"{prefix}: {percent}%")
        visible = (
            abs(float(zoom) - 1.0) > 1e-3
            or abs(float(pan_x)) > 1e-4
            or abs(float(pan_y)) > 1e-4
        )
        was_visible = self.isVisible()
        if not visible or self._target_widget is None:
            if was_visible:
                flyout_debug("zoom_indicator: update_zoom -> hide (zoom=%.4f)", zoom)
            self.hide()
            return
        flyout_debug(
            "zoom_indicator: update_zoom(zoom=%.4f, pan=(%.2f, %.2f)) was_visible=%s "
            "caller=%s",
            zoom,
            pan_x,
            pan_y,
            was_visible,
            caller_str() if flyout_debug_enabled() else "",
        )
        self._ensure_overlay_parent(self._target_widget)
        self._position()
        if not was_visible:
            self.show()
        self._raise_self()
        if not was_visible:
            # First time this indicator becomes visible in a while (or ever):
            # a single _position() pass right here can still leave `row`'s
            # nested layout (label + reset button) geometry inconsistent --
            # reported live as "рендерит только кнопку сброса" for the first
            # couple of frames, then the zoom text popping in but overlapping
            # the button, stuck that way until something unrelated (a
            # language switch) forced a full extra relayout. Root cause not
            # fully pinned down (unlike the earlier "text doesn't grow"
            # bug -- an offscreen repro of a *never-shown* widget tree gave
            # inconsistent, not-trustworthy numbers for this specific cold-
            # start case, unlike the warm-tree case that _reflow_container()
            # targets), but a zero-delay deferred second pass -- running
            # after Qt's event loop has processed whatever pending
            # show/reparent/style-polish work was still in flight during the
            # synchronous call above -- mirrors what the language-switch
            # workaround does by accident (QEvent::LanguageChange forces a
            # full-tree relayout) and is cheap enough to always do on this
            # not-hot (first-show-only) path.
            flyout_debug("zoom_indicator: update_zoom -> scheduling deferred _position()")

            def _deferred_position(_pass: int = 1) -> None:
                flyout_debug("zoom_indicator: deferred _position() firing now (pass=%d)", _pass)
                self._position()
                # One deferred pass mostly closes the gap but is not
                # airtight -- reported live again after this HUD started
                # hiding/re-showing on every tab switch (see
                # MultiCompareWidget.hideEvent/showEvent), which retriggers
                # this cold-start path far more often than the original
                # once-per-launch case this was written for. A second
                # zero-delay pass, one more event-loop tick later, is still
                # cheap on this not-hot path and gives Qt's pending style/
                # layout work one extra chance to settle before we trust
                # `row`'s sizeHint.
                if _pass == 1:
                    QTimer.singleShot(0, lambda: _deferred_position(2))

            QTimer.singleShot(0, _deferred_position)

    def sync_position(self):
        flyout_debug("zoom_indicator: sync_position()")
        self._resync()

    def _position(self) -> None:
        target = self._target_widget
        if target is None:
            return
        if flyout_debug_enabled():
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if not isinstance(app, QApplication):
                app = None
            flyout_debug(
                "zoom_indicator: _position() ENTRY self=%#x label=%#x caller=%s "
                "label.font=(family=%r pointSizeF=%.2f pixelSize=%d key=%r) "
                "app.font=(family=%r pointSizeF=%.2f)",
                id(self),
                id(self._label),
                caller_str(),
                self._label.font().family(),
                self._label.font().pointSizeF(),
                self._label.font().pixelSize(),
                self._label.font().key(),
                app.font().family() if app is not None else None,
                app.font().pointSizeF() if app is not None else -1.0,
            )
        start = flyout_debug_timer()
        self._reflow_container()
        self.adjustSize()

        anchor_rect = surface_anchor_rect(self, target, self.overlay_layer)
        available = surface_available_rect(self, target, self.overlay_layer)
        w, h = self.width(), self.height()
        margin = scaled_px(_MARGIN)
        x = anchor_rect.right() - w - margin
        y = anchor_rect.top() + margin
        self.setGeometry(clamp_surface_rect(QRect(x, y, w, h), available))
        flyout_debug(
            "zoom_indicator: _position() target=%s target.size=%r target.isVisible=%s "
            "overlay_layer=%r anchor_rect=%r available=%r self.parent=%s",
            type(target).__name__,
            target.size(),
            target.isVisible(),
            self.overlay_layer,
            anchor_rect,
            available,
            type(self.parentWidget()).__name__ if self.parentWidget() else None,
        )
        flyout_debug(
            "zoom_indicator: _position() layout+geometry took %.2fms "
            "self=%r container=%r row=%r label=%r label.text=%r "
            "label.sizeHint=%r btn=%r btn.pos=%r",
             flyout_debug_elapsed_ms(start),
             self.geometry(),
             self.container.geometry(),
             (self._label.parentWidget().geometry() if self._label.parentWidget() else None),  # type: ignore[union-attr]  # debug-only: double call, no narrowing
             self._label.geometry(),
            self._label.text(),
            self._label.sizeHint(),
            self.btn_zoom_reset.geometry(),
            self.btn_zoom_reset.pos(),
        )
        self._refresh_backdrop()

ZoomIndicator.inspect_spec = InspectSpec(
    family="ZoomIndicator",
    state=(
        SpecField("target", "_target_widget", private=True),
    ),
    docs="docs/dev/widgets/glass_hud.md",
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
ZoomIndicator.widget_descriptor = WidgetDescriptor(
    family=ZoomIndicator.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(ZoomIndicator.inspect_spec, 'config', ()),
        state=ZoomIndicator.inspect_spec.state,
        token_family=getattr(ZoomIndicator.inspect_spec, 'token_family', ()),
        regions=getattr(ZoomIndicator.inspect_spec, 'regions', False),
        layers=getattr(ZoomIndicator.inspect_spec, 'layers', False),
        docs=getattr(ZoomIndicator.inspect_spec, 'docs', ''),
        preview_seed=getattr(ZoomIndicator.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(ZoomIndicator.inspect_spec, 'apply_config_refresh', None),
    ),
)