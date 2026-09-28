"""Stats strip for Stage 2 triage — Label + Buttons + mode chip.

Painter pipeline only: ``Button`` ``variant="surface"``, ``Label``,
``scaled_px`` for every geometry constant, no ad-hoc stylesheets.

Signals:
    keepBestClicked — Keep best per series.
    cleanClicked    — Clean rejected (live count).
    compareClicked  — Compare finalists.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, Label


# -- theme helpers (sanctioned wrapper only) ----------------------------------

def _is_dark() -> bool:
    """Darkness for fallback selection — delegates to ``dots._is_dark``."""
    try:
        from tabs.image_gallery.ui.card.dots import _is_dark as _dots_is_dark

        return bool(_dots_is_dark())
    except Exception:
        return True


def _fallback_for(light: str, dark: str) -> str:
    """Pick the theme-appropriate fallback hex (no dark-only defaults)."""
    try:
        return dark if _is_dark() else light
    except Exception:
        return dark

def _token_qcolor(token: str, fallback_hex: str) -> QColor:
    """Resolve *token* via ``try_resolve_theme_color`` with *fallback_hex*."""
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        col = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if col is not None:
            if isinstance(col, QColor):
                return col
            return QColor(col)
    except Exception:
        pass
    return QColor(fallback_hex)


def _token_rgba_qcolor(token: str, fallback_rgba: tuple[int, int, int, int]) -> QColor:
    """Resolve *token* via wrapper; fallback to rgba tuple (e.g. input.border.thin)."""
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        col = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if col is not None:
            if isinstance(col, QColor):
                return col
            return QColor(col)
    except Exception:
        pass
    return QColor(*fallback_rgba)


def _accent_color() -> QColor:
    """Accent resolved through the theme token chain (no hand-color).

    Chain (frozen seam): ``accent`` token → ``#0078D4`` (light) / ``#0096FF`` (dark).
    """
    return _token_qcolor("accent", _fallback_for("#0078D4", "#0096FF"))


def _accent_soft_color() -> QColor:
    """Enabled clean button text — accent lighter (≈ #7fc4ff)."""
    base = _token_qcolor("accent", _fallback_for("#0078D4", "#0096FF"))
    try:
        # lighter(150) approximates #7fc4ff from #0096FF
        c = QColor(base)
        return c.lighter(150)
    except Exception:
        pass
    return _token_qcolor("accent", "#7fc4ff")


def _stats_text_color() -> QColor:
    """Stats body text: ``gallery.stats.text`` → light/dark fallback."""
    return _token_qcolor("gallery.stats.text", _fallback_for("#1f1f1f", "#dfdfdf"))


def _header_text_color() -> QColor:
    """Dim header text: ``gallery.header.text`` → light/dark fallback."""
    return _token_qcolor("gallery.header.text", _fallback_for("#434343", "#9a9a9a"))


def _flyout_border_color() -> QColor:
    """Subtle border: ``flyout.border`` → light/dark fallback."""
    return _token_qcolor("flyout.border", _fallback_for("#e0e0e0", "#4a4a4a"))


def _thin_border_color() -> QColor:
    """Hairline border: ``input.border.thin`` → per-theme rgba fallback."""
    if _is_dark():
        return _token_rgba_qcolor("input.border.thin", (255, 255, 255, 60))
    return _token_rgba_qcolor("input.border.thin", (0, 0, 0, 45))


def _stats_bg_color() -> QColor:
    """Stats bar surface: ``gallery.stats.background`` → light/dark fallback.

    NOTE: the historical dark-only ``#333333`` default is kept for the dark
    theme only; the light theme falls back to the registered ``#8a8a8a``.
    """
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        col = try_resolve_theme_color(ThemeManager.get_instance(), "gallery.stats.background")
        if col is not None:
            return col if isinstance(col, QColor) else QColor(col)
    except Exception:
        pass
    if _is_dark():
        return QColor(0x33, 0x33, 0x33)
    return QColor("#8a8a8a")


def _stats_border_color() -> QColor:
    """Stats strip edge: ``gallery.card.border`` → ``flyout.border`` → theme-aware fallback.

    Mockup (v2-light): stats strip is a #ffffff card with a 1px #e2e4e8 edge —
    same hairline as gallery cards. Frozen seam: ``try_resolve_theme_color`` only.
    """
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        mgr = ThemeManager.get_instance()
        for _tok in ("gallery.card.border", "flyout.border"):
            try:
                col = try_resolve_theme_color(mgr, _tok)
            except Exception:
                col = None
            if col is not None:
                return col if isinstance(col, QColor) else QColor(col)
    except Exception:
        pass
    if _is_dark():
        return QColor(255, 255, 255, 30)
    return QColor("#e2e4e8")


def _accent_border_color() -> QColor:
    """Enabled clean button border — accent with 60% opacity (alpha 153)."""
    base = _token_qcolor("accent", _fallback_for("#0078D4", "#0096FF"))
    try:
        c = QColor(base)
        c.setAlpha(153)
        return c
    except Exception:
        pass
    # fallback — ensure alpha applied
    try:
        fallback = _token_qcolor("accent", _fallback_for("#0078D4", "#0096FF"))
        c2 = QColor(fallback)
        c2.setAlpha(153)
        return c2
    except Exception:
        pass
    return _token_qcolor("accent", _fallback_for("#0078D4", "#0096FF"))


class StatsStrip(QWidget):
    """Top strip: stats label + actions + mode chip."""

    keepBestClicked = Signal()
    showAllClicked = Signal()  # Keep best ↔ Show all (mode via set_keep_mode)
    cleanClicked = Signal()
    compareClicked = Signal()

    def __init__(self, parent: QWidget | None = None, *, translate=None) -> None:
        super().__init__(parent)
        self.setObjectName("GalleryStatsStrip")
        self._tr = translate
        self._rejected = 0
        self._keep_mode = "keep"
        # Cached surface color; repainted explicitly in paintEvent (never via
        # palette/auto-fill — see THEMING.md warm-up quirk).
        self._stats_bg = _stats_bg_color()
        self._stats_border = _stats_border_color()
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_gallery_theme_changed)
        except Exception:
            pass

        layout = QHBoxLayout(self)
        layout.setContentsMargins(scaled_px(16), scaled_px(5), scaled_px(16), scaled_px(5))
        layout.setSpacing(scaled_px(10))
        # real_design.md:2.2 bar bg r8 — rounded via paintEvent, painter pipeline only
        try:
            self.setFixedHeight(scaled_px(34))
        except Exception:
            pass

        # S2-6: stats as a small row of Labels so the "N redundant" segment
        # can carry the accent token (svg: "33 redundant" in #0096FF) while
        # the rest stays default. Toolkit Label has no rich-text/segment API,
        # so the segments are sibling Labels — still no QSS.
        self._stats_container = QWidget(self)
        stats_layout = QHBoxLayout(self._stats_container)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(0)

        # gallery.stats.text via color_token so the toolkit re-resolves on flip.
        self._stats_prefix_label = Label("", pixel_size=13, color_token="gallery.stats.text", parent=self._stats_container)
        self._stats_prefix_label.setObjectName("gallery_stats_prefix")
        stats_layout.addWidget(self._stats_prefix_label)

        self._stats_redundant_label = Label("", pixel_size=13, color_token="accent", parent=self._stats_container)
        self._stats_redundant_label.setObjectName("gallery_stats_redundant")
        stats_layout.addWidget(self._stats_redundant_label)

        self._stats_label = self._stats_container
        self._stats_label.setObjectName("gallery_stats_label")
        layout.addWidget(self._stats_label)

        layout.addStretch(1)

        self._keep_btn = Button(text="Keep best", variant="ghost", size=(0, 24), parent=self)
        self._keep_btn.setObjectName("gallery_keep_best")
        try:
            _c = _stats_text_color()
            _b = _thin_border_color()
            self._keep_btn.setForegroundColor(_c)
            self._keep_btn.setBorderColor(_b)
        except Exception:
            try:
                self._keep_btn.setForegroundColor(_stats_text_color())
                self._keep_btn.setBorderColor(_thin_border_color())
            except Exception:
                pass
        self._keep_btn.clicked.connect(self._on_keep_btn_clicked)
        try:
            self._keep_btn.setEnabled(False)
        except Exception:
            pass
        layout.addWidget(self._keep_btn)

        self._clean_btn = Button(
            regions=[
                ButtonRegion(
                    id="_main",
                    rows=[
                        ButtonRow(
                            text="Clean rejected (0)",
                            size=None,
                            ratio=1.0,
                            color=_header_text_color(),
                        )
                    ],
                    override_border_color=_flyout_border_color(),
                )
            ],
            variant="ghost",
            size=(0, 24),
            parent=self,
        )
        self._clean_btn.setObjectName("gallery_clean_rejected")
        self._clean_btn.setEnabled(False)
        self._clean_btn.clicked.connect(self.cleanClicked.emit)
        # Sync Button._rows for correct sizeHint (regions rows alone leave hint 36) then restore fixedHeight 24
        try:
            self._clean_btn.setRows(
                [ButtonRow(text="Clean rejected (0)", size=None, ratio=1.0, color=_header_text_color())]
            )
            self._clean_btn.setFixedHeight(scaled_px(24))
            self._clean_btn.setEnabled(False)
        except Exception:
            pass
        layout.addWidget(self._clean_btn)

        self._compare_btn = Button(text="Compare finalists", variant="ghost", size=(0, 24), parent=self)
        self._compare_btn.setObjectName("gallery_compare_finalists")
        try:
            _c2 = _stats_text_color()
            _b2 = _thin_border_color()
            self._compare_btn.setForegroundColor(_c2)
            self._compare_btn.setBorderColor(_b2)
        except Exception:
            try:
                self._compare_btn.setForegroundColor(_stats_text_color())
                self._compare_btn.setBorderColor(_thin_border_color())
            except Exception:
                pass
        self._compare_btn.clicked.connect(self.compareClicked.emit)
        try:
            self._compare_btn.setEnabled(False)
        except Exception:
            pass
        layout.addWidget(self._compare_btn)

        self._mode_chip = Label("FIDELITY MODE · source: …", pixel_size=11, parent=self)
        self._mode_chip.setObjectName("gallery_mode_chip")
        try:
            self._mode_chip.setColorToken("accent")
        except Exception:
            pass
        # real_design.md:54 — no debug MODE in stats bar, hidden
        try:
            self._mode_chip.hide()
        except Exception:
            pass
        # keep in layout but hidden (or not added) to satisfy tests that query mode_chip
        layout.addWidget(self._mode_chip)
        try:
            self._mode_chip.setVisible(False)
        except Exception:
            pass

    def _on_keep_btn_clicked(self) -> None:
        """Route the keep-button click by mode (Keep best ↔ Show all)."""
        try:
            sig = self.showAllClicked if self._keep_mode == "show" else self.keepBestClicked
            sig.emit()
        except Exception:
            pass

    def set_keep_mode(self, mode: str) -> None:
        """Flip the keep button between "Keep best" and "Show all"."""
        show = str(mode or "keep").strip().lower().startswith("show")
        self._keep_mode = "show" if show else "keep"
        try:
            self._keep_btn.setText("Show all" if show else "Keep best")
        except Exception:
            pass

    def set_action_states(self, *, keep_best: bool, compare_finalists: bool) -> None:
        """Enable/disable Keep best + Compare finalists (dead buttons stay off)."""
        try:
            self._keep_btn.setEnabled(bool(keep_best))
        except Exception:
            pass
        try:
            self._compare_btn.setEnabled(bool(compare_finalists))
        except Exception:
            pass

    def _on_gallery_theme_changed(self) -> None:
        """Refresh cached surface + token-driven foregrounds on theme flip."""
        try:
            self._stats_bg = _stats_bg_color()
        except Exception:
            pass
        try:
            self._stats_border = _stats_border_color()
        except Exception:
            pass
        try:
            self._keep_btn.setForegroundColor(_stats_text_color())
            self._keep_btn.setBorderColor(_thin_border_color())
        except Exception:
            pass
        try:
            self._compare_btn.setForegroundColor(_stats_text_color())
            self._compare_btn.setBorderColor(_thin_border_color())
        except Exception:
            pass
        try:
            self.set_rejected_count(self._rejected)
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtGui import QPainter
            from PySide6.QtCore import QRectF

            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(QColor(0, 0, 0, 0))
            try:
                bg = self._stats_bg
            except Exception:
                bg = _stats_bg_color()
            p.setBrush(bg)
            r = QRectF(self.rect())
            p.drawRoundedRect(r, 8, 8)
            try:
                border = self._stats_border
            except Exception:
                border = _stats_border_color()
            try:
                p.setBrush(QColor(0, 0, 0, 0))
                pen = border
                try:
                    from PySide6.QtGui import QPen

                    pen = QPen(border, 1)
                except Exception:
                    pass
                p.setPen(pen)
                p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
            except Exception:
                pass
            p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass

    # -- public API -------------------------------------------------------

    def set_stats(self, total: int, series: int, redundant: int) -> None:
        # S2-6: split segments — default prefix + accent "N redundant".
        t = int(total)
        img_word = "image" if t == 1 else "images"
        prefix = f"{t} {img_word} · {int(series)} series · "
        redundant_text = f"{int(redundant)} redundant"
        try:
            self._stats_prefix_label.setText(prefix)
        except Exception:
            pass
        try:
            self._stats_redundant_label.setText(redundant_text)
        except Exception:
            pass

    def set_rejected_count(self, n: int) -> None:
        self._rejected = int(n)
        txt = f"Clean rejected ({int(n)})"
        enabled = int(n) > 0
        if enabled:
            col = _accent_soft_color()
            border = _accent_border_color()
        else:
            col = _header_text_color()
            border = _flyout_border_color()
        try:
            # Update region border + row color via region API (painter pipeline)
            try:
                region = self._clean_btn.region("_main")
                if region is not None:
                    region.override_border_color = border
            except Exception:
                pass
            self._clean_btn.setRows(
                [ButtonRow(text=txt, size=None, ratio=1.0, color=col)]
            )
            # setRows triggers _apply_text_geometry -> clears fixedHeight 24 -> min 32; restore
            try:
                self._clean_btn.setFixedHeight(scaled_px(24))
            except Exception:
                pass
        except Exception:
            try:
                self._clean_btn.setText(txt)
            except Exception:
                pass
        try:
            self._clean_btn.setEnabled(enabled)
        except Exception:
            pass

    def set_mode(self, mode: str, source: str | Path | None = None) -> None:
        mode_up = str(mode or "fidelity").strip().upper()
        if not mode_up:
            mode_up = "FIDELITY"
        if not mode_up.endswith(" MODE"):
            mode_up = f"{mode_up} MODE"
        src = ""
        if source is not None:
            try:
                src = Path(source).name if isinstance(source, (str, Path)) else str(source)
            except Exception:
                src = str(source)
        chip = f"{mode_up} · source: {src}" if src else f"{mode_up} · source: …"
        try:
            self._mode_chip.setText(chip)
        except Exception:
            pass

    @property
    def stats_label(self) -> QWidget:
        # S2-6: container of the per-segment stat Labels (kept as a property
        # for callers/tests that looked up the old single Label).
        return self._stats_label

    @property
    def stats_prefix_label(self) -> Label:
        return self._stats_prefix_label

    @property
    def stats_redundant_label(self) -> Label:
        return self._stats_redundant_label

    @property
    def clean_button(self) -> Button:
        return self._clean_btn
