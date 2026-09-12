"""Background-tab gate — stack visibility + stale-flush.

Split from ``background_parts/render_flow.py`` per
``docs/dev/CODE_PATTERNS.md`` thin owner + ``use_cases/`` and
``docs/dev/FILE_SIZE_POLICY.md`` (500L). The gate detects whether the
IC page that owns *presenter* is the current stack page via
``stack.currentWidget() is not page`` (see ``docs/dev/tabs/isolation.md``),
falls back to ``widget.isVisible()`` when the stack is not yet available
(early startup / tests), and defers work by marking ``_render_stale``.
All functions take ``presenter`` as first argument (CODE_PATTERNS).

``render_flow.py`` keeps thin delegators that forward to these bodies so
existing imports (``widget.py``, ``coordinators.py``, tests) keep working.
"""

from __future__ import annotations


def is_background_tab(presenter) -> bool:
    """True when the IC page that owns *presenter* is not the current stack page.

    Mirrors ``tabs/use_cases/appearance.py``'s ``stack.currentWidget() is not page``
    check so hidden tabs are detected via the registry/stack contract, not via
    an implied ``isVisible`` lookup (see ``docs/dev/tabs/isolation.md``).
    Falls back to ``widget.isVisible()`` when the stack is not yet available
    (early startup / tests).
    """
    widget = getattr(presenter, "widget", None)
    if widget is None:
        return False
    try:
        window = getattr(presenter, "main_window_app", None)
        ui = getattr(window, "ui", None) if window is not None else None
        if ui is None:
            pp = getattr(window, "presenter", None) if window is not None else None
            ui = getattr(pp, "ui", None) if pp is not None else None
        stack = getattr(ui, "workspace_stack", None) if ui is not None else None
        if stack is not None:
            current = stack.currentWidget()
            if current is widget:
                return False
            # page may be ancestor of widget (wrapper pattern not used for IC,
            # but keep symmetric with MC)
            if current is not None and hasattr(current, "isAncestorOf"):
                try:
                    if current.isAncestorOf(widget):
                        return False
                except Exception:
                    pass
            return True
        # fallback: hidden stack pages are not visible
        return not bool(widget.isVisible())
    except Exception:
        try:
            return not bool(widget.isVisible())
        except Exception:
            return False


def mark_render_stale(presenter) -> None:
    widget = getattr(presenter, "widget", None)
    if widget is not None:
        widget._render_stale = True  # type: ignore[attr-defined]
    try:
        from core.tracing.tracer import Tracer

        if Tracer.enabled():
            Tracer.instance().record(
                "render.ic.deferred",
                "IC render deferred - background tab",
                {"stale": True},
            )
    except Exception:
        pass


def is_render_stale(presenter) -> bool:
    widget = getattr(presenter, "widget", None)
    return bool(getattr(widget, "_render_stale", False)) if widget is not None else False


def flush_stale_render(presenter) -> bool:
    """Flush a deferred IC render if the page is now visible (stale-flush)."""
    widget = getattr(presenter, "widget", None)
    if widget is None or not getattr(widget, "_render_stale", False):
        return False
    if is_background_tab(presenter):
        return False
    widget._render_stale = False  # type: ignore[attr-defined]
    try:
        from core.tracing.tracer import Tracer

        if Tracer.enabled():
            Tracer.instance().record(
                "render.ic.flush",
                "IC stale render flushed on show",
                {},
            )
    except Exception:
        pass
    try:
        return bool(presenter.update_comparison_if_needed())
    except Exception:
        try:
            presenter.schedule_update()
            return True
        except Exception:
            return False
