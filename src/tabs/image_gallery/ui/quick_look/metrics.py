"""Quick look metrics — plain functions taking overlay as first arg."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px


def _is_dark_theme() -> bool:
    try:
        from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _bars_is_dark

        return bool(_bars_is_dark())
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
    return QColor(fallback_hex if not _is_dark_theme() else fallback_dark_hex)


def rebuild_metrics(overlay, item, is_fidelity: bool, mode_str: str) -> None:
    try:
        from tabs.image_gallery.ui.quick_look.helpers import _make_label
    except Exception:
        from sli_ui_toolkit.widgets import Label as _Label

        def _make_label(text="", parent=None, pixel_size=10, pt=None, **kwargs):  # type: ignore
            return _Label(text, pixel_size=pixel_size, parent=parent, **kwargs)

    for w in list(overlay._metric_rows):
        try:
            overlay._metrics_layout.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        except Exception:
            pass
    overlay._metric_rows.clear()
    metrics = getattr(item, "metrics", None) or {}
    if not isinstance(metrics, dict):
        metrics = {}

    def _add_metric_row(title: str, value_text: str, fraction: float, color=None, value_color=None, value_elide: bool = True) -> None:
        row = QWidget(overlay._metrics_host)
        rl = QVBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(scaled_px(2))  # W5: fit budget (helpers outer note)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(scaled_px(6))
        t = _make_label(title, parent=row, pixel_size=11, pt=11.5)
        header.addWidget(t)
        # W7: no spacer here — the value below is horizontal-Ignored (it
        # contributes no sizeHint so the 296px column never h-scrolls) and
        # an Ignored label beside a spacer would collapse to its 40px
        # minimum and elide EVERYTHING ("+0…"). The value takes the free
        # row width via stretch and end-aligns per the mockup (svg:84
        # text-anchor=end); it elides only when the title genuinely
        # leaves no room.
        vc = _ok_color() if value_color is None else value_color
        if value_elide:
            v = _make_label(value_text, parent=row, pixel_size=11, pt=11.5, color=vc, elide=True, minimum_width=40)
        else:
            v = _make_label(value_text, parent=row, pixel_size=11, pt=11.5, color=vc)
        try:
            v.setAlignment(Qt.AlignmentFlag.AlignRight)
        except Exception:
            pass
        header.addWidget(v, 1)
        rl.addLayout(header)
        # Lazy import bar widget
        from tabs.image_gallery.ui.quick_look.bars import _BarWidget

        bar = _BarWidget(fraction=fraction, fill_color=color, parent=row)
        rl.addWidget(bar)
        overlay._metrics_layout.addWidget(row)
        overlay._metric_rows.append(row)

    def _ok_color():
        # NOTE: was #3fbf5f (dark-only) — now gallery.status.ok light/dark chain.
        return _token_qcolor("gallery.status.ok", "#2e7d32", "#43a047")

    def _warn_color():
        # NOTE: was #e8b64c (dark-only) — now gallery.status.warn light/dark chain.
        return _token_qcolor("gallery.status.warn", "#b77900", "#d9a441")

    def _muted_color():
        return _token_qcolor("gallery.status.neutral", "#8a8a8a")

    def _add_unmeasured_row(title: str) -> None:
        """Unmeasured state: an explicit 'not measured' row, never a plausible
        constant. Fabricated values (0.94 SSIM, 120 sharpness, …) made missing
        data look measured; gaps must read as gaps. The value is a fixed
        short constant that always fits the column, so it skips elision
        (W5: keeps .text() verbatim for readers that match on it)."""
        _add_metric_row(title, "— · not measured", 0.0, _muted_color(), value_color=_muted_color(), value_elide=False)

    if is_fidelity:
        ssim = metrics.get("ssim")
        rank = getattr(item, "rank", None) or getattr(item, "crown_rank", None)
        rank_txt = f"#{rank} of {len(overlay._series_items)}" if rank is not None else f"#{overlay._current_idx+1} of {len(overlay._series_items)}"
        if ssim is None:
            _add_unmeasured_row("SSIM vs source")
        else:
            try:
                ssim_f = float(ssim)
            except Exception:
                ssim_f = None
            if ssim_f is None:
                _add_unmeasured_row("SSIM vs source")
            else:
                ssim_f = max(0.0, min(1.0, ssim_f))
                _add_metric_row("SSIM vs source", f"{ssim_f:.2f} · {rank_txt}", ssim_f, _ok_color())
        subline = ssim_subline(overlay, item)
        if subline:
            sub_row = QWidget(overlay._metrics_host)
            sub_lay = QVBoxLayout(sub_row)
            sub_lay.setContentsMargins(0, 0, 0, 0)
            sub_lay.setSpacing(0)
            sub_lay.addWidget(_make_label(subline, parent=sub_row, pixel_size=9, pt=9.5, color_token="list_item.text.rating", elide=True, minimum_width=40))
            overlay._metrics_layout.addWidget(sub_row)
            overlay._metric_rows.append(sub_row)
        hf = metrics.get("hf_ratio") if "hf_ratio" in metrics else metrics.get("detail_gain")
        hf_f = None
        if hf is not None:
            try:
                hf_f = float(hf)
            except Exception:
                hf_f = None
        if hf_f is None:
            _add_unmeasured_row("Detail gain (HF ratio)")
        else:
            pct = f"{int(hf_f*100):+d}% " + ("plausible" if hf_f >= 0 else "loss")
            row = QWidget(overlay._metrics_host)
            rl = QVBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(scaled_px(2))  # W5: fit budget (helpers outer note)
            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(scaled_px(6))
            t = _make_label("Detail gain (HF ratio)", parent=row, pixel_size=11, pt=11.5)
            header.addWidget(t)
            # W7: value takes free row width via stretch (see _add_metric_row).
            v = _make_label(pct, parent=row, pixel_size=11, pt=11.5, color=_ok_color(), elide=True, minimum_width=40)
            try:
                v.setAlignment(Qt.AlignmentFlag.AlignRight)
            except Exception:
                pass
            header.addWidget(v, 1)
            rl.addLayout(header)
            from tabs.image_gallery.ui.quick_look.bars import _DualRestoredInventedBar

            dual = _DualRestoredInventedBar(hf_ratio=hf_f, parent=row)
            rl.addWidget(dual)
            sub = QHBoxLayout()
            sub.setContentsMargins(0, 0, 0, 0)
            sub.setSpacing(scaled_px(6))
            lab_l = _make_label("restored texture", parent=row, pixel_size=9, pt=9.5)
            sub.addWidget(lab_l)
            sub.addStretch(1)
            lab_r = _make_label("invented / hallucinated", parent=row, pixel_size=9, pt=9.5)
            sub.addWidget(lab_r)
            rl.addLayout(sub)
            overlay._metrics_layout.addWidget(row)
            overlay._metric_rows.append(row)
        de = metrics.get("delta_e") if "delta_e" in metrics else metrics.get("deltaE") or metrics.get("color_shift")
        de_f = None
        if de is not None:
            try:
                de_f = float(de)
            except Exception:
                de_f = None
        if de_f is None:
            _add_unmeasured_row("Color shift ΔE")
        else:
            de_frac = max(0.0, min(1.0, de_f / 10.0))
            de_label = f"{de_f:.1f} · " + ("imperceptible" if de_f < 2.3 else "visible" if de_f < 5 else "strong")
            _add_metric_row("Color shift ΔE", de_label, de_frac, _ok_color() if de_f < 3 else _warn_color())
    elif "CAMERA" in mode_str:
        sharp = metrics.get("sharpness")
        sharp_f = None
        if sharp is not None:
            try:
                sharp_f = float(sharp)
            except Exception:
                sharp_f = None
        if sharp_f is None:
            _add_unmeasured_row("Sharpness (Laplacian var)")
        else:
            frac = max(0.0, min(1.0, sharp_f / 400.0))
            _add_metric_row("Sharpness (Laplacian var)", f"{sharp_f:.0f}", frac, _ok_color() if sharp_f > 100 else _warn_color())
        exposure = metrics.get("exposure")
        exp_f = None
        if exposure is not None:
            try:
                exp_f = float(exposure)
            except Exception:
                exp_f = None
        if exp_f is None:
            _add_unmeasured_row("Exposure")
        else:
            frac2 = max(0.0, min(1.0, exp_f if exp_f <= 1 else exp_f / 100))
            exp_label = f"{exp_f:.2f}" if exp_f <= 1 else f"{exp_f:.0f}%"
            _add_metric_row("Exposure", exp_label, frac2, _ok_color())
        clipping = metrics.get("clipping") or metrics.get("clipping_pct")
        clip_f = None
        if clipping is not None:
            try:
                clip_f = float(clipping)
            except Exception:
                clip_f = None
        if clip_f is None:
            _add_unmeasured_row("Clipping %")
        else:
            frac3 = max(0.0, min(1.0, clip_f / 10 if clip_f > 1 else clip_f))
            _add_metric_row("Clipping %", f"{clip_f:.1f}%", frac3, _warn_color() if clip_f > 2 else _ok_color())
        noise = None
        for nk in ("noise", "noise_estimate", "noise_level"):
            if metrics.get(nk) is not None:
                noise = metrics.get(nk)
                break
        if noise is not None:
            try:
                n_f = float(noise)
                if n_f <= 1.0:
                    n_frac = max(0.0, min(1.0, n_f))
                    n_text = f"{n_f:.2f}"
                elif n_f <= 10.0:
                    n_frac = max(0.0, min(1.0, n_f / 10.0))
                    n_text = f"{n_f:.1f}"
                else:
                    n_frac = max(0.0, min(1.0, n_f / 100.0))
                    n_text = f"{n_f:.0f}%"
                _add_metric_row("Noise", n_text, n_frac, _warn_color() if n_frac > 0.5 else _ok_color())
            except Exception:
                pass
        wb = None
        for wk in ("wb_shift", "white_balance"):
            if metrics.get(wk) is not None:
                wb = metrics.get(wk)
                break
        if wb is not None:
            try:
                wb_f = float(wb)
                if wb_f > 0.05:
                    wb_text = f"{wb_f:+.2f} · warm"
                elif wb_f < -0.05:
                    wb_text = f"{wb_f:+.2f} · cool"
                else:
                    wb_text = f"{wb_f:+.2f} · neutral"
                wb_frac = max(0.0, min(1.0, abs(wb_f)))
                _add_metric_row("WB shift", wb_text, wb_frac, _warn_color() if wb_frac > 0.15 else _ok_color())
            except Exception:
                try:
                    wb_text = str(wb)
                    _add_metric_row("WB shift", wb_text, 0.5, _ok_color())
                except Exception:
                    pass
    else:
        dist = metrics.get("embedding_dist_to_centroid")
        d_f = None
        if dist is not None:
            try:
                d_f = float(dist)
            except Exception:
                d_f = None
        if d_f is None:
            _add_unmeasured_row("Distance to centroid")
        else:
            frac = max(0.0, min(1.0, 1.0 - min(1.0, d_f)))
            _add_metric_row("Distance to centroid", f"{d_f:.2f}", frac, _ok_color())
        aesthetic = metrics.get("aesthetic") or metrics.get("aesthetic_score")
        aes_f = None
        if aesthetic is not None:
            try:
                aes_f = float(aesthetic)
            except Exception:
                aes_f = None
        if aes_f is None:
            _add_unmeasured_row("Aesthetic (tie-break)")
        else:
            frac2 = max(0.0, min(1.0, aes_f if aes_f <= 1 else aes_f / 10))
            _add_metric_row("Aesthetic (tie-break)", f"{aes_f:.2f}", frac2, _ok_color())


def ssim_subline(overlay, item) -> str:
    """Build the fidelity SSIM subline from series items (S4-5)."""
    try:
        def _ssim_of(m):
            mt = getattr(m, "metrics", None) or {}
            try:
                return float(mt.get("ssim"))
            except Exception:
                return None

        def _rank_of(m, default):
            r = getattr(m, "rank", None) or getattr(m, "crown_rank", None)
            try:
                return int(r) if r is not None else default
            except Exception:
                return default

        parts: list[str] = []
        viewing_rank = _rank_of(item, overlay._current_idx + 1)
        others = [m for m in overlay._series_items if m is not item]
        next_item = None
        best = None
        for m in others:
            r = getattr(m, "rank", None) or getattr(m, "crown_rank", None)
            try:
                r = int(r) if r is not None else None
            except Exception:
                r = None
            if r is not None and r > viewing_rank:
                if next_item is None or r < next_item[0]:
                    next_item = (r, m)
            if r is not None and (best is None or r < best[0]):
                best = (r, m)
        pick = next_item if next_item is not None else best
        if pick is not None:
            s = _ssim_of(pick[1])
            if s is not None:
                parts.append(f"#{pick[0]} scores {s:.2f}")
        rejected = [m for m in others if bool(getattr(m, "rejected", False))]
        tail = [v for v in (_ssim_of(m) for m in rejected) if v is not None]
        if tail:
            parts.append(f"rejected tail ≤ {min(tail):.2f}")
        return " · ".join(parts)
    except Exception:
        return ""
