"""Stats strip for Stage 2 triage — Text + Buttons + mode chip.
Audit-Meta: pattern=compound-widget size=exempt reason="one stats strip — stats/mode/action buttons share one paint/theme lifecycle"


Painter pipeline only: ``Button`` ``variant="surface"``, ``Text``,
``scaled_px`` for every geometry constant, no ad-hoc stylesheets.

Signals:
    keepBestClicked — Keep best per series.
    cleanClicked    — Clean rejected (live count).
    compareClicked  — Compare finalists.

The old active-metric-profile chip (and the domain flyout it opened) was
deleted with the manual domain pin (owner decision 2026-10-20, plan
``plan-gallery-analysis-engine-2026-10-20`` §Product decision): the measured
axes are already visible as rows/dots, and per-axis provenance replaces the
chip's one-line claim.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, Text

# Package split (plan-gallery-split-2026-10-17, Part C6): the colour/token
# helpers live in theme.py; re-export them so
# ``tabs.image_gallery.ui.stats_strip`` keeps its full surface for importers.
from .theme import (  # noqa: F401
    _accent_border_color,
    _accent_color,
    _accent_soft_color,
    _fallback_for,
    _flyout_border_color,
    _header_text_color,
    _is_dark,
    _stats_bg_color,
    _stats_border_color,
    _stats_text_color,
    _thin_border_color,
    _token_qcolor,
    _token_rgba_qcolor,
)


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

        # S2-6: stats as a small row of Text widgets so the "N redundant" segment
        # can carry the accent token (svg: "33 redundant" in #0096FF) while
        # the rest stays default. Plain Text has no rich-text/segment API,
        # so the segments are sibling Text widgets — still no QSS.
        self._stats_container = QWidget(self)
        stats_layout = QHBoxLayout(self._stats_container)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(0)

        # gallery.stats.text via color_token so the toolkit re-resolves on flip.
        self._stats_prefix_label = Text("", mode="plain", pixel_size=14, color_token="gallery.stats.text", parent=self._stats_container)
        self._stats_prefix_label.setObjectName("gallery_stats_prefix")
        stats_layout.addWidget(self._stats_prefix_label)

        self._stats_redundant_label = Text("", mode="plain", pixel_size=14, color_token="accent", parent=self._stats_container)
        self._stats_redundant_label.setObjectName("gallery_stats_redundant")
        stats_layout.addWidget(self._stats_redundant_label)

        self._stats_label = self._stats_container
        self._stats_label.setObjectName("gallery_stats_label")
        layout.addWidget(self._stats_label)

        layout.addStretch(1)

        # Rank provenance chip — which ranker produced the series ranks
        # (Algorithms | AI (Jev) | Manual). Hidden until set.
        self._rank_provenance_label = Text("", mode="plain", pixel_size=14, parent=self)
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

        self._mode_chip = Text("FIDELITY MODE · source: …", mode="plain", pixel_size=11, parent=self)
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

        # Live UI-scale re-derive for the strip's cached design geometry.
        self._subscribe_ui_metrics()

    def _subscribe_ui_metrics(self) -> None:
        """Subscribe to the unified metrics bus for the SCALE axis only.

        The strip's fixed height and the row margins/spacing are design px
        resolved once in ``__init__``; on a live factor change they stayed at
        the 1.0 px and clipped the (font-scaled) stats labels. Buttons re-derive
        their own ``size=`` and labels re-resolve their font, so only the
        scale-derived chrome needs the explicit re-run.
        """
        try:
            from sli_ui_toolkit.ui.managers import connect_ui_metrics
            from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_SCALE
        except Exception:
            return
        try:
            connect_ui_metrics(self, self._on_ui_metrics, axes=frozenset({AXIS_SCALE}))
        except Exception:
            pass

    def _on_ui_metrics(self, *_axes) -> None:
        """Re-apply every build-time-cached design-px value at the new factor."""
        try:
            self.setFixedHeight(scaled_px(34))
        except Exception:
            pass
        try:
            layout = self.layout()
            if layout is not None:
                layout.setContentsMargins(
                    scaled_px(16), scaled_px(5), scaled_px(16), scaled_px(5)
                )
                layout.setSpacing(scaled_px(10))
        except Exception:
            pass
        try:
            self._clean_btn.setFixedHeight(scaled_px(24))
        except Exception:
            pass
        try:
            self.updateGeometry()
        except Exception:
            pass
        try:
            self.update()
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
            p.drawRoundedRect(r, scaled_px(8), scaled_px(8))
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
                p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), scaled_px(8), scaled_px(8))
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
        # S2-6: container of the per-segment stat Text widgets (kept as a
        # property for callers/tests that looked up the old single Label).
        return self._stats_label

    @property
    def stats_prefix_label(self) -> Text:
        return self._stats_prefix_label

    @property
    def stats_redundant_label(self) -> Text:
        return self._stats_redundant_label

    @property
    def rank_provenance_label(self) -> Text:
        return self._rank_provenance_label

    @property
    def rank_source(self) -> str:
        return str(getattr(self, "_rank_source", "") or "")

    @property
    def clean_button(self) -> Button:
        return self._clean_btn
