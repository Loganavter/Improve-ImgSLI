"""Quick look bars — QWidget bar widgets with painter palette (no QSS)."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from sli_ui_toolkit.managers import scaled_px


def _is_dark_theme() -> bool:
    """True when the dark palette is active (fallbacks stay theme-aware)."""
    try:
        from sli_ui_toolkit.managers import ThemeManager

        inst = ThemeManager.get_instance()
        try:
            return bool(inst.is_dark())
        except Exception:
            pass
        try:
            return str(inst.get_current_theme()).lower() != "light"
        except Exception:
            pass
    except Exception:
        pass
    return True


def _token_qcolor(token: str, fallback_hex: str, fallback_dark_hex: str | None = None) -> QColor:
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if c is not None:
            return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    if fallback_dark_hex is None:
        return QColor(fallback_hex)
    # NOTE: old code used dark-only fallbacks (#3fbf5f, #4a4a4a, ...) — now light/dark chains.
    return QColor(fallback_hex if not _is_dark_theme() else fallback_dark_hex)


def _token_rgba_qcolor(token: str, fallback_rgba: tuple[int, int, int, int]) -> QColor:
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if c is not None:
            return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    return QColor(*fallback_rgba)


def _connect_theme_refresh(slot) -> None:
    """Subscribe *slot* to ThemeManager.theme_changed (best effort)."""
    try:
        from sli_ui_toolkit.managers import ThemeManager

        ThemeManager.get_instance().theme_changed.connect(slot)
    except Exception:
        pass


def _set_painted_width(block, width: int, floor: int) -> None:
    """Set a fill segment width as paint geometry, never as a layout floor.

    The width rides on the block's ``sizeHint`` (see ``_FillBlock``): the
    layout grants a stretch-0 item exactly its hint, so no fixed min/max
    pins are needed. Pinning via ``setFixedWidth`` and then lowering the
    minimum left hint-less blocks collapsing to the minimum on the next
    layout pass (bars rendered full on the first frame, then ~zero, with
    the <1px storm guard suppressing every correction). The constant floor
    minimum stays (no grow→shrink ratchet); ``resizeEvent`` recomputes the
    hint on real size changes.
    """
    try:
        block.setMinimumWidth(int(floor))
    except Exception:
        pass
    try:
        setter = getattr(block, "set_painted_width", None)
        if callable(setter):
            setter(max(int(floor), int(width)))
            return
    except Exception:
        pass
    try:  # legacy fallback for non-_FillBlock callers (none in-tree)
        block.setFixedWidth(max(int(floor), int(width)))
    except Exception:
        return
    try:
        block.setMinimumWidth(int(floor))
    except Exception:
        pass


class _FillBlock(QWidget):
    """Solid color block painted explicitly (explicit paintEvent fill).

    Shared painted primitive for bar segments: color is cached explicitly and
    refreshed by the owner on theme change via :meth:`set_fill_color`.
    """

    def __init__(self, color: QColor | str | None = None, parent=None) -> None:
        super().__init__(parent)
        self._color = QColor(0, 0, 0, 0)
        self._painted_w: int | None = None
        if color is not None:
            self.set_fill_color(color)

    def set_painted_width(self, width: int) -> None:
        """Painted width via sizeHint (layout grants it, minimum stays floor)."""
        try:
            self._painted_w = max(0, int(width))
        except Exception:
            return
        try:
            self.updateGeometry()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def sizeHint(self) -> QSize:  # noqa: N802
        try:
            if self._painted_w is not None:
                return QSize(int(self._painted_w), super().sizeHint().height())
        except Exception:
            pass
        return super().sizeHint()

    def set_fill_color(self, color: QColor | str) -> None:
        try:
            self._color = color if isinstance(color, QColor) else QColor(color)
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            p = QPainter(self)
            p.fillRect(self.rect(), self._color)
            p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass


def dual_marker_frac(hf_ratio: float) -> float:
    """Marker fraction on the restored↔invented axis for an HF ratio.

    ``frac = 0.5 - clamp(hf,-1,1)*0.5`` — positive gain (plausible detail)
    leans the marker onto the restored (left) side, so ``+0.18 → 0.41``
    per ``design/ui-mockup-v4-quicklook.svg``. Pure (unit-testable).
    """
    try:
        hf = max(-1.0, min(1.0, float(hf_ratio)))
    except Exception:
        return 0.5
    return 0.5 - hf * 0.5


class _BarWidget(QWidget):
    """Simple horizontal bar: background + fill fraction (painter-painted)."""

    def __init__(self, fraction: float = 0.0, fill_color=None, parent=None) -> None:
        super().__init__(parent)
        self._fraction = max(0.0, min(1.0, float(fraction)))
        # Last painted width: resizeEvent storms (one per mouse-move, plus
        # layout feedback) must not re-pin the fill for sub-pixel noise —
        # every setFixedWidth invalidates the parent layout and feeds the
        # next resize at the minimum card size (histogram jitter).
        self._last_pw = -1
        # Explicit caller color is kept as-is; None means "default ok token"
        # which is re-resolved on every theme change.
        self._explicit_fill = fill_color
        self.setFixedHeight(scaled_px(6))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._fill = _FillBlock(parent=self)
        self._fill.setObjectName("QuickLookBarFill")
        outer.addWidget(self._fill, 0)
        outer.addStretch(1)
        self._bg_color = _token_qcolor("quick_look.bar.background", "#e8e8e8", "#262626")
        self._refresh_fill()
        _connect_theme_refresh(self._on_theme_changed)
        self._update_fill()

    @staticmethod
    def _default_fill() -> QColor:
        # NOTE: was #3fbf5f (dark-only fallback) — now gallery.status.ok light/dark chain.
        return _token_qcolor("gallery.status.ok", "#2e7d32", "#43a047")

    def _refresh_fill(self) -> None:
        try:
            if self._explicit_fill is not None:
                col = (
                    self._explicit_fill
                    if isinstance(self._explicit_fill, QColor)
                    else QColor(self._explicit_fill)
                )
            else:
                col = self._default_fill()
            self._fill.set_fill_color(col)
        except Exception:
            pass

    def _on_theme_changed(self) -> None:
        try:
            self._bg_color = _token_qcolor("quick_look.bar.background", "#e8e8e8", "#262626")
        except Exception:
            pass
        if self._explicit_fill is None:
            try:
                self._refresh_fill()
            except Exception:
                pass
        try:
            self.update()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            p = QPainter(self)
            p.fillRect(self.rect(), self._bg_color)
            p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass

    def _update_fill(self) -> None:
        try:
            layout = self.layout()
            if layout is not None and layout.count() >= 2:
                pass
        except Exception:
            pass
        try:
            pw = self.width()
            if pw > 0:
                if abs(pw - self._last_pw) < 1:
                    return
                self._last_pw = pw
                fw = int(pw * self._fraction)
                _set_painted_width(self._fill, fw, scaled_px(4))
            else:
                pass
        except Exception:
            pass

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        try:
            pw = self.width()
            if abs(pw - self._last_pw) < 1:
                return
            self._last_pw = pw
            fw = int(pw * self._fraction) if pw > 0 else scaled_px(40)
            _set_painted_width(self._fill, fw, scaled_px(4))
        except Exception:
            pass


class _DualRestoredInventedBar(QWidget):
    """Detail gain dual scale: restored (green) ↔ invented (red) via ThemeManager.

    Fidelity mode HF ratio: center = 0 (0.5 fraction). Left segment = restored,
    right segment = invented. Marker position encodes hf_ratio.
    """

    def __init__(self, hf_ratio: float = 0.18, parent=None) -> None:
        super().__init__(parent)
        self._hf = float(hf_ratio)
        # Same 1px storm guard as _BarWidget (see above).
        self._last_pw = -1
        self.setFixedHeight(scaled_px(6))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._bg_color = _token_qcolor("quick_look.bar.background", "#e8e8e8", "#262626")
        self._left = _FillBlock(parent=self)
        self._left.setObjectName("DualBarLeft")
        self._right = _FillBlock(parent=self)
        self._right.setObjectName("DualBarRight")
        self._refresh_segment_colors()
        outer.addWidget(self._left, 0)
        outer.addWidget(self._right, 0)
        outer.addStretch(1)
        _connect_theme_refresh(self._on_theme_changed)
        self._update_geometry()

    def _refresh_segment_colors(self) -> None:
        try:
            # NOTE: was #3fbf5f (dark-only) — now gallery.status.ok light/dark chain.
            # QColor(...) copy: never setAlpha a manager-owned instance in place.
            left_base = QColor(_token_qcolor("gallery.status.ok", "#2e7d32", "#43a047"))
            try:
                left_base.setAlpha(140)
            except Exception:
                pass
            self._left.set_fill_color(left_base)
        except Exception:
            pass
        try:
            # NOTE: was #D93025 (dark-only) — now gallery.status.danger light/dark chain.
            right_base = QColor(_token_qcolor("gallery.status.danger", "#c0392b", "#d64545"))
            try:
                right_base.setAlpha(115)
            except Exception:
                pass
            self._right.set_fill_color(right_base)
        except Exception:
            pass

    def _on_theme_changed(self) -> None:
        try:
            self._bg_color = _token_qcolor("quick_look.bar.background", "#e8e8e8", "#262626")
        except Exception:
            pass
        try:
            self._refresh_segment_colors()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    def _update_geometry(self) -> None:
        try:
            frac = dual_marker_frac(self._hf)
            pw = self.width()
            if pw <= 0:
                # W13: pre-layout there is no column width yet — wait for
                # the first resizeEvent instead of assuming the old
                # fixed-296 column. The bar fills whatever width the
                # stretched layout gives it once shown (Expanding policy).
                return
            if abs(pw - self._last_pw) < 1:
                return
            self._last_pw = pw
            total = pw
            marker_x = int(total * frac)
            left_w = max(scaled_px(4), marker_x)
            right_w = max(0, total - marker_x)
            _set_painted_width(self._left, left_w, scaled_px(4))
            _set_painted_width(self._right, right_w, 0)
        except Exception:
            pass

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._update_geometry()

    def paintEvent(self, event):  # noqa: N802
        try:
            p = QPainter(self)
            p.fillRect(self.rect(), self._bg_color)
            p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass
        try:
            from PySide6.QtGui import QBrush

            frac = dual_marker_frac(self._hf)
            cx = int(self.width() * frac)
            cy = self.height() // 2
            r = scaled_px(5)
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            dot_col = _token_qcolor("button.primary.text", "#000000", "#ffffff")
            p.setBrush(QBrush(dot_col))
            p.setPen(dot_col)
            p.drawEllipse(cx - r // 2, cy - r // 2, r, r)
            p.end()
        except Exception:
            pass
