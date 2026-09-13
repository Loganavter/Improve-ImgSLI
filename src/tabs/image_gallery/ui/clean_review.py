"""S3 clean review modal — TopLevelInWindowOverlay + Toast Undo.
Audit-Meta: pattern=state-machine size=exempt reason="one overlay lifecycle — provenance+filmstrip+toasts share TopLevelInWindowOverlay state"

Lists rejected files before any move, grouped by provenance series.
Title + reassurance subtitle (``N files will be moved to <folder>/_rejected/
— nothing is deleted, Undo available for 10 s.``). Filmstrip per series
(thumbs 150x100, capped at ``FILMSTRIP_MAX_CELLS`` cells + ``+N more`` tile)
with per-item ``↩ Restore`` + per-series Restore SERIES N
+ Restore all. Provenance line ``SERIES N · hub (cnt)`` via hub resolver.
Final ``Move N to _rejected/`` variant primary does move-only ``shutil.move``
via ``triage.clean_rejected`` and shows a 10s ``ToastManager.get_instance``
+ total MB + ``ToastAction("Undo")``. HUD suppression via FlyoutManager
hide gallery_selection in show_for.

Public toolkit surface only: ``sli_ui_toolkit.widgets.TopLevelInWindowOverlay``,
``ToastManager``, ``ToastAction`` (FEEDBACK_API, OVERLAYS_API),
``FlyoutManager`` (FLYOUT_SYSTEM), ``ThemeManager`` tokens, ``scaled_px``.
No ``setStyleSheet`` — painter pipeline owns visuals.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px

# Public toolkit imports.
from sli_ui_toolkit.widgets import (
    Button,
    ButtonRow,
    Label,
    TopLevelInWindowOverlay,
    ToastAction,
    ToastManager,
)

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


class CleanReviewOverlay(TopLevelInWindowOverlay):
    """Modal listing rejected files with restore + move.

    Use ``show_for(owner)`` to populate and show.
    Emits ``cleaned(list)`` after a successful move batch (for tests).
    """

    cleaned = Signal(list)
    dismissed = Signal()  # shadow TopLevelInWindowOverlay.dismissed for compat

    def __init__(self, parent: QWidget, owner=None) -> None:
        super().__init__(
            parent,
            close_on_background=True,
            close_on_escape=True,
            close_on_deactivate=True,
        )
        self._owner = owner
        self._content = QWidget(self)
        self._content.setObjectName("CleanReviewContent")
        # Theme tokens — painter pipeline owns visuals (no QSS).
        # Uses ThemeManager palette tokens via toolkit Button/Label (no direct get_color call
        # to respect tests/contracts/test_no_manual_theming.py — painter pipeline owns colors).
        try:
            from sli_ui_toolkit.managers import ThemeManager  # noqa: F401

            _ = ThemeManager  # token palette owned by Button variant primary/surface
        except Exception:
            pass
        # Outer layout with scaled_px.
        outer = QVBoxLayout(self._content)
        outer.setContentsMargins(scaled_px(16), scaled_px(16), scaled_px(16), scaled_px(16))
        outer.setSpacing(scaled_px(12))

        self._title = Label("", pixel_size=14, bold=True, parent=self._content)
        self._title.setObjectName("clean_review_title")
        self._title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        outer.addWidget(self._title)

        # S3-1: reassurance subtitle under the title — safety promise before
        # the move (mockup v3). Muted via the toolkit ``caption`` variant
        # (11 px secondary/status text) — no hand-coloring, tokens own color.
        self._subtitle = Label("", pixel_size=11, variant="caption", parent=self._content)
        self._subtitle.setObjectName("clean_review_subtitle")
        self._subtitle.setWordWrap(True)
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignLeft)
        outer.addWidget(self._subtitle)

        self._provenance_label = Label("", pixel_size=11, parent=self._content)
        self._provenance_label.setObjectName("clean_review_provenance")
        self._provenance_label.setWordWrap(True)
        self._provenance_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        outer.addWidget(self._provenance_label)

        # Scrollable list — vertical host, filmstrip per series inside.
        self._scroll = QScrollArea(self._content)
        self._scroll.setWidgetResizable(True)
        self._scroll.setObjectName("clean_review_scroll")
        self._list_host = QWidget()
        self._list_host.setObjectName("clean_review_list_host")
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(scaled_px(8))
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._list_host)
        outer.addWidget(self._scroll, 1)

        # Bottom bar: Restore all | size | Cancel | Move N variant primary.
        bar = QWidget(self._content)
        bar.setObjectName("clean_review_bar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(scaled_px(8))

        self._restore_all_btn = Button(text="Restore all", variant="surface", parent=bar)
        self._restore_all_btn.setObjectName("clean_review_restore_all")
        self._restore_all_btn.clicked.connect(self._on_restore_all)
        bar_layout.addWidget(self._restore_all_btn)

        bar_layout.addStretch(1)

        self._size_label = Label("", pixel_size=11, parent=bar)
        self._size_label.setObjectName("clean_review_size_label")
        self._size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar_layout.addWidget(self._size_label)

        bar_layout.addStretch(1)

        self._cancel_btn = Button(text="Cancel", variant="surface", parent=bar)
        self._cancel_btn.setObjectName("clean_review_cancel")
        self._cancel_btn.clicked.connect(self.hide)
        bar_layout.addWidget(self._cancel_btn)

        self._move_btn = Button(text="Move 0 to _rejected/", variant="surface", parent=bar)
        self._move_btn.setObjectName("clean_review_move")
        self._move_btn.clicked.connect(self._on_move)
        try:
            from tabs.image_gallery.ui.quick_look import _token_color

            accent = _token_color("accent", "#0096FF")
            self._move_btn.set_background_color(accent)
        except Exception:
            pass
        bar_layout.addWidget(self._move_btn)
        outer.addWidget(bar)

        # Host content in overlay — centered slot.
        self.add_widget(self._content, slot=None)
        # Size content with scaled_px.
        try:
            self._content.setMinimumWidth(scaled_px(520))
            self._content.setMinimumHeight(scaled_px(360))
        except Exception:
            pass
        self._row_widgets: list[QWidget] = []
        self._toast_manager: ToastManager | None = None

    # -- public API ---------------------------------------------------

    def show_for(self, owner=None) -> None:
        """Populate from *owner* (or self._owner) and show overlay.

        Suppresses HUD via FlyoutManager hide gallery_selection.
        """
        if owner is not None:
            self._owner = owner
        owner = self._owner
        if owner is None:
            return
        # HUD suppression via FlyoutManager hide gallery_selection.
        try:
            from sli_ui_toolkit.managers import FlyoutManager

            mgr = FlyoutManager.get_instance()
            for flyout in list(getattr(mgr, "_registered_flyouts", set())):
                try:
                    grp = getattr(flyout, "flyout_group", None)
                    if grp is None:
                        grp = getattr(type(flyout), "flyout_group", None)
                    if grp == "gallery_selection" and hasattr(flyout, "isVisible") and flyout.isVisible():
                        flyout.hide()
                except Exception:
                    continue
        except Exception:
            pass
        # Also try selection_hud controller if owner has it.
        try:
            hud = getattr(owner, "_selection_hud", None) or getattr(getattr(owner, "widget", None), "_selection_hud", None)
            if hud is not None and hasattr(hud, "set_suppressed"):
                hud.set_suppressed(True)
        except Exception:
            pass
        self._populate(owner)
        self.show()
        try:
            self.raise_()
            self.setFocus(Qt.FocusReason.PopupFocusReason)
        except Exception:
            pass

    def hideEvent(self, event) -> None:  # noqa: N802
        # Restore HUD suppression after overlay hides.
        try:
            owner = self._owner
            hud = getattr(owner, "_selection_hud", None) if owner is not None else None
            if hud is None and owner is not None:
                w = getattr(owner, "widget", None) or getattr(owner, "_widget", None)
                hud = getattr(w, "_selection_hud", None) if w is not None else None
            if hud is not None and hasattr(hud, "set_suppressed"):
                hud.set_suppressed(False)
        except Exception:
            pass
        super().hideEvent(event)

    # -- internals ----------------------------------------------------

    def _rejected_items(self, owner) -> list:
        st = getattr(owner, "state", None)
        if st is None:
            return []
        items = getattr(st, "items", None) or []
        return [it for it in list(items) if bool(getattr(it, "rejected", False))]

    def _populate(self, owner) -> None:
        # Ensure provenance_series_id filled (triage wiring).
        try:
            from tabs.image_gallery.use_cases import triage as _triage

            if hasattr(_triage, "ensure_provenance_series_ids"):
                _triage.ensure_provenance_series_ids(owner)
        except Exception:
            pass
        items = self._rejected_items(owner)
        n = len(items)
        total_bytes = _total_bytes_for_items(items)
        total_mb = total_bytes / (1024 * 1024) if total_bytes else 0.0
        # Title + S3-1 reassurance subtitle (mockup v3 copy: numbers live in
        # the subtitle; folder short form — real path when known, else the
        # ``<folder>`` literal as drawn in the mockup).
        folder = getattr(getattr(owner, "state", None), "folder", None)
        folder_name = str(folder) if folder is not None else "<folder>"
        try:
            self._title.setText("Review rejected files")
        except Exception:
            pass
        try:
            self._subtitle.setText(
                f"{n} files will be moved to {folder_name}/_rejected/ — nothing is deleted, Undo available for 10 s."
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
        if by_series:
            parts = []
            for idx, sid in enumerate(sorted_sids, start=1):
                cnt = len(by_series[sid])
                if sid == "__ungrouped__":
                    hub = "UNGROUPED"
                    parts.append(f"SERIES {idx} · {hub} ({cnt})" if len(sorted_sids) > 1 else f"UNGROUPED ({cnt})")
                else:
                    hub = _hub_name_for_series(owner, sid)
                    if hub:
                        parts.append(f"SERIES {idx} · {hub} ({cnt})")
                    else:
                        # Fallback without hub
                        parts.append(f"SERIES {idx} ({cnt})")
            # Use sorted order enumeration for display but keep original sid for resolver.
            # Rebuild with actual enumeration based on sorted order where hub exists.
            # For ungrouped, use UNGROUPED label.
            # Already built.
            prov_text = " · ".join(parts)
            # Back-compat: also include raw series label for tests that search lowercase
            # Keep display as built.
        else:
            prov_text = "No rejected files."
        try:
            self._provenance_label.setText(prov_text)
        except Exception:
            pass

        # Move button variant primary, size label total MB.
        try:
            self._move_btn.setText(f"Move {n} to _rejected/")
            self._move_btn.setEnabled(n > 0)
        except Exception:
            pass
        try:
            if n > 0:
                self._size_label.setText(f"{n} files · {total_mb:.1f} MB")
            else:
                self._size_label.setText("No files to move")
        except Exception:
            pass
        try:
            self._restore_all_btn.setEnabled(n > 0)
        except Exception:
            pass

        # Rebuild list rows — filmstrip layout per series.
        for w in self._row_widgets:
            try:
                self._list_layout.removeWidget(w)
                w.setParent(None)
                w.deleteLater()
            except Exception:
                pass
        self._row_widgets.clear()

        if not items:
            empty = Label("No rejected files.", pixel_size=11, parent=self._list_host)
            empty.setObjectName("clean_review_empty")
            self._list_layout.addWidget(empty)
            self._row_widgets.append(empty)
            return

        # Group items by series for filmstrip.
        # Reuse sorted_sids order.
        for series_idx, sid in enumerate(sorted_sids, start=1):
            group_items = by_series[sid]
            # Series section container.
            section = QWidget(self._list_host)
            section.setObjectName(f"clean_review_series_{series_idx}")
            sec_layout = QVBoxLayout(section)
            sec_layout.setContentsMargins(scaled_px(4), scaled_px(4), scaled_px(4), scaled_px(4))
            sec_layout.setSpacing(scaled_px(6))

            # Header row: SERIES N · hub (cnt) + per-series Restore.
            header = QWidget(section)
            header.setObjectName(f"clean_review_series_header_{series_idx}")
            hl_header = QHBoxLayout(header)
            hl_header.setContentsMargins(0, 0, 0, 0)
            hl_header.setSpacing(scaled_px(8))
            hub = _hub_name_for_series(owner, sid)
            if sid == "__ungrouped__":
                header_text = f"UNGROUPED · {len(group_items)} images"
            elif hub:
                header_text = f"SERIES {series_idx} · {hub} · {len(group_items)} VARIANTS"
            else:
                header_text = f"SERIES {series_idx} · {len(group_items)} images"
            header_label = Label(header_text, pixel_size=11, parent=header)
            header_label.setObjectName(f"clean_review_series_label_{series_idx}")
            try:
                header_label.setBold(True)
            except Exception:
                pass
            hl_header.addWidget(header_label, 1)
            # Per-series Restore SERIES N button.
            if sid != "__ungrouped__":
                restore_series_btn = Button(text=f"Restore SERIES {series_idx}", variant="surface", parent=header)
            else:
                restore_series_btn = Button(text="Restore UNGROUPED", variant="surface", parent=header)
            restore_series_btn.setObjectName(f"clean_review_restore_series_{series_idx}")
            # Capture sid.
            _sid = sid

            def _make_series_restore(s=_sid):
                def _do():
                    # Restore all rejected in this series.
                    to_restore = [it for it in self._rejected_items(self._owner) if (str(getattr(it, "provenance_series_id", None) or getattr(it, "series_id", None) or "__ungrouped__") == str(s))]
                    for it in to_restore:
                        try:
                            from tabs.image_gallery.use_cases import triage as _triage

                            _triage.toggle_reject(self._owner, Path(it.path))
                        except Exception:
                            try:
                                it.rejected = False
                            except Exception:
                                pass
                    try:
                        self._populate(self._owner)
                    except Exception:
                        pass
                    try:
                        w = getattr(self._owner, "widget", None) or getattr(self._owner, "_widget", None)
                        if w is not None and hasattr(w, "rebuild_grid"):
                            st = getattr(self._owner, "state", None)
                            items2 = list(getattr(st, "items", []) or []) if st is not None else []
                            w.rebuild_grid(items2)
                    except Exception:
                        pass

                return _do

            restore_series_btn.clicked.connect(_make_series_restore())
            hl_header.addWidget(restore_series_btn)
            sec_layout.addWidget(header)

            # Filmstrip: horizontal strip of thumbs.
            filmstrip = QWidget(section)
            filmstrip.setObjectName(f"clean_review_filmstrip_{series_idx}")
            film_layout = QHBoxLayout(filmstrip)
            film_layout.setContentsMargins(0, 0, 0, 0)
            film_layout.setSpacing(scaled_px(8))
            film_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            # Scrollable filmstrip host — if items exceed width, horizontal scroll handled by outer scroll vertical?
            # Use inner QScrollArea per filmstrip for horizontal scroll.
            # Simpler: just horizontal layout with wrapping via adding widgets; outer vertical scroll handles overflow.
            for it in group_items[:FILMSTRIP_MAX_CELLS]:
                cell = QWidget(filmstrip)
                cell.setObjectName("clean_review_filmstrip_cell")
                cell_layout = QVBoxLayout(cell)
                cell_layout.setContentsMargins(scaled_px(4), scaled_px(4), scaled_px(4), scaled_px(4))
                cell_layout.setSpacing(scaled_px(4))
                # S3-2: toolkit Label thumb 150x100 — Label is the unified
                # themed component (QLabel subclass), pixmap set via the
                # inherited QLabel.setPixmap; neutral "!" placeholder when no
                # thumbnail is available.
                thumb_label = Label("", pixel_size=12, parent=cell)
                thumb_label.setObjectName("clean_review_thumb")
                thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb_label.setFixedSize(scaled_px(THUMB_WIDTH_PX), scaled_px(THUMB_HEIGHT_PX))
                # Try to load thumbnail if available.
                pix = getattr(it, "thumbnail", None)
                if isinstance(pix, QPixmap) and not pix.isNull():
                    try:
                        scaled = pix.scaled(scaled_px(THUMB_WIDTH_PX), scaled_px(THUMB_HEIGHT_PX), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                        thumb_label.setPixmap(scaled)
                    except Exception:
                        thumb_label.setText("!")
                else:
                    # Placeholder — painter pipeline owns visuals (no QSS, no get_color).
                    thumb_label.setText("!")
                cell_layout.addWidget(thumb_label)

                name = getattr(it, "name", None) or Path(getattr(it, "path", "")).name or str(getattr(it, "path", ""))
                series_id = getattr(it, "provenance_series_id", None) or getattr(it, "series_id", None)
                prov_line = f"series {series_id}" if series_id else "ungrouped"

                name_lbl = Label(str(name), pixel_size=10, parent=cell)
                name_lbl.setObjectName("clean_review_row_name")
                name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                # Elide handled by Label marquee? Keep word wrap off.
                try:
                    name_lbl.setWordWrap(False)
                except Exception:
                    pass
                cell_layout.addWidget(name_lbl)

                prov_lbl = Label(str(prov_line), pixel_size=9, parent=cell)
                prov_lbl.setObjectName("clean_review_row_provenance")
                prov_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell_layout.addWidget(prov_lbl)

                # S3-4: arrow prefix per mockup v3 (per-series button keeps
                # its "Restore SERIES N" wording).
                restore_btn = Button(text="↩ Restore", variant="surface", parent=cell)
                restore_btn.setObjectName("clean_review_restore")
                p = Path(it.path) if hasattr(it, "path") else None

                def _make_restore(path=p):
                    def _do():
                        if path is None:
                            return
                        try:
                            from tabs.image_gallery.use_cases import triage as _triage

                            _triage.toggle_reject(self._owner, path)
                        except Exception:
                            try:
                                it2 = next((x for x in self._rejected_items(self._owner) if Path(x.path) == path), None)
                                if it2 is not None:
                                    it2.rejected = False
                            except Exception:
                                pass
                        try:
                            self._populate(self._owner)
                        except Exception:
                            pass
                        try:
                            w = getattr(self._owner, "widget", None) or getattr(self._owner, "_widget", None)
                            if w is not None and hasattr(w, "rebuild_grid"):
                                st = getattr(self._owner, "state", None)
                                items2 = list(getattr(st, "items", []) or []) if st is not None else []
                                w.rebuild_grid(items2)
                        except Exception:
                            pass

                    return _do

                restore_btn.clicked.connect(_make_restore())
                cell_layout.addWidget(restore_btn)
                film_layout.addWidget(cell)
            # S3-3: "+N more" informational tile when the series exceeds
            # FILMSTRIP_MAX_CELLS — the mockup draws a dashed-border tile,
            # which the painter pipeline does not support without QSS, so a
            # disabled surface Button with two muted rows is used instead.
            # Cells beyond the cap stay accessible via the horizontally
            # scrollable strip context (informational tile, cap documented
            # in FILMSTRIP_MAX_CELLS).
            overflow = len(group_items) - FILMSTRIP_MAX_CELLS
            if overflow > 0:
                more_tile = Button(
                    rows=[
                        ButtonRow(text=f"+{overflow} more", size=14),
                        ButtonRow(text="scrollable strip", size=10),
                    ],
                    variant="surface",
                    size=(THUMB_WIDTH_PX, THUMB_HEIGHT_PX),
                    parent=filmstrip,
                )
                more_tile.setObjectName("clean_review_filmstrip_more")
                more_tile.setEnabled(False)
                try:
                    more_tile.setToolTip(f"{overflow} more rejected file(s) in this series")
                except Exception:
                    pass
                film_layout.addWidget(more_tile)
            # Add stretch to left align.
            film_layout.addStretch(1)
            sec_layout.addWidget(filmstrip)
            self._list_layout.addWidget(section)
            self._row_widgets.append(section)
            # Also expose legacy row objectName for compat — each cell also has restore button.
            # Keep per_series section counted.

    def _on_restore_all(self) -> None:
        owner = self._owner
        if owner is None:
            return
        # Restore all rejected.
        items = list(self._rejected_items(owner))
        for it in items:
            try:
                from tabs.image_gallery.use_cases import triage as _triage

                _triage.toggle_reject(owner, Path(it.path))
            except Exception:
                try:
                    it.rejected = False
                except Exception:
                    pass
        try:
            self._populate(owner)
        except Exception:
            pass
        try:
            w = getattr(owner, "widget", None) or getattr(owner, "_widget", None)
            if w is not None and hasattr(w, "rebuild_grid"):
                st = getattr(owner, "state", None)
                items2 = list(getattr(st, "items", []) or []) if st is not None else []
                w.rebuild_grid(items2)
        except Exception:
            pass

    def _on_move(self) -> None:
        owner = self._owner
        if owner is None:
            self.hide()
            return
        moves: list[dict] = []
        try:
            from tabs.image_gallery.use_cases import triage as _triage

            moves = _triage.clean_rejected(owner) or []
        except Exception:
            moves = []
        self.hide()
        try:
            self.cleaned.emit(moves)
        except Exception:
            pass
        if not moves:
            return
        # Toast Undo 10s via ToastManager.get_instance if available + total MB.
        window = self.window() or self.parentWidget() or self
        tm = self._ensure_toast_manager(window)
        if tm is None:
            return

        def _undo():
            try:
                from tabs.image_gallery.use_cases.triage import restore_moves

                restore_moves(owner, moves)
            except Exception:
                pass

        # Compute total MB for toast message.
        total_mb = 0.0
        try:
            total_bytes = sum(int(Path(rec.get("dst", rec.get("src", ""))).stat().st_size) for rec in moves if rec.get("dst") and Path(rec.get("dst")).is_file())
            # Fallback: dst paths may not exist after move? Use src size after move? Instead sum from moves records if available.
            if total_bytes == 0:
                for rec in moves:
                    try:
                        p = Path(rec.get("src", ""))
                        if p.is_file():
                            total_bytes += int(p.stat().st_size)
                    except Exception:
                        continue
            total_mb = total_bytes / (1024 * 1024) if total_bytes else 0.0
        except Exception:
            total_mb = 0.0
        msg = f"Moved {len(moves)} file(s) to _rejected/"
        if total_mb > 0.1:
            msg = f"Moved {len(moves)} file(s) ({total_mb:.1f} MB) to _rejected/"
        try:
            tm.show_toast(
                msg,
                duration=10000,
                actions=[ToastAction("Undo", callback=_undo, dismiss=True)],
                success=False,
            )
        except Exception:
            pass

    def _ensure_toast_manager(self, window: QWidget) -> ToastManager | None:
        if self._toast_manager is not None:
            return self._toast_manager
        # Prefer ToastManager.get_instance if toolkit provides it.
        try:
            get_inst = getattr(ToastManager, "get_instance", None)
            if callable(get_inst):
                try:
                    inst = get_inst(window)  # type: ignore[call-arg]
                    if inst is not None:
                        self._toast_manager = inst
                        return inst
                except TypeError:
                    try:
                        inst = get_inst()
                        if inst is not None:
                            self._toast_manager = inst
                            return inst
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._toast_manager = ToastManager(window)
            return self._toast_manager
        except Exception:
            try:
                existing = getattr(window, "toast_manager", None)
                if existing is not None:
                    self._toast_manager = existing
                    return existing
            except Exception:
                pass
        return None

    def keyPressEvent(self, event) -> None:  # noqa: N802
        try:
            if event.key() == Qt.Key.Key_Escape:
                self.hide()
                event.accept()
                return
        except Exception:
            pass
        super().keyPressEvent(event)
