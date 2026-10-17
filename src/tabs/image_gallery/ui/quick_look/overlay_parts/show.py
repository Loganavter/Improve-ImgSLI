"""QuickLookOverlay show/refresh — ``show_for`` + ``refresh_*`` + rebuilds.

Moved verbatim from ``ui/quick_look.py`` (plan-gallery-split-2026-10-17,
Part C2). Plain functions taking the overlay as their first argument; the
class keeps same-named one-line delegators.

The rebuild one-liners (``_rebuild_metrics`` / ``_rebuild_artifacts`` /
``_ssim_subline`` / ``_rebuild_strip``) are the metric/artifact/strip
seams: each lazily imports its concern module and no-ops fail-open.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt


def show_for(self, item, owner=None) -> None:
    import time as _time

    from tabs.image_gallery.debug import gallery_debug as _dbg
    from tabs.image_gallery.debug import gallery_debug_enabled as _dbg_enabled

    _dbg_on = _dbg_enabled()
    _t0 = _time.perf_counter() if _dbg_on else 0.0
    if _dbg_on:
        try:
            _dbg("quick look show_for begin path=%s", getattr(item, "path", item))
        except Exception:
            pass
    if owner is not None:
        # Explicit owner from the caller (see __init__ note): the only
        # re-assignment point besides construction.
        self._owner = owner
    try:
        self._ql_chrome_painted = False
    except Exception:
        pass
    self._current_item = item
    # Remember the opener for the close path: focus must land back on the card
    # the panel was opened from, and that card can be recycled while the panel
    # is open — the stable identity is the item's path
    # (quick_look/focus_restore.py, restored by the lifecycle's nav exit).
    try:
        from tabs.image_gallery.ui.quick_look import focus_restore as _focus_restore

        _focus_restore.remember_opener(self, item)
    except Exception:
        pass
    # Modal input grab: never disabled, never mouse-transparent — while
    # visible every press lands here (veil dismiss or card swallow),
    # never in the gallery beneath.
    try:
        self.setEnabled(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
    except Exception:
        pass
    owner = self._owner
    mode_val = source = series_raw = None
    all_items = None
    try:
        st = getattr(owner, "state", None) if owner is not None else None
        if st is not None:
            mode_val = getattr(st, "mode", None)
            source = getattr(st, "source_path", None)
            series_raw = getattr(st, "series", None)
            all_items = getattr(st, "items", None)
        else:
            mode_val = getattr(owner, "_mode", None) if owner is not None else None
            source = getattr(owner, "_source_path", None) if owner is not None else None
            series_raw = getattr(owner, "_series", None) if owner is not None else None
    except Exception:
        pass
    self._mode = mode_val
    self._source_path = Path(source) if source is not None else None
    if _dbg_on:
        _t_state = _time.perf_counter()
    self._series_items = self._resolve_series(item, series_raw, all_items)
    self._current_idx = 0
    try:
        for i, m in enumerate(self._series_items):
            if Path(getattr(m, "path", "")) == Path(getattr(item, "path", "")):
                self._current_idx = i
                break
    except Exception:
        pass
    if _dbg_on:
        _t_series = _time.perf_counter()
        _dbg(
            "quick look show_for phase state-resolve=%.1fms series-resolve=%.1fms n_series=%d",
            (_t_state - _t0) * 1000.0,
            (_t_series - _t_state) * 1000.0,
            len(self._series_items),
        )
        _t_pop = _time.perf_counter()
    self._populate()
    if _dbg_on:
        _t_pop_done = _time.perf_counter()
        _dbg(
            "quick look show_for phase populate=%.1fms total=%.1fms",
            (_t_pop_done - _t_pop) * 1000.0,
            (_t_pop_done - _t0) * 1000.0,
        )
    self.show()
    try:
        self.raise_()
        self.setFocus(Qt.FocusReason.PopupFocusReason)
    except Exception:
        pass
    # Re-assert the modal input grab AFTER show: populate-time rebuilds
    # must never leave the overlay disabled/transparent (a visible but
    # hit-test-invisible veil passes every press to the gallery beneath
    # while looking modal — clicks select behind it, X/veil go dead).
    try:
        self.setEnabled(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
    except Exception:
        pass
    if _dbg_on:
        try:
            from PySide6.QtWidgets import QApplication as _QA2

            _app2 = _QA2.instance()
            _grab = None
            try:
                from PySide6.QtWidgets import QWidget as _QW2

                _grab = _QW2.mouseGrabber()
            except Exception:
                pass
            _dbg(
                "quick look show input grabber=%s focus=%s active=%s",
                type(_grab).__name__ if _grab is not None else None,
                type(_app2.focusWidget()).__name__ if _app2 is not None and _app2.focusWidget() is not None else None,
                type(_app2.activeWindow()).__name__ if _app2 is not None and _app2.activeWindow() is not None else None,
            )
        except Exception:
            pass
    if _dbg_on:
        _t_show = _time.perf_counter()
    try:
        self.show_overlay()
    except Exception:
        pass
    if _dbg_on:
        _t_overlay = _time.perf_counter()
        _dbg(
            "quick look show_for phase show=%.1fms show_overlay=%.1fms",
            (_t_show - _t_pop_done) * 1000.0,
            (_t_overlay - _t_show) * 1000.0,
        )
    # Post-show re-pin: base reposition() recenters the card AFTER
    # _populate ran on stale pre-show geometry, and overlay-child nav
    # circles are unknown to it — re-run the pin hooks on live geometry
    # (same idiom as resizeEvent/eventFilter), or arrows/inset/grip keep
    # the previous opening's coordinates on reopen.
    try:
        self._reposition_source_inset()
    except Exception:
        pass
    try:
        from tabs.image_gallery.ui.quick_look.helpers import reposition_grip

        reposition_grip(self)
    except Exception:
        pass
    # The overlay owns its keys through the app's navigation model while it is
    # visible: a ToolbarRowsSection over [strip row, action bar] — ←/→ move the
    # focus ring along a row, ↓/↑ cross the rows, Enter activates the focused
    # button (quick_look/nav_section.py). Registered LAST, after show_overlay()
    # has taken its own focus grab: register() lands the ring on the item
    # already on screen, and the manager's deferred owner-bootstrap only fires
    # while the bare owner holds focus — with the registration earlier, the
    # grab that lands after it left the ring on the FIRST thumb on reopen (found
    # while writing quick_look's navigation tests, 2026-10-17).
    try:
        from tabs.image_gallery.ui.quick_look import nav_section as _nav

        _nav.register(self)
    except Exception:
        pass
    if _dbg_on:
        _dbg(
            "quick look show_for done total=%.1fms repin=%.1fms path=%s",
            (_time.perf_counter() - _t0) * 1000.0,
            (_time.perf_counter() - _t_overlay) * 1000.0,
            getattr(item, "path", item),
        )


def show_quick_look(self, item, owner=None) -> None:
    self.show_for(item, owner)


def refresh_artifacts(self, item) -> None:
    try:
        cur = getattr(self, "_current_item", None)
        if cur is None:
            return
        try:
            if Path(getattr(cur, "path", "")) != Path(getattr(item, "path", "")):
                return
        except Exception:
            if cur is not item:
                return
        if not self.isVisible():
            return
        self._rebuild_artifacts(item)
    except Exception:
        pass


def refresh_metrics(self, item) -> None:
    """W1 seam — W2 calls this from ``_on_fidelity_ready`` / set-source paths.

    Mirrors ``refresh_artifacts``: rebuilds metrics + meta + brief for the
    open overlay (no reopen needed when fidelity numbers land); no-op when
    hidden or for another item. Never copied between items (path-guarded).
    """
    try:
        cur = getattr(self, "_current_item", None)
        if cur is None:
            return
        try:
            if Path(getattr(cur, "path", "")) != Path(getattr(item, "path", "")):
                return
        except Exception:
            if cur is not item:
                return
        if not self.isVisible():
            return
        try:
            self._current_item = item
        except Exception:
            pass
        # Re-read mode from owner state (W2 may have flipped it, e.g.
        # set-as-source → FIDELITY) before rebuilding.
        try:
            owner = getattr(self, "_owner", None)
            st = getattr(owner, "state", None) if owner is not None else None
            if st is not None and getattr(st, "mode", None) is not None:
                self._mode = st.mode
        except Exception:
            pass
        mode_str = "FIDELITY MODE"
        try:
            mode = getattr(self, "_mode", None)
            if mode is not None:
                mode_str = str(mode.value) if hasattr(mode, "value") else str(mode)
            mode_str = mode_str.upper()
            if not mode_str.endswith(" MODE"):
                mode_str = f"{mode_str} MODE"
        except Exception:
            pass
        is_fidelity = "FIDELITY" in mode_str
        try:
            from tabs.image_gallery.ui.quick_look.helpers import (
                populate_brief,
                populate_filename_meta,
            )

            populate_filename_meta(self, item, is_fidelity, getattr(self, "_owner", None))
        except Exception:
            pass
        self._rebuild_metrics(item, is_fidelity, mode_str)
        try:
            from tabs.image_gallery.ui.quick_look.helpers import populate_brief as _pb

            _pb(self, item)
        except Exception:
            pass
    except Exception:
        pass


def refresh_quick_look(self, item) -> None:
    self.refresh_artifacts(item)


def _rebuild_metrics(self, item, is_fidelity: bool, mode_str: str) -> None:
    try:
        from tabs.image_gallery.ui.quick_look.metrics import rebuild_metrics
        rebuild_metrics(self, item, is_fidelity, mode_str)
    except Exception:
        pass


def _rebuild_artifacts(self, item) -> None:
    try:
        from tabs.image_gallery.ui.quick_look.artifacts import rebuild_artifacts
        rebuild_artifacts(self, item)
    except Exception:
        pass


def _ssim_subline(self, item) -> str:
    try:
        from tabs.image_gallery.ui.quick_look.metrics import ssim_subline
        return ssim_subline(self, item)
    except Exception:
        return ""


def _rebuild_strip(self) -> None:
    try:
        from tabs.image_gallery.ui.quick_look.strip import rebuild_strip
        rebuild_strip(self)
    except Exception:
        pass
