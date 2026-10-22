"""Toolbar sort/view/domain wiring + view-prefs persistence + page paint.

Bodies extracted from ``ImageGalleryWidget`` (plan Part B, Wave 2) per
``CODE_PATTERNS.md`` (thin owner + functions-taking-owner); the widget
keeps same-named one-line delegators so call sites and tests do not move.
The ``paintEvent`` body lives here as ``paint_event(owner, event)`` — the
class keeps the Qt-required ``paintEvent`` name and delegates.

These functions are fail-open like the surrounding widget chrome: a
storeless / unattached widget must never raise.
"""

from __future__ import annotations

from tabs.image_gallery.debug import gallery_debug as _dbg


def current_sort_text(owner) -> str:
    """The toolbar's current sort label ("" when the chrome is not built)."""
    try:
        text = owner.toolbar.sort_text()
        return str(text or "")
    except Exception:
        return ""


def sort_keyfunc(owner, text: str):
    """The active sort key function, or ``None`` for an unknown label.

    Domain gate (plan-gallery-two-domain-axes W2): "Sort: AI quality" is an
    AI-domain ordering; outside the AI domain it falls back to Rank so the
    algorithms view never orders by an AI score. ``None`` (an unwired
    fake/legacy owner with no domain state) keeps the legacy behaviour.
    """
    key = str(text or "").lower()
    if "quality" in key:
        _domain = getattr(owner, "_judgment_domain", None)
        if _domain is not None and _domain != "ai":
            key = "rank"
    try:
        return owner._sort_keyfunc(key)
    except Exception:
        return None


def sort_series(owner, series, keyfunc):
    """Sort clusters' members and the clusters themselves (idempotent)."""
    out = []
    for cl in list(series or []):
        try:
            out.append(sorted(cl, key=keyfunc))
        except Exception:
            out.append(list(cl))
    try:
        out.sort(key=lambda cl: keyfunc(cl[0]) if cl else None)
    except Exception:
        pass
    return out


def sort_items(owner, items, keyfunc):
    try:
        return sorted(items, key=keyfunc)
    except Exception:
        return list(items)


def resort_after_rank_change(owner) -> None:
    """Re-apply the ACTIVE sort after ranks changed (fusion / Jev).

    The sort is a live ORDER, not a one-off shuffle: with "Sort: Rank" the grid
    must follow the numbers when a ranker writes them. It did not — a Jev pass
    stamped ranks on the cards while the grid kept the old order until the user
    re-picked the sort (owner report 2026-10-22: "jev проставил оценки и нихуя
    порядок не изменился"). One entry point, called from both rank landings.
    """
    try:
        widget = getattr(owner, "widget", None) or owner
        text = current_sort_text(widget)
        if sort_keyfunc(widget, text) is None:
            return
        setter = getattr(widget, "_on_sort_changed", None)
        if callable(setter):
            setter(text)
    except Exception:
        pass


def _persist_sort(owner) -> None:
    """Remember the toolbar sort position with the other view prefs."""
    state = getattr(owner, "_session_state", None)
    if state is None:
        return
    try:
        state.set("sort_index", int(owner.toolbar.sort_index))
    except Exception:
        pass


def _on_sort_changed(owner, text: str) -> None:
    # S2: toolbar sort combo "Sort: Rank/Name/Date" — reorder grid.
    try:
        keyfunc = sort_keyfunc(owner, text)
        if keyfunc is None:
            return
        _persist_sort(owner)
        items = list(owner._items or [])
        # Rebuild grid preserving series grouping if active
        if owner._series:
            # Sort applies to grouped series: members within each
            # cluster AND cluster order (by first member), then ONE
            # rebuild via set_triage (stats/hubs recomputed there).
            # The old flat rebuild_grid first was a wasted pass whose
            # order set_triage discarded anyway.
            sorted_series = sort_series(owner, owner._series, keyfunc)
            try:
                member_paths = {
                    str(it.path) for cl in sorted_series for it in cl
                }
            except Exception:
                member_paths = set()
            try:
                ungrouped = sorted(
                    (
                        it for it in (owner._items or [])
                        if str(it.path) not in member_paths
                    ),
                    key=keyfunc,
                )
            except Exception:
                ungrouped = [
                    it for it in (owner._items or [])
                    if str(it.path) not in member_paths
                ]
            owner._items = [it for cl in sorted_series for it in cl] + ungrouped
            try:
                owner.set_triage(sorted_series, owner._mode, owner._source_path)
            except Exception:
                pass
        else:
            try:
                items.sort(key=keyfunc)
            except Exception:
                pass
            owner.rebuild_grid(items)
    except Exception:
        pass


