"""S3 clean-review row building — filmstrip cells, provenance line, footer state.
Audit-Meta: pattern=thin-owner-target size=exempt reason="one row-builder concern — filmstrip cells + provenance + footer share the modal layout contract; body moved verbatim from the overlay's _populate"

Split out of the clean-review overlay module (plan-gallery-split-2026-10-17,
Part C3):
``populate(overlay, owner)`` is the row-building body of
``CleanReviewOverlay._populate`` (which now delegates here). The provenance
resolver and per-card helpers it uses live here too; the tab translator reaches
them through ``overlay._t`` so the EN defaults / per-locale strings are
unchanged. Moved verbatim — same behaviour, ``self`` renamed to ``overlay``.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.ui.layout_settle import settle_layout

from tabs.image_gallery.debug import gallery_debug

# Public toolkit imports.
from sli_ui_toolkit.widgets import (
    Button,
    ButtonRow,
    Label,
    OverlayScrollArea,
)

from .plate import _ReviewPlate

# S3-2: filmstrip thumb geometry (design px — pass through scaled_px for
# raw geometry, Button scales its own ``size=`` internally).
THUMB_WIDTH_PX = 150
THUMB_HEIGHT_PX = 100
# S3-3: per-series filmstrip cap — show the first N cells, then a
# "+N more / scrollable strip" informational tile (mockup v3).
FILMSTRIP_MAX_CELLS = 8


def _hub_name_for_series(owner, series_id: str) -> str | None:
    """Hub resolver for provenance — SERIES N · hub (cnt).

    Tries state.series (Series dataclass) first, then fallback to first
    rejected item's stem. Returns None if unresolved.
    """
    if series_id == "__ungrouped__":
        return None
    # Try owner.state.series
    try:
        st = getattr(owner, "state", None)
        series_list = getattr(st, "series", None) if st is not None else None
        if series_list:
            for ser in list(series_list):
                sid = getattr(ser, "id", None)
                if sid is not None and str(sid) == str(series_id):
                    members = getattr(ser, "members", None) or []
                    if members:
                        # Prefer rank 1 hub if available
                        try:
                            ranked = sorted(members, key=lambda it: int(getattr(it, "rank", 999) or 999))
                            hub_item = ranked[0] if ranked else members[0]
                        except Exception:
                            hub_item = members[0]
                        try:
                            return Path(getattr(hub_item, "path")).stem
                        except Exception:
                            try:
                                return str(getattr(hub_item, "name", "")) or None
                            except Exception:
                                pass
    except Exception:
        pass
    # Fallback: first item with that provenance
    try:
        st = getattr(owner, "state", None)
        items = getattr(st, "items", None) or []
        for it in list(items):
            pid = getattr(it, "provenance_series_id", None) or getattr(it, "series_id", None)
            if pid is not None and str(pid) == str(series_id):
                try:
                    return Path(getattr(it, "path")).stem
                except Exception:
                    continue
    except Exception:
        pass
    return None


def _total_bytes_for_items(items: list) -> int:
    total = 0
    for it in items:
        try:
            p = Path(getattr(it, "path"))
            if p.is_file():
                total += int(p.stat().st_size)
        except Exception:
            continue
    return total


def _rounded_top_pixmap(pix: QPixmap, w: int, h: int) -> QPixmap:
    """Clip a pixmap to top-rounded corners (recent/grid card idiom).

    Radius 10 like the other cards, bottom corners square. Returns the
    source untouched when sizes are degenerate.
    """
    try:
        from PySide6.QtGui import QPainterPath

        w, h = int(w), int(h)
        if w <= 0 or h <= 0 or pix.isNull():
            return pix
        r = min(scaled_px(10), w // 2, h // 2)
        out = QPixmap(w, h)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            path = QPainterPath()
            path.moveTo(0, h)
            path.lineTo(0, r)
            path.arcTo(0, 0, 2 * r, 2 * r, 180.0, -90.0)
            path.lineTo(w - r, 0)
            path.arcTo(w - 2 * r, 0, 2 * r, 2 * r, 90.0, -90.0)
            path.lineTo(w, h)
            path.closeSubpath()
            p.setClipPath(path)
            p.drawPixmap(0, 0, pix)
        finally:
            p.end()
        return out
    except Exception:
        return pix


def _display_folder_for_items(owner, items: list) -> str:
    """Folder shown in the subtitle/move title.

    Resolves through the same helper as the move itself
    (``triage.resolve_move_folder``), so the subtitle can never promise a
    target the move refuses; the ``<folder>`` literal is the last resort
    (no paths at all or parents disagree).
    """
    try:
        from tabs.image_gallery.use_cases.triage import resolve_move_folder

        folder = resolve_move_folder(owner, items)
        if folder is not None:
            return str(folder)
    except Exception:
        pass
    return "<folder>"


def _with_count(text: str, cnt: int) -> str:
    """Append `` (cnt)`` unless the count is 1 (a lone hub needs no count —
    and filenames like ``pic(1)`` would stutter into ``(1) (1)``)."""
    try:
        if int(cnt) > 1:
            return f"{text} ({int(cnt)})"
    except Exception:
        pass
    return text


def populate(overlay, owner) -> None:
    # Ensure provenance_series_id filled (triage wiring).
    try:
        from tabs.image_gallery.use_cases import triage as _triage

        if hasattr(_triage, "ensure_provenance_series_ids"):
            _triage.ensure_provenance_series_ids(owner)
    except Exception:
        pass
    items = overlay._rejected_items(owner)
    n = len(items)
    total_bytes = _total_bytes_for_items(items)
    total_mb = total_bytes / (1024 * 1024) if total_bytes else 0.0
    # Title + S3-1 reassurance subtitle (mockup v3 copy: numbers live in
    # the subtitle; folder short form — real path when known, else the
    # ``<folder>`` literal as drawn in the mockup).
    folder_name = _display_folder_for_items(owner, items)
    try:
        overlay._title.setText(
            overlay._t("image_gallery.clean_review.title", "Review rejected files")
        )
    except Exception:
        pass
    try:
        overlay._subtitle.setText(
            overlay._t(
                "image_gallery.clean_review.subtitle",
                "{n} files will be moved to {folder}/_rejected/ — nothing is deleted, Undo available for 10 s.",
            ).format(n=n, folder=folder_name)
        )
    except Exception:
        pass

    # Provenance-by-series line: SERIES N · hub (cnt) with hub resolver.
    by_series: dict[str, list] = {}
    for it in items:
        sid = getattr(it, "provenance_series_id", None) or getattr(it, "series_id", None) or "__ungrouped__"
        sid = str(sid)
        by_series.setdefault(sid, []).append(it)
    # Sort keys: SERIES numeric first, ungrouped last.
    def _series_sort_key(k: str):
        if k == "__ungrouped__":
            return (9999, k)
        # Extract numeric suffix if series_N
        try:
            if k.startswith("series_"):
                return (int(k.split("_")[1]), k)
        except Exception:
            pass
        return (0, k)

    sorted_sids = sorted(by_series.keys(), key=_series_sort_key)
    # Build hub-aware provenance parts with SERIES N indexing.
    _series_label = overlay._t("image_gallery.clean_review.series", "SERIES {n}")
    if by_series:
        parts = []
        for idx, sid in enumerate(sorted_sids, start=1):
            cnt = len(by_series[sid])
            _sid_label = _series_label.format(n=idx)
            if sid == "__ungrouped__":
                hub = overlay._t("image_gallery.clean_review.ungrouped", "UNGROUPED")
                parts.append(_with_count(hub, cnt) if len(sorted_sids) == 1 else _with_count(f"{_sid_label} · {hub}", cnt))
            else:
                hub = _hub_name_for_series(owner, sid)
                if hub:
                    parts.append(_with_count(f"{_sid_label} · {hub}", cnt))
                else:
                    # Fallback without hub
                    parts.append(_with_count(_sid_label, cnt))
        # Use sorted order enumeration for display but keep original sid for resolver.
        # Rebuild with actual enumeration based on sorted order where hub exists.
        # For ungrouped, use UNGROUPED label.
        # Already built.
        prov_text = overlay._t("image_gallery.clean_review.provenance_prefix", "from: ") + " · ".join(parts)
        # Back-compat: also include raw series label for tests that search lowercase
        # Keep display as built.
    else:
        prov_text = overlay._t("image_gallery.clean_review.no_rejected", "No rejected files.")
    try:
        overlay._provenance_label.setText(prov_text)
    except Exception:
        pass

    # Move button variant primary, size label total MB.
    try:
        overlay._move_btn.setText(overlay._t("image_gallery.clean_review.move", "Move {n}").format(n=n))
        overlay._move_btn.setEnabled(n > 0)
    except Exception:
        pass
    try:
        if n > 0:
            overlay._size_label.setText(
                overlay._t(
                    "image_gallery.clean_review.size", "{n} files · {mb} MB"
                ).format(n=n, mb=f"{total_mb:.1f}")
            )
        else:
            overlay._size_label.setText(
                overlay._t("image_gallery.clean_review.no_files", "No files to move")
            )
    except Exception:
        pass
    try:
        overlay._restore_all_btn.setEnabled(n > 0)
    except Exception:
        pass

    # Rebuild list rows — Phase 6: ONE flat horizontal strip over ALL
    # rejected items in stable order (mockup v3: borderless strip, no
    # per-series boxes/headers; series survive only in the provenance
    # line above). Per-series Restore buttons are gone by design
    # (mockup has none); Restore all + per-thumb Restore remain.
    for w in overlay._row_widgets:
        try:
            overlay._list_layout.removeWidget(w)
            # Hide before orphaning (stillborn-toplevel guard).
            w.hide()
            w.setParent(None)
            w.deleteLater()
        except Exception:
            pass
    overlay._row_widgets.clear()

    if not items:
        empty = Label(
            overlay._t("image_gallery.clean_review.no_rejected", "No rejected files."),
            pixel_size=14,
            parent=overlay._list_host,
        )
        empty.setObjectName("clean_review_empty")
        overlay._list_layout.addWidget(empty)
        overlay._row_widgets.append(empty)
        return

    # Flat order: series groups in stable SERIES order, items in state
    # order within each group (reuses sorted_sids above).
    flat: list = []
    for sid in sorted_sids:
        flat.extend(by_series[sid])

    # Filmstrip: single horizontally scrollable, frameless strip of
    # thumbs (mockup v3 "scrollable strip" — capped cells exceed the
    # modal width, so the strip scrolls horizontally past the cap to
    # the +N tile). NoFrame: borderless strip over the plate.
    strip_scroll = OverlayScrollArea(overlay._list_host, corner_radius=0)
    strip_scroll.setObjectName("clean_review_filmstrip")
    strip_scroll.setWidgetResizable(True)
    strip_scroll.setFrameShape(QFrame.Shape.NoFrame)
    # Native bars stay hidden (overlay invariant — the floating custom
    # bar appears on horizontal overflow by itself).
    strip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    strip_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    filmstrip = QWidget()
    filmstrip.setObjectName("clean_review_filmstrip_inner")
    # Filmstrip host auto-fills raw ``Window`` (dark #1e1e1e) — the band
    # behind the cells. Same panel token as the list host.
    try:
        from tabs.image_gallery.ui.quick_look.labels_theme import _apply_panel_background

        _apply_panel_background(strip_scroll)
        _apply_panel_background(filmstrip)
    except Exception:
        pass
    film_layout = QHBoxLayout(filmstrip)
    film_layout.setContentsMargins(0, 0, 0, 0)
    film_layout.setSpacing(scaled_px(8))
    film_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
    for it in flat[:FILMSTRIP_MAX_CELLS]:
        # One framed card per item (recent-panel idiom): picture on top,
        # Restore button below — the plate frame makes them read as one
        # card instead of floating thumb + button parts.
        cell = _ReviewPlate(filmstrip, hover_wash=True)
        cell.setObjectName("clean_review_filmstrip_cell")
        cell._s3_item = it  # type: ignore[attr-defined]
        try:
            cell.installEventFilter(overlay)
        except Exception:
            pass
        cell_layout = QVBoxLayout(cell)
        cell_layout.setContentsMargins(scaled_px(8), scaled_px(8), scaled_px(8), scaled_px(8))
        cell_layout.setSpacing(scaled_px(6))
        # S3-2: toolkit Label thumb 150x100 — Label is the unified
        # themed component (QLabel subclass), pixmap set via the
        # inherited QLabel.setPixmap; neutral "!" placeholder when no
        # thumbnail is available.
        thumb_label = Label("", pixel_size=12, parent=cell)
        thumb_label.setObjectName("clean_review_thumb")
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setFixedSize(scaled_px(THUMB_WIDTH_PX), scaled_px(THUMB_HEIGHT_PX))
        # Try to load thumbnail if available (top corners rounded like
        # the other cards; bottom stays square into the card).
        pix = getattr(it, "thumbnail", None)
        if isinstance(pix, QPixmap) and not pix.isNull():
            try:
                scaled = pix.scaled(scaled_px(THUMB_WIDTH_PX), scaled_px(THUMB_HEIGHT_PX), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                thumb_label.setPixmap(
                    _rounded_top_pixmap(scaled, scaled_px(THUMB_WIDTH_PX), scaled_px(THUMB_HEIGHT_PX))
                )
            except Exception:
                thumb_label.setText("!")
        else:
            # Placeholder — painter pipeline owns visuals (no QSS, no get_color).
            thumb_label.setText("!")
        cell_layout.addWidget(thumb_label)

        # Recent-projects-panel idiom: the cell is picture on top,
        # Restore button below — no name label; the filename rides
        # the button tooltip instead.
        name = getattr(it, "name", None) or Path(getattr(it, "path", "")).name or str(getattr(it, "path", ""))

        restore_btn = Button(
            text="↩ " + overlay._t("image_gallery.clean_review.restore", "Restore"),
            variant="surface",
            parent=cell,
        )
        restore_btn.setObjectName("clean_review_restore")
        # The cell is one hover surface: hovering anywhere on the card
        # (thumb or plate) lights this Restore button too
        # (HoverCoordinator hover host — mirror of the parent-stays-lit rule).
        try:
            restore_btn.setHoverHost(cell)
        except Exception:
            pass
        try:
            restore_btn.setToolTip(str(name))
        except Exception:
            pass
        cell_layout.addWidget(restore_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        p = Path(it.path) if hasattr(it, "path") else None

        def _make_restore(path=p):
            def _do():
                if path is None:
                    return
                try:
                    from tabs.image_gallery.use_cases import triage as _triage

                    _triage.toggle_reject(overlay._owner, path)
                except Exception:
                    try:
                        it2 = next((x for x in overlay._rejected_items(overlay._owner) if Path(x.path) == path), None)
                        if it2 is not None:
                            it2.rejected = False
                    except Exception:
                        pass
                try:
                    overlay._populate(overlay._owner)
                except Exception:
                    pass
                try:
                    w = getattr(overlay._owner, "widget", None) or getattr(overlay._owner, "_widget", None)
                    if w is not None and hasattr(w, "rebuild_grid"):
                        st = getattr(overlay._owner, "state", None)
                        items2 = list(getattr(st, "items", []) or []) if st is not None else []
                        w.rebuild_grid(items2)
                except Exception:
                    pass

            return _do

        restore_btn.clicked.connect(_make_restore())
        # Mockup v3 thumb row: every cell top-aligned so thumbs
        # share one top edge (QHBoxLayout would vertically center
        # shorter items like the +N tile otherwise).
        film_layout.addWidget(cell, 0, Qt.AlignmentFlag.AlignTop)
    # S3-3: "+N more" informational tile when ALL rejected exceed
    # FILMSTRIP_MAX_CELLS — the mockup draws a dashed-border tile,
    # which the painter pipeline does not support without QSS, so a
    # disabled surface Button with two muted rows is used instead.
    # Cells beyond the cap stay accessible via the horizontally
    # scrollable strip context (informational tile, cap documented
    # in FILMSTRIP_MAX_CELLS).
    overflow = len(flat) - FILMSTRIP_MAX_CELLS
    if overflow > 0:
        more_tile = Button(
            rows=[
                ButtonRow(
                    text=overlay._t(
                        "image_gallery.clean_review.more_tile", "+{n} more", n=overflow
                    ),
                    size=14,
                ),
                ButtonRow(
                    text=overlay._t(
                        "image_gallery.clean_review.more_tile_sub", "scrollable strip"
                    ),
                    size=10,
                ),
            ],
            variant="surface",
            size=(THUMB_WIDTH_PX, THUMB_HEIGHT_PX),
            parent=filmstrip,
        )
        more_tile.setObjectName("clean_review_filmstrip_more")
        more_tile.setEnabled(False)
        try:
            more_tile.setToolTip(
                overlay._t(
                    "image_gallery.clean_review.more_tooltip",
                    "{n} more rejected file(s)",
                    n=overflow,
                )
            )
        except Exception:
            pass
        # Top-aligned with the cells (mockup v3: tile shares the
        # thumb-row top edge, not the row vertical center).
        film_layout.addWidget(more_tile, 0, Qt.AlignmentFlag.AlignTop)
    # Add stretch to left align.
    film_layout.addStretch(1)
    strip_scroll.setWidget(filmstrip)
    # Settle-then-read (quick_look/strip.py:378 documents the trap): a
    # fresh layout can report a stale hint before its first pass, so
    # activate the filmstrip layout before deriving the scroller's
    # fixed height from it.
    try:
        film_layout.activate()
    except Exception:
        pass
    try:
        strip_scroll.setFixedHeight(filmstrip.sizeHint().height() + scaled_px(16))
    except Exception:
        pass
    overlay._list_layout.addWidget(strip_scroll)
    overlay._row_widgets.append(strip_scroll)
    # Explicit show (quick_look/strip.py:367 documents the trap): a
    # child added while the host is visible stays hidden until the next
    # turn — excluded from layout hints, so the host collapses and the
    # strip paints a frame late.
    try:
        strip_scroll.show()
    except Exception:
        pass
    # Synchronous settle so the host and the strip agree in the same
    # frame (qt-selfsizing A1): without this the strip keeps its old
    # geometry until the next event-loop turn.
    try:
        settle_layout(overlay._list_host, filmstrip, strip_scroll)
    except Exception:
        gallery_debug("clean_review filmstrip settle failed")
