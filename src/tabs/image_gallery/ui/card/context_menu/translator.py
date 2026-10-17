"""Translator resolution + binding for the gallery card context menu.

Split out of ``ui/card/context_menu.py`` per the module→package split
(``plan-gallery-split-2026-10-17``); function names/bodies moved verbatim.
"""

from __future__ import annotations


def _t(translate, key: str, default: str) -> str:
    if translate is None:
        return default
    try:
        return translate(key, default)
    except Exception:
        try:
            return translate(key)  # type: ignore[call-arg]
        except Exception:
            return default


def _resolve_menu_translator(card, owner, translate):
    """Best translator for this menu WITHOUT a threaded ``translate=``.

    Priority: an explicit ``translate=``; the nearest subtree translator
    bound on *card* (the page's ``install_translator`` root, resolved via
    ``translator_for``); then the triage owner's ``_tr`` (the Quick Look strip
    path, whose anchor lives under the window-parented overlay, not the page).
    ``None`` when nothing is wired — the caller keeps the literal fallbacks.
    """
    if callable(translate):
        return translate
    try:
        from sli_ui_toolkit.i18n import translator_for, tr as _global_tr

        resolved = translator_for(card)
        if resolved is not _global_tr:
            return resolved
    except Exception:
        pass
    try:
        owner_tr = getattr(owner, "_tr", None)
        if callable(owner_tr):
            return owner_tr
    except Exception:
        pass
    return None


def _bind_menu_translator(menu, translate) -> None:
    """Drive the menu's declarative ``text_key`` rows through *translate*.

    The menu is a popup parented to the card/anchor but created AFTER the
    page's ``install_translator`` walk ran, so it is never auto-covered;
    resolve the translator here and bind it explicitly. No-op when *translate*
    is ``None``. Fail-open (fake/test menus lack the protocol).
    """
    if not callable(translate):
        return
    try:
        from sli_ui_toolkit.i18n import bind_translator

        bind_translator(menu, translate)
    except Exception:
        pass
