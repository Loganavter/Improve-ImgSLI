"""QuickLookOverlay populate — ``_populate`` + series resolve + ``_walk``.

Moved verbatim from ``ui/quick_look.py`` (plan-gallery-split-2026-10-17,
Part C2). Plain functions taking the overlay as their first argument; the
class keeps same-named one-line delegators. The section helpers live in
``quick_look/helpers`` (labels/chrome, preview, meta, headers); metrics /
artifacts / strip rebuild through the overlay's own delegators.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.ui.quick_look.helpers import _set_colored_text


def _resolve_series(self, item, series_raw, all_items=None) -> list:
    """Cluster for *item*: its series, or the ungrouped group.

    Multi-member cluster wins. A singleton cluster (or no cluster at
    all) falls back to the ungrouped group — every item outside a
    multi-member cluster, in folder order — so the strip and the nav
    arrows keep working instead of stranding one lonely thumb. The
    grid shows singles under its UNGROUPED tail the same way.
    """
    if series_raw is None:
        try:
            series_raw = getattr(self._owner, "_series", None) if self._owner is not None else None
        except Exception:
            series_raw = None
    normalized: list[list] = []
    if series_raw:
        for entry in list(series_raw):
            if hasattr(entry, "members"):
                members = list(getattr(entry, "members") or [])
            elif isinstance(entry, (list, tuple)):
                members = list(entry)
            else:
                members = [entry]
            if members:
                normalized.append(members)
    try:
        cur_path = Path(getattr(item, "path", ""))
    except Exception:
        cur_path = None
        if normalized:
            return normalized[0] if normalized else [item]
        return [item]
    for cl in normalized:
        try:
            if any(Path(getattr(m, "path", "")) == cur_path for m in cl):
                if len(cl) > 1:
                    return list(cl)
                break  # singleton cluster → ungrouped group below
        except Exception:
            continue
    try:
        grouped = set()
        for cl in normalized:
            if len(cl) <= 1:
                continue
            for m in cl:
                try:
                    grouped.add(Path(getattr(m, "path", "")))
                except Exception:
                    continue
        pool = list(all_items) if all_items else [item]
        ungrouped = []
        for m in pool:
            try:
                if Path(getattr(m, "path", "")) not in grouped:
                    ungrouped.append(m)
            except Exception:
                continue
        if len(ungrouped) > 1:
            return ungrouped
    except Exception:
        pass
    return [item]


def _populate(self) -> None:
    import time as _time

    from tabs.image_gallery.debug import gallery_debug as _dbg
    from tabs.image_gallery.debug import gallery_debug_enabled as _dbg_enabled

    _dbg_on = _dbg_enabled()
    _tp0 = _time.perf_counter() if _dbg_on else 0.0
    item = self._current_item
    if item is None:
        return
    # Hydrate the cached analysis BEFORE the report rebuild: the
    # Composition metric row reads ``item.analysis`` and must be on the
    # item by then (otherwise a cached analysis opens without the row).
    # Per-axis AI notes no longer render on rows (plan-gallery-ai-quality
    # UX contract).
    try:
        if getattr(item, "analysis", None) is None:
            _owner = getattr(self, "_owner", None)
            _hydrate = getattr(_owner, "hydrate_cached_analysis", None)
            if callable(_hydrate):
                _hydrate(item)
    except Exception:
        pass
    # Explicit triage owner for the populate helpers (G3: helpers take
    # owner instead of reading the private attr).
    try:
        _populate_owner = self._owner
    except Exception:
        _populate_owner = None
    # Populate-next lifecycle: walk-step release (memos survive the walk;
    # hide/close take the full release). No fd/memmap leaks across walks;
    # no-op label-only.
    try:
        self._release_preview_resources(for_walk=True)
    except Exception:
        pass
    mode_str = ""
    try:
        if self._mode is not None:
            mode_str = str(self._mode.value) if hasattr(self._mode, "value") else str(self._mode)
        else:
            mode_str = "fidelity"
        mode_str = mode_str.upper()
        if not mode_str.endswith(" MODE"):
            mode_str = f"{mode_str} MODE"
    except Exception:
        mode_str = "FIDELITY MODE"
    is_fidelity = "FIDELITY" in mode_str
    # Delegate populated sections
    if _dbg_on:
        _tp_sections = _time.perf_counter()
    try:
        from tabs.image_gallery.ui.quick_look.helpers import (
            populate_brief,
            populate_filename_meta,
            populate_preview,
            populate_report_header,
            populate_source_inset,
        )
        if _dbg_on:
            _t = _time.perf_counter()
        populate_preview(self, item)
        if _dbg_on:
            _dbg("quick look populate preview=%.1fms path=%s", (_time.perf_counter() - _t) * 1000.0, getattr(item, "path", item))
            _t = _time.perf_counter()
        populate_source_inset(self, item, is_fidelity, _populate_owner)
        if _dbg_on:
            _dbg("quick look populate source-inset=%.1fms", (_time.perf_counter() - _t) * 1000.0)
            _t = _time.perf_counter()
        populate_filename_meta(self, item, is_fidelity, _populate_owner)
        if _dbg_on:
            _dbg("quick look populate filename-meta=%.1fms", (_time.perf_counter() - _t) * 1000.0)
            _t = _time.perf_counter()
        populate_report_header(self, is_fidelity, mode_str)
        if _dbg_on:
            _dbg("quick look populate report-header=%.1fms", (_time.perf_counter() - _t) * 1000.0)
    except Exception:
        pass
    if _dbg_on:
        _t = _time.perf_counter()
    self._rebuild_metrics(item, is_fidelity, mode_str)
    if _dbg_on:
        _dbg("quick look populate metrics=%.1fms", (_time.perf_counter() - _t) * 1000.0)
        _t = _time.perf_counter()
    self._rebuild_artifacts(item)
    if _dbg_on:
        _dbg("quick look populate artifacts=%.1fms", (_time.perf_counter() - _t) * 1000.0)
        _t = _time.perf_counter()
    try:
        from tabs.image_gallery.ui.quick_look.helpers import populate_brief as _pb
        _pb(self, item)
    except Exception:
        pass
    if _dbg_on:
        _dbg("quick look populate brief=%.1fms", (_time.perf_counter() - _t) * 1000.0)
        _t = _time.perf_counter()
    self._rebuild_strip()
    if _dbg_on:
        _dbg(
            "quick look populate strip=%.1fms n_series=%d n_thumbs=%d total_populate=%.1fms",
            (_time.perf_counter() - _t) * 1000.0,
            len(self._series_items),
            len(getattr(self, "_strip_buttons", [])),
            (_time.perf_counter() - _tp0) * 1000.0,
        )
    try:
        has_series = len(self._series_items) > 1
        self._prev_btn.setEnabled(bool(has_series))
        self._next_btn.setEnabled(bool(has_series))
    except Exception:
        pass
    try:
        # Always available (every mode): set-as-source from camera/batch
        # switches to fidelity; on the current source it reads "Unset".
        self._set_source_btn.setVisible(True)
        is_src = (
            self._source_path is not None
            and Path(getattr(item, "path", "")) == Path(self._source_path)
        )
        if callable(_set_colored_text):
            _set_colored_text(
                self._set_source_btn,
                self._t("image_gallery.quick_look.unset_source", "Unset")
                if is_src
                else self._t("image_gallery.action.set_as_source", "Set as source"),
                None,
            )
    except Exception:
        pass
    try:
        rejected = bool(getattr(item, "rejected", False))
        if callable(_set_colored_text):
            _set_colored_text(
                self._reject_btn,
                self._t("image_gallery.quick_look.restore", "Restore")
                if rejected
                else f'✕ {self._t("image_gallery.quick_look.reject", "Reject")}',
                None,
            )
    except Exception:
        pass
    try:
        _cmp = getattr(self, "_compare_btn", None)
        if _cmp is not None:
            _cmp.setEnabled(True)
        _mlt = getattr(self, "_multi_btn", None)
        if _mlt is not None:
            _mlt.setEnabled(True)
    except Exception:
        pass
    # W4 item 6: best-effort nav pin after populate (resizeEvent re-pins
    # once live geometry lands).
    try:
        from tabs.image_gallery.ui.quick_look.helpers import reposition_nav_buttons
        reposition_nav_buttons(self)
    except Exception:
        pass
    # W8: pin the resize grip with the other absolute card children
    # (the _content Resize filter re-pins on every later resize).
    try:
        from tabs.image_gallery.ui.quick_look.helpers import reposition_grip
        reposition_grip(self)
    except Exception:
        pass
    # Modal stacking: stay above window siblings (toasts/flyouts) while
    # visible — a popup grab (card menu) still wins, by Qt design.
    try:
        if self.isVisible():
            self.raise_()
    except Exception:
        pass


def _walk(self, delta: int) -> None:
    if not self._series_items or len(self._series_items) <= 1:
        return
    n = len(self._series_items)
    self._current_idx = (self._current_idx + delta) % n
    try:
        self._current_item = self._series_items[self._current_idx]
    except Exception:
        return
    self._populate()
