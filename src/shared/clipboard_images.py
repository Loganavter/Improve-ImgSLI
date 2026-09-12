"""Collect image paths / URLs from the system clipboard.

Shared by tab-owned ``clipboard_paste_service`` implementations so paste
sources stay consistent across session types.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
import urllib.request

from PySide6.QtWidgets import QApplication

logger = logging.getLogger("ImproveImgSLI")


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
            if os.path.exists(line) or line.startswith("file://"):
                path = line[7:] if line.startswith("file://") else line
                if os.path.exists(path):
                    items.append(path)
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
            qimage.save(temp_path, "PNG")
            items.append(temp_path)

    # File managers often put the same path in both text and urls.
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
                    if content_type and content_type.startswith("image/"):
                        temp_dir = tempfile.gettempdir()
                        timestamp = int(time.time() * 1000)
                        ext = (content_type.split("/")[-1] or "png").lower()
                        if ext == "jpeg":
                            ext = "jpg"
                        temp_filename = f"url_image_{os.getpid()}_{timestamp}.{ext}"
                        image_path = os.path.join(temp_dir, temp_filename)
                        with open(image_path, "wb") as f:
                            f.write(response.read())
                        downloaded_paths.append(image_path)
            except Exception as e:
                logger.warning("Failed to download image from URL %s: %s", url_str, e)
        return downloaded_paths
    except Exception as e:
        logger.error("Unexpected error during URL downloads: %s", e)
        return downloaded_paths
