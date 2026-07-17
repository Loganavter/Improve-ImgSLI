"""Soft warning for still-image export beyond the tested resolution edge."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import QDialog, QWidget

from core.constants import AppConstants
from shared_toolkit.ui.message_dialog import AppMessageDialog, MessageKind

_Translate = Callable[..., str]
_SuppressCallback = Callable[[], None]

_TITLE_KEY = "msg.export_untested_resolution_title"
_BODY_KEY = "msg.export_untested_resolution_body"
_DONT_SHOW_KEY = "msg.dont_show_again"
_TITLE_DEFAULT = "Untested export resolution"
_BODY_DEFAULT = (
    "Export resolution exceeds {edge} px on a side ({width}×{height}). "
    "Rendering may fail or run out of memory — sizes beyond {edge} px are "
    "not guaranteed and have not been tested. Continue anyway?"
)
_DONT_SHOW_DEFAULT = "Don't show again"


def exceeds_tested_export_edge(width: int, height: int) -> bool:
    edge = int(AppConstants.EXPORT_TESTED_MAX_EDGE)
    return max(int(width or 0), int(height or 0)) > edge


def _translate(tr: _Translate, key: str, default: str, **kwargs: Any) -> str:
    try:
        text = tr(key, default)
    except TypeError:
        text = tr(key)
    if not text or text == key:
        text = default
    try:
        return str(text).format(**kwargs)
    except (KeyError, ValueError, IndexError):
        return str(text)


def confirm_untested_export_resolution(
    parent: QWidget | None,
    width: int,
    height: int,
    *,
    translate: _Translate,
    suppressed: bool = False,
    on_suppress: _SuppressCallback | None = None,
) -> bool:
    """Warn when over the tested edge. Return False if the user dismisses."""
    if not exceeds_tested_export_edge(width, height):
        return True
    if suppressed:
        return True
    edge = int(AppConstants.EXPORT_TESTED_MAX_EDGE)
    title = _translate(translate, _TITLE_KEY, _TITLE_DEFAULT, edge=edge)
    body = _translate(
        translate,
        _BODY_KEY,
        _BODY_DEFAULT,
        edge=edge,
        width=int(width),
        height=int(height),
    )
    checkbox = _translate(translate, _DONT_SHOW_KEY, _DONT_SHOW_DEFAULT)
    code, dont_show = AppMessageDialog.show_modal_ex(
        parent,
        MessageKind.WARNING,
        title,
        body,
        checkbox_text=checkbox,
    )
    if int(code) != int(QDialog.DialogCode.Accepted):
        return False
    if dont_show and on_suppress is not None:
        on_suppress()
    return True
