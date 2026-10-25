"""Show/hide wiring for the tab-level Ask AI sidebar.

The gallery toolbar's AI toggle owns the user action; this module owns the
state transition: take/hand the shared surface, localize the chrome, keep the
toolbar button (and its Show/Hide tooltip) in sync, and re-read the Q/A history
from ``services.ask_log`` when the panel opens.

Kept out of the thin widget owner like the other ``ui/widget_parts/`` modules
(``CODE_PATTERNS.md``); fail-open throughout.
"""

from __future__ import annotations

import logging
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def _ensure_sidebar(owner):
    sidebar = getattr(owner, "_ask_ai_sidebar", None)
    if sidebar is None:
        from tabs.image_gallery.ui.ask_sidebar import AskAiSidebar

        sidebar = AskAiSidebar(owner)
        try:
            sidebar.closed.connect(lambda _o=owner: set_visible(_o, False))
        except Exception:
            pass
        owner._ask_ai_sidebar = sidebar
        row = getattr(owner, "_content_row", None)
        if row is not None:
            try:
                row.addWidget(sidebar)
            except Exception:
                pass
    return sidebar


def _texts(owner) -> dict:
    """Localized chrome for the sidebar host (tab translator, English fallback)."""
    from tabs.image_gallery.ui.widget_parts import ask_ai_surface

    texts = ask_ai_surface.default_texts(owner)
    tr = getattr(owner, "_tr_ui", None)
    if callable(tr):
        try:
            texts["sidebar_show"] = tr(
                "image_gallery.ask_ai.sidebar_show", "Show AI sidebar"
            )
            texts["sidebar_hide"] = tr(
                "image_gallery.ask_ai.sidebar_hide", "Hide AI sidebar"
            )
        except Exception:
            pass
    texts.setdefault("sidebar_show", "Show AI sidebar")
    texts.setdefault("sidebar_hide", "Hide AI sidebar")
    return texts


def _sync_toggle(owner, visible: bool, texts: dict) -> None:
    toolbar = getattr(owner, "toolbar", None)
    if toolbar is None:
        return
    try:
        setter = getattr(toolbar, "set_ask_sidebar_texts", None)
        if callable(setter):
            setter(texts["sidebar_show"], texts["sidebar_hide"])
    except Exception:
        pass
    try:
        checked = getattr(toolbar, "set_ask_sidebar_checked", None)
        if callable(checked):
            checked(bool(visible))
    except Exception:
        pass


def set_visible(owner, visible: bool) -> None:
    """Show or hide the Ask AI sidebar; the shared surface moves with it."""
    if getattr(owner, "_ask_sidebar_setting", False):
        return
    owner._ask_sidebar_setting = True
    try:
        sidebar = _ensure_sidebar(owner)
        texts = _texts(owner)
        if visible:
            from tabs.image_gallery.ui.widget_parts import ask_ai_surface

            # A popup over the docked panel would compete for the same surface.
            flyout = getattr(owner, "_ask_ai_flyout", None)
            if flyout is not None and flyout.isVisible():
                try:
                    flyout.hide()
                except Exception:
                    pass
            surface = ask_ai_surface._ensure_ask_surface(owner)
            # The docked panel starts on the live selection; a card/series ask
            # opened while it is visible retargets this scope until it is
            # reopened here.
            scope = ask_ai_surface.default_scope()
            owner._ask_ai_scope = scope
            owner._ask_ai_scope_key = ask_ai_surface._ask_scope_key(owner, scope)
            surface_texts = {
                key: value
                for key, value in texts.items()
                if key
                in (
                    "title",
                    "busy",
                    "read_badge",
                    "error",
                    "images_hint",
                    "cached",
                    "history",
                    "history_title",
                    "history_empty",
                )
            }
            try:
                surface.set_texts(**surface_texts)
            except Exception:
                pass
            sidebar.set_texts(title=texts["title"], close=texts["sidebar_hide"])
            sidebar.attach_surface(surface)
            records = ask_ai_surface._ask_history(owner)
            try:
                surface.set_history_records(
                    records, show_tail=not surface.has_answer()
                )
            except Exception:
                pass
            sidebar.show()
            sidebar.focus_question()
        else:
            sidebar.hide()
        _sync_toggle(owner, bool(visible), texts)
    except Exception:
        logger.debug("ask-ai sidebar toggle failed", exc_info=True)
    finally:
        owner._ask_sidebar_setting = False


def toggle(owner) -> None:
    """Flip the sidebar's visibility (toolbar toggle path)."""
    sidebar = _ensure_sidebar(owner)
    set_visible(owner, not sidebar.isVisible())


def retranslate(owner) -> None:
    """Re-apply localized chrome after a live language switch."""
    sidebar = getattr(owner, "_ask_ai_sidebar", None)
    if sidebar is None:
        return
    texts = _texts(owner)
    try:
        sidebar.set_texts(title=texts["title"], close=texts["sidebar_hide"])
    except Exception:
        pass
    surface = getattr(owner, "_ask_ai_surface", None)
    if surface is not None:
        try:
            surface.set_texts(
                title=texts["title"],
                busy=texts["busy"],
                read_badge=texts["read_badge"],
                error=texts["error"],
                history=texts["history"],
                history_title=texts["history_title"],
                history_empty=texts["history_empty"],
            )
        except Exception:
            pass
    _sync_toggle(owner, bool(getattr(sidebar, "isVisible", lambda: False)()), texts)
