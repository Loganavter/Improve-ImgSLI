"""Quick look helpers — plain functions (no owner state).
Audit-Meta: pattern=thin-owner-target size=exempt reason="ui/quick_look helpers — overlay build + populate helpers sharing one overlay"

Extracted from quick_look.py per CODE_PATTERNS.md thin owner + ui/.
Painter pipeline owns visuals; no setStyleSheet. Lazy imports for theming.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap


def _load_preview_pixmap(path: Path, target_w: int = 640, target_h: int = 456) -> QPixmap | None:
    try:
        pm = QPixmap(str(path))
        if pm.isNull():
            return None
        w = pm.width()
        h = pm.height()
        if w <= 0 or h <= 0:
            return pm
        return pm.scaled(target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    except Exception:
        return None


def _thumb_pixmap(item, size: int = 66) -> QPixmap | None:
    try:
        thumb = getattr(item, "thumbnail", None)
        if thumb is not None and not thumb.isNull():
            return thumb.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        pm = QPixmap(str(getattr(item, "path", "")))
        if pm is not None and not pm.isNull():
            return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    except Exception:
        pass
    return None


def _theme_color(token: str, fallback: str) -> object:
    """Resolve ThemeManager token with fallback hex via ui.theming wrapper (contract-safe)."""
    try:
        from ui.theming import resolve_theme_color

        from sli_ui_toolkit.managers import ThemeManager

        return resolve_theme_color(ThemeManager.get_instance(), token)
    except Exception:
        try:
            from PySide6.QtGui import QColor

            return QColor(fallback)
        except Exception:
            return None


def _token_color(token: str, fallback: str) -> QColor | None:
    """Resolve a ThemeManager token, falling back to *fallback* hex when absent.

    Goes through the sanctioned ``ui.theming.try_resolve_theme_color`` wrapper
    (contract: manual theming glue lives only in theme infra).
    """
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if c is not None:
            return QColor(c) if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    try:
        return QColor(fallback)
    except Exception:
        return None


def _token_rgba_qcolor(token: str, fallback_rgba: tuple[int, int, int, int]) -> QColor | None:
    """Resolve token via ``try_resolve_theme_color`` with rgba fallback."""
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if c is not None:
            return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    try:
        return QColor(*fallback_rgba)
    except Exception:
        return None


def _set_colored_text(btn, text: str, color: QColor | None) -> None:
    """Painter-pipeline text color via ButtonRow color (no QSS, no palette)."""
    try:
        from sli_ui_toolkit.widgets import ButtonRow

        btn.setRows([ButtonRow(text=text, size=None, ratio=1.0, color=color)])
    except Exception:
        try:
            btn.setText(text)
        except Exception:
            pass


def _source_dimensions(src_item, src_path) -> tuple[int, int] | None:
    """Source image dimensions: metrics width/height first, QPixmap fallback."""
    metrics = getattr(src_item, "metrics", None) if src_item is not None else None
    if isinstance(metrics, dict):
        try:
            w = metrics.get("width")
            h = metrics.get("height")
            if w and h:
                return int(w), int(h)
        except Exception:
            pass
    try:
        if src_path is not None:
            pm = QPixmap(str(src_path))
            if not pm.isNull():
                return pm.width(), pm.height()
    except Exception:
        pass
    return None


# -- UI construction helpers (thin owner delegation) -------------------------

def build_overlay_ui(overlay) -> None:
    """Construct QuickLookOverlay layout (thin owner delegator).

    Reads/writes overlay attributes directly per CODE_PATTERNS plain function.
    No QSS, painter pipeline only, lazy imports for theming.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

    from sli_ui_toolkit.managers import scaled_px
    from sli_ui_toolkit.widgets import Button, Label

    try:
        from tabs.image_gallery.ui.quick_look.source_inset import _SourceInsetHost
    except Exception:
        _SourceInsetHost = QWidget  # type: ignore

    overlay._content = QWidget(overlay)
    overlay._content.setObjectName("QuickLookContent")
    overlay._content.setMinimumSize(scaled_px(900), scaled_px(520))
    try:
        overlay._content.setMaximumSize(scaled_px(1040), scaled_px(620))
    except Exception:
        pass
    outer = QVBoxLayout(overlay._content)
    outer.setContentsMargins(scaled_px(16), scaled_px(12), scaled_px(16), scaled_px(12))
    outer.setSpacing(scaled_px(8))
    chip_row = QHBoxLayout()
    chip_row.setContentsMargins(0, 0, 0, 0)
    chip_row.setSpacing(scaled_px(8))
    overlay._mode_chip = Label("FIDELITY MODE", pixel_size=10, color_token="accent", parent=overlay._content)
    overlay._mode_chip.setObjectName("quicklook_mode_chip")
    try:
        overlay._mode_chip.setBold(True)
    except Exception:
        pass
    chip_row.addWidget(overlay._mode_chip)
    chip_row.addStretch(1)
    overlay._close_btn = Button(text="✕", variant="surface", size=(28, 28), parent=overlay._content)
    overlay._close_btn.setObjectName("quicklook_close")
    overlay._close_btn.clicked.connect(overlay.hide)
    chip_row.addWidget(overlay._close_btn)
    outer.addLayout(chip_row)
    mid = QHBoxLayout()
    mid.setContentsMargins(0, 0, 0, 0)
    mid.setSpacing(scaled_px(16))
    left = QWidget(overlay._content)
    left.setObjectName("QuickLookLeft")
    left_lay = QVBoxLayout(left)
    left_lay.setContentsMargins(0, 0, 0, 0)
    left_lay.setSpacing(scaled_px(8))
    preview_row = QHBoxLayout()
    preview_row.setContentsMargins(0, 0, 0, 0)
    preview_row.setSpacing(scaled_px(6))
    preview_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
    overlay._prev_btn = Button(text="‹", variant="surface", size=(36, 36), parent=left)
    overlay._prev_btn.setObjectName("quicklook_prev")
    overlay._prev_btn.clicked.connect(lambda: overlay._walk(-1))
    preview_row.addWidget(overlay._prev_btn)
    preview_host = QWidget(left)
    preview_host.setObjectName("QuickLookPreviewHost")
    overlay._preview_host = preview_host
    preview_host_lay = QVBoxLayout(preview_host)
    preview_host_lay.setContentsMargins(0, 0, 0, 0)
    preview_host_lay.setSpacing(scaled_px(6))
    overlay._preview_label = QLabel(preview_host)
    overlay._preview_label.setObjectName("quicklook_preview")
    overlay._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    overlay._preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    overlay._preview_label.setMinimumSize(scaled_px(320), scaled_px(260))
    try:
        overlay._preview_label.setScaledContents(False)
    except Exception:
        pass
    preview_host_lay.addWidget(overlay._preview_label, 1)
    overlay._source_inset_host = _SourceInsetHost(overlay._preview_label)
    overlay._source_inset_host.setObjectName("quicklook_source_inset_host")
    src_lay = QVBoxLayout(overlay._source_inset_host)
    src_lay.setContentsMargins(scaled_px(2), scaled_px(2), scaled_px(2), scaled_px(2))
    src_lay.setSpacing(scaled_px(2))
    overlay._source_inset_label = Label("SOURCE", pixel_size=9, parent=overlay._source_inset_host)
    overlay._source_inset_label.setObjectName("quicklook_source_inset_title")
    src_lay.addWidget(overlay._source_inset_label)
    overlay._source_inset_pix = QLabel(overlay._source_inset_host)
    overlay._source_inset_pix.setObjectName("quicklook_source_inset_pix")
    overlay._source_inset_pix.setFixedSize(scaled_px(150), scaled_px(84))
    overlay._source_inset_pix.setAlignment(Qt.AlignmentFlag.AlignCenter)
    overlay._source_inset_pix.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    try:
        pal = overlay._source_inset_host.palette()
        bg = _token_rgba_qcolor("shadow.color", (0, 0, 0, 140))
        if bg is not None:
            # Ensure overlay alpha 140 if token is opaque
            try:
                if bg.alpha() == 255:
                    bg.setAlpha(140)
            except Exception:
                pass
        pal.setColor(overlay._source_inset_host.backgroundRole(), bg)
        overlay._source_inset_host.setAutoFillBackground(True)
        overlay._source_inset_host.setPalette(pal)
    except Exception:
        pass
    src_lay.addWidget(overlay._source_inset_pix)
    overlay._source_inset_host.raise_()
    overlay._source_inset_host.hide()
    overlay._crop_host = QWidget(preview_host)
    overlay._crop_host.setObjectName("quicklook_crop_host")
    crop_lay = QVBoxLayout(overlay._crop_host)
    crop_lay.setContentsMargins(0, 0, 0, 0)
    crop_lay.setSpacing(scaled_px(2))
    overlay._crop_title = Label("SHARPNESS CROP", pixel_size=9, parent=overlay._crop_host)
    overlay._crop_title.setObjectName("quicklook_crop_title")
    crop_lay.addWidget(overlay._crop_title)
    overlay._crop_pix = QLabel(overlay._crop_host)
    overlay._crop_pix.setObjectName("quicklook_crop_pix")
    overlay._crop_pix.setFixedSize(scaled_px(150), scaled_px(84))
    overlay._crop_pix.setAlignment(Qt.AlignmentFlag.AlignCenter)
    overlay._crop_pix.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    crop_lay.addWidget(overlay._crop_pix)
    preview_host_lay.addWidget(overlay._crop_host)
    fname_row = QHBoxLayout()
    fname_row.setContentsMargins(0, 0, 0, 0)
    fname_row.setSpacing(scaled_px(8))
    overlay._filename_label = Label("", pixel_size=12, parent=preview_host)
    overlay._filename_label.setObjectName("quicklook_filename")
    try:
        overlay._filename_label.setBold(True)
    except Exception:
        pass
    fname_row.addWidget(overlay._filename_label)
    overlay._meta_label = Label("", pixel_size=11, parent=preview_host)
    overlay._meta_label.setObjectName("quicklook_meta")
    fname_row.addWidget(overlay._meta_label)
    fname_row.addStretch(1)
    preview_host_lay.addLayout(fname_row)
    preview_row.addWidget(preview_host, 1)
    overlay._next_btn = Button(text="›", variant="surface", size=(36, 36), parent=left)
    overlay._next_btn.setObjectName("quicklook_next")
    overlay._next_btn.clicked.connect(lambda: overlay._walk(1))
    preview_row.addWidget(overlay._next_btn)
    left_lay.addLayout(preview_row, 1)
    overlay._hint_label = Label("Esc closes · ←→ walk series", pixel_size=10, parent=left)
    overlay._hint_label.setObjectName("quicklook_hint")
    left_lay.addWidget(overlay._hint_label)
    mid.addWidget(left, 2)
    right_scroll = QScrollArea(overlay._content)
    right_scroll.setObjectName("quicklook_right_scroll")
    right_scroll.setWidgetResizable(True)
    right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    right_host = QWidget(right_scroll)
    right_host.setObjectName("quicklook_right_host")
    right_lay = QVBoxLayout(right_host)
    right_lay.setContentsMargins(0, 0, 0, 0)
    right_lay.setSpacing(scaled_px(10))
    right_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
    overlay._report_title = Label("Fidelity report", pixel_size=13, parent=right_host)
    overlay._report_title.setObjectName("quicklook_report_title")
    try:
        overlay._report_title.setBold(True)
    except Exception:
        pass
    right_lay.addWidget(overlay._report_title)
    overlay._report_sub = Label("", pixel_size=10, parent=right_host)
    overlay._report_sub.setObjectName("quicklook_report_sub")
    right_lay.addWidget(overlay._report_sub)
    overlay._metrics_host = QWidget(right_host)
    overlay._metrics_host.setObjectName("quicklook_metrics_host")
    overlay._metrics_layout = QVBoxLayout(overlay._metrics_host)
    overlay._metrics_layout.setContentsMargins(0, 0, 0, 0)
    overlay._metrics_layout.setSpacing(scaled_px(8))
    right_lay.addWidget(overlay._metrics_host)
    overlay._artifacts_host = QWidget(right_host)
    overlay._artifacts_host.setObjectName("quicklook_artifacts_host")
    overlay._artifacts_layout = QVBoxLayout(overlay._artifacts_host)
    overlay._artifacts_layout.setContentsMargins(0, 0, 0, 0)
    overlay._artifacts_layout.setSpacing(scaled_px(6))
    right_lay.addWidget(overlay._artifacts_host)
    overlay._series_header = Label("Series", pixel_size=11, parent=right_host)
    overlay._series_header.setObjectName("quicklook_series_header")
    try:
        overlay._series_header.setBold(True)
    except Exception:
        pass
    right_lay.addWidget(overlay._series_header)
    overlay._series_sub = Label("", pixel_size=10, parent=right_host)
    overlay._series_sub.setObjectName("quicklook_series_sub")
    right_lay.addWidget(overlay._series_sub)
    overlay._strip_host = QWidget(right_host)
    overlay._strip_host.setObjectName("quicklook_strip_host")
    overlay._strip_layout = QHBoxLayout(overlay._strip_host)
    overlay._strip_layout.setContentsMargins(0, 0, 0, 0)
    overlay._strip_layout.setSpacing(scaled_px(6))
    overlay._strip_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
    right_lay.addWidget(overlay._strip_host)
    overlay._brief_label = Label("", pixel_size=11, parent=right_host)
    overlay._brief_label.setObjectName("quicklook_brief")
    overlay._brief_label.setWordWrap(True)
    right_lay.addWidget(overlay._brief_label)
    right_scroll.setWidget(right_host)
    mid.addWidget(right_scroll, 1)
    outer.addLayout(mid, 1)
    # bottom bar
    bar = QWidget(overlay._content)
    bar.setObjectName("quicklook_bottom_bar")
    bar_lay = QHBoxLayout(bar)
    bar_lay.setContentsMargins(0, scaled_px(6), 0, 0)
    bar_lay.setSpacing(scaled_px(8))
    accent = _token_color("accent", "#0096FF")
    danger = _token_color("danger", "#D93025")
    warning = _token_color("warning", "#e8b64c")
    overlay._compare_btn = Button(text="Compare →", variant="surface", parent=bar)
    overlay._compare_btn.setObjectName("quicklook_compare")
    try:
        if accent is not None:
            overlay._compare_btn.set_background_color(accent)
            _set_colored_text(overlay._compare_btn, "Compare →", accent)
    except Exception:
        pass
    overlay._compare_btn.clicked.connect(overlay._on_compare)
    bar_lay.addWidget(overlay._compare_btn)
    overlay._multi_btn = Button(text="Add to Multi Compare", variant="surface", parent=bar)
    overlay._multi_btn.setObjectName("quicklook_multi")
    overlay._multi_btn.clicked.connect(overlay._on_multi)
    bar_lay.addWidget(overlay._multi_btn)
    overlay._reject_btn = Button(text="✕ Reject", variant="surface", parent=bar)
    overlay._reject_btn.setObjectName("quicklook_reject")
    overlay._reject_text_color = danger
    try:
        if danger is not None:
            overlay._reject_btn.set_border_color(danger)
            _set_colored_text(overlay._reject_btn, "✕ Reject", danger)
    except Exception:
        pass
    overlay._reject_btn.clicked.connect(overlay._on_reject)
    bar_lay.addWidget(overlay._reject_btn)
    overlay._set_source_btn = Button(text="Set as source", variant="surface", parent=bar)
    overlay._set_source_btn.setObjectName("quicklook_set_source")
    try:
        if warning is not None:
            overlay._set_source_btn.set_border_color(warning)
            _set_colored_text(overlay._set_source_btn, "Set as source", warning)
    except Exception:
        pass
    overlay._set_source_btn.clicked.connect(overlay._on_set_source)
    bar_lay.addWidget(overlay._set_source_btn)
    bar_lay.addStretch(1)
    outer.addWidget(bar)
    overlay.add_widget(overlay._content, slot=None)
    overlay._strip_buttons: list = []
    overlay._metric_rows: list = []
    overlay._artifact_rows: list = []
    overlay._strip_caption_labels: list = []


