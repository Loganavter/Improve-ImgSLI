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
    return fallback if translated == key else translated


def current_keyboard_overrides() -> dict[str, str]:
    """Live ``action_id -> shortcut`` overrides from the active session store.

    Walks top-level widgets once; callers building many rows (Find Action's
    list) should call this once per rebuild and pass the result down, not
    once per row.
    """
    try:
        from PySide6.QtWidgets import QApplication

        for widget in QApplication.topLevelWidgets():
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
