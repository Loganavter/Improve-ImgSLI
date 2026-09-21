"""Shared helpers for Find Action palette UI (not a re-export façade)."""

from __future__ import annotations

from resources.translations import get_current_language, tr


def language() -> str:
    try:
        return get_current_language() or "en"
    except Exception:
        return "en"


def tr_action(key: str, fallback: str) -> str:
    translated = tr(key, language())
    if translated != key:
        return translated
    # No translation: humanize instead of leaking a raw dotted key.
    return _humanize_key(fallback or key)


def _humanize_key(key: str) -> str:
    tail = (key or "").rsplit(".", 1)[-1].replace("_", " ").strip()
    return tail.title() if tail else (key or "")


# Explicit keyboard-override store. The binder publishes the authoritative
# ``action_id → shortcut`` map here on every resync; palette rows and menus
# read it without walking top-level widgets. The walk survives only as a
# fail-open fallback for surfaces that render before the first resync.
_EXPLICIT_OVERRIDES: dict[str, str] | None = None


def set_keyboard_overrides(overrides: dict[str, str] | None) -> None:
    """Publish the authoritative override map (binder resync does this)."""
    global _EXPLICIT_OVERRIDES
    _EXPLICIT_OVERRIDES = dict(overrides) if overrides is not None else None


def clear_keyboard_overrides_for_tests() -> None:
    """Drop the published map — tests only."""
    global _EXPLICIT_OVERRIDES
    _EXPLICIT_OVERRIDES = None


def current_keyboard_overrides() -> dict[str, str]:
    """Live ``action_id -> shortcut`` overrides from the active session store.

    Reads the explicit store published by the binder resync; falls back to a
    top-level widget walk only when nothing was published yet (fail-open for
    surfaces that render before the first resync).

    Walks top-level widgets once; callers building many rows (Find Action's
    list) should call this once per rebuild and pass the result down, not
    once per row.
    """
    if _EXPLICIT_OVERRIDES is not None:
        return dict(_EXPLICIT_OVERRIDES)
    try:
        from PySide6.QtWidgets import QApplication

        for widget in QApplication.topLevelWidgets():  # ALLOWED: system-wide keyboard-overrides lookup — walks top-levels generically for store.settings, not tab-specific
            presenter = getattr(widget, "presenter", None)
            store = getattr(presenter, "store", None) if presenter is not None else None
            settings = getattr(store, "settings", None) if store is not None else None
            overrides = getattr(settings, "keyboard_overrides", None)
            if isinstance(overrides, dict):
                return dict(overrides)
    except Exception:
        pass
    return {}


def target_is_revealable(target: object | None) -> bool:
    if target is None:
        return False
    if getattr(target, "widget", None) is not None:
        return True
    if callable(getattr(target, "resolve_widget", None)):
        return True
    if callable(getattr(target, "ensure_visible", None)):
        return True
    return bool(getattr(target, "menu_action_id", None))