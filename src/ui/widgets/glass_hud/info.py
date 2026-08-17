from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

from PySide6.QtCore import QRect, QTimer
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import UiFont, scaled_px
from sli_ui_toolkit.ui.in_window_surface import (
    clamp_surface_rect,
    surface_anchor_rect,
    surface_available_rect,
)

from ui.widgets.glass_hud.hud import GlassHUD
from ui.widgets.flyout_debug import (
    flyout_debug,
    flyout_debug_elapsed_ms,
    flyout_debug_timer,
)

_MARGIN = 8


class InfoHUD(GlassHUD):
    """Persistent read-only info chip inset into a corner of a canvas.

    A ``pinned`` flyout (see sli-ui-toolkit's FLYOUT_SYSTEM.md "Pinned
    flyouts"): survives outside clicks, outside wheel, window deactivate,
    and its anchor moving/resizing — unlike a normal flyout it does not
    close for any of those. It tracks its anchor's resize/move itself (see
    ``GlassHUD._watch_target``), so the host doesn't need to wire that up;
    `reposition()` remains for hosts that want to force a resync eagerly
    (mirrors `ZoomIndicator.sync_position()`).

    `show_aligned` doesn't fit here — it places a flyout *outside* its
    anchor (dropdown under a button); this widget sits *inside* a corner of
    its anchor, inset by a margin, so it computes its own geometry instead.

    Tagged with its own ``flyout_group`` (rather than falling back to the
    untagged default) so the host's ``GroupShowPolicy`` can give it
    "never dismissed by another flyout opening" rules without lumping it
    in with ordinary popups — see ``src/ui/flyout_policy.py``.
    """

    flyout_group = "info_hud"

    def __init__(self, parent: QWidget, *, corner: str = "left"):
        super().__init__(parent)
        self._corner = corner
        self._target_widget: QWidget | None = None
        # The host's labels (toolkit `Label`, scale-resolved on their own)
        # resize when the UI scale/font changes; re-lay this HUD around
        # their new sizeHint like ZoomIndicator does.
        UiFont.get_instance().font_changed.connect(self._on_ui_font_changed)

    def _on_ui_font_changed(self) -> None:
        if self.isVisible():
            self._position()

    def add_label(self, label: QWidget) -> None:
        self.add_widget(label)

    def show_on(self, target_widget: QWidget) -> None:  # noqa
        flyout_debug("info_hud[%s]: show_on(%r)", self._corner, target_widget)
        was_visible = self.isVisible()
        if self._target_widget is not target_widget:
            self._connect_zoom_refresh(target_widget)
        self._watch_target(target_widget)
        self._target_widget = target_widget
        self._ensure_overlay_parent(target_widget)
        self._position()
        self.show()
        self._raise_self()
        if not was_visible:
            # See ZoomIndicator.update_zoom()'s identical guard for the full
            # rationale: a single _position() pass right after first
            # becoming visible can still leave geometry unsettled for one
            # frame or two. Cheap, first-show-only.
            flyout_debug("info_hud[%s]: show_on -> scheduling deferred _position()", self._corner)

            def _deferred_position() -> None:
                flyout_debug("info_hud[%s]: deferred _position() firing now", self._corner)
                self._position()

            QTimer.singleShot(0, _deferred_position)

    def reposition(self) -> None:
        flyout_debug("info_hud[%s]: reposition()", self._corner)
        self._resync()

    def _position(self) -> None:
        target = self._target_widget
        if target is None:
            return
        start = flyout_debug_timer()
        self._reflow_container()
        self.adjustSize()

        anchor_rect = surface_anchor_rect(self, target, self.overlay_layer)
        available = surface_available_rect(self, target, self.overlay_layer)
        w, h = self.width(), self.height()
        margin = scaled_px(_MARGIN)
        y = anchor_rect.bottom() - h - margin
        x = (
            anchor_rect.left() + margin
            if self._corner == "left"
            else anchor_rect.right() - w - margin
        )
        self.setGeometry(clamp_surface_rect(QRect(x, y, w, h), available))
        flyout_debug(
            "info_hud[%s]: _position() layout+geometry took %.2fms "
            "self=%r container=%r",
            self._corner,
            flyout_debug_elapsed_ms(start),
            self.geometry(),
            self.container.geometry(),
        )
        self._refresh_backdrop()

InfoHUD.inspect_spec = InspectSpec(
    family="InfoHUD",
    state=(
        SpecField("corner", "_corner", private=True),
        SpecField("target", "_target_widget", private=True),
    ),
    docs="docs/dev/widgets/glass_hud.md",
)