# -- populate helpers -------------------------------------------------------

def populate_preview(overlay, item) -> None:
    try:
        from sli_ui_toolkit.managers import scaled_px
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap
        pm = _load_preview_pixmap(Path(getattr(item, "path", "")), scaled_px(640), scaled_px(456))
        if pm is not None and not pm.isNull():
            overlay._preview_label.setPixmap(pm)
        else:
            thumb = getattr(item, "thumbnail", None)
            if thumb is not None and not thumb.isNull():
                overlay._preview_label.setPixmap(thumb.scaled(scaled_px(320), scaled_px(260), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                overlay._preview_label.setText("No preview")
                overlay._preview_label.setPixmap(QPixmap())
    except Exception:
        pass


def populate_source_inset(overlay, item, is_fidelity: bool) -> None:
    try:
        overlay._source_inset_host.setVisible(bool(is_fidelity))
        if is_fidelity:
            from tabs.image_gallery.ui.quick_look.source_inset import reposition_source_inset
            reposition_source_inset(overlay)
    except Exception:
        pass
    if not is_fidelity:
        return
    try:
        from sli_ui_toolkit.managers import scaled_px
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap
        src = overlay._source_path
        src_item = None
        owner = overlay._owner
        try:
            items = list(getattr(getattr(owner, "state", None), "items", []) or []) if owner is not None else []
            if src is not None:
                for it2 in items:
                    if Path(getattr(it2, "path", "")) == Path(src):
                        src_item = it2
                        break
        except Exception:
            pass
        pix = None
        if src_item is not None:
            pix = _thumb_pixmap(src_item, scaled_px(150))
        elif src is not None:
            try:
                pm2 = QPixmap(str(src))
                if not pm2.isNull():
                    pix = pm2.scaled(scaled_px(150), scaled_px(84), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            except Exception:
                pass
        if pix is not None and not pix.isNull():
            overlay._source_inset_pix.setPixmap(pix)
        else:
            overlay._source_inset_pix.setText("—")
        src_name = Path(src).name if src is not None else "source"
        caption = f"SOURCE · {src_name}"
        dims = _source_dimensions(src_item, src)
        if dims is not None:
            caption += f" · {dims[0]}×{dims[1]}"
        overlay._source_inset_label.setText(caption)
    except Exception:
        pass


def populate_crop(overlay, item) -> None:
    try:
        from sli_ui_toolkit.managers import scaled_px
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap
        pm_full = QPixmap(str(getattr(item, "path", "")))
        if not pm_full.isNull():
            w = pm_full.width()
            h = pm_full.height()
            cw = max(1, w // 3)
            ch = max(1, h // 3)
            x = max(0, (w - cw) // 2)
            y = max(0, (h - ch) // 2)
            crop = pm_full.copy(x, y, cw, ch)
            crop_scaled = crop.scaled(scaled_px(150), scaled_px(84), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            overlay._crop_pix.setPixmap(crop_scaled)
        else:
            thumb = getattr(item, "thumbnail", None)
            if thumb is not None and not thumb.isNull():
                overlay._crop_pix.setPixmap(thumb.scaled(scaled_px(150), scaled_px(84), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
            else:
                overlay._crop_pix.setText("—")
    except Exception:
        pass


def populate_filename_meta(overlay, item, is_fidelity: bool) -> None:
    try:
        overlay._filename_label.setText(str(getattr(item, "name", Path(getattr(item, "path", "")).name)))
    except Exception:
        pass
    try:
        from PySide6.QtGui import QPixmap
        meta_parts = []
        p = Path(getattr(item, "path", ""))
        try:
            if p.is_file():
                sz = p.stat().st_size
                if sz < 1024:
                    meta_parts.append(f"{sz} B")
                elif sz < 1024 * 1024:
                    meta_parts.append(f"{sz/1024:.1f} KB")
                else:
                    meta_parts.append(f"{sz/1024/1024:.1f} MB")
                meta_parts.append(p.suffix.lstrip(".").upper() or "IMG")
            pm_meta = QPixmap(str(p))
            if not pm_meta.isNull():
                meta_parts.append(f"{pm_meta.width()} × {pm_meta.height()}")
        except Exception:
            pass
        metrics = getattr(item, "metrics", None) or {}
        if isinstance(metrics, dict) and metrics.get("upscale_factor"):
            try:
                meta_parts.append(f"upscale ×{metrics.get('upscale_factor')}")
            except Exception:
                pass
        if is_fidelity and overlay._source_path is not None:
            meta_parts.append("upscale from source")
        overlay._meta_label.setText(" · ".join(meta_parts))
    except Exception:
        pass


def populate_report_header(overlay, is_fidelity: bool, mode_str: str) -> None:
    try:
        if is_fidelity:
            overlay._report_title.setText("Fidelity report")
            src_name = Path(overlay._source_path).name if overlay._source_path is not None else "source"
            overlay._report_sub.setText(f"vs SOURCE {src_name} · shared/analysis engine")
        else:
            if "CAMERA" in mode_str:
                overlay._report_title.setText("Camera report")
                overlay._report_sub.setText("sharpness / exposure profile · local metrics")
            else:
                overlay._report_title.setText("Batch report")
                overlay._report_sub.setText("distance to centroid · artifact flags")
    except Exception:
        pass


def populate_series_header(overlay) -> None:
    try:
        n = len(overlay._series_items)
        overlay._series_header.setText(f"Series · {n} images" if n > 1 else "Single")
        rejected_cnt = sum(1 for m in overlay._series_items if bool(getattr(m, "rejected", False)))
        pending = sum(1 for m in overlay._series_items if bool(getattr(m, "vlm_tie_pending", False)))
        if n > 1:
            sub = f"rank by fidelity · {rejected_cnt} rejected"
            if pending:
                sub += f" · {pending} tie-break pending"
            overlay._series_sub.setText(sub)
        else:
            overlay._series_sub.setText("ungrouped")
    except Exception:
        pass


def populate_brief(overlay, item) -> None:
    try:
        brief = ""
        vlm_brief = getattr(item, "vlm_brief", None)
        status = getattr(item, "vlm_brief_status", "none")
        if vlm_brief is not None:
            try:
                summary = getattr(vlm_brief, "summary", "") or ""
                diffs = getattr(vlm_brief, "differences", ()) or ()
                if summary:
                    brief = summary
                    if diffs:
                        brief += " — " + "; ".join(list(diffs)[:2])
                else:
                    brief = "; ".join(list(diffs)[:2]) if diffs else ""
                if status == "pending":
                    brief = "AI brief…"
            except Exception:
                brief = ""
            if not brief and status == "pending":
                brief = "AI brief…"
        if brief:
            overlay._brief_label.setText(brief)
            overlay._brief_label.setVisible(True)
        else:
            overlay._brief_label.setText("")
            overlay._brief_label.setVisible(False)
    except Exception:
        try:
            overlay._brief_label.setVisible(False)
        except Exception:
            pass

