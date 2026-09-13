"""Quick look series strip — plain functions taking overlay."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsOpacityEffect, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, Label


def rebuild_strip(overlay) -> None:
    for b in list(overlay._strip_buttons):
        try:
            overlay._strip_layout.removeWidget(b)
            b.setParent(None)
            b.deleteLater()
        except Exception:
            pass
    overlay._strip_buttons.clear()
    for cap in list(getattr(overlay, "_strip_caption_labels", [])):
        try:
            overlay._strip_layout.removeWidget(cap)
            cap.setParent(None)
            cap.deleteLater()
        except Exception:
            pass
    overlay._strip_caption_labels.clear()
    try:
        while overlay._strip_layout.count():
            it = overlay._strip_layout.takeAt(0)
            w = it.widget() if it is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
    except Exception:
        pass
    for idx, m in enumerate(overlay._series_items):
        is_viewing = idx == overlay._current_idx
        is_source = False
        try:
            if overlay._source_path is not None and Path(getattr(m, "path", "")) == Path(overlay._source_path):
                is_source = True
        except Exception:
            pass
        rejected = bool(getattr(m, "rejected", False))
        pending = bool(getattr(m, "vlm_tie_pending", False))
        if is_source:
            text = "SOURCE"
        elif rejected:
            text = "✕"
        elif is_viewing:
            text = f"#{idx+1} viewing"
        else:
            text = f"#{idx+1}"
        thumb_pm = None
        try:
            from tabs.image_gallery.ui.quick_look.helpers import _thumb_pixmap

            thumb_pm = _thumb_pixmap(m, scaled_px(66))
        except Exception:
            thumb_pm = None
        container = QWidget(overlay._strip_host)
        container.setObjectName(f"quicklook_strip_container_{idx}")
        cont_lay = QVBoxLayout(container)
        cont_lay.setContentsMargins(0, 0, 0, 0)
        cont_lay.setSpacing(scaled_px(2))
        cont_lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        btn_kwargs = dict(variant="surface", size=(74, 44), parent=container)
        if thumb_pm is not None and not thumb_pm.isNull():
            try:
                btn = Button(text=text, pixmap=thumb_pm, parent=container, **{k: v for k, v in btn_kwargs.items() if k != "parent"})
                try:
                    btn.setProperty("image_fill", "cover")
                except Exception:
                    pass
            except Exception:
                btn = Button(text=text, variant="surface", size=(74, 44), parent=container)
        else:
            btn = Button(text=text, variant="surface", size=(74, 44), parent=container)
        btn.setObjectName(f"quicklook_strip_{idx}")
        try:
            if pending:
                btn.setBadge("…")
                try:
                    from tabs.image_gallery.ui.quick_look.helpers import _token_color, _token_rgba_qcolor

                    bg = _token_color("surface.button", "#5a5a5a")
                    # badge text white via theme token
                    from PySide6.QtGui import QColor as _QC

                    try:
                        from sli_ui_toolkit.managers import ThemeManager

                        from ui.theming import try_resolve_theme_color

                        _txt = try_resolve_theme_color(ThemeManager.get_instance(), "button.primary.text")
                        txt_col = _txt if isinstance(_txt, _QC) else _QC(_txt) if isinstance(_txt, str) else _QC(255, 255, 255)
                        if _txt is None:
                            txt_col = _QC(255, 255, 255)
                    except Exception:
                        txt_col = _QC(255, 255, 255)
                    if bg is None:
                        bg = _QC(90, 90, 90)
                    btn.setBadgeStyle(filled=True, background_color=bg, text_color=txt_col)
                except Exception:
                    pass
            elif is_source:
                pass
        except Exception:
            pass
        try:
            btn.setProperty("gallery_path", str(getattr(m, "path", "")))
        except Exception:
            pass
        try:
            if is_viewing:
                btn.setChecked(True)
        except Exception:
            pass
        try:
            btn.setEnabled(True)
        except Exception:
            pass
        try:
            if is_source:
                from tabs.image_gallery.ui.quick_look.helpers import _token_color

                gold = _token_color("warning", "#e8b64c")
                if gold is not None:
                    btn.set_border_color(gold)
            elif is_viewing:
                from tabs.image_gallery.ui.quick_look.helpers import _token_color

                accent_c = _token_color("accent", "#0096FF")
                if accent_c is not None:
                    btn.set_border_color(accent_c)
        except Exception:
            pass
        try:
            current_effect = btn.graphicsEffect()
            if rejected:
                if not isinstance(current_effect, QGraphicsOpacityEffect):
                    eff = QGraphicsOpacityEffect(btn)
                    eff.setOpacity(0.4)
                    btn.setGraphicsEffect(eff)
                else:
                    current_effect.setOpacity(0.4)
            elif isinstance(current_effect, QGraphicsOpacityEffect):
                btn.setGraphicsEffect(None)
        except Exception:
            pass

        def _make_switch(target=m):
            def _do():
                overlay._current_item = target
                try:
                    for i, mm in enumerate(overlay._series_items):
                        if Path(getattr(mm, "path", "")) == Path(getattr(target, "path", "")):
                            overlay._current_idx = i
                            break
                except Exception:
                    pass
                overlay._populate()
            return _do

        btn.clicked.connect(_make_switch())
        cont_lay.addWidget(btn)
        caption_text = ""
        if pending:
            caption_text = "tie-break pending"
        elif is_viewing and len(overlay._series_items) > 1:
            caption_text = ""
        if caption_text:
            cap = Label(caption_text, pixel_size=9, parent=container)
            cap.setObjectName(f"quicklook_strip_cap_{idx}")
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cont_lay.addWidget(cap)
            overlay._strip_caption_labels.append(cap)
        overlay._strip_buttons.append(container)
        overlay._strip_layout.addWidget(container)
    try:
        has_pending = any(bool(getattr(m, "vlm_tie_pending", False)) for m in overlay._series_items)
        if not has_pending and overlay._series_items:
            hint = Label("click thumb = switch preview", pixel_size=9, parent=overlay._strip_host)
            hint.setObjectName("quicklook_strip_hint")
            overlay._strip_layout.addWidget(hint)
            overlay._strip_caption_labels.append(hint)
    except Exception:
        pass