def _sort_keyfunc(owner, key: str):
    """Sort key for a toolbar sort label, or None for unknown labels.

    ``owner`` is unused (the key derivation is pure) but kept so every
    function in this module has the functions-taking-owner shape; the
    class keeps ``_sort_keyfunc`` as a staticmethod delegator.
    """
    if "name" in key:
        return lambda it: (
            getattr(getattr(it, "path", None), "name", "") or ""
        ).lower()
    if "date" in key:
        # Newest first: use mtime_ns descending
        return lambda it: -int(getattr(it, "mtime_ns", 0) or 0)
    if "quality" in key:
        # AI quality first (higher mean score first); unscored items sink.
        def _quality_key(it):
            try:
                from tabs.image_gallery.models import ai_quality_score

                score = ai_quality_score(getattr(it, "analysis", None))
            except Exception:
                score = None
            if score is None:
                return (1, 0.0)
            return (0, -float(score))

        return _quality_key
    if "rank" in key:
        # Rank 1 first, then embedding distance
        def _rank_key(it):
            r = getattr(it, "rank", None) or getattr(it, "crown_rank", None)
            try:
                rk = int(r) if r is not None else 999
            except Exception:
                rk = 999
            metrics = getattr(it, "metrics", None)
            d = metrics.get("embedding_dist_to_centroid") if isinstance(metrics, dict) else None
            try:
                df = float(d) if d is not None else 1e9
            except Exception:
                df = 1e9
            return (rk, df)

        return _rank_key
    return None


def _on_view_toggled(owner, checked: bool) -> None:
    # View switch toggle (grid/list) — one view, builders swap inside
    # GalleryGridView (recent items_view parity). Series, selection and
    # triage state are untouched; the grid rebuilds its cards in place.
    try:
        owner._view_mode = bool(checked)
    except Exception:
        pass
    try:
        owner._grid_view.set_view_mode("list" if checked else "grid")
    except Exception:
        pass
    try:
        _dbg("view toggled %s", bool(checked))
    except Exception:
        pass
    try:
        owner._persist_view_prefs()
    except Exception:
        pass


def _on_domain_changed(owner, domain: str) -> None:
    """Toolbar domain switch changed — normalize, store, mirror.

    Transient view state only: the session-slot persistence of
    ``judgment_domain`` is out of scope (follow-up). The controller mirror
    (``state.judgment_domain``) is best-effort — a widget without an
    attached controller still tracks its own domain (storeless tests).
    """
    try:
        from tabs.image_gallery import models as _models

        valid = tuple(getattr(_models, "JUDGMENT_DOMAINS", ("algorithms", "ai")))
    except Exception:
        valid = ("algorithms", "ai")
    dom = str(domain or "").strip().lower()
    if dom not in valid:
        dom = "algorithms"
    owner._judgment_domain = dom
    try:
        ctrl = getattr(owner, "_controller", None) or getattr(
            owner, "_attached_controller", None
        )
    except Exception:
        ctrl = None
    try:
        activate = getattr(ctrl, "activate_judgment_domain", None)
        if callable(activate):
            # The switch's real effect: lazily analyze the visible items
            # (or show the not-configured error on the cards).
            activate(dom)
        else:
            state = getattr(ctrl, "state", None)
            if state is not None:
                state.judgment_domain = dom
    except Exception:
        pass
    try:
        _dbg("judgment domain %s", dom)
    except Exception:
        pass
    try:
        owner._persist_view_prefs()
    except Exception:
        pass


def attach_session_state(owner, state) -> None:
    """Attach the tab's ``SessionState`` facade (toolbar chrome writes)."""
    owner._session_state = state


#: Design px of the page's root chrome (real_design.md §2.7): 24 horizontal
#: padding and 12 between stacked regions. NO bottom margin: the grid's
#: ``OpaqueFillHost`` (the scroll well) must reach the tab's bottom edge — the
#: old 40 px band "to clear the selection HUD" outlived the HUD (removed,
#: ``widget.py``: selection lives in the card context menu) and read as a dead
#: strip under the grid (owner report 2026-10-22).
ROOT_MARGIN_PX = (24, 12, 24, 0)
ROOT_SPACING_PX = 12


def apply_root_design_metrics(owner) -> None:
    """Resolve the page root's design px at the live scale factor.

    Called at build and re-called on every ``UiScale`` change so a live
    interface-scale change moves the page chrome with the rest of the UI.
    """
    from sli_ui_toolkit.managers import scaled_px

    layout = owner.layout()
    if layout is None:
        return
    layout.setContentsMargins(*(scaled_px(v) if v else 0 for v in ROOT_MARGIN_PX))
    layout.setSpacing(scaled_px(ROOT_SPACING_PX))


