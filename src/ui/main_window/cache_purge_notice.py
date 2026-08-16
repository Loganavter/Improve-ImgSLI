"""One-time notice after upgrading from a version that left stale
TiledPixelStore spill files behind between sessions (see
core.bootstrap.ApplicationContext._maybe_flag_cache_purge_notice and
shared.image_processing.tiled_pixel_store.purge_stale_spill_files)."""

from __future__ import annotations

import logging

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

logger = logging.getLogger("ImproveImgSLI")


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def schedule_cache_purge_notice(parent: QWidget, reclaimed_bytes: int | None) -> None:
    """After the main window is shown, tell the user about a one-time
    startup cache cleanup, if ``bootstrap`` flagged one as worth mentioning."""
    if not reclaimed_bytes:
        return

    def _present() -> None:
        try:
            from resources.translations import tr as app_tr
            from shared_toolkit.ui.message_dialog import AppMessageDialog

            store = getattr(parent, "store", None)
            lang = "en"
            if store is not None:
                lang = (
                    getattr(getattr(store, "settings", None), "current_language", "en")
                    or "en"
                )
            title = app_tr("msg.cache_purge_notice_title", lang)
            text = app_tr("msg.cache_purge_notice_body", lang).format(
                size=_format_size(reclaimed_bytes)
            )
            ok_text = app_tr("common.ok", lang)
            AppMessageDialog.information(parent, title, text, ok_text=ok_text)
        except Exception:
            logger.exception("Failed to show cache purge notice dialog")

    QTimer.singleShot(0, _present)
