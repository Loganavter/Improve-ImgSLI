"""Show a user-visible error when startup had to fall back from a broken RHI API."""

from __future__ import annotations

import logging

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from ui.widgets.canvas.rhi_backend import (
    RhiFallbackNotice,
    take_rhi_fallback_notice,
)

logger = logging.getLogger("ImproveImgSLI.rhi")


def _backend_display_name(backend: str, lang: str) -> str:
    from resources.translations import tr as app_tr

    key = (backend or "default").strip().lower()
    i18n_key = f"settings.render_backend_{key}"
    label = app_tr(i18n_key, lang)
    if label == i18n_key:
        return key
    return label


def _show_fallback_dialog(parent: QWidget | None, notice: RhiFallbackNotice) -> None:
    from resources.translations import tr as app_tr
    from shared_toolkit.ui.message_dialog import AppMessageDialog

    lang = "en"
    store = getattr(parent, "store", None) if parent is not None else None
    if store is not None:
        lang = getattr(getattr(store, "settings", None), "current_language", "en") or "en"
        try:
            store.settings.rhi_backend = notice.effective
        except Exception:
            logger.exception("Failed to sync store.settings.rhi_backend after fallback")

    title = app_tr("settings.render_backend_fallback_title", lang)
    text = app_tr("settings.render_backend_fallback_message", lang).format(
        requested=_backend_display_name(notice.requested, lang),
        effective=_backend_display_name(notice.effective, lang),
    )
    ok_text = app_tr("common.ok", lang)
    AppMessageDialog.critical(parent, title, text, ok_text=ok_text)


def schedule_rhi_fallback_user_notice(parent: QWidget | None) -> None:
    """After the main window is shown, surface any startup RHI fallback as an error."""
    notice = take_rhi_fallback_notice()
    if notice is None:
        return

    def _present() -> None:
        try:
            _show_fallback_dialog(parent, notice)
        except Exception:
            logger.exception(
                "Failed to show RHI fallback dialog (requested=%s effective=%s)",
                notice.requested,
                notice.effective,
            )

    QTimer.singleShot(0, _present)