def on_root_metrics_changed(owner, *_args) -> None:
    apply_root_design_metrics(owner)
    owner.updateGeometry()


def _persist_view_prefs(owner) -> None:
    """Write both toolbar switch positions through the session-state facade."""
    state = getattr(owner, "_session_state", None)
    if state is None:
        return
    try:
        state.set("view_list", bool(getattr(owner, "_view_mode", False)))
        state.set("judgment_domain", str(getattr(owner, "_judgment_domain", "algorithms")))
        try:
            state.set("sort_index", int(owner.toolbar.sort_index))
        except Exception:
            pass
    except Exception:
        pass


def paint_event(owner, event) -> None:
    """Paint the page's own opaque themed background (live on theme flip).

    Reads the token at paint time (no cached colour) and paints with alpha
    255, so the page is a self-sufficient opaque surface — the sibling of
    ``SessionPickerWidget`` / the image_compare page. Without this the
    content area (e.g. the blank empty state) showed the composited host
    fill, which does not refresh on a live theme switch.
    """
    try:
        from PySide6.QtGui import QColor, QPainter

        from sli_ui_toolkit.managers import ThemeManager
        from ui.theming import try_resolve_theme_color

        col = try_resolve_theme_color(ThemeManager.get_instance(), "surface.background")
        bg = QColor(col) if isinstance(col, str) else col
        if bg is None or not bg.isValid() or bg.alpha() == 0:
            bg = QColor("#ffffff")
        bg.setAlpha(255)
        painter = QPainter(owner)
        painter.fillRect(event.rect(), bg)
        painter.end()
    except Exception:
        pass

    try:
        # ``owner``'s class is the QWidget subclass that owns this page; a
        # module function cannot use bare ``super()``, so resolve the base
        # paint explicitly (equivalent to ``super()`` in the delegator).
        super(type(owner), owner).paintEvent(event)
    except Exception:
        pass


def apply_view_prefs(owner, *, view_list: bool, judgment_domain: str, sort_index=None) -> None:
    """Restore both switches from the session slot.

    The view is applied directly (widget ``_view_mode`` + grid) so it never
    relies on the toolbar's exclusive helper emitting ``viewToggled`` (which
    early-returns when the toolbar is already in the matching state). The
    domain is the controller's single authority (``_set_judgment_domain``);
    the toolbar stays signal-blocked so it never double-emits. No run fires
    HERE: the AI-domain work is re-derived LEVEL-triggered at the metrics
    pass settle (``_run_ai_on_settle`` + ``_run_jev_on_settle``), so a
    restored ``ai`` domain reproduces the scorecards/rank without starting
    network work during view restore.
    """
    is_list = bool(view_list)
    owner._view_mode = is_list
    try:
        owner._grid_view.set_view_mode("list" if is_list else "grid")
    except Exception:
        pass
    if sort_index is not None:
        try:
            owner.toolbar.set_sort_index(int(sort_index))
            # The index alone does not reorder anything: the grid was (or will
            # be) built in triage order. Apply the restored sort to the current
            # items too, otherwise a reopened tab shows "Sort: Name" on an
            # unsorted grid until the user re-picks it.
            text = current_sort_text(owner)
            if sort_keyfunc(owner, text) is not None:
                setter = getattr(owner, "_on_sort_changed", None)
                if callable(setter):
                    setter(text)
        except Exception:
            pass
    dom = str(judgment_domain or "algorithms").strip().lower()
    if dom not in ("algorithms", "ai"):
        dom = "algorithms"
    owner._judgment_domain = dom
    try:
        tb = owner.toolbar
        tb.blockSignals(True)
        try:
            tb.set_view_list(is_list)
            tb.set_judgment_domain(dom)
        finally:
            tb.blockSignals(False)
    except Exception:
        pass
    try:
        ctrl = getattr(owner, "_controller", None) or getattr(
            owner, "_attached_controller", None
        )
        setter = getattr(ctrl, "_set_judgment_domain", None)
        if callable(setter):
            setter(dom)
    except Exception:
        pass
    # WHY Jev does / does not run: observability only (the AI work is
    # re-derived level-triggered at the metrics pass settle). Same
    # IMGSLI_AI_DEBUG key.
    try:
        from tabs.image_gallery.services.ai_client import _ai_debug

        _ai_debug(
            "view restored: judgment_domain=%s (AI work derived at metrics settle)",
            dom,
        )
    except Exception:
        pass
