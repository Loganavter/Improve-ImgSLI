"""Ask AI surface wiring for the gallery widget (plan Part B, Wave 4).

Bodies extracted from ``ImageGalleryWidget`` per ``CODE_PATTERNS.md``
(thin owner + functions-taking-owner); the class keeps same-named one-line
delegators so call sites and tests do not move. Fail-open like the
surrounding widget chrome.

One surface, two hosts: ``_ensure_ask_surface`` owns the single
``AskAiSurface`` instance; the flyout and the tab-level sidebar both embed it
(never a second copy, never a second flyout). The Q/A history comes from
``services.ask_log.recent`` — selecting a row re-displays the stored answer with
no backend call.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("ImproveImgSLI")

#: Localised chrome defaults for the ask surface (English; the controller
#: overrides them with the tab translator on the flyout path).
ASK_TEXT_DEFAULTS = {
    "title": "Ask AI",
    "busy": "Thinking…",
    "read_badge": "AI read, unverified",
    "error": "AI could not answer.",
    "images_hint": "Send images with the question",
    "cached": " · cached",
    "history": "{n} previous questions",
    "history_title": "History",
    "history_empty": "No questions yet.",
}


def _ensure_ask_surface(owner):
    """The single ask surface instance shared by both hosts."""
    surface = getattr(owner, "_ask_ai_surface", None)
    if surface is None:
        from tabs.image_gallery.ui.ask_surface import AskAiSurface

        surface = AskAiSurface(owner)
        try:
            surface.setObjectName("gallery_ask_ai_surface")
        except Exception:
            pass
        try:
            surface.imageActivated.connect(owner._on_ask_ai_image_activated)
        except Exception:
            pass
        # One submit route for both hosts: the scope is whatever the last open
        # set (the sidebar keeps a selection scope; a card/series open replaces
        # it). Resolving the scope's paths at submit time is ask_context's job,
        # so an empty-paths selection scope always follows the live selection.
        try:
            surface.submitted.connect(
                lambda question, _owner=owner: _submit_ask_ai(
                    _owner, getattr(_owner, "_ask_ai_scope", None), question
                )
            )
        except Exception:
            pass
        owner._ask_ai_surface = surface
    return surface


def _ensure_ask_ai_flyout(owner):
    flyout = getattr(owner, "_ask_ai_flyout", None)
    if flyout is None:
        from tabs.image_gallery.ui.ask_ai import AskAiFlyout

        flyout = AskAiFlyout(owner)
        try:
            flyout.setObjectName("gallery_ask_ai_flyout")
        except Exception:
            pass
        # An answer's image link opens Quick Look for that image.
        try:
            flyout.imageActivated.connect(owner._on_ask_ai_image_activated)
        except Exception:
            pass
        owner._ask_ai_flyout = flyout
    # Always host the shared surface (a sidebar may have taken it).
    try:
        flyout.attach_surface(_ensure_ask_surface(owner))
    except Exception:
        pass
    return flyout


def _on_ask_ai_image_activated(owner, path: str) -> None:
    """Open Quick Look for an image named in the Ask AI answer.

    The flyout closes first: leaving it open over Quick Look strands
    its (link-clicked) text caret on screen.
    """
    try:
        flyout = getattr(owner, "_ask_ai_flyout", None)
        if flyout is not None and flyout.isVisible():
            flyout.hide()
    except Exception:
        pass
    try:
        owner.show_quick_look(str(path))
    except Exception:
        logger.debug("ask-ai image activation failed", exc_info=True)


def _ask_history_count(owner) -> int:
    """How many earlier asks the disk log holds for the open scope (0 on fail)."""
    try:
        from tabs.image_gallery.services import ask_log

        scope = getattr(owner, "_ask_ai_scope", None)
        paths = tuple(getattr(scope, "paths", ()) or ())
        return int(ask_log.count(scope_paths=paths or None))
    except Exception:
        return 0


def _ask_history(owner) -> list:
    """The stored exchanges for the open scope, newest first (``[]`` on fail)."""
    try:
        from tabs.image_gallery.services import ask_log
        from tabs.image_gallery.ui.ask_surface import HISTORY_LIMIT

        scope = getattr(owner, "_ask_ai_scope", None)
        paths = tuple(getattr(scope, "paths", ()) or ())
        return list(
            ask_log.recent(scope_paths=paths or None, limit=HISTORY_LIMIT)
        )
    except Exception:
        return []


def default_texts(owner) -> dict:
    """Localised chrome for a host that opens without the controller's texts."""
    tr = getattr(owner, "_tr_ui", None)
    out = dict(ASK_TEXT_DEFAULTS)
    if not callable(tr):
        return out
    try:
        out["title"] = tr("image_gallery.ask_ai.title", out["title"])
        out["busy"] = tr("image_gallery.ask_ai.busy", out["busy"])
        out["read_badge"] = tr(
            "image_gallery.ask_ai.read_badge", out["read_badge"]
        )
        out["error"] = tr("image_gallery.ask_ai.error", out["error"])
        out["images_hint"] = tr(
            "image_gallery.ask_ai.images_toggle_hint", out["images_hint"]
        )
        out["cached"] = tr("image_gallery.ask_ai.cached", out["cached"])
        out["history"] = tr(
            "image_gallery.ask_ai.history_count", out["history"]
        )
        out["history_title"] = tr(
            "image_gallery.ask_ai.history_title", out["history_title"]
        )
        out["history_empty"] = tr(
            "image_gallery.ask_ai.history_empty", out["history_empty"]
        )
    except Exception:
        return dict(ASK_TEXT_DEFAULTS)
    return out


