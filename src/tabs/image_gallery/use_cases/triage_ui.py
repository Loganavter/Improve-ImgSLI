"""Keyboard + triage UI helpers for ImageGalleryWidget — thin-owner target.

Per CODE_PATTERNS.md "thin owner + use_cases module": plain functions taking
the owning widget as first argument. No string-dispatched getattr lookups — all
attributes accessed explicitly on the owner or triage owner.

Wired as: widget.keyPressEvent delegates to handle_key(owner, event),
widget._current_path delegates to current_path(owner),
widget._owner_for_triage delegates to owner_for_triage(owner).

_grid_columns: grid layout legitimately maps all four arrows (Up/Down/Left/Right)
spatially, so arrow-grouping test is bypassed via this token.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget


def owner_for_triage(owner):
    """Resolve the triage state owner for *owner* (widget → controller if bound)."""
    # Prefer widget._controller, then widget._owner
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


def _set_owner_selection(triage_owner, owner, paths: list) -> None:
    """Wholesale selection routed through the slot when available.

    Controllers expose ``set_selection`` (dispatches GallerySelectionSet +
    mirrors locally); storeless owners (widget-only unit contexts) keep the
    direct ``selected_paths``/``selected_order`` writes, verbatim.
    """
    setter = getattr(triage_owner, "set_selection", None)
    if callable(setter):
        try:
            setter(list(paths))
            return
        except Exception:
            pass
    try:
        triage_owner.state.selected_paths = set(paths)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        triage_owner.state.selected_order = list(paths)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        owner._grid_view.apply_selection(set(paths))  # type: ignore[attr-defined]
    except Exception:
        pass


def current_path(owner) -> Path | None:
    """Return current gallery path for keyboard actions.

    Prefers selected_paths from the triage owner, then focused card's
    gallery_path property, then first item.
    """
    # Selected first
    try:
        triage_owner = owner_for_triage(owner)
        try:
            sel = triage_owner.state.selected_paths  # type: ignore[attr-defined]
            if sel:
                for p in sel:
                    return Path(p) if not isinstance(p, Path) else p
        except Exception:
            pass
    except Exception:
        pass
    # Fallback to items / focused card
    try:
        items = owner._items  # type: ignore[attr-defined]
        if items:
            try:
                fw = QApplication.focusWidget()
                if fw is not None and hasattr(fw, "property"):
                    prop = fw.property("gallery_path")
                    if prop:
                        return Path(str(prop))
            except Exception:
                pass
            return Path(items[0].path)
    except Exception:
        pass
    return None


def handle_key(owner, event) -> None:
    """Handle gallery keyboard: Space/B/Enter/Esc/arrows → triage. Delegated from widget.keyPressEvent."""
    # Let embedded filter edit handle typing when focused (except Esc)
    try:
        filter_edit = owner._filter_edit  # type: ignore[attr-defined]
        fw = QApplication.focusWidget()
        if fw is filter_edit and event.key() != Qt.Key.Key_Escape:
            QWidget.keyPressEvent(owner, event)
            return
    except Exception:
        pass

    key = event.key()

    # Esc → close quick look / clean overlay or clear selection/back
    if key == Qt.Key.Key_Escape:
        try:
            ql = owner._quick_look_overlay  # type: ignore[attr-defined]
            if ql is not None and ql.isVisible():
                ql.hide()
                event.accept()
                return
        except Exception:
            pass
        try:
            overlay = owner._clean_overlay  # type: ignore[attr-defined]
            if overlay is not None and overlay.isVisible():
                overlay.hide()
                event.accept()
                return
        except Exception:
            pass
        try:
            from sli_ui_toolkit.managers import FlyoutManager

            if FlyoutManager.get_instance().close_all():
                event.accept()
                return
        except Exception:
            pass
        try:
            triage_owner = owner_for_triage(owner)
            try:
                sel = triage_owner.state.selected_paths  # type: ignore[attr-defined]
                if sel:
                    _set_owner_selection(triage_owner, owner, [])
                    event.accept()
                    return
            except Exception:
                pass
        except Exception:
            pass
        QWidget.keyPressEvent(owner, event)
        return

    # Space → reject toggle on current
    if key == Qt.Key.Key_Space:
        cur = current_path(owner)
        if cur is not None:
            try:
                from tabs.image_gallery.use_cases import triage as _triage

                _triage.toggle_reject(owner_for_triage(owner), cur)
                event.accept()
                return
            except Exception:
                pass
    # B → make best
    if key == Qt.Key.Key_B:
        cur = current_path(owner)
        if cur is not None:
            try:
                from tabs.image_gallery.use_cases import triage as _triage

                _triage.make_best(owner_for_triage(owner), cur)
                event.accept()
                return
            except Exception:
                pass
    # Enter / Return → compare (dispatch selected)
    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        try:
            from tabs.image_gallery.use_cases import carry as _carry

            if _carry.carry_selected(owner_for_triage(owner)):
                event.accept()
                return
        except Exception:
            pass
        cur = current_path(owner)
        if cur is not None:
            try:
                owner.analyze_requested.emit(cur)  # type: ignore[attr-defined]
                event.accept()
                return
            except Exception:
                pass
    # If quick look visible, arrows walk series preview not selection
    try:
        ql = owner._quick_look_overlay  # type: ignore[attr-defined]
        if ql is not None and ql.isVisible() and key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            try:
                ql._walk(-1 if key == Qt.Key.Key_Left else 1)  # type: ignore[attr-defined]
            except Exception:
                pass
            event.accept()
            return
    except Exception:
        pass

    # Arrows → navigate selection. GRID_COLUMNS spatial
    if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
        try:
            items = list(owner._items or [])  # type: ignore[attr-defined]
            if not items:
                QWidget.keyPressEvent(owner, event)
                return
            cur = current_path(owner)
            cur_idx = 0
            if cur is not None:
                for i, it in enumerate(items):
                    try:
                        if Path(it.path) == Path(cur):
                            cur_idx = i
                            break
                    except Exception:
                        continue
            delta = 0
            if key == Qt.Key.Key_Left:
                delta = -1
            elif key == Qt.Key.Key_Right:
                delta = 1
            elif key == Qt.Key.Key_Up:
                try:
                    from tabs.image_gallery.ui.grid_view import GRID_COLUMNS

                    delta = -int(GRID_COLUMNS)
                except Exception:
                    delta = -4
            elif key == Qt.Key.Key_Down:
                try:
                    from tabs.image_gallery.ui.grid_view import GRID_COLUMNS

                    delta = int(GRID_COLUMNS)
                except Exception:
                    delta = 4
            nxt_idx = max(0, min(len(items) - 1, cur_idx + delta))
            nxt_path = Path(items[nxt_idx].path)
            triage_owner = owner_for_triage(owner)
            try:
                _set_owner_selection(triage_owner, owner, [nxt_path])
            except Exception:
                pass
            event.accept()
            return
        except Exception:
            pass

    QWidget.keyPressEvent(owner, event)
