"""Project scene thumbnail (``preview.jpg``) helpers for portable ``.imgsli`` files."""

from __future__ import annotations

import hashlib
import logging
import zipfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPixmap

logger = logging.getLogger("ImproveImgSLI")

PREVIEW_MEMBER = "preview.jpg"
PREVIEW_WIDTH = 160
PREVIEW_HEIGHT = 90
PREVIEW_JPEG_QUALITY = 80

_SKIP_SESSION_TYPES = frozenset({"session_picker", ""})


def project_previews_cache_dir() -> Path:
    from services.io.project_package import _cache_root

    root = _cache_root() / "project_previews"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cache_key(path: Path) -> str:
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        mtime_ns = 0
    digest = hashlib.sha256(f"{path.resolve()}:{mtime_ns}".encode("utf-8")).hexdigest()
    return digest[:24]


def _scale_cover(image: QImage, width: int, height: int) -> QImage:
    if image.isNull() or width <= 0 or height <= 0:
        return QImage()
    scaled = image.scaled(
        width,
        height,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - width) // 2)
    y = max(0, (scaled.height() - height) // 2)
    return scaled.copy(x, y, width, height)


def qimage_to_jpeg_bytes(
    image: QImage,
    *,
    quality: int = PREVIEW_JPEG_QUALITY,
) -> bytes | None:
    if image.isNull():
        return None
    # JPEG has no alpha — composite onto opaque black first.
    if image.hasAlphaChannel():
        flat = QImage(image.size(), QImage.Format.Format_RGB32)
        flat.fill(Qt.GlobalColor.black)
        from PySide6.QtGui import QPainter

        painter = QPainter(flat)
        painter.drawImage(0, 0, image)
        painter.end()
        image = flat
    else:
        image = image.convertToFormat(QImage.Format.Format_RGB32)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    ok = image.save(buf, "JPG", int(quality))
    buf.close()
    if not ok or ba.isEmpty():
        return None
    return bytes(ba)


def _canvas_attr(host) -> Any:
    if host is None:
        return None
    for attr in ("image_label", "canvas", "compare_canvas"):
        canvas = getattr(host, attr, None)
        if canvas is not None:
            return canvas
    return None


def _canvas_from_page(page) -> Any:
    """Resolve the live canvas widget for a workspace page.

    Image Compare returns the host widget itself (``image_label``). Multi Compare
    wraps ``MultiCompareWidget`` in an outer ``QWidget``, so the canvas lives on
    a child — walk direct/deep children when the page has no canvas attr.
    """
    found = _canvas_attr(page)
    if found is not None:
        return found
    try:
        from PySide6.QtWidgets import QWidget

        if not isinstance(page, QWidget):
            return None
        for child in page.findChildren(QWidget):
            found = _canvas_attr(child)
            if found is not None:
                return found
    except Exception:
        logger.debug("Canvas lookup under page failed", exc_info=True)
    return None


def _grab_widget_image(widget) -> QImage | None:
    if widget is None:
        return None
    try:
        if hasattr(widget, "grabFramebuffer"):
            # Ensure a current frame exists (QRhiWidget can return empty
            # otherwise — same prep pattern as multi-compare GPU export).
            try:
                widget.update()
                from PySide6.QtWidgets import QApplication

                app = QApplication.instance()
                if app is not None:
                    app.processEvents()
            except Exception:
                pass
            image = widget.grabFramebuffer()
            if isinstance(image, QImage) and not image.isNull():
                return image
        pix = widget.grab()
        if isinstance(pix, QPixmap) and not pix.isNull():
            return pix.toImage()
    except Exception:
        logger.debug("Canvas grab for project preview failed", exc_info=True)
    return None


def capture_project_preview_jpeg(
    window,
    *,
    size: tuple[int, int] = (PREVIEW_WIDTH, PREVIEW_HEIGHT),
    quality: int = PREVIEW_JPEG_QUALITY,
) -> bytes | None:
    """Capture a small JPEG of the active workspace canvas (UI thread)."""
    store = getattr(window, "store", None)
    if store is None:
        return None
    session = store.get_active_workspace_session()
    if session is None:
        return None
    session_type = str(getattr(session, "session_type", "") or "")
    if session_type in _SKIP_SESSION_TYPES:
        return None

    registry = None
    ui = getattr(window, "ui", None)
    if ui is not None:
        registry = getattr(ui, "_tab_registry", None)
    if registry is None:
        try:
            from tabs.registry import get_shared_tab_registry

            registry = get_shared_tab_registry()
        except Exception:
            registry = None
    if registry is None:
        return None

    page = None
    try:
        page = registry.get_page(session_type)
    except Exception:
        page = None

    image = _grab_widget_image(_canvas_from_page(page))
    if image is None or image.isNull():
        return None

    out_w, out_h = int(size[0]), int(size[1])
    cover = _scale_cover(image, out_w, out_h)
    return qimage_to_jpeg_bytes(cover, quality=quality)


def zip_has_preview(path: str | Path) -> bool:
    path = Path(path)
    if not path.is_file():
        return False
    try:
        with zipfile.ZipFile(path, "r") as zf:
            return PREVIEW_MEMBER in zf.namelist()
    except Exception:
        return False


def read_preview_jpeg_bytes(path: str | Path) -> bytes | None:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        with zipfile.ZipFile(path, "r") as zf:
            if PREVIEW_MEMBER not in zf.namelist():
                return None
            return zf.read(PREVIEW_MEMBER)
    except Exception:
        logger.debug("Failed reading %s from %s", PREVIEW_MEMBER, path, exc_info=True)
        return None


def peek_project_preview(path: str | Path) -> QPixmap | None:
    """Load ``preview.jpg`` from a project zip, with an mtime-keyed disk cache."""
    path = Path(path)
    if not path.is_file():
        return None

    cache_path = project_previews_cache_dir() / f"{_cache_key(path)}.jpg"
    try:
        if cache_path.is_file():
            pix = QPixmap(str(cache_path))
            if not pix.isNull():
                return pix
    except Exception:
        pass

    raw = read_preview_jpeg_bytes(path)
    if not raw:
        return None
    pix = QPixmap()
    if not pix.loadFromData(raw, "JPG"):
        return None
    try:
        cache_path.write_bytes(raw)
    except OSError:
        pass
    return pix