def default_scope():
    """Selection scope resolved against the live selection at ask time."""
    from tabs.image_gallery.services.ask_context import AskScope

    return AskScope(kind="selection", paths=(), label="")


def open_ask_ai(
    owner,
    anchor,
    scope,
    *,
    default_prompt: str = "What matters here?",
    texts=None,
    grow_up: bool = False,
    show_images_toggle: bool = True,
) -> None:
    """Show the Ask AI surface; submit routes to ``controller.ask_ai_question``."""
    surface = _ensure_ask_surface(owner)
    if texts:
        try:
            surface.set_texts(**texts)
        except Exception:
            pass
    scope_key = owner._ask_scope_key(scope)

    # A visible sidebar hosts the surface: today's ask simply retargets it
    # instead of opening a popup over the docked panel.
    sidebar = getattr(owner, "_ask_ai_sidebar", None)
    if sidebar is not None and sidebar.isVisible():
        owner._ask_ai_scope = scope
        owner._ask_ai_scope_key = scope_key
        try:
            label = getattr(scope, "label", "") or ""
        except Exception:
            label = ""
        surface.prepare_scope(
            scope_label=label,
            default_prompt=default_prompt,
            show_images_toggle=show_images_toggle,
            history_count=_ask_history_count(owner),
            history_records=_ask_history(owner),
        )
        sidebar.focus_question()
        return

    flyout = _ensure_ask_ai_flyout(owner)
    # Re-invoking on the SAME scope toggles closed instead of re-running
    # the show animation (a second right-click looked like "reopening").
    try:
        if flyout.isVisible() and getattr(owner, "_ask_ai_scope_key", None) == scope_key:
            flyout.hide()
            return
    except Exception:
        pass
    try:
        label = getattr(scope, "label", "") or ""
    except Exception:
        label = ""
    owner._ask_ai_anchor = anchor or owner
    owner._ask_ai_scope = scope
    owner._ask_ai_scope_key = scope_key
    # Preserve the last answer across hide/reopen, seeding it BEFORE the
    # show animation (seeding after the show calls reposition() mid-fade,
    # which flashes the panel white).
    initial_result = None
    initial_error = ""
    initial_links: dict = {}
    if getattr(owner, "_ask_ai_last_key", None) == getattr(
        owner, "_ask_ai_scope_key", None
    ):
        if getattr(owner, "_ask_ai_last_result", None) is not None:
            initial_result = owner._ask_ai_last_result
            initial_links = dict(getattr(owner, "_ask_ai_last_links", None) or {})
        elif getattr(owner, "_ask_ai_last_error", None):
            initial_error = owner._ask_ai_last_error
    flyout.open_for(
        owner._ask_ai_anchor,
        scope_label=label,
        default_prompt=default_prompt,
        initial_result=initial_result,
        initial_error=initial_error,
        initial_links=initial_links,
        grow_up=grow_up,
        show_images_toggle=show_images_toggle,
        history_count=_ask_history_count(owner),
        history_records=_ask_history(owner),
    )


