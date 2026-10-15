"""Stats strip for Stage 2 triage — Label + Buttons + mode chip.
Audit-Meta: pattern=compound-widget size=exempt reason="one stats strip — stats/mode/action buttons share one paint/theme lifecycle"


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
        self._stats = (0, 0, 0)
        # Ranker provenance shown in the strip ("Ranked by Algorithms / AI (Jev)
        # / Manual"). Resolved token or "" (hidden) — never a fabricated ranker.
        self._rank_source = ""
        # Last affordance applied per action button ("keep"/"compare"). Used to
        # swap the dimmed/bright tokens only on the enabled↔disabled boundary
        # (see ``_apply_action_affordance``) — an empty cache forces the first
        # ``set_action_states`` call to apply.
        self._action_affordance: dict[str, bool] = {}
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

        # Rank provenance chip — which ranker produced the series ranks
        # (Algorithms | AI (Jev) | Manual). Hidden until set.
        self._rank_provenance_label = Label("", pixel_size=11, parent=self)
        self._rank_provenance_label.setObjectName("gallery_rank_provenance")
        try:
            self._rank_provenance_label.setColorToken("accent")
        except Exception:
            pass
        try:
            self._rank_provenance_label.hide()
        except Exception:
            pass
        layout.addWidget(self._rank_provenance_label)

        self._keep_btn = Button(
            text=self._t("image_gallery.action.keep_best", "Keep best"),
            variant="ghost",
            size=(0, 24),
            parent=self,
        )
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
        # Starts disabled: match the dimmed disabled look immediately (an empty
        # cache would otherwise leave it lit until the first gate refresh).
        try:
            self._apply_action_affordance(self._keep_btn, False)
            self._action_affordance["keep"] = False
        except Exception:
            pass
        layout.addWidget(self._keep_btn)

        self._clean_btn = Button(
            regions=[
                ButtonRegion(
                    id="_main",
                    rows=[
                        ButtonRow(
                            text=self._t("image_gallery.stats.clean_rejected", "Clean rejected ({n})").format(n=0),
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
                [
                    ButtonRow(
                        text=self._t("image_gallery.stats.clean_rejected", "Clean rejected ({n})").format(n=0),
                        size=None,
                        ratio=1.0,
                        color=_header_text_color(),
                    )
                ]
            )
            self._clean_btn.setFixedHeight(scaled_px(24))
            self._clean_btn.setEnabled(False)
        except Exception:
            pass
        layout.addWidget(self._clean_btn)

        self._compare_btn = Button(
            text=self._t("image_gallery.stats.compare_finalists", "Compare finalists"),
            variant="ghost",
            size=(0, 24),
            parent=self,
        )
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
        try:
            self._apply_action_affordance(self._compare_btn, False)
            self._action_affordance["compare"] = False
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

    def _t(self, key: str, default: str) -> str:
        """Translate *key* via the injected translator (fail-open to *default*)."""
        tr = getattr(self, "_tr", None)
        if tr is None:
            return default
        try:
            return tr(key, default)
        except Exception:
            return default

    def _on_keep_btn_clicked(self) -> None:
        """Route the keep-button click by mode (Keep best ↔ Show all)."""
        try:
            sig = self.showAllClicked if self._keep_mode == "show" else self.keepBestClicked
            sig.emit()
        except Exception:
            pass

    def set_keep_mode(self, mode: str) -> None:
        """Flip the keep-mode button label (keep ↔ show).

        In "show" mode the button is always actionable (there are rejected
        items to restore), so it is force-enabled here: the gate
        (``set_action_states``) may have disabled it *before* the mode flipped
        (``_refresh_owner_grid`` rebuilds the grid, then sets the mode), leaving
        a disabled "Show all" button that cannot be clicked.
        """
        show = str(mode or "keep").strip().lower().startswith("show")
        self._keep_mode = "show" if show else "keep"
        try:
            if show:
                self._keep_btn.setText(self._t("image_gallery.stats.show_all", "Show all"))
            else:
                self._keep_btn.setText(self._t("image_gallery.action.keep_best", "Keep best"))
        except Exception:
            pass
        if show:
            try:
                self._keep_btn.setEnabled(True)
            except Exception:
                pass

    def _apply_action_affordance(self, btn: Button, enabled: bool) -> None:
        """Swap an action button's text/border tokens to match *enabled*.

        A disabled ``variant="ghost"`` Button with a host-set foreground/border
        renders identically to enabled — the ghost resolver ignores DISABLED
        (``variants.py``) and the text/border overrides have no disabled branch
        (``content.py``/``border.py``). The host therefore owns the dimmed look:
        disabled → dimmed tokens (``gallery.header.text`` / ``flyout.border``),
        enabled → normal ones (``gallery.stats.text`` / ``input.border.thin``).
        Mirrors ``set_rejected_count``.
        """
        if enabled:
            color, border = _stats_text_color(), _thin_border_color()
        else:
            color, border = _header_text_color(), _flyout_border_color()
        try:
            btn.setForegroundColor(color)
        except Exception:
            pass
        try:
            btn.setBorderColor(border)
        except Exception:
            pass

    def set_action_states(self, *, keep_best: bool, compare_finalists: bool) -> None:
        """Enable/disable Keep best + Compare finalists (dead buttons stay off).

        Also swaps the text/border tokens on the enabled↔disabled boundary so a
        disabled ghost button reads as disabled instead of lit-but-dead.
        """
        for key, btn, enabled in (
            ("keep", self._keep_btn, bool(keep_best)),
            ("compare", self._compare_btn, bool(compare_finalists)),
        ):
            try:
                if btn.isEnabled() != enabled:
                    btn.setEnabled(enabled)
            except Exception:
                pass
            try:
                if self._action_affordance.get(key) != enabled:
                    self._apply_action_affordance(btn, enabled)
                    self._action_affordance[key] = enabled
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
            keep_enabled = self._keep_btn.isEnabled()
            self._apply_action_affordance(self._keep_btn, keep_enabled)
            self._action_affordance["keep"] = keep_enabled
        except Exception:
            pass
        try:
            compare_enabled = self._compare_btn.isEnabled()
            self._apply_action_affordance(self._compare_btn, compare_enabled)
            self._action_affordance["compare"] = compare_enabled
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
        self._stats = (t, int(series), int(redundant))
        prefix = (
            self._t("image_gallery.stats.images", "{n} images").format(n=t)
            + " · "
            + self._t("image_gallery.stats.series", "{n} series").format(n=int(series))
            + " · "
        )
        redundant_text = self._t("image_gallery.stats.redundant", "{n} redundant").format(n=int(redundant))
        try:
            self._stats_prefix_label.setText(prefix)
        except Exception:
            pass
        try:
            self._stats_redundant_label.setText(redundant_text)
        except Exception:
            pass

    def set_rank_provenance(self, source: str | None = None, *, domain: str | None = None) -> None:
        """State which ranker produced the series ranks.

        *source* is a ``rank_source`` token (``fusion`` = Algorithms,
        ``jev`` = AI (Jev), ``manual``); when it is missing/unknown, *domain*
        ("algorithms"|"ai") picks the label for the current backend. Neither
        known ⇒ the chip hides (never a fabricated ranker).
        """
        src = ""
        try:
            src = str(source or "").strip().lower()
        except Exception:
            src = ""
        if not src:
            dom = str(domain or "").strip().lower()
            if dom == "ai":
                src = "jev"
            elif dom == "algorithms":
                src = "fusion"
        _valid = ("fusion", "jev", "manual")
        self._rank_source = src if src in _valid else ""
        self._apply_rank_provenance()

    def _apply_rank_provenance(self) -> None:
        """Render/refresh the provenance chip from ``self._rank_source``."""
        src = str(getattr(self, "_rank_source", "") or "")
        label = self._rank_provenance_label if hasattr(self, "_rank_provenance_label") else None
        if label is None:
            return
        if not src:
            try:
                label.setText("")
                label.hide()
            except Exception:
                pass
            return
        try:
            from tabs.image_gallery.services.rank_badge import RANK_SOURCE_LABEL

            key, default = RANK_SOURCE_LABEL.get(src, ("", ""))
        except Exception:
            key, default = ("", "")
        if not default:
            try:
                label.setText("")
                label.hide()
            except Exception:
                pass
            return
        text = self._t("image_gallery.rank.ranked_by", "Ranked by {source}").format(
            source=self._t(key, default)
        )
        try:
            label.setText(text)
            label.show()
        except Exception:
            pass

    def set_rejected_count(self, n: int) -> None:
        self._rejected = int(n)
        txt = self._t("image_gallery.stats.clean_rejected", "Clean rejected ({n})").format(n=int(n))
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

    def retranslate(self, translate=None) -> None:
        """Re-apply every translated label (language switch).

        Re-reads the Keep-best/Show-all button text (via ``set_keep_mode``),
        the rejected count and the stats segments so a live language switch
        never leaves stale English behind.

        Also the toolkit protocol hook (``retranslate(lang)`` via
        ``install_translator``): a non-callable (language string) is ignored and
        the live ``_tr`` re-applies — never overwrite the callable with a str.
        """
        if callable(translate):
            self._tr = translate
        try:
            self._compare_btn.setText(
                self._t("image_gallery.stats.compare_finalists", "Compare finalists")
            )
        except Exception:
            pass
        try:
            self.set_keep_mode(self._keep_mode)
        except Exception:
            pass
        try:
            self.set_rejected_count(self._rejected)
        except Exception:
            pass
        try:
            self.set_stats(*self._stats)
        except Exception:
            pass
        try:
            self._apply_rank_provenance()
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
    def rank_provenance_label(self) -> Label:
        return self._rank_provenance_label

    @property
    def rank_source(self) -> str:
        return str(getattr(self, "_rank_source", "") or "")

    @property
    def clean_button(self) -> Button:
        return self._clean_btn
