"""Ask AI flyout surface for the gallery widget (plan Part B, Wave 4).

Bodies extracted from ``ImageGalleryWidget`` per ``CODE_PATTERNS.md``
(thin owner + functions-taking-owner); the class keeps same-named one-line
delegators so call sites and tests do not move. Fail-open like the
surrounding widget chrome.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("ImproveImgSLI")


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
    """How many earlier asks the disk log holds for the open scope (0 on fail).

    Backs the flyout's "N previous questions" line. Count only — reading the
    labels/list is deliberately out of scope here (later task).
    """
    try:
        from tabs.image_gallery.services import ask_log

        scope = getattr(owner, "_ask_ai_scope", None)
        paths = tuple(getattr(scope, "paths", ()) or ())
        return int(ask_log.count(scope_paths=paths or None))
    except Exception:
        return 0


def open_ask_ai(
    owner, anchor, scope, *, default_prompt: str = "What matters here?", texts=None, grow_up: bool = False, show_images_toggle: bool = True
) -> None:
    """Show the Ask AI flyout; submit routes to ``controller.ask_ai_question``."""
    flyout = owner._ensure_ask_ai_flyout()
    if texts:
        try:
            flyout.set_texts(**texts)
        except Exception:
            pass
    # Re-invoking on the SAME scope toggles closed instead of re-running
    # the show animation (a second right-click looked like "reopening").
    scope_key = owner._ask_scope_key(scope)
    try:
        if flyout.isVisible() and getattr(owner, "_ask_ai_scope_key", None) == scope_key:
            flyout.hide()
            return
    except Exception:
        pass
    # One live scope per open: drop the previous submit binding (disconnect
    # the exact slot; a bare disconnect() warns when nothing is bound).
    bound = getattr(owner, "_ask_ai_submit_slot", None)
    if bound is not None:
        try:
            flyout.submitted.disconnect(bound)
        except Exception:
            pass
    slot = lambda question, _s=scope: owner._submit_ask_ai(_s, question)  # noqa: E731
    owner._ask_ai_submit_slot = slot
    flyout.submitted.connect(slot)
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
    _triage_owner = owner._owner_for_triage()
    fn = getattr(_triage_owner, "ask_ai_question", None)
    if callable(fn):
        include = False
        try:
            flyout = getattr(owner, "_ask_ai_flyout", None)
            inc = getattr(flyout, "include_images", None)
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
        owner._ensure_ask_ai_flyout().set_busy(True)
    except Exception:
        pass


def show_ask_ai_result(owner, result, model: str = "", links: dict | None = None) -> None:
    try:
        flyout = owner._ensure_ask_ai_flyout()
        flyout.set_busy(False)
        flyout.show_result(
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
        # new count so the persisted history is observable in the app.
        flyout.set_history_count(_ask_history_count(owner))
        owner._resume_ask_ai_if_hidden(flyout)
    except Exception:
        pass


def show_ask_ai_error(owner, message: str) -> None:
    try:
        flyout = owner._ensure_ask_ai_flyout()
        flyout.set_busy(False)
        flyout.show_error(message)
        owner._ask_ai_last_key = getattr(owner, "_ask_ai_scope_key", None)
        owner._ask_ai_last_result = None
        owner._ask_ai_last_links = {}
        owner._ask_ai_last_error = message
        owner._resume_ask_ai_if_hidden(flyout)
    except Exception:
        pass


def _resume_ask_ai_if_hidden(owner, flyout) -> None:
    """A late answer must not vanish: re-show the flyout if it was dismissed."""
    try:
        if flyout.isVisible():
            return
        anchor = getattr(owner, "_ask_ai_anchor", None)
        if anchor is not None:
            flyout.reshow(anchor)
    except Exception:
        pass
