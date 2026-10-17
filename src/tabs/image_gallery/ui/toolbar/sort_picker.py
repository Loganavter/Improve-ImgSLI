"""Gallery toolbar sort picker — surface Button + SimpleOptionsFlyout wiring.

Split out of ``ui/toolbar.py`` (plan-gallery-split-2026-10-17, Part C6): the
bodies of ``GalleryToolbar._sort_flyout_ensure`` / ``_sort_options_for_domain``
/ ``_on_sort_clicked`` / ``_on_sort_chosen`` moved here verbatim (``self``
renamed to ``owner``) as plain functions-taking-owner; ``GalleryToolbar`` keeps
same-named thin delegators so call sites and tests do not move.
"""

from __future__ import annotations

from sli_ui_toolkit.widgets import SimpleOptionsFlyout


def sort_flyout_ensure(owner) -> SimpleOptionsFlyout | None:
    parent = None
    try:
        parent = owner.window()
    except Exception:
        parent = None
    if parent is None:
        try:
            parent = owner
        except Exception:
            return None
    flyout = getattr(owner, "_sort_flyout", None)
    if flyout is None:
        try:
            flyout = SimpleOptionsFlyout(parent_widget=parent)
        except Exception:
            return None
        try:
            flyout.item_chosen.connect(owner._on_sort_chosen)
        except Exception:
            pass
        owner._sort_flyout = flyout
    return flyout


def sort_options_for_domain(owner) -> list[str]:
    """Sort labels selectable in the current judgment domain.

    The AI-quality sort orders by a judgment-domain score, so the
    ``algorithms`` domain does not offer it. The row is *listed* in the
    flyout (canonical ``_sort_items`` indices stay 1:1 — no remap) but
    disabled; the widget also fails it over to Rank — see
    ``ImageGalleryWidget._on_sort_changed``.
    """
    try:
        if owner.judgment_domain == "ai":
            return list(owner._sort_items)
    except Exception:
        return list(owner._sort_items)
    return [opt for opt in owner._sort_items if opt != owner._AI_SORT_LABEL]


def on_sort_clicked(owner) -> None:
    """Open the sort flyout under the button (toggles on re-click)."""
    try:
        flyout = sort_flyout_ensure(owner)
        if flyout is None:
            return
        # Manual same-anchor toggle: a visible flyout closes on re-click
        # (deterministic here; show_below toggles same-anchor too).
        try:
            if flyout.isVisible():
                flyout.hide()
                return
        except Exception:
            pass
        # Match the button metrics (transient_interpolation.py precedent:
        # set_row_height takes design px, button height is 34 design).
        try:
            flyout.set_row_height(34)
        except Exception:
            pass
        flyout.populate(
            [owner._sort_display(i) for i in range(len(owner._sort_items))],
            int(owner._sort_index),
        )
        # Domain gate: "Sort: AI quality" is listed (canonical indices)
        # but not selectable outside the AI domain.
        try:
            selectable = set(sort_options_for_domain(owner))
            for _i, _opt in enumerate(owner._sort_items):
                _row = flyout.row_widget(_i)
                if _row is not None:
                    _row.setEnabled(_opt in selectable)
        except Exception:
            pass
        # Content width: uniform rows on the widest label
        # ("Sort: Name"), tight card. The button carries " ▾" the rows
        # don't, so anchor-matching leaves trailing slack in every row.
        flyout.show_below(owner._sort_combo, width_mode="content")
    except Exception:
        pass


def on_sort_chosen(owner, index: int) -> None:
    owner.set_sort_index(index)
