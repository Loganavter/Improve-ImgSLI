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
    """Resolve the triage state owner for *owner* (widget → controller if bound).

    Protocol-first (G5): an attached controller via the widget protocol
    wins; a controller passed directly passes through. The legacy binds
    below are last-resort for storeless doubles — the window walk is gone
    (no writer ever set it since G1/G2 deleted the pokes).
    """
    # Prefer the attached controller via the widget protocol (G2).
    try:
        resolve = getattr(owner, "_owner_for_triage", None)
        if callable(resolve):
            try:
                cand = resolve()
            except Exception:
                cand = None
            if cand is not None:
                return cand
    except Exception:
        pass
    if callable(getattr(owner, "set_selection", None)):
        return owner
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
    return owner


def _resolve_selection_controller(triage_owner):
    """Return the object exposing ``set_selection`` for wholesale writes.

    Prefers *triage_owner* itself (controller with dispatch + mirror +
    grid apply); when handed a widget, resolves through its
    ``_owner_for_triage()`` (G2). None = storeless unit context.
    """
    try:
        if callable(getattr(triage_owner, "set_selection", None)):
            return triage_owner
    except Exception:
        pass
    try:
        resolver = getattr(triage_owner, "_owner_for_triage", None)
        if callable(resolver):
            try:
                cand = resolver()
            except Exception:
                cand = None
            if cand is not None and callable(getattr(cand, "set_selection", None)):
                return cand
    except Exception:
        pass
    return None


def _set_owner_selection(triage_owner, owner, paths: list) -> None:
    """Wholesale selection routed through the controller dispatch.

    Controllers expose ``set_selection`` (dispatches GallerySelectionSet +
    mirrors locally + applies the grid); storeless owners (widget-only unit
    contexts) keep the local mirror via ``setattr``, verbatim. No direct
    ``owner.state.* =`` writes anywhere here.
    """
    ctrl = _resolve_selection_controller(triage_owner)
    if ctrl is not None:
        try:
            ctrl.set_selection(list(paths))
            return
        except Exception:
            pass
    try:
        setattr(triage_owner.state, "selected_paths", set(paths))  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        setattr(triage_owner.state, "selected_order", list(paths))  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        owner._grid_view.apply_selection(set(paths))  # type: ignore[attr-defined]
    except Exception:
        pass


def dismiss_gallery_modals(owner) -> None:
    """Modal-lifetime (W1): tab-owned window-parented modals must not outlive the tab.

    Dismisses the QuickLook (``_quick_look_overlay``) and CleanReview
    (``_clean_overlay``) overlays via the existing ``dismiss()``/``hide()``
    APIs. Fail-open throughout: missing attrs, detached widgets, and
    partially-constructed overlays never raise.

    Beyond the widget refs, sweeps the window for visible
    QuickLook/CleanReview overlays tagged ``owner_tab="image_gallery"``
    (untagged production instances are treated as ours; foreign tags are
    never touched). No new overlay resolvers, no focus calls.
    """
    for attr in ("_quick_look_overlay", "_clean_overlay"):
        try:
            overlay = getattr(owner, attr, None)
        except Exception:
            continue
        _dismiss_one(overlay)
    try:
        window = owner.window() if hasattr(owner, "window") else None
    except Exception:
        window = None
    if window is None:
        return
    try:
        for child in window.findChildren(QWidget):
            try:
                if type(child).__name__ not in ("QuickLookOverlay", "CleanReviewOverlay"):
                    continue
                if not child.isVisible():
                    continue
                if child.property("owner_tab") not in (None, "", "image_gallery"):
                    continue
                _dismiss_one(child)
            except Exception:
                continue
    except Exception:
        pass


def _dismiss_one(overlay) -> None:
    """Dismiss a single overlay if visible — fail-open."""
    if overlay is None:
        return
    try:
        if not overlay.isVisible():
            return
    except Exception:
        return
    try:
        dismiss = getattr(overlay, "dismiss", None)
        if callable(dismiss):
            dismiss()
        else:
            overlay.hide()
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
    """Handle gallery keyboard: Space/Delete/B/Enter/Esc/arrows → triage. Delegated from widget.keyPressEvent."""
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

    # Space / Delete / Backspace → remove ALL selected cards from the grid.
    # Empty selection is a no-op (never fall back to the first item).
    if key in (Qt.Key.Key_Space, Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
        try:
            triage_owner = owner_for_triage(owner)
            targets: list = []
            try:
                sel = triage_owner.state.selected_paths  # type: ignore[attr-defined]
            except Exception:
                sel = None
            if sel:
                try:
                    order = triage_owner.state.selected_order  # type: ignore[attr-defined]
                except Exception:
                    order = None
                try:
                    sel_set = {Path(p) if not isinstance(p, Path) else p for p in sel}
                except Exception:
                    sel_set = set()
                if order:
                    try:
                        ordered = [Path(p) if not isinstance(p, Path) else p for p in order]
                        targets = [p for p in ordered if p in sel_set]
                        # Survivors missing from order (shouldn't happen) — append sorted.
                        missing = [p for p in sel_set if p not in set(targets)]
                        try:
                            missing = sorted(missing, key=str)
                        except Exception:
                            pass
                        targets.extend(missing)
                    except Exception:
                        try:
                            targets = sorted(sel_set, key=str)
                        except Exception:
                            targets = list(sel_set)
                else:
                    try:
                        targets = sorted(sel_set, key=str)
                    except Exception:
                        targets = list(sel_set)
            if not targets:
                # Nothing selected → ignore, don't delete the first card.
                QWidget.keyPressEvent(owner, event)
                return
            from tabs.image_gallery.use_cases import triage as _triage

            removed = _triage.remove_paths_from_grid(triage_owner, targets)
            if removed:
                event.accept()
                return
        except Exception:
            pass
        QWidget.keyPressEvent(owner, event)
        return
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
