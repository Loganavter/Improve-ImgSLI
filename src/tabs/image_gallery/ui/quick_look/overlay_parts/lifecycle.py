"""QuickLookOverlay lifecycle — canvas release + close cover + hide/close.

Moved verbatim from ``ui/quick_look.py`` (plan-gallery-split-2026-10-17,
Part C2). Plain functions taking the overlay as their first argument; the
class keeps same-named one-line delegators so Qt's virtual dispatch is
unchanged. ``super()`` becomes an explicit ``TopLevelInWindowOverlay`` call
(the sole base) — same resolution.
"""

from __future__ import annotations

from sli_ui_toolkit.widgets import TopLevelInWindowOverlay


def _release_preview_resources(self, *, for_walk: bool = False) -> None:
    """Canvas lifecycle: clear_source() + close store + drop the cover.

    Walk steps (``_populate``) keep both memo dicts so revisits reuse
    the memoized store; hide/close drop everything. Idempotent; no-op
    when the canvas path was never taken.
    """
    try:
        if for_walk:
            from tabs.image_gallery.ui.quick_look.preview_canvas_host import (
                release_preview_canvas_for_walk,
            )

            release_preview_canvas_for_walk(self)
            return
        from tabs.image_gallery.ui.quick_look.preview_canvas_host import release_preview_canvas

        release_preview_canvas(self)
    except Exception:
        pass


def _grab_close_frame(self):
    """Grab the last canvas frame for the close cover (None on miss)."""
    try:
        canvas = getattr(self, "_preview_canvas", None)
        if canvas is None:
            return None
        try:
            if not canvas.isVisible():
                return None
        except Exception:
            pass
        try:
            shot = canvas.grab()
        except Exception:
            return None
        try:
            if shot is None or shot.isNull():
                return None
        except Exception:
            return None
        return shot
    except Exception:
        return None


def _plant_close_cover(self, shot) -> None:
    """Freeze *shot* as an opaque raster cover (call while visible).

    The canvas is a NATIVE window: when it unmaps, the compositor has
    nothing for that rect for 1-2 frames (black flash) — no amount of
    backing-store repainting fixes a compositor-level hole (proven:
    synchronous grid pre-paint changed nothing). The cover is a plain
    non-native QLabel: shown + repaint()ed synchronously while the
    overlay is still up, it rides out the unmap and hides with the
    overlay in the same stack. Next show_for drops it via the existing
    "re-cover" path (release drops covers too, so plant AFTER release,
    from a frame grabbed BEFORE it). Fail-open: no frame → no cover.
    """
    try:
        if shot is None:
            return
        try:
            if shot.isNull():
                return
        except Exception:
            return
        try:
            host = getattr(self, "_preview_host", None)
            if host is None:
                return
            from PySide6.QtCore import Qt as _Qt
            from PySide6.QtWidgets import QLabel as _QLabel

            cover = _QLabel(host)
            try:
                cover.setObjectName("quicklook_preview_close_cover")
            except Exception:
                pass
            try:
                cover.setAlignment(_Qt.AlignmentFlag.AlignCenter)
            except Exception:
                pass
            try:
                cover.setPixmap(shot)
            except Exception:
                return
            try:
                cover.setAutoFillBackground(True)
            except Exception:
                pass
            try:
                cover.setGeometry(host.rect())
            except Exception:
                pass
            try:
                cover.show()
                cover.raise_()
                cover.repaint()
            except Exception:
                pass
            try:
                self._preview_cover = cover
            except Exception:
                pass
        except Exception:
            pass
    except Exception:
        pass


def hide(self) -> None:  # noqa: N802
    # Cover-then-release-then-hide, all while still visible: planting in
    # hideEvent would be too late (hidden parent never paints). Covers
    # every path — direct hide(), close() (via its internal hide) and
    # toolkit dismiss() — since all funnel through here.
    try:
        if self.isVisible():
            shot = self._grab_close_frame()
            try:
                self._release_preview_resources()
            except Exception:
                pass
            if shot is not None:
                self._plant_close_cover(shot)
    except Exception:
        pass
    try:
        TopLevelInWindowOverlay.hide(self)
    except Exception:
        pass


def hideEvent(self, event) -> None:  # noqa: N802
    try:
        self._release_preview_resources()
    except Exception:
        pass
    TopLevelInWindowOverlay.hideEvent(self, event)


def closeEvent(self, event) -> None:  # noqa: N802
    # Same cover-then-release order as hide(): the default closeEvent
    # hides only at its end, but our release runs first — grab the
    # frame here while the canvas still presents. The internal hide()
    # below finds the canvas already released (grab misses, idempotent
    # release) and keeps the planted cover.
    try:
        if self.isVisible():
            shot = self._grab_close_frame()
            try:
                self._release_preview_resources()
            except Exception:
                pass
            if shot is not None:
                self._plant_close_cover(shot)
    except Exception:
        pass
    try:
        TopLevelInWindowOverlay.closeEvent(self, event)
    except Exception:
        pass
