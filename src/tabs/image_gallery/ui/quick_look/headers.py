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
        else:
            if "CAMERA" in mode_str:
                overlay._report_title.setText("Camera report")
                overlay._report_sub.setText("sharpness / exposure profile · local metrics")
            else:
                overlay._report_title.setText("Batch report")
                overlay._report_sub.setText("distance to centroid · artifact flags")
    except Exception:
        pass


def populate_series_header(overlay) -> None:
    """S4 mockup series context: ``Series 1 · <hub>`` + fidelity subline."""
    try:
        items = list(overlay._series_items or [])
        n = len(items)
        cur = getattr(overlay, "_current_item", None)
        # 1-based cluster index among the owner's series (display only —
        # triage ownership stays in use_cases/wave A, never duplicated here).
        idx = 1
        try:
            owner = getattr(overlay, "_owner", None)
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
            if is_fidelity:
                sub = f"{n} upscales of one source · rank by fidelity · {rejected_cnt} rejected"
            else:
                sub = f"rank by fidelity · {rejected_cnt} rejected"
            if pending:
                sub += f" · {pending} tie-break pending"
            overlay._series_sub.setText(sub)
        else:
            overlay._series_sub.setText("ungrouped")
    except Exception:
        pass
