"""Quick look report + series headers — plain functions (no owner state).

Extracted verbatim from ``helpers.py`` per CODE_PATTERNS.md thin owner + ui/.
"""

from __future__ import annotations

from pathlib import Path


def populate_report_header(overlay, is_fidelity: bool, mode_str: str) -> None:
    try:
        if is_fidelity:
            # Viewing the source itself → this is not a comparison report.
            _is_source = False
            try:
                _sp = getattr(overlay, "_source_path", None)
                _cur = getattr(overlay, "_current_item", None)
                _is_source = _sp is not None and _cur is not None and Path(getattr(_cur, "path", "")) == Path(_sp)
            except Exception:
                _is_source = False
            if _is_source:
                # The source is the reference — no comparison report at all.
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
                overlay._report_title.setText("Fidelity report")
                src_name = Path(overlay._source_path).name if overlay._source_path is not None else "source"
                overlay._report_sub.setText(f"vs SOURCE {src_name}")
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
    """Size tracker: 'mixed sizes' when members differ, '' otherwise/unknown.

    A uniform series is the expected case and the viewing item's dims are
    already the first part of the meta line, so the old ``same size WxH``
    note only repeated them (and doubled the fidelity ``same size as
    source`` claim) — dropped. Only the non-obvious ``mixed sizes`` signal
    remains.
    """
    dims_list = [_member_dims(m) for m in items]
    if not dims_list or any(d is None for d in dims_list):
        return ""
    first = dims_list[0]
    if all(d == first for d in dims_list):
        return ""
    return "mixed sizes"


def series_size_note(overlay) -> str:
    """Series size/upscale note for the filename meta line (sidebar top).

    Multi-item series only: fidelity members larger than the source read
    ``"N upscales of one source"``; a series whose members differ in size
    adds ``"mixed sizes"`` (a uniform series adds nothing — its dims are
    already on the line). Counts and rejected tallies are deliberately
    excluded (user-facing series chrome is gone — the strip carries
    identity now).
    """
    try:
        items = list(getattr(overlay, "_series_items", None) or [])
        n = len(items)
        if n <= 1:
            return ""
        try:
            is_fidelity = bool(getattr(overlay, "_source_path", None) is not None)
        except Exception:
            is_fidelity = False
        parts: list[str] = []
        if is_fidelity:
            # Honest label: "upscales" only when members are actually
            # larger than the source (long side).
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
                    parts.append(f"{n} upscales of one source")
            except Exception:
                pass
        size_note = _size_note(items)
        if size_note:
            parts.append(size_note)
        return " · ".join(parts)
    except Exception:
        return ""
