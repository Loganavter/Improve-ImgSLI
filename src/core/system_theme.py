"""Resolve the ``theme`` setting to a concrete light/dark theme.

The persisted setting may be ``"auto"``, meaning "follow the OS". This module
turns that into ``"light"``/``"dark"`` without ever rewriting the setting, and
it works inside the Flatpak sandbox:

1. XDG desktop portal over D-Bus (``org.freedesktop.portal.Settings`` ->
   ``org.freedesktop.appearance`` ``color-scheme``) — the only signal visible
   inside Flatpak, where ``~/.config/kdeglobals`` is not mounted.
2. Qt's ``QStyleHints.colorScheme()`` (Qt 6.5+).
3. ``"light"`` when nothing reports a preference.

Every probe is best-effort: a missing D-Bus, portal or Qt API must never break
startup.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("ImproveImgSLI")

VALID_THEMES = ("light", "dark")
AUTO_THEME = "auto"

_PORTAL_BUS = "org.freedesktop.portal.Desktop"
_PORTAL_PATH = "/org/freedesktop/portal/desktop"
_PORTAL_IFACE = "org.freedesktop.portal.Settings"
_PORTAL_APPEARANCE = "org.freedesktop.appearance"
_PORTAL_COLOR_SCHEME = "color-scheme"
_PORTAL_TIMEOUT_MS = 1500

def normalize_theme(value: object) -> str | None:
    """Return ``"light"``/``"dark"`` for a concrete value, else ``None``."""
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    return candidate if candidate in VALID_THEMES else None

def _portal_color_scheme() -> str | None:
    """Read the freedesktop color-scheme preference, or ``None``."""
    try:
        from PySide6.QtCore import QDBusMessage, QVariant
        from PySide6.QtDBus import QDBusConnection, QDBusInterface
    except Exception:
        return None

    try:
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return None
        interface = QDBusInterface(_PORTAL_BUS, _PORTAL_PATH, _PORTAL_IFACE, bus)
        if not interface.isValid():
            return None
        set_timeout = getattr(interface, "setTimeout", None)
        if callable(set_timeout):
            set_timeout(_PORTAL_TIMEOUT_MS)
        reply = interface.call("Read", _PORTAL_APPEARANCE, _PORTAL_COLOR_SCHEME)
        if reply is None or reply.type() == QDBusMessage.MessageType.ErrorMessage:
            return None
        arguments = reply.arguments()
        if not arguments:
            return None
        value: object = arguments[0]
        for _ in range(3):
            if isinstance(value, QVariant):
                value = value.value()
            elif hasattr(value, "variant"):
                value = value.variant()
            else:
                break
        scheme = int(value)
    except Exception:
        logger.debug("XDG portal color-scheme probe failed", exc_info=True)
        return None

    if scheme == 1:
        return "dark"
    if scheme == 2:
        return "light"
    return None

def _style_hints_color_scheme() -> str | None:
    """Read Qt's platform color scheme, or ``None`` when unavailable."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
    except Exception:
        return None

    try:
        application = QGuiApplication.instance()
        if application is None:
            return None
        color_scheme = getattr(application.styleHints(), "colorScheme", None)
        if color_scheme is None:
            return None
        value = color_scheme() if callable(color_scheme) else color_scheme
        enum = getattr(Qt, "ColorScheme", None)
        if enum is None:
            return None
        dark = getattr(enum, "Dark", None)
        light = getattr(enum, "Light", None)
        if dark is not None and value == dark:
            return "dark"
        if light is not None and value == light:
            return "light"
    except Exception:
        logger.debug("QStyleHints color-scheme probe failed", exc_info=True)
        return None

    return None

def detect_system_theme() -> str:
    """Best-effort OS color-scheme detection; always returns a concrete theme."""
    for probe in (_portal_color_scheme, _style_hints_color_scheme):
        try:
            detected = probe()
        except Exception:
            logger.debug("system theme probe %s failed", probe.__name__, exc_info=True)
            continue
        if detected in VALID_THEMES:
            return detected
    return "light"

def resolve_theme(requested: object) -> str:
    """Map a setting value to a concrete ``"light"``/``"dark"`` theme.

    Explicit ``"light"``/``"dark"`` pass through unchanged; ``"auto"`` and
    unknown values follow the OS (falling back to ``"light"``).
    """
    explicit = normalize_theme(requested)
    if explicit is not None:
        return explicit
    return detect_system_theme()
