"""Quick look artifacts — plain functions taking overlay."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px


def rebuild_artifacts(overlay, item) -> None:
    """Rebuild artifact rows — ALL severities incl. clean (W4 item 8).

    Diagnosis for the empty banding visual (W4 item 8): the detector path
    was clean-by-default (``_sev_for`` returns ``"clean"`` for every
    unknown/absent key) and the old code *hid* clean rows and collapsed the
    whole section — so an all-clean item showed no banding base at all,
    and the section vanished. Delivery itself is not racy here:
    ``refresh_artifacts`` rebuilds the open overlay on every artifacts
    delivery (path-guarded, mirrors ``refresh_metrics``). Fix: render every
    row including clean, so the banding base is always visible; keep the
    section host always visible.
    """
    try:
        from tabs.image_gallery.ui.quick_look.helpers import _make_label
    except Exception:
        from sli_ui_toolkit.widgets import Label as _Label

        def _make_label(text="", parent=None, pixel_size=10, pt=None, **kwargs):  # type: ignore
            return _Label(text, pixel_size=pixel_size, parent=parent, **kwargs)

    for w in list(overlay._artifact_rows):
        try:
            overlay._artifacts_layout.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        except Exception:
            pass
    overlay._artifact_rows.clear()
    metrics = getattr(item, "metrics", None) or {}
    if not isinstance(metrics, dict):
        metrics = {}
    artifacts = ["banding", "halo", "over_smoothing", "invented_texture", "blocking", "chroma_fringing", "noise_amplification"]
    artifacts_map: dict[str, str] = {}
    try:
        raw = getattr(item, "artifacts", None)
        if isinstance(raw, dict) and raw:
            for k, v in raw.items():
                try:
                    key = k.value if hasattr(k, "value") else str(k)
                    val = v.value if hasattr(v, "value") else str(v)
                    artifacts_map[str(key).lower()] = str(val).lower()
                except Exception:
                    pass
        ma = metrics.get("artifacts") if isinstance(metrics, dict) else None
        if isinstance(ma, dict):
            for k, v in ma.items():
                lk = str(k).lower()
                if lk not in artifacts_map:
                    try:
                        artifacts_map[lk] = str(v).lower() if not hasattr(v, "value") else str(v.value).lower()
                    except Exception:
                        pass
            if "noise_amp" in ma and "noise_amplification" not in artifacts_map:
                try:
                    v = ma["noise_amp"]
                    artifacts_map["noise_amplification"] = str(v).lower() if not hasattr(v, "value") else str(v.value).lower()
                except Exception:
                    pass
    except Exception:
        pass

    def _sev_for(aid: str) -> str:
        lvl = artifacts_map.get(aid)
        if lvl in ("clean", "mild", "flagged"):
            return lvl
        for mk in (f"{aid}_level", aid, "artifact_level"):
            lvl2 = metrics.get(mk)
            if lvl2 is not None:
                try:
                    s = lvl2.value if hasattr(lvl2, "value") else str(lvl2)
                    s = s.lower()
                    if s in ("clean", "mild", "flagged"):
                        return s
                except Exception:
                    pass
        if aid == "noise_amplification":
            for mk in ("noise_amp_level", "noise_amp"):
                lvl2 = metrics.get(mk)
                if lvl2 is not None:
                    try:
                        s = lvl2.value if hasattr(lvl2, "value") else str(lvl2)
                        s = s.lower()
                        if s in ("clean", "mild", "flagged"):
                            return s
                    except Exception:
                        pass
        if aid == "banding" and metrics.get("banding_score"):
            try:
                sc = float(metrics.get("banding_score"))
                return "flagged" if sc > 0.7 else "mild" if sc > 0.3 else "clean"
            except Exception:
                pass
        return "clean"

    shown: list[tuple[str, str]] = [(aid, _sev_for(aid)) for aid in artifacts]

    for aid, lvl in shown:
        row = QWidget(overlay._artifacts_host)
        rl = QVBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(scaled_px(4))
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(scaled_px(6))
        title_map = {
            "banding": "Banding",
            "halo": "Halo / overshoot",
            "over_smoothing": "Over-smoothing",
            "invented_texture": "Invented texture",
            "blocking": "Blocking",
            "chroma_fringing": "Chroma fringing",
            "noise_amplification": "Noise amplification",
            "noise_amp": "Noise amplification",
        }
        t = _make_label(title_map.get(aid, aid), parent=row, pixel_size=11, pt=11.5)
        header.addWidget(t)
        header.addStretch(1)
        # P0-8: no region analysis exists — never claim one. Severity only.
        lvl_label = {"clean": "clean edges" if aid == "halo" else "clean", "mild": "mild", "flagged": "flagged"}[lvl]
        # S4 mockup severity colors: mild amber, flagged red — single mapping in
        # ui/card/dots.py (frozen seam: no second severity mapping here).
        try:
            from tabs.image_gallery.ui.card.dots import _severity_color as _dots_severity_color

            sev_color = _dots_severity_color(lvl)
        except Exception:
            sev_color = None
        v = _make_label(lvl_label, parent=row, pixel_size=11, pt=11.5, color=sev_color)
        header.addWidget(v)
        rl.addLayout(header)
        if aid == "banding":
            # Banding keeps histogram + base + caption (W4 item 8).
            from tabs.image_gallery.ui.quick_look.histograms import _BandingCombHistogram

            hist = _BandingCombHistogram(severity=lvl, parent=row)
        elif aid == "halo":
            # Halo renders as a horizontal _BarWidget like the metric rows
            # (W4 item 8): severity-mapped fraction in the severity color.
            from tabs.image_gallery.ui.quick_look.bars import _BarWidget

            halo_frac = {"clean": 0.15, "mild": 0.5, "flagged": 0.9}[lvl]
            hist = _BarWidget(fraction=halo_frac, fill_color=sev_color, parent=row)
        else:
            from tabs.image_gallery.ui.quick_look.histograms import _GenericHistogram

            hist = _GenericHistogram(severity=lvl, parent=row)
        rl.addWidget(hist)
        if aid == "banding":
            note = _make_label("gradient histogram — comb spikes = banding steps (sky)", parent=row, pixel_size=9, pt=9)
            rl.addWidget(note)
        overlay._artifacts_layout.addWidget(row)
        overlay._artifact_rows.append(row)
    # W4 item 8: every row renders incl. clean — the section never collapses.
    try:
        overlay._artifacts_host.setVisible(True)
    except Exception:
        pass
