"""QuickLookOverlay region selection — LMB drag over the preview → Ask AI box.

Moved verbatim from ``ui/quick_look.py`` (plan-gallery-split-2026-10-17,
Part C2). Plain functions taking the overlay as their first argument; the
class keeps same-named one-line delegators. The band widget lives in
``quick_look/region.py``; the normalized box mapping in ``region``.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt


def _preview_rect_in_overlay(self):
    host = getattr(self, "_preview_host", None)
    if host is None:
        return None
    try:
        top_left = host.mapTo(self, QPoint(0, 0))
        return QRect(top_left, host.size())
    except Exception:
        return None


def _ensure_region_band(self):
    band = getattr(self, "_region_band", None)
    host = getattr(self, "_preview_host", None)
    if band is None and host is not None:
        try:
            from tabs.image_gallery.ui.quick_look.region import RegionBand

            band = RegionBand(host)
            self._region_band = band
        except Exception:
            band = None
    try:
        if band is not None and host is not None:
            band.setGeometry(host.rect())
    except Exception:
        pass
    return band


def _maybe_start_region(self, event) -> bool:
    try:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
    except Exception:
        return False
    rect = self._preview_rect_in_overlay()
    if rect is None:
        return False
    try:
        pos = event.position().toPoint()
    except Exception:
        return False
    if not rect.contains(pos):
        return False
    host = getattr(self, "_preview_host", None)
    try:
        local = host.mapFrom(self, pos)
    except Exception:
        return False
    self._region_active = True
    self._region_start_host = QPoint(local)
    band = self._ensure_region_band()
    if band is not None:
        try:
            band.set_band(QRect(QPoint(local), QSize(0, 0)))
            band.show()
            band.raise_()
        except Exception:
            pass
        # A new marquee supersedes whatever dismissal the previous
        # selection armed: the close ending that flyout session must
        # not wipe this one (one-gesture dismiss + reselect).
        try:
            begin = getattr(band, "begin_selection", None)
            if callable(begin):
                begin()
        except Exception:
            pass
    return True


def _update_region(self, event) -> None:
    if not getattr(self, "_region_active", False):
        return
    band = getattr(self, "_region_band", None)
    host = getattr(self, "_preview_host", None)
    if band is None or host is None:
        return
    try:
        local = host.mapFrom(self, event.position().toPoint())
    except Exception:
        return
    local = QPoint(
        max(0, min(host.width(), local.x())),
        max(0, min(host.height(), local.y())),
    )
    start = getattr(self, "_region_start_host", None) or QPoint(0, 0)
    band.set_band(QRect(start, local).normalized())


def _finish_region(self, event) -> None:
    if not getattr(self, "_region_active", False):
        return
    self._region_active = False
    band = getattr(self, "_region_band", None)
    rect = getattr(band, "_rect", None) if band is not None else None
    if rect is None or rect.width() < 4 or rect.height() < 4:
        # Too small to ask about: drop the band as before.
        if band is not None:
            try:
                band.hide()
            except Exception:
                pass
            try:
                band.clear()
            except Exception:
                pass
        return
    # Valid selection: KEEP the band visible. The Ask AI flyout anchors
    # to it (RegionBand.flyoutAnchorRect — above the selected region,
    # not the preview corner) and dismisses it when it closes.
    if band is not None:
        try:
            band.show()
            band.raise_()
        except Exception:
            pass
    canvas = getattr(self, "_preview_canvas", None)
    box = None
    if canvas is not None:
        try:
            from tabs.image_gallery.ui.quick_look.region import norm_rect_for_band

            box = norm_rect_for_band(canvas, rect)
        except Exception:
            box = None
    item = getattr(self, "_current_item", None)
    path = getattr(item, "path", None)
    if path is None or not box:
        return
    try:
        self.regionAskRequested.emit(str(path), box)
    except Exception:
        pass


def region_selection_anchor(self):
    """Anchor for the region Ask AI flyout: the held selection band.

    Returns the band while a valid selection is held (so the flyout
    opens above the selected region via ``flyoutAnchorRect``), else
    ``None`` (callers fall back to the preview host).
    """
    band = getattr(self, "_region_band", None)
    try:
        if band is not None and not band.isHidden():
            rect = getattr(band, "_rect", None)
            if (
                rect is not None
                and not rect.isNull()
                and rect.width() >= 4
                and rect.height() >= 4
            ):
                return band
    except Exception:
        pass
    return None


def hide_region_band(self) -> None:
    """Drop a held region selection (the flyout-closed path)."""
    band = getattr(self, "_region_band", None)
    if band is None:
        return
    try:
        dismiss = getattr(band, "dismiss_selection", None)
        if callable(dismiss):
            dismiss()
            return
    except Exception:
        pass
    try:
        band.hide()
    except Exception:
        pass
