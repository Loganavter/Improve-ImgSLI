"""Quick look artifacts — plain functions taking overlay."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px

# Unified quality view of a categorical artifact: higher = cleaner/better.
_ARTIFACT_QUALITY = {"clean": 100, "mild": 50, "flagged": 15}


def _heatmap_pixmap(rows, px: int = 22):
    """Coarse localization grid (0..1) -> green→yellow→red mini pixmap."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage, QPixmap

    g = len(rows)
    if g <= 0:
        return None
    img = QImage(g, g, QImage.Format.Format_ARGB32)
    for y, row in enumerate(rows):
        for x, value in enumerate(row):
            try:
                v = max(0.0, min(1.0, float(value)))
            except Exception:
                v = 0.0
            r = int(255 * min(1.0, v * 2.0))
            gg = int(255 * min(1.0, (1.0 - v) * 2.0))
            img.setPixelColor(x, y, QColor(r, gg, 0))
    return QPixmap.fromImage(img).scaled(
        px, px, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation
    )
# Positive titles so the row reads like the metric rows (higher = better).
_POSITIVE_ARTIFACT_LABELS = {
    "banding": "Gradients",
    "halo": "Edges",
    "over_smoothing": "Detail",
    "invented_texture": "Texture",
    "blocking": "Blocks",
    "chroma_fringing": "Chroma",
    "noise_amplification": "Clean",
}


