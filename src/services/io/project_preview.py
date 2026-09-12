"""Project scene thumbnail (``preview.png``) for portable ``.imgsli`` files.

Embedded preview is a cover-scaled grab of the active workspace canvas (IC /
MC). Session Picker cards and the Linux XDG thumbnailer both read this
member. Legacy packages may still carry ``preview.jpg``; readers accept both.
"""

from __future__ import annotations

import hashlib
import logging
import zipfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap

logger = logging.getLogger("ImproveImgSLI")

PREVIEW_MEMBER = "preview.png"
PREVIEW_LEGACY_MEMBERS = ("preview.jpg",)
PREVIEW_MEMBERS = (PREVIEW_MEMBER, *PREVIEW_LEGACY_MEMBERS)
PREVIEW_WIDTH = 160
PREVIEW_HEIGHT = 90
PREVIEW_PNG_COMPRESS = 6
# Kept for call sites / tests that still pass ``quality=``.
PREVIEW_JPEG_QUALITY = 80

try:
    from core.store import INITIAL_WORKSPACE_SESSION_TYPE as _SKIP_PICKER

    _SKIP_SESSION_TYPES = frozenset({_SKIP_PICKER, ""})
except Exception:
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


def qimage_to_png_bytes(
    image: QImage,
    *,
    compress: int = PREVIEW_PNG_COMPRESS,
) -> bytes | None:
    if image.isNull():
        return None
    if image.hasAlphaChannel():
        flat = QImage(image.size(), QImage.Format.Format_RGB32)
        flat.fill(Qt.GlobalColor.black)
        painter = QPainter(flat)
        painter.drawImage(0, 0, image)
        painter.end()
        image = flat
    else:
        image = image.convertToFormat(QImage.Format.Format_RGB32)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    ok = image.save(buf, "PNG", int(compress))  # type: ignore[call-overload]  # PySide6 runtime wants str format for QIODevice
    buf.close()
    if not ok or ba.isEmpty():
        return None
    return bytes(ba)  # type: ignore[call-overload]  # QByteArray supports buffer protocol



def _canvas_attr(host) -> Any:
    """Legacy canvas probe — kept as fallback for tabs not yet providing
    ``capture_preview_image`` service. New tabs should implement that service
    instead of adding their canvas attr name here (see C1).
    """
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

    Prefer ``capture_preview_image`` service; this is fallback only.
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


def _grab_via_service(registry, session_type: str) -> QImage | None:
    """Try tab-provided ``capture_preview_image`` service before duck-typing."""
    if registry is None or not session_type:
        return None
    try:
        # Prefer targeted create_service_for so only the active tab answers.
        if hasattr(registry, "create_service_for"):
            image = registry.create_service_for(
                session_type, "capture_preview_image"
            )
            if isinstance(image, QImage) and not image.isNull():
                return image
        # Fallback to active-tab create_service (works when preview
        # is requested for the currently active session).
        if hasattr(registry, "create_service"):
            image = registry.create_service("capture_preview_image")
            if isinstance(image, QImage) and not image.isNull():
                return image
    except Exception:
        logger.debug("capture_preview_image service failed", exc_info=True)
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


def capture_project_preview_png(
    window,
    *,
    size: tuple[int, int] = (PREVIEW_WIDTH, PREVIEW_HEIGHT),
    compress: int = PREVIEW_PNG_COMPRESS,
) -> bytes | None:
    """Capture a small PNG of the active workspace canvas (UI thread)."""
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

    # Prefer service-provided image (no widget-name literals).
    image = _grab_via_service(registry, session_type)
    if image is None:
        # Legacy fallback: duck-typed canvas hunt — deprecated path (C1).
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
    return qimage_to_png_bytes(cover, compress=compress)



def zip_has_preview(path: str | Path) -> bool:
    path = Path(path)
    if not path.is_file():
        return False
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
            return any(name in names for name in PREVIEW_MEMBERS)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        logger.debug("No readable preview archive at %s", path, exc_info=True)
        return False
    except Exception:
        logger.warning("Unexpected error checking preview in %s", path, exc_info=True)
        return False


def read_preview_image_bytes(path: str | Path) -> bytes | None:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        from services.io.project_package import ZIP_MAX_PREVIEW_BYTES, _capped_copy

        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
            for member in PREVIEW_MEMBERS:
                if member in names:
                    try:
                        info = zf.getinfo(member)
                        if info.file_size > ZIP_MAX_PREVIEW_BYTES:
                            logger.warning("Preview %s too large (%d bytes), skipping", member, info.file_size)
                            continue
                    except KeyError:
                        pass
                    import io

                    with zf.open(member) as fh:
                        buf = io.BytesIO()
                        try:
                            _capped_copy(fh, buf, ZIP_MAX_PREVIEW_BYTES, member)
                        except ValueError as exc:
                            logger.warning("%s", exc)
                            continue
                        return buf.getvalue()
    except Exception:
        logger.debug("Failed reading preview from %s", path, exc_info=True)
        return None
    return None



def peek_project_preview(path: str | Path) -> QPixmap | None:
    """Load ``preview.png`` (or legacy ``preview.jpg``), with mtime disk cache.

    Returns ``None`` when the package has no preview member — cards then fall
    back to the session-type icon (no branded logo placeholder).
    """
    path = Path(path)
    if not path.is_file():
        return None

    cache_path = project_previews_cache_dir() / f"{_cache_key(path)}.png"
    try:
        if cache_path.is_file():
            pix = QPixmap(str(cache_path))
            if not pix.isNull():
                return pix
    except Exception:
        pass

    raw = read_preview_image_bytes(path)
    if not raw:
        return None
    pix = QPixmap()
    if not pix.loadFromData(raw):
        return None
    try:
        cache_path.write_bytes(raw)
    except OSError:
        pass
    return pix