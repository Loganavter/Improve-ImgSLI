"""Quick look overlay helpers for ImageGalleryWidget — thin-owner target.

Per CODE_PATTERNS.md: plain functions taking the owning widget as first
argument. No string-dispatched getattr for dispatch — owner and paths are
passed explicitly.

Widget keeps thin delegators:
    def show_quick_look(self, x): return quick_look_hooks.show_quick_look(self, x)
    def eventFilter(self, w,e): return quick_look_hooks.event_filter(self,w,e)
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget


def owner_for_triage(owner):
    """Local resolve — mirrors use_cases.triage_ui.owner_for_triage explicitly."""
    try:
        ctrl = owner._controller  # type: ignore[attr-defined]
        if ctrl is not None:
            return ctrl
    except AttributeError:
        pass
    try:
        ctrl = owner._owner  # type: ignore[attr-defined]
        if ctrl is not None:
            return ctrl
    except AttributeError:
        pass
    try:
        win = owner.window()
        if win is not None:
            try:
                ctrl = win._gallery_controller  # type: ignore[attr-defined]
                if ctrl is not None:
                    return ctrl
            except AttributeError:
                pass
    except Exception:
        pass
    return owner


def _overlay_parent_window(owner, triage_owner) -> QWidget | None:
    """Resolve overlay parent as window (TopLevelInWindowOverlay requires in-window parent)."""
    for cand in (owner, triage_owner):
        if isinstance(cand, QWidget):
            try:
                win = cand.window()
                if isinstance(win, QWidget):
                    return win
            except Exception:
                pass
            return cand
        # Controller case with widget attr
        for attr in ("widget", "_widget", "_gallery_widget"):
            try:
                w = getattr(cand, attr, None)
                if isinstance(w, QWidget):
                    try:
                        win = w.window()
                        if isinstance(win, QWidget):
                            return win
                    except Exception:
                        pass
                    return w
            except Exception:
                continue
    # Fallback callable window()
    for cand in (owner, triage_owner):
        try:
            win = cand.window()  # type: ignore[union-attr]
            if isinstance(win, QWidget):
                return win
        except Exception:
            continue
    if isinstance(owner, QWidget):
        return owner
    return None


def show_quick_look(owner, item_or_path) -> None:
    """Open quick look for *item* — resolves via owner state series."""
    try:
        # Normalize to GalleryItem
        item = None
        path_val = None
        if hasattr(item_or_path, "path"):
            item = item_or_path
            path_val = Path(getattr(item, "path"))
        else:
            path_val = Path(str(item_or_path))
            for it in list(owner._items or []):  # type: ignore[attr-defined]
                try:
                    if Path(it.path) == path_val:
                        item = it
                        break
                except Exception:
                    continue
        if item is None:
            return
        triage_owner = owner_for_triage(owner)
        overlay = owner._quick_look_overlay  # type: ignore[attr-defined]
        if overlay is None:
            try:
                from tabs.image_gallery.ui.quick_look import QuickLookOverlay

                parent = _overlay_parent_window(owner, triage_owner)
                if parent is None or not isinstance(parent, QWidget):
                    try:
                        parent = owner.window() or owner  # type: ignore[union-attr]
                    except Exception:
                        parent = owner  # type: ignore[assignment]
                overlay = QuickLookOverlay(parent, triage_owner)
                owner._quick_look_overlay = overlay  # type: ignore[attr-defined]
                try:
                    overlay.compareRequested.connect(lambda p: on_quick_compare(owner, p))
                except Exception:
                    pass
                try:
                    overlay.rejectToggled.connect(lambda p: on_quick_reject(owner, p))
                except Exception:
                    pass
                try:
                    overlay.setSource.connect(lambda p: on_quick_set_source(owner, p))
                except Exception:
                    pass
            except Exception:
                return
        else:
            try:
                overlay._owner = triage_owner  # type: ignore[attr-defined]
            except Exception:
                pass
        overlay.show_for(item, triage_owner)
    except Exception:
        pass


def on_quick_compare(owner, path) -> None:
    try:
        from tabs.image_gallery.use_cases import carry as _carry

        triage_owner = owner_for_triage(owner)
        try:
            state = triage_owner.state  # type: ignore[attr-defined]
            state.selected_paths = {Path(path)}  # type: ignore[attr-defined]
            try:
                state.selected_order = [Path(path)]  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            pass
        _carry.carry_selected(triage_owner)
    except Exception:
        pass


def on_quick_reject(owner, path) -> None:
    try:
        from tabs.image_gallery.use_cases import triage as _triage

        triage_owner = owner_for_triage(owner)
        _triage.toggle_reject(triage_owner, Path(path))
        try:
            overlay = owner._quick_look_overlay  # type: ignore[attr-defined]
            if overlay is not None and overlay.isVisible():
                for it in list(owner._items or []):  # type: ignore[attr-defined]
                    if Path(it.path) == Path(path):
                        overlay.show_for(it, triage_owner)
                        break
        except Exception:
            pass
    except Exception:
        pass


def on_quick_set_source(owner, path) -> None:
    try:
        triage_owner = owner_for_triage(owner)
        try:
            state = triage_owner.state  # type: ignore[attr-defined]
            state.source_path = Path(path)  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            owner._source_path = Path(path)  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            try:
                st = triage_owner.state  # type: ignore[attr-defined]
                mode = getattr(st, "mode", None) if st is not None else owner._mode  # type: ignore[attr-defined]
            except Exception:
                mode = owner._mode  # type: ignore[attr-defined]
            owner.stats_strip.set_mode(str(mode or "fidelity"), Path(path))  # type: ignore[attr-defined]
        except Exception:
            pass
    except Exception:
        pass


def refresh_quick_look(owner, item) -> None:
    """Stage 2: refresh quick look report after artifact analysis."""
    try:
        overlay = owner._quick_look_overlay  # type: ignore[attr-defined]
        if overlay is not None and hasattr(overlay, "refresh_artifacts"):
            overlay.refresh_artifacts(item)
    except Exception:
        pass


def refresh_artifacts_for(owner, item) -> None:
    refresh_quick_look(owner, item)


def install_hooks(owner) -> None:
    """Install double-click event filter on current card pool for quick look."""
    try:
        # Iterate widget's own _cards
        try:
            for _path, card in list(owner._cards.items()):  # type: ignore[attr-defined]
                try:
                    card.installEventFilter(owner)
                except Exception:
                    pass
        except Exception:
            pass
        # Also cover grid_view internal pool
        try:
            for _str_path, card in list(owner._grid_view._cards_by_path.items()):  # type: ignore[attr-defined]
                try:
                    card.installEventFilter(owner)
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        pass


def event_filter(owner, watched, event) -> bool:
    """Double-click on gallery card → show_quick_look. Return True if consumed."""
    try:
        from PySide6.QtCore import QEvent as _QEvt
        from PySide6.QtWidgets import QWidget as _QW

        if event.type() == _QEvt.Type.MouseButtonDblClick:
            path_prop = None
            try:
                path_prop = watched.property("gallery_path")
            except Exception:
                path_prop = None
            if path_prop:
                try:
                    p = Path(str(path_prop))
                    for it in list(owner._items or []):  # type: ignore[attr-defined]
                        if Path(it.path) == p:
                            show_quick_look(owner, it)
                            return True
                except Exception:
                    pass
            try:
                item = watched._gallery_item  # type: ignore[attr-defined]
                if item is not None:
                    show_quick_look(owner, item)
                    return True
            except Exception:
                pass
    except Exception:
        pass
    try:
        return _QW.eventFilter(owner, watched, event)  # type: ignore[call-arg]
    except Exception:
        try:
            from PySide6.QtWidgets import QWidget

            return QWidget.eventFilter(owner, watched, event)  # type: ignore[call-arg]
        except Exception:
            return False