def rebuild_artifacts(overlay, item) -> None:
    """Rebuild artifact rows — the mode triple, same three as the card dots.

    The rows mirror ``use_cases/quality.MODE_ARTIFACTS`` for the overlay
    mode (fidelity: banding/halo/blocking; camera: noise/chroma/halo), so
    the dots and the graphs can never disagree on the set. Severities
    resolve through the single source of truth (``use_cases/quality.py``);
    every shown row renders incl. clean (W4 item 8 — hiding clean rows hid
    the banding base on all-clean items). Delivery is not racy here:
    ``refresh_artifacts`` rebuilds the open overlay on every artifacts
    delivery (path-guarded, mirrors ``refresh_metrics``).
    """
    try:
        from tabs.image_gallery.ui.quick_look.helpers import _make_label
    except Exception:
        from sli_ui_toolkit.widgets import Label as _Label

        def _make_label(text="", parent=None, pixel_size=10, pt=None, **kwargs):  # type: ignore
            return _Label(text, pixel_size=pixel_size, parent=parent, **kwargs)

    # Rows live flat in right_lay (see helpers.relayout_report_rows).
    host = getattr(overlay, "_report_host", None)
    lay = getattr(overlay, "_right_lay", None)
    # Same triple as the card dots (use_cases/quality.MODE_ARTIFACTS). The
    # severity is the CURRENT domain's read (plan-gallery-ai-backend-owns-
    # quality): the AI domain shows the VLM's reported defects, Algorithms the
    # local source-anchored detector severities — never both.
    try:
        from tabs.image_gallery.services import quality_read as _quality_read
        from tabs.image_gallery.ui.quick_look.metrics import _overlay_judgment_domain

        domain = _overlay_judgment_domain(overlay)
    except Exception:
        _quality_read = None  # type: ignore[assignment]
        domain = "algorithms"
    try:
        from tabs.image_gallery.use_cases import quality as _quality

        artifacts = list(_quality.MODE_ARTIFACTS[_quality.normalize_mode(getattr(overlay, "_mode", None))])
        if _quality_read is not None:
            shown = [(aid, _quality_read.domain_artifact_severity(item, aid, domain=domain)) for aid in artifacts]
        else:
            shown = [(aid, _quality.severity(item, aid)) for aid in artifacts]
    except Exception:
        artifacts = ["banding", "halo"]
        shown = [(aid, "clean") for aid in artifacts]
    # Drop rows that duplicate a measured metric (noise) or are unreliable:
    # in camera mode the no-reference halo/chroma detectors are blind to thin
    # rims (they average out under the detector's downscale), so hide them —
    # the source-relative fidelity rows carry halo/chroma where a source exists.
    _drop = {"noise_amplification"}
    try:
        from tabs.image_gallery.use_cases import quality as _q

        if _q.normalize_mode(getattr(overlay, "_mode", None)) == "camera":
            _drop |= {"chroma_fringing", "halo"}
    except Exception:
        pass
    shown = [(aid, sev) for aid, sev in shown if aid not in _drop]
    # The change key is the shown (artifact, severity) pairs — the domain's read
    # already resolved into them, so a domain switch changes the key and rebuilds.
    shown_key = [(aid, lvl) for aid, lvl in shown]


    # Delivery handlers fire per worker result: rebuilding identical rows
    # (widget teardown + creation + layout activation) in the same tick as
    # the grid repaint storm stalls the loop. Skip when nothing changed.
    try:
        if list(getattr(overlay, "_artifact_sevs", None) or []) == shown_key:
            return
    except Exception:
        pass
    try:
        overlay._artifact_sevs = list(shown_key)
    except Exception:
        pass
    for w in list(overlay._artifact_rows):
        try:
            if lay is not None:
                lay.removeWidget(w)
            # Hide before orphaning (stillborn-toplevel guard).
            w.hide()
            w.setParent(None)
            w.deleteLater()
        except Exception:
            pass
    overlay._artifact_rows.clear()

    for aid, lvl in shown:
        row = QWidget(host)
        rl = QVBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(scaled_px(6))  # label→bar gap (W5 fit budget checked)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(scaled_px(6))
        # Unified 0-100% quality, same reading as the metric rows above:
        # POSITIVE label + NN%, higher always better. Severity maps to a
        # quality score (clean 100 / mild 50 / flagged 15); the value/bar
        # color reuses the single severity mapping (ui/card/dots.py).
        label = _POSITIVE_ARTIFACT_LABELS.get(aid, aid)
        _tr_ov = getattr(overlay, "_tr", None)
        if callable(_tr_ov):
            try:
                label = str(_tr_ov(f"image_gallery.artifact.{aid}", label))
            except Exception:
                pass
        score = _ARTIFACT_QUALITY.get(lvl, 100)
        # A localized band descriptor for the row (same helper the metric rows
        # use, ``image_gallery.metric_note.<aid>.<band>`` — no second key set).
        # The severity itself is already the current domain's read (see above).
        try:
            from tabs.image_gallery.ui.quick_look.metrics import _metric_note

            _note = _metric_note(overlay, aid, score)
        except Exception:
            _note = ""
        if _note:
            label = f"{label} — {_note}"
        try:
            from tabs.image_gallery.ui.card.dots import _severity_color as _dots_severity_color

            sev_color = _dots_severity_color(lvl)
        except Exception:
            sev_color = None
        t = _make_label(label, parent=row, pixel_size=11, pt=11.5)
        header.addWidget(t)
        # Coarse localization map (where the artifact fired) when available.
        try:
            _hm = item.artifact_maps.get(aid) if isinstance(getattr(item, "artifact_maps", None), dict) else None
        except Exception:
            _hm = None
        if _hm:
            try:
                from PySide6.QtWidgets import QLabel as _QLabel

                _hm_lbl = _QLabel(row)
                _hm_lbl.setPixmap(_heatmap_pixmap(_hm))
                _tip = (
                    "Where this artifact is strongest — coarse 5×5 grid:\n"
                    "green = none · yellow = mild · red = strongest"
                )
                _tr_overlay = getattr(overlay, "_tr", None)
                if callable(_tr_overlay):
                    try:
                        _tip = _tr_overlay("image_gallery.quick_look.artifact_grid_tooltip", _tip)
                    except Exception:
                        pass
                _hm_lbl.setToolTip(_tip)
                header.addWidget(_hm_lbl)
            except Exception:
                pass
        header.addStretch(1)
        v = _make_label(f"{score}%", parent=row, pixel_size=11, pt=11.5, color=sev_color)
        header.addWidget(v)
        rl.addLayout(header)
        from tabs.image_gallery.ui.quick_look.bars import _BarWidget

        rl.addWidget(_BarWidget(fraction=score / 100.0, fill_color=sev_color, parent=row))
        overlay._artifact_rows.append(row)
    # Flat placement (rows + uniform spacers) is owned by the coordinator.
    try:
        from tabs.image_gallery.ui.quick_look.helpers import relayout_report_rows

        relayout_report_rows(overlay)
    except Exception:
        pass
    # W5: both mockup rows render incl. clean — the section never collapses
    # (rows are always appended above, even with no measurements).
