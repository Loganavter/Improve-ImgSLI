"""Quick look report + series headers — plain functions (no owner state).

Extracted verbatim from ``helpers.py`` per CODE_PATTERNS.md thin owner + ui/.
"""

from __future__ import annotations

from pathlib import Path


def populate_report_header(overlay, is_fidelity: bool, mode_str: str) -> None:
    try:
        if is_fidelity:
            overlay._report_title.setText("Fidelity report")
            src_name = Path(overlay._source_path).name if overlay._source_path is not None else "source"
            overlay._report_sub.setText(f"vs SOURCE {src_name} · shared/analysis engine")
            for w in (overlay._report_title, overlay._report_sub):
                try:
                    w.setVisible(True)
                except Exception:
                    pass
        else:
            if "CAMERA" in mode_str:
                # No header labels in camera mode (rows are self-evident).
                for w in (overlay._report_title, overlay._report_sub):
                    try:
                        w.setText("")
                    except Exception:
                        pass
                    try:
                        w.hide()
                    except Exception:
                        pass
            else:
                overlay._report_title.setText("Batch report")
                overlay._report_sub.setText("distance to centroid · artifact flags")
                for w in (overlay._report_title, overlay._report_sub):
                    try:
                        w.setVisible(True)
                    except Exception:
                        pass
    except Exception:
        pass


def _member_dims(item) -> tuple[int, int] | None:
    """Member dimensions: metrics width/height first, QImageReader fast path."""
    try:
        metrics = getattr(item, "metrics", None)
        if isinstance(metrics, dict):
            w = metrics.get("width")
            h = metrics.get("height")
            if w and h:
                return int(w), int(h)
    except Exception:
        pass
    try:
        from tabs.image_gallery.ui.quick_look.preview import _fast_image_size

        dims = _fast_image_size(getattr(item, "path", ""))
        if dims is not None:
            return dims
    except Exception:
        pass
    return None


def _size_note(items) -> str:
    """Size tracker: 'same size WxH' / 'mixed sizes' / '' when unknown."""
    dims_list = [_member_dims(m) for m in items]
    if not dims_list or any(d is None for d in dims_list):
        return ""
    first = dims_list[0]
    if all(d == first for d in dims_list):
        return f" · same size {first[0]}×{first[1]}"
    return " · mixed sizes"


def populate_series_header(overlay, owner=None) -> None:
    """S4 mockup series context: ``Series 1 · <hub>`` + fidelity subline.

    *owner* is the explicit triage owner (threaded from the overlay's
    ``show_for``); when None, falls back to the overlay's stored owner for
    direct unit calls (back-compat — production always passes it).
    """
    try:
        items = list(overlay._series_items or [])
        n = len(items)
        cur = getattr(overlay, "_current_item", None)
        # 1-based cluster index among the owner's series (display only —
        # triage ownership stays in use_cases/wave A, never duplicated here).
        idx = 1
        try:
            if owner is None:
                try:
                    owner = overlay._owner
                except Exception:
                    owner = None
            series_raw = getattr(getattr(owner, "state", None), "series", None)
            if series_raw:
                clusters: list[list] = []
                for entry in list(series_raw):
                    if hasattr(entry, "members"):
                        clusters.append(list(getattr(entry, "members") or []))
                    elif isinstance(entry, (list, tuple)):
                        clusters.append(list(entry))
                if clusters and cur is not None:
                    try:
                        cur_path = Path(getattr(cur, "path", ""))
                        for i, cl in enumerate(clusters):
                            if any(Path(getattr(m, "path", "")) == cur_path for m in cl):
                                idx = i + 1
                                break
                    except Exception:
                        pass
        except Exception:
            pass
        # Hub label: source stem when a source is set, else the first member
        # stem of the viewing cluster (a real member, never invented).
        hub = ""
        try:
            src = getattr(overlay, "_source_path", None)
            if src is not None:
                hub = Path(src).stem
            elif items:
                hub = Path(getattr(items[0], "path", "")).stem
        except Exception:
            pass
        if n > 1:
            overlay._series_header.setText(f"Series {idx} · {hub}" if hub else f"Series {idx}")
        else:
            overlay._series_header.setText("Single")
        rejected_cnt = sum(1 for m in items if bool(getattr(m, "rejected", False)))
        pending = sum(1 for m in items if bool(getattr(m, "vlm_tie_pending", False)))
        if n > 1:
            try:
                is_fidelity = bool(getattr(overlay, "_source_path", None) is not None)
            except Exception:
                is_fidelity = False
            size_note = _size_note(items)
            if is_fidelity:
                # Honest label: "upscales" only when members are actually
                # larger than the source (long side). Same-size FullHD sets
                # or unknown dims are "images", never fabricated upscales.
                label = f"{n} images of one source"
                try:
                    from tabs.image_gallery.ui.quick_look.preview import _fast_image_size

                    src_dims = _fast_image_size(getattr(overlay, "_source_path", ""))
                    member_dims = [_member_dims(m) for m in items]
                    if (
                        src_dims is not None
                        and member_dims
                        and all(d is not None for d in member_dims)
                        and all(max(d[0], d[1]) > max(src_dims[0], src_dims[1]) for d in member_dims)  # type: ignore[index]
                    ):
                        label = f"{n} upscales of one source"
                except Exception:
                    pass
                sub = f"{label} · {rejected_cnt} rejected{size_note}"
            else:
                sub = f"{n} images · {rejected_cnt} rejected{size_note}"
            if pending:
                sub += f" · {pending} tie-break pending"
            overlay._series_sub.setText(sub)
        else:
            overlay._series_sub.setText("ungrouped")
    except Exception:
        pass
