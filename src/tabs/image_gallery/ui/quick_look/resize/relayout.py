"""Quick look card resize — card re-layout after a resize step.

Bodies moved verbatim from ``ui/quick_look/resize.py`` (plan-gallery-split-
2026-10-17, Part C2). Plain functions taking the overlay as their first
argument (``CODE_PATTERNS.md`` "thin owner + use_cases module"); function
names and signatures are unchanged.

``_relayout_on_card_resize`` is the entry (preview-with-aspect rescale +
column-floor redistribution + footer reflow); ``relayout_report_rows``
re-seats metric/artifact rows flat in the right column.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from tabs.image_gallery.ui.quick_look.preview_canvas_host import _fit_preview_slot

from .zones import reposition_grip


def _distribute_column_floors(overlay) -> None:
    """Pin left/right minimums from the LIVE card width (65/35 split).

    QBoxLayout hands all undistributed extra space to a single side, so
    stretch factors alone cannot hold mockup proportions AND share growth:
    the column ended stranded at ~496px after shrink-back (clipped preview).
    Instead the floors consume the width exactly — left (preview priority)
    takes 65% of the extra, right 35% — leaving no remainder to misdeal.
    Floors derive from the card width only (never from grown children), so
    nothing ratchets: shrink restores 640/296.
    """
    try:
        from sli_ui_toolkit.managers import scaled_px

        content = getattr(overlay, "_content", None)
        host = getattr(overlay, "_preview_host", None)
        if content is None or host is None:
            return
        left = host.parentWidget()
        scroll = content.findChild(QWidget, "quicklook_right_scroll")
        if left is None or scroll is None:
            return
        outer = content.layout()
        mid = left.parentWidget().layout()
        try:
            om = outer.contentsMargins()
            mm = mid.contentsMargins()
            avail = (
                content.width()
                - om.left() - om.right()
                - mm.left() - mm.right()
                - mid.spacing()
            )
        except Exception:
            avail = content.width() - scaled_px(40)
        base_l, base_r = scaled_px(640), scaled_px(296)
        extra = max(0, int(avail) - base_l - base_r)
        left_extra = int(round(extra * 0.65))
        left.setMinimumWidth(base_l + left_extra)
        scroll.setMinimumWidth(base_r + (extra - left_extra))
    except Exception:
        pass


def relayout_report_rows(overlay) -> None:
    """Lay metric + artifact rows flat in the right column, uniformly spaced.

    Rows (tracked in ``overlay._metric_rows`` / ``overlay._artifact_rows``)
    become direct ``right_lay`` children with stretch 0, in visual order,
    with one stretch-1 spacer before the first row, between every
    consecutive pair, and after the last row — metrics rows, then artifact
    rows, inserted right before the series divider. The group's outer gaps
    (to the dims/format/size meta row above, to the series/analysis divider
    below) therefore match the inter-row gaps. Rows pin at sizeHint; ALL
    surplus splits evenly among the N+1 equal spacers at every height
    (gap = surplus/(N+1), collapsing to the spacing floor when short). The
    series/strip/brief blocks below stay pinned after the last row. Called
    after every metrics/artifacts rebuild (either order); never raises.
    """
    try:
        lay = getattr(overlay, "_right_lay", None)
        host = getattr(overlay, "_report_host", None)
        anchor = getattr(overlay, "_div_series", None)
        if lay is None or host is None or anchor is None:
            return
        rows = list(getattr(overlay, "_metric_rows", [])) + list(getattr(overlay, "_artifact_rows", []))
        # Detach previous pass: tracked rows plus any spacers this function
        # inserted (this layout owns no other spacers, so sweep them all).
        for row in rows:
            try:
                lay.removeWidget(row)
            except Exception:
                pass
        for i in range(lay.count() - 1, -1, -1):
            try:
                it = lay.itemAt(i)
            except Exception:
                continue
            if it is not None and it.widget() is None and it.spacerItem() is not None:
                try:
                    lay.removeItem(it)
                except Exception:
                    pass
        try:
            idx = lay.indexOf(anchor)
        except Exception:
            idx = -1
        if idx < 0:
            return
        # Leading spacer: the first metric row breathes from the
        # dims/format/size meta row above exactly like rows from each other
        # (no fixed meta_gap widget — that would make the top seam larger).
        if rows:
            try:
                lay.insertStretch(idx, 1)
            except Exception:
                pass
            idx += 1
        for row in rows:
            try:
                if row.parent() is not host:
                    row.setParent(host)
            except Exception:
                pass
            try:
                lay.insertWidget(idx, row, 0)
            except Exception:
                continue
            # Walk rebuilds create rows under an already-visible host, and
            # new children of a visible parent stay hidden (no implicit
            # show — same as the strip host in strip.py): hidden rows are
            # excluded from layout hints, so bars settle at a ~100px
            # default and read as lowered values for ~2 frames. Show
            # explicitly; first build is a no-op (ancestor show covers it).
            try:
                row.show()
            except Exception:
                pass
            idx += 1
            # Spacer after every row (including the last): the last metric
            # row breathes from the divider below exactly like rows from
            # each other.
            try:
                lay.insertStretch(idx, 1)
            except Exception:
                pass
            idx += 1
        # Bar-fill settle: fill widths ride on child sizeHints, and one
        # lay.activate() does NOT recurse synchronously into row/bar
        # layouts (each level settles on a later event-loop pass) — so the
        # first paint(s) after a rebuild show stale/small fills (walk:
        # lowered bars for ~2 frames, then correct). Settle every level
        # explicitly, top-down, before the next paint: column → row
        # layouts (bar resizeEvents fire synchronously inside and push
        # fill hints) → bar layouts (fills take geometries). Same
        # stale-hint precedent as the strip host (strip.py). No-op when
        # hidden (widths 0, updates deferred to resizeEvent as before).
        try:
            lay.activate()
        except Exception:
            pass
        try:
            from tabs.image_gallery.ui.quick_look.bars import (
                _BarWidget,
                _DualRestoredInventedBar,
            )

            for row in rows:
                try:
                    rl = row.layout()
                    if rl is not None:
                        rl.activate()
                except Exception:
                    pass
                try:
                    for bar in row.findChildren(_BarWidget):
                        try:
                            bar._update_fill()
                        except Exception:
                            pass
                        try:
                            bl = bar.layout()
                            if bl is not None:
                                bl.activate()
                        except Exception:
                            pass
                    for dual in row.findChildren(_DualRestoredInventedBar):
                        try:
                            dual._update_geometry()
                        except Exception:
                            pass
                        try:
                            dl = dual.layout()
                            if dl is not None:
                                dl.activate()
                        except Exception:
                            pass
                except Exception:
                    continue
        except Exception:
            pass
        try:
            lay.activate()
        except Exception:
            pass
    except Exception:
        pass


def _repin_after_card_resize(overlay) -> None:
    """Re-run the absolute-child pin hooks after a card resize step.

    W-B: the card re-layout (preview-with-aspect rescale + footer reflow)
    rides along via ``reposition_grip`` (called below), so the drag paths
    (border / ring) and the overlay Resize paths all re-layout
    through this one entry.
    """
    try:
        overlay._reposition_source_inset()
    except Exception:
        pass
    try:
        reposition_grip(overlay)
    except Exception:
        pass


def _reflow_footer(overlay) -> None:
    """Reflow the bottom action bar after a card resize (W-B).

    Export-window idiom: action buttons keep their natural widths on the
    left, the trailing stretch pins them there. The layout does the reflow
    itself; this hook only refreshes bar geometry so a resize can never
    strand the bar mid-layout. The bar hint is gone (no hint re-pin).
    Never hides or closes anything.
    """
    try:
        bar = None
        try:
            content = getattr(overlay, "_content", None)
            if content is not None:
                bar = content.findChild(QWidget, "quicklook_bottom_bar")
        except Exception:
            bar = None
        if bar is None:
            return
        try:
            bar.updateGeometry()
        except Exception:
            pass
    except Exception:
        pass


def _relayout_on_card_resize(overlay) -> None:
    """Card re-layout entry for every resize step (W-B).

    Preview stretches with aspect, footer reflows. Called from
    ``reposition_grip`` (the in-scope hook every resize path already runs);
    also reachable directly. No close paths, no size-policy changes (W8
    min-only stays: minimum 1040×680, no maximum).
    """
    _distribute_column_floors(overlay)
    _fit_preview_slot(overlay)
    _reflow_footer(overlay)