def _ask_scope_key(owner, scope):
    """Stable identity for one ask scope (used to restore the last answer)."""
    try:
        paths = tuple(sorted(str(p) for p in (getattr(scope, "paths", ()) or ())))
        return (
            str(getattr(scope, "kind", "")),
            paths,
            str(getattr(scope, "series_id", "") or ""),
            str(getattr(scope, "label", "") or ""),
            tuple(getattr(scope, "box", ()) or ()),
        )
    except Exception:
        return None


def _submit_ask_ai(owner, scope, question: str) -> None:
    if scope is None:
        scope = default_scope()
    flyout = getattr(owner, "_ask_ai_flyout", None)
    surface = getattr(owner, "_ask_ai_surface", None)
    context = surface if surface is not None else flyout
    _triage_owner = owner._owner_for_triage()
    fn = getattr(_triage_owner, "ask_ai_question", None)
    if callable(fn):
        include = False
        try:
            inc = getattr(context, "include_images", None)
            if callable(inc):
                include = bool(inc())
        except Exception:
            include = False
        try:
            fn(scope, question, include_images=include)
        except TypeError:
            fn(scope, question)
        return
    owner.show_ask_ai_error("AI is unavailable.")


def show_ask_ai_busy(owner) -> None:
    try:
        _ensure_ask_surface(owner).set_busy(True)
    except Exception:
        pass


def show_ask_ai_result(owner, result, model: str = "", links: dict | None = None) -> None:
    try:
        surface = _ensure_ask_surface(owner)
        flyout = getattr(owner, "_ask_ai_flyout", None)
        surface.set_busy(False)
        surface.show_result(
            getattr(result, "text", "") or "",
            model=model,
            backend=getattr(result, "backend", "") or "",
            cached=bool(getattr(result, "cached", False)),
            links=links,
        )
        owner._ask_ai_last_key = getattr(owner, "_ask_ai_scope_key", None)
        owner._ask_ai_last_result = result
        owner._ask_ai_last_links = dict(links or {})
        owner._ask_ai_last_error = None
        # The completion path appended this answer to the disk log; show the
        # new count + exchange, parking the list cursor on the newest row while
        # the pane keeps the live answer (with its image links).
        surface.set_history_count(_ask_history_count(owner))
        surface.set_history_records(_ask_history(owner), highlight_tail=True)
        _resume_ask_ai_if_hidden(owner, flyout)
    except Exception:
        pass


def show_ask_ai_error(owner, message: str) -> None:
    try:
        surface = _ensure_ask_surface(owner)
        flyout = getattr(owner, "_ask_ai_flyout", None)
        surface.set_busy(False)
        surface.show_error(message)
        owner._ask_ai_last_key = getattr(owner, "_ask_ai_scope_key", None)
        owner._ask_ai_last_result = None
        owner._ask_ai_last_links = {}
        owner._ask_ai_last_error = message
        _resume_ask_ai_if_hidden(owner, flyout)
    except Exception:
        pass


def _resume_ask_ai_if_hidden(owner, flyout) -> None:
    """A late answer must not vanish: re-show the host if it was dismissed.

    The sidebar is always visible while it hosts the surface (no re-show
    needed); only the flyout is subject to dismissal.
    """
    try:
        sidebar = getattr(owner, "_ask_ai_sidebar", None)
        if sidebar is not None and sidebar.isVisible():
            return
        if flyout is None or flyout.isVisible():
            return
        anchor = getattr(owner, "_ask_ai_anchor", None)
        if anchor is not None:
            flyout.reshow(anchor)
    except Exception:
        pass
