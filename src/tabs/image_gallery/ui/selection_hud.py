"""Selection HUD collaborator — pinned BaseFlyout bottom-center group gallery_selection.

The HUD is a small collaborator object that owns a ``BaseFlyout`` with
``pinned=True`` and ``flyout_group = "gallery_selection"``. It is shown while
the gallery has a non-empty selection and hidden otherwise. Group
``gallery_selection`` is expected to coexist with other flyouts (registered via
the host's ``GroupShowPolicy``); the HUD itself never steals focus.

Usage:
    hud = SelectionHudController(parent_widget, on_clear=..., on_carry=...)
    hud.update(count)  # show/hide automatically
    # on resize/move:
    hud.reposition()
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QLinearGradient
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import BaseFlyout, Button

# Gap between HUD elements.
_HUD_SPACING = 8
_HUD_MARGIN = 8


def _t(translate, key: str, default: str) -> str:
    """i18n helper — use *translate* when available, else *default*."""
    if translate is None:
        return default
    try:
        return translate(key, default)
    except Exception:
        try:
            return translate(key)  # type: ignore[call-arg]
        except Exception:
            return default


class SelectionHudController:
    """Owns the bottom-center pinned selection flyout."""

    flyout_group = "gallery_selection"

    def __init__(
        self,
        parent: QWidget,
        *,
        on_clear: Callable[[], None] | None = None,
        on_carry: Callable[[], None] | None = None,
        on_analyze: Callable[[], None] | None = None,
        on_find_similar: Callable[[], None] | None = None,
        translate: Callable[[str, str], str] | None = None,
    ) -> None:
        self._parent = parent
        self._on_clear = on_clear
        self._on_carry = on_carry
        self._on_analyze = on_analyze
        self._on_find_similar = on_find_similar
        self._translate = translate
        self._count = 0
        self._suppressed = False
        self._notify_active = False
        self._notify_token = 0

        flyout = BaseFlyout(parent, pinned=True)
        flyout.setObjectName("GallerySelectionHud")
        # Mark group for FlyoutManager policy / LayerStack.
        try:
            flyout.flyout_group = self.flyout_group  # type: ignore[attr-defined]
        except Exception:
            pass
        # Glass gradient — subtle vertical shading composited INTO one opaque
        # brush. NOTE: BaseFlyout.set_background_brush REPLACES the panel fill
        # (it does not layer over it), so a translucent white tint here used
        # to leave the body ~transparent with only the shadow visible.
        # Keep the glassy look with an opaque base→light gradient instead.
        try:
            from sli_ui_toolkit.managers import ThemeManager
            from ui.theming import try_resolve_theme_color

            base = None
            for token in ("surface.background", "flyout.background"):
                base = try_resolve_theme_color(ThemeManager.get_instance(), token)
                if base is not None:
                    break
            base = base if isinstance(base, QColor) else QColor(base) if base is not None else QColor(56, 56, 56)
            base.setAlpha(255)
            top = QColor(base).lighter(118)
            top.setAlpha(255)
            grad = QLinearGradient(0, 0, 0, scaled_px(44))
            grad.setColorAt(0.0, top)
            grad.setColorAt(1.0, base)
            flyout.set_background_brush(QBrush(grad))
        except Exception:
            pass
        self.flyout = flyout

        # Build content: label + actions row.
        container = QWidget(flyout)
        row = QHBoxLayout(container)
        row.setContentsMargins(
            scaled_px(_HUD_MARGIN),
            scaled_px(_HUD_MARGIN),
            scaled_px(_HUD_MARGIN),
            scaled_px(_HUD_MARGIN),
        )
        row.setSpacing(scaled_px(_HUD_SPACING))

        self._label = QLabel(container)
        self._label.setObjectName("gallery_selection_label")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._label)

        # Actions: Clear, Analyze (optional), Find similar, Compare → (carry).
        self._clear_btn = Button(
            text=_t(translate, "image_gallery.selection.clear", "Clear"),
            variant="ghost",
            parent=container,
        )
        self._clear_btn.setObjectName("gallery_selection_clear")
        self._clear_btn.clicked.connect(self._handle_clear)
        row.addWidget(self._clear_btn)

        if on_analyze is not None:
            self._analyze_btn = Button(
                text=_t(translate, "image_gallery.selection.analyze", "Analyze"),
                variant="ghost",
                parent=container,
            )
            self._analyze_btn.setObjectName("gallery_selection_analyze")
            self._analyze_btn.clicked.connect(self._handle_analyze)
            row.addWidget(self._analyze_btn)
        else:
            self._analyze_btn = None

        # Find similar — always present (disabled when no selection), triggers on_find_similar.
        self._find_similar_btn = Button(
            text=_t(translate, "image_gallery.selection.find_similar", "Find similar"),
            variant="ghost",
            parent=container,
        )
        self._find_similar_btn.setObjectName("gallery_selection_find_similar")
        self._find_similar_btn.clicked.connect(self._handle_find_similar)
        row.addWidget(self._find_similar_btn)

        self._carry_btn = Button(
            text=_t(translate, "image_gallery.selection.compare", "Compare →"),
            variant="surface",
            parent=container,
        )
        self._carry_btn.setObjectName("gallery_selection_carry")
        self._carry_btn.clicked.connect(self._handle_carry)
        row.addWidget(self._carry_btn)

        flyout.add_widget(container)
        # Default label.
        self._refresh_label()

    # -- public -------------------------------------------------------------

    def update(self, count: int) -> None:
        """Update HUD for *count* selected items (show if >0, hide if 0)."""
        self._count = int(count)
        self._refresh_label()
        if self._count > 0:
            self.show()
        else:
            self.hide()

    # Alias for alternative call sites.
    def set_count(self, count: int) -> None:
        self.update(count)

    def show(self) -> None:
        if self._suppressed:
            return
        if self.flyout.isVisible() and self._count > 0 and not self._notify_active:
            # Already visible — keep position fresh.
            self.reposition()
            return
        if self._count <= 0 and not self._notify_active:
            return
        # Bottom-center of the parent (gallery widget / window content).
        try:
            self.flyout.show_aligned(
                self._parent,
                "bottom-center",
                "bottom-center",
                offset=scaled_px(12),
                animation="none",
                grab_focus=False,
            )
        except Exception:
            try:
                self.flyout.show()
            except Exception:
                pass

    def hide(self) -> None:
        try:
            self.flyout.hide()
        except Exception:
            pass

    def reposition(self) -> None:
        if self._suppressed:
            return
        try:
            self.flyout.reposition()
        except Exception:
            pass

    def set_suppressed(self, suppressed: bool) -> None:
        """Suppress HUD while S3 overlay is visible (FlyoutManager group gallery_selection)."""
        self._suppressed = bool(suppressed)
        if self._suppressed:
            try:
                self.flyout.hide()
            except Exception:
                pass
        elif self._count > 0:
            self.show()

    def notify(self, text: str, timeout_ms: int = 2500) -> None:
        """Transient notice in place of the action row (fail-open).

        Hides the action buttons, shows *text*, then restores the row.
        A newer notify wins: stale timers are ignored via token.
        """
        try:
            self._notify_token += 1
            token = self._notify_token
            self._notify_active = True
            for btn in (
                getattr(self, "_clear_btn", None),
                getattr(self, "_analyze_btn", None),
                getattr(self, "_find_similar_btn", None),
                getattr(self, "_carry_btn", None),
            ):
                try:
                    if btn is not None:
                        btn.setVisible(False)
                except Exception:
                    pass
            try:
                self._label.setText(text)
            except Exception:
                pass
            self.show()
            try:
                QTimer.singleShot(int(timeout_ms), lambda: self._end_notify(token))
            except Exception:
                pass
        except Exception:
            pass

    def _end_notify(self, token: int) -> None:
        try:
            if token != getattr(self, "_notify_token", token):
                return
            self._notify_active = False
            for btn in (
                getattr(self, "_clear_btn", None),
                getattr(self, "_analyze_btn", None),
                getattr(self, "_find_similar_btn", None),
                getattr(self, "_carry_btn", None),
            ):
                try:
                    if btn is not None:
                        btn.setVisible(True)
                except Exception:
                    pass
            self._refresh_label()
            self.update(self._count)
        except Exception:
            pass

    # -- internals ---------------------------------------------------------

    def _refresh_label(self) -> None:
        n = int(self._count)
        tr = getattr(self, "_translate", None)
        if n <= 0:
            text = _t(tr, "image_gallery.selection.none", "No selection")
        elif n == 1:
            text = _t(tr, "image_gallery.selection.one", "1 selected")
        else:
            # Keep simple fallback; i18n can use placeholder later.
            raw = _t(tr, "image_gallery.selection.many", "{n} selected")
            try:
                text = raw.format(n=n) if "{n}" in raw else f"{n} selected" if raw == "{n} selected" else raw.replace("{n}", str(n))
                # If translation returned default with placeholder, ensure n inserted.
                if text == raw and "{n}" not in raw:
                    text = f"{n} selected"
            except Exception:
                text = f"{n} selected"
        try:
            self._label.setText(text)
        except Exception:
            pass
        # Enable/disable actions based on count.
        try:
            self._carry_btn.setEnabled(n > 0)
        except Exception:
            pass
        try:
            self._clear_btn.setEnabled(n > 0)
        except Exception:
            pass
        try:
            self._find_similar_btn.setEnabled(n > 0)
        except Exception:
            pass
        if self._analyze_btn is not None:
            try:
                self._analyze_btn.setEnabled(n > 0)
            except Exception:
                pass

    def _handle_clear(self) -> None:
        if callable(self._on_clear):
            try:
                self._on_clear()
            except Exception:
                pass

    def _handle_carry(self) -> None:
        if callable(self._on_carry):
            try:
                self._on_carry()
            except Exception:
                pass

    def _handle_analyze(self) -> None:
        if callable(self._on_analyze):
            try:
                self._on_analyze()
            except Exception:
                pass

    def _handle_find_similar(self) -> None:
        if callable(getattr(self, "_on_find_similar", None)):
            try:
                self._on_find_similar()  # type: ignore[misc]
            except Exception:
                pass
