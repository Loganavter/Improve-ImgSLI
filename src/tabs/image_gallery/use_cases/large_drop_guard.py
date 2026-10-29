"""Large-drop cost guard for the Image Gallery AI domain.

While the gallery's AI judgment domain is active, a single drop that carries
more than ``LARGE_DROP_THRESHOLD`` images would fan the whole batch into paid
AI calls at once. That is exactly the case the user asked to gate: ask first
with a warning window offering "Confirm and don't ask again" / "Confirm" /
"Cancel".

Reuses the shared ``AppMessageDialog`` (warning chrome + CSD); the suppress
flag lives in the gallery AI settings group (``AiSettingsStore``).
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QWidget

from tabs.host_helpers import AppMessageDialog, MessageKind

#: A single drop of more than this many images warns before reaching the AI.
LARGE_DROP_THRESHOLD = 35

_TITLE_KEY = "image_gallery.large_drop.title"
_BODY_KEY = "image_gallery.large_drop.body"
_CONFIRM_KEY = "image_gallery.large_drop.confirm"
_CONFIRM_DONT_ASK_KEY = "image_gallery.large_drop.confirm_dont_ask"
_CANCEL_KEY = "image_gallery.large_drop.cancel"

_TITLE_DEFAULT = "Large AI batch"
_BODY_DEFAULT = (
    "You are about to send {count} images to the AI at once. This can take a "
    "while and may add up to a large API cost. Continue?"
)
_CONFIRM_DEFAULT = "Confirm"
_CONFIRM_DONT_ASK_DEFAULT = "Confirm and don't ask again"
_CANCEL_DEFAULT = "Cancel"


def _translate(controller, key: str, default: str, **kwargs) -> str:
    """Resolve *key* via the controller's ``_tr`` and format placeholders."""
    translate = getattr(controller, "_tr", None)
    text = default
    if callable(translate):
        try:
            value = translate(key, default)
        except TypeError:
            value = default
        if value and value != key:
            text = str(value)
    try:
        return text.format(**kwargs)
    except (KeyError, ValueError, IndexError):
        return text


def is_ai_domain(controller) -> bool:
    """True while the gallery ranks through the AI domain."""
    domain = str(
        getattr(controller, "_judgment_domain", "algorithms") or "algorithms"
    ).lower()
    return domain == "ai"


def is_suppressed() -> bool:
    """True once the user chose “Confirm and don't ask again”."""
    try:
        from tabs.image_gallery.services.ai_settings_store import AiSettingsStore

        return bool(AiSettingsStore().load().suppress_large_drop_warning)
    except Exception:
        return False


def set_suppressed(value: bool = True) -> None:
    try:
        from tabs.image_gallery.services.ai_settings_store import AiSettingsStore

        AiSettingsStore().save_field("suppress_large_drop_warning", bool(value))
    except Exception:
        pass


def should_warn(controller, image_count: int) -> bool:
    """True when a drop of *image_count* images must be confirmed first."""
    try:
        count = int(image_count)
    except (TypeError, ValueError):
        return False
    if count <= LARGE_DROP_THRESHOLD:
        return False
    if not is_ai_domain(controller):
        return False
    return not is_suppressed()


def guard_large_drop(parent: QWidget | None, controller, image_count: int) -> bool:
    """Confirm a large AI-domain drop.

    Return ``True`` to proceed with the drop, ``False`` when the user cancels.
    A no-op (returns ``True``) when the guard does not apply.
    """
    if not should_warn(controller, image_count):
        return True
    count = int(image_count)
    title = _translate(controller, _TITLE_KEY, _TITLE_DEFAULT)
    body = _translate(controller, _BODY_KEY, _BODY_DEFAULT, count=count)
    confirm = _translate(controller, _CONFIRM_KEY, _CONFIRM_DEFAULT)
    confirm_dont_ask = _translate(
        controller, _CONFIRM_DONT_ASK_KEY, _CONFIRM_DONT_ASK_DEFAULT
    )
    cancel = _translate(controller, _CANCEL_KEY, _CANCEL_DEFAULT)
    code, dont_ask = AppMessageDialog.show_modal_ex(
        parent,
        MessageKind.WARNING,
        title,
        body,
        ok_text=confirm,
        dont_ask_text=confirm_dont_ask,
        cancel_text=cancel,
    )
    if int(code) != int(QDialog.DialogCode.Accepted):
        return False
    if dont_ask:
        set_suppressed(True)
    return True
