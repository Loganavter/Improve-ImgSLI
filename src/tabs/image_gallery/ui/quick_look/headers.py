"""Quick look report + series headers — plain functions (no owner state).

Extracted verbatim from ``helpers.py`` per CODE_PATTERNS.md thin owner + ui/.
"""

from __future__ import annotations


def populate_report_header(overlay, is_fidelity: bool, mode_str: str) -> None:
    try:
        if is_fidelity:
            # Decluttered: the report is self-evident — no "Fidelity report"
            # title and no "vs SOURCE <name>" subtitle (the metric rows and
            # the strip carry identity). Hide both, whatever the item.
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
                tr = getattr(overlay, "_tr", None)

                def _t(key: str, default: str) -> str:
                    if callable(tr):
                        try:
                            return tr(key, default)
                        except Exception:
                            return default
                    return default

                overlay._report_title.setText(
                    _t("image_gallery.quick_look.report_title", "Batch report")
                )
                overlay._report_sub.setText(
                    _t(
                        "image_gallery.quick_look.report_sub",
                        "distance to centroid · artifact flags",
                    )
                )
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


def _ql_note(overlay, key: str, default: str, **fmt) -> str:
    """Localized Quick Look note (``image_gallery.quick_look.<key>``), fail-open.

    ``overlay._tr`` is the injected tab translator; a missing/non-callable one
    (or a miss) keeps the EN ``default``. ``**fmt`` fills ``{n}``-style
    placeholders in the resolved text.
    """
    text = default
    tr = getattr(overlay, "_tr", None)
    if callable(tr):
        try:
            text = str(tr(f"image_gallery.quick_look.{key}", default))
        except Exception:
            text = default
    if fmt:
        try:
            text = text.format(**fmt)
        except Exception:
            pass
    return text


def _size_note(overlay, items) -> str:
    """Size tracker: 'mixed sizes' when members differ, '' otherwise/unknown.

    A uniform series is the expected case and the viewing item's dims are
    already the first part of the meta line, so the old ``same size WxH``
    note only repeated them (and doubled the fidelity ``same size as
    source`` claim) — dropped. Only the non-obvious ``mixed sizes`` signal
    remains (localized via ``image_gallery.quick_look.mixed_sizes``).
    """
    dims_list = [_member_dims(m) for m in items]
    if not dims_list or any(d is None for d in dims_list):
        return ""
    first = dims_list[0]
    if all(d == first for d in dims_list):
        return ""
    return _ql_note(overlay, "mixed_sizes", "mixed sizes")


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
                    parts.append(
                        _ql_note(
                            overlay,
                            "upscales_note",
                            "{n} upscales of one source",
                            n=n,
                        )
                    )
            except Exception:
                pass
        size_note = _size_note(overlay, items)
        if size_note:
            parts.append(size_note)
        return " · ".join(parts)
    except Exception:
        return ""
