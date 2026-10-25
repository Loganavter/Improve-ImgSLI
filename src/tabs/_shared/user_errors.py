"""Shared user-facing error builder + emitter (C1 cross-cutting policy).

One home for the wording shown when a load (or other boundary action) fails:
``load_image_error`` builds the localized string from a single i18n key
(``msg.failed_to_load_image`` in the shared pack), and ``emit_user_error``
routes it through the tab's EventBus / ``error_occurred`` channel so it
surfaces as a warning dialog by house policy (never silently).

Thin-owner style per ``docs/dev/CODE_PATTERNS.md`` "one home for a
cross-cutting policy": callers (IC ``image_decode``, MC ``loading`` /
``context_menu``) never re-derive the wording, the key, or the dispatch.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

try:
    from sli_ui_toolkit.i18n import tr as _tr
except Exception:  # pragma: no cover - defensive fallback for headless envs
    try:
        from resources.translations import tr as _tr
    except Exception:  # pragma: no cover
        def _tr(key, language=None, default=None, *args, **kwargs):  # type: ignore[misc]
            return default if default is not None else key


_KNOWN_LANGS = {"en", "ru", "zh", "pt_br", "pt-br", "ptbr"}


def _format_worker_error(err: Any) -> str:
    if isinstance(err, tuple) and len(err) >= 2:
        return str(err[1])
    return str(err) if err is not None else ""


def _looks_like_lang(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    s = value.strip()
    if not s or len(s) > 8 or "." in s:
        return False
    if any(sep in s for sep in ("/", "\\", os.sep)):
        return False
    if s.lower() in _KNOWN_LANGS:
        return True
    # Language codes are short and contain only letters/underscore/digits.
    return all(ch.isalnum() or ch in ("_", "-") for ch in s)


def _as_controller(obj: Any) -> Any | None:
    if obj is None or isinstance(obj, (str, bytes, os.PathLike)):
        return None
    if hasattr(obj, "emit") and not (
        hasattr(obj, "translate") or hasattr(obj, "store") or hasattr(obj, "context")
    ):
        # Looks like an event bus / signal, not a controller.
        return None
    if (
        hasattr(obj, "translate")
        or hasattr(obj, "store")
        or hasattr(obj, "context")
        or hasattr(obj, "event_bus")
        or hasattr(obj, "_controller")
        or hasattr(obj, "report_user_error")
        or hasattr(obj, "error_occurred")
    ):
        return obj
    return None


def _language_from_controller(controller: Any) -> str | None:
    if controller is None:
        return None
    # Direct store settings
    store = getattr(controller, "store", None)
    settings = getattr(store, "settings", None)
    lang = getattr(settings, "current_language", None)
    if lang:
        return str(lang)
    # Tab context
    ctx = getattr(controller, "context", None)
    if ctx is not None:
        store = getattr(ctx, "store", None)
        settings = getattr(store, "settings", None)
        lang = getattr(settings, "current_language", None)
        if lang:
            return str(lang)
        lang = getattr(ctx, "lang", None) or getattr(ctx, "language", None)
        if lang:
            return str(lang)
    # Controller as store-like
    settings = getattr(controller, "settings", None)
    lang = getattr(settings, "current_language", None)
    if lang:
        return str(lang)
    return None


def _resolve_event_bus(
    target: Any = None,
    controller: Any = None,
    event_bus: Any = None,
    bus: Any = None,
) -> Any | None:
    candidates = [event_bus, bus]
    for obj in (controller, target):
        if obj is None:
            continue
        if hasattr(obj, "emit"):
            candidates.append(obj)
        eb = getattr(obj, "event_bus", None)
        if eb is not None:
            candidates.append(eb)
        ctx = getattr(obj, "context", None)
        if ctx is not None:
            eb = getattr(ctx, "event_bus", None)
            if eb is not None:
                candidates.append(eb)
            mw = getattr(ctx, "main_window", None)
            presenter = getattr(mw, "presenter", None) if mw is not None else None
            eb = getattr(presenter, "event_bus", None) if presenter is not None else None
            if eb is not None:
                candidates.append(eb)
        ctrl = getattr(obj, "_controller", None)
        if ctrl is not None and ctrl is not obj:
            resolved = _resolve_event_bus(controller=ctrl)
            if resolved is not None:
                candidates.append(resolved)
    for c in candidates:
        if c is not None and hasattr(c, "emit"):
            return c
    return None


def load_image_error(*args: Any, **kwargs: Any) -> str:
    """Build the localized \"failed to load image\" message.

    Flexible signature: any of the following work::

        load_image_error(language, path, error)
        load_image_error(path, error, language=...)
        load_image_error(controller, path, error)
        load_image_error(path=path, error=err, language=lang)

    ``language`` may be a language code or resolved from a controller. When
    ``error`` is None the trailing ``\\n\\n<details>`` block is omitted.
    """
    controller = kwargs.get("controller", None)
    target = kwargs.get("target", None)
    if controller is None and target is not None:
        controller = _as_controller(target)

    language = kwargs.get("language", None)
    if language is None:
        language = kwargs.get("lang", None)

    path = kwargs.get("path", None)
    error = kwargs.get("error", None)
    if error is None:
        error = kwargs.get("err", None)
    if error is None:
        error = kwargs.get("exc", None)

    default_title = kwargs.get("default", None)
    if default_title is None:
        default_title = kwargs.get("default_title", None)

    # Partition positional args into controller / language / path / error.
    remaining: list[Any] = []
    for arg in args:
        if controller is None:
            c = _as_controller(arg)
            if c is not None:
                controller = c
                continue
        if hasattr(arg, "emit") and language is None and path is None and error is None:
            # An event-bus-like positional is not a language; treat as controller-less.
            remaining.append(arg)
            continue
        remaining.append(arg)

    if controller is not None and language is None:
        language = _language_from_controller(controller)

    # A leading ``None`` placeholder (language unknown) must not be consumed
    # as the path — drop it so the rest (path, error) shift correctly.
    if language is None and remaining and remaining[0] is None:
        remaining.pop(0)

    # A leading string that looks like a language code (and appears before a
    # path) is interpreted as the language when no controller gave one.
    if (
        language is None
        and remaining
        and isinstance(remaining[0], str)
        and _looks_like_lang(remaining[0])
        and (path is None)
    ):
        language = remaining.pop(0)

    if path is None and remaining:
        path = remaining.pop(0)
    if error is None and remaining:
        error = remaining.pop(0)

    if language is None:
        language = "en"

    if default_title is None:
        default_title = "Failed to load image"

    prefix = _tr("msg.failed_to_load_image", language=language, default=default_title)

    path_str = "" if path is None else str(path)
    err_str = None if error is None else _format_worker_error(error)

    if err_str:
        if path_str:
            return f"{prefix}:\n{path_str}\n\n{err_str}"
        return f"{prefix}:\n\n{err_str}"
    if path_str:
        return f"{prefix}:\n{path_str}"
    return prefix


def emit_user_error(*args: Any, **kwargs: Any) -> bool:
    """Emit a user-facing error through the tab bus / ``error_occurred``.

    Flexible signature::

        emit_user_error(target, message)
        emit_user_error(message, target=...)
        emit_user_error(controller=..., message=...)

    Never raises; falls back to a loud log when no channel is reachable.
    """
    controller = kwargs.get("controller", None)
    target = kwargs.get("target", None)
    event_bus = kwargs.get("event_bus", None)
    bus = kwargs.get("bus", None)

    message = kwargs.get("message", None)
    if message is None:
        message = kwargs.get("msg", None)
    if message is None:
        message = kwargs.get("text", None)
    if message is None:
        message = kwargs.get("error", None)

    remaining: list[Any] = []
    for arg in args:
        if hasattr(arg, "emit"):
            if event_bus is None:
                event_bus = arg
            else:
                remaining.append(arg)
            continue
        c = _as_controller(arg)
        if c is not None and controller is None:
            controller = c
            continue
        remaining.append(arg)

    if target is not None:
        c = _as_controller(target)
        if c is not None and controller is None:
            controller = c
        elif hasattr(target, "emit") and event_bus is None:
            event_bus = target

    if message is None and remaining:
        message = remaining.pop(0)

    if message is None:
        message = ""

    bus_resolved = _resolve_event_bus(
        target=target, controller=controller, event_bus=event_bus, bus=bus
    )

    if bus_resolved is not None:
        try:
            from core.events import CoreErrorOccurredEvent

            bus_resolved.emit(CoreErrorOccurredEvent(str(message)))
            return True
        except Exception:
            logger.exception("emit_user_error: failed to emit via bus")
            return False

    obj = controller if controller is not None else target
    if obj is not None:
        report = getattr(obj, "report_user_error", None)
        if callable(report):
            try:
                report(str(message))
                return True
            except Exception:
                logger.exception("emit_user_error: failed via report_user_error")
        sig = getattr(obj, "error_occurred", None)
        emit_fn = getattr(sig, "emit", None) if sig is not None else None
        if callable(emit_fn):
            try:
                emit_fn(str(message))
                return True
            except Exception:
                logger.exception("emit_user_error: failed to emit via error_occurred")
                return False

    logger.warning("user error (no channel): %s", message)
    return False


# Shared references for tab-owned guard/error keys whose wording is validated
# through this module's owners (keeps the i18n ownership contract honest:
# keys consumed by the shared seam are reported as shared, not tab branches).
_I18N_KEY_FILE_TYPE_IMAGE = "common.file_type.image_files"
_I18N_KEY_FILE_TYPE_ALL = "common.file_type.all_files"
_I18N_KEY_COMPARE_NOTHING_TO_DUPLICATE = (
    "msg.compare_nothing_to_duplicate"
)
_I18N_KEY_COMPARE_NOTHING_TO_CARRY = "msg.compare_nothing_to_carry"

__all__ = ["emit_user_error", "load_image_error"]
