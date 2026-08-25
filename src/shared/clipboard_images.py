"""Collect image paths / URLs from the system clipboard.

Shared by tab-owned ``clipboard_paste_service`` implementations so paste
sources stay consistent across session types.
"""

from __future__ import annotations

import atexit
import logging
import os
import tempfile
import time
import urllib.parse
import urllib.request
from urllib.parse import urlparse
from urllib.request import url2pathname

from PySide6.QtWidgets import QApplication

logger = logging.getLogger("ImproveImgSLI")

_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
_MAX_DOWNLOAD_PER_URL = _MAX_DOWNLOAD_BYTES
_TEMP_CLIPBOARD_FILES: set[str] = set()


def _register_temp_file(path: str) -> None:
    _TEMP_CLIPBOARD_FILES.add(path)


def _unregister_and_remove(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    _TEMP_CLIPBOARD_FILES.discard(path)


def _schedule_temp_cleanup(path: str, delay_ms: int = 60000) -> None:
    _register_temp_file(path)
    try:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(delay_ms, lambda p=path: _unregister_and_remove(p))
    except Exception:
        pass


@atexit.register
def _cleanup_clipboard_temps() -> None:
    for p in list(_TEMP_CLIPBOARD_FILES):
        _unregister_and_remove(p)


def collect_clipboard_image_items() -> list[str]:
    """Return local paths and http(s) URLs found in the clipboard.

    Raw clipboard images are written to a temp PNG and included as a path.
    """
    clipboard = QApplication.clipboard()
    mime_data = clipboard.mimeData()
    items: list[str] = []

    text_content = mime_data.text()
    if text_content:
        for line in text_content.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("file://"):
                try:
                    parsed = urlparse(line)
                    path = url2pathname(parsed.path)
                    if parsed.netloc:
                        path = os.path.join(f"//{parsed.netloc}", path.lstrip("/\\"))
                    if os.name == "nt" and len(path) >= 3 and path[0] == "/" and path[2] == ":":
                        path = path[1:]
                    else:
                        path = urllib.parse.unquote(path) if "%" in path else path
                except Exception:
                    path = urllib.parse.unquote(line[7:])
                if os.path.exists(path):
                    items.append(path)
            elif os.path.exists(line):
                items.append(line)
            elif line.startswith(("http://", "https://")):
                items.append(line)

    if mime_data.hasUrls():
        for url in mime_data.urls():
            url_str = url.toString()
            if url.isLocalFile():
                items.append(url.toLocalFile())
            elif url_str.startswith(("http://", "https://")):
                items.append(url_str)

    if not items and mime_data.hasImage():
        qimage = clipboard.image()
        if not qimage.isNull():
            temp_path = os.path.join(
                tempfile.gettempdir(),
                f"clip_{int(time.time() * 1000)}.png",
            )
            qimage.save(temp_path, "PNG")  # type: ignore[call-overload]
            _schedule_temp_cleanup(temp_path, delay_ms=300000)
            items.append(temp_path)

    return _dedupe_clipboard_items(items)


def _dedupe_clipboard_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item.startswith(("http://", "https://")):
            key = item
        else:
            key = os.path.normcase(os.path.normpath(item))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def download_images_from_urls(urls: list[str], timeout: int = 10) -> list[str]:
    downloaded_paths: list[str] = []
    try:
        for url_str in urls:
            try:
                with urllib.request.urlopen(url_str, timeout=timeout) as response:
                    content_type = response.headers.get_content_type()
                    if not (content_type and content_type.startswith("image/")):
                        continue
                    content_length = response.headers.get("Content-Length")
                    if content_length is not None:
                        try:
                            if int(content_length) > _MAX_DOWNLOAD_PER_URL:
                                logger.warning("URL download rejected (too large %s bytes): %s", content_length, url_str)
                                continue
                        except ValueError:
                            pass
                    data = response.read(_MAX_DOWNLOAD_PER_URL + 1)
                    if len(data) > _MAX_DOWNLOAD_PER_URL:
                        logger.warning("URL download body truncated (exceeds %s bytes): %s", _MAX_DOWNLOAD_PER_URL, url_str)
                        continue
                    if not data:
                        continue
                    temp_dir = tempfile.gettempdir()
                    timestamp = int(time.time() * 1000)
                    ext = (content_type.split("/")[-1] or "png").lower()
                    if ext == "jpeg":
                        ext = "jpg"
                    ext = "".join(c for c in ext if c.isalnum())[:8] or "png"
                    temp_filename = f"url_image_{os.getpid()}_{timestamp}.{ext}"
                    image_path = os.path.join(temp_dir, temp_filename)
                    with open(image_path, "wb") as f:
                        f.write(data)
                    _schedule_temp_cleanup(image_path, delay_ms=300000)
                    downloaded_paths.append(image_path)
            except Exception as e:
                logger.warning("Failed to download image from URL %s: %s", url_str, e)
        return downloaded_paths
    except Exception as e:
        logger.error("Unexpected error during URL downloads: %s", e)
        return downloaded_paths
