"""Drag & drop orchestration for ``ImageGalleryWidget`` — thin-owner split.
Audit-Meta: pattern=single-router size=exempt reason="one drop-routing rule for zone+widget surfaces incl. single-writer pool discipline; splitting would scatter the accept/route/dispatch branches pinned as one unit"

Split out of ``widget.py`` per ``CODE_PATTERNS.md`` thin owner + ``ui/`` use_cases:
``ImageGalleryWidget`` keeps Qt-required method names (``dragEnterEvent`` etc.)
as one-liners that delegate here. All logic lives as plain functions taking
the owning widget as first argument, reading/writing its instance state
(``_empty_state``, ``_controller``, ``folder_pick_requested``) directly.

Public imports only; no ``setStyleSheet`` — painter pipeline owns visuals.
Controller dependency is explicit via a ``controller`` parameter threaded
from the widget call sites (fail-open legacy bind only for direct test
calls — no scans, no window walk).

Reference: ``tabs/multi_compare/ui/drag_drop.py``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QObject

from shared.image_drop import (
    extract_image_paths_from_mime as _extract_paths,
)
from shared.image_drop import (
    has_acceptable_image_drop as _has_image_drop,
)
from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS as _ACCEPTED_EXTS
from tabs.image_gallery.debug import gallery_debug as _dbg
from tabs.image_gallery.debug import gallery_dnd_debug as _dnd_log

logger = logging.getLogger("ImproveImgSLI")


# -- helpers ---------------------------------------------------------------


def is_acceptable_drop(owner, event) -> bool:
    """Delegate to ``shared/image_drop.py`` — single source for image accept."""
    try:
        mime = event.mimeData()
        ok = _has_image_drop(mime)
        if not ok and mime is not None:
            # Log non-local skips at debug level for hang diagnosis
            for url in mime.urls():
                if not url.isLocalFile():
                    _dnd_log("is_acceptable_drop: skip non-local url %r", url.toString())
        return ok
    except Exception as e:
        _dnd_log("is_acceptable_drop exception: %r", e)
        return False


def _set_highlight(owner, active: bool) -> None:
    """Toggle the empty-state zone chrome; safe for fakes without the API."""
    try:
        empty = getattr(owner, "_empty_state", None)
        if empty is None:
            return
        meth = getattr(empty, "set_drag_highlight", None)
        if callable(meth):
            meth(bool(active))
    except Exception:
        pass


def drag_enter_event(owner, event) -> None:
    # Internal gallery moves first: accept on series chrome, never as files.
    try:
        if has_internal_mime(event.mimeData()):
            if _grid_has_headers(owner):
                _dnd_log("dragEnterEvent: internal gallery mime -> accept (series targets)")
                event.acceptProposedAction()
            else:
                _dnd_log("dragEnterEvent: internal gallery mime, no series chrome -> ignore")
                event.ignore()
            return
    except Exception:
        pass
    _dnd_log("dragEnterEvent: mime_hasUrls=%s", event.mimeData().hasUrls() if event.mimeData() else False)
    ok = is_acceptable_drop(owner, event)
    _dnd_log("dragEnterEvent: is_acceptable=%s", ok)
    if ok:
        event.acceptProposedAction()
        try:
            owner._empty_state.set_state("empty")
            owner._empty_state.show()
        except Exception:
            pass
        _set_highlight(owner, True)
    else:
        _set_highlight(owner, False)
        event.ignore()


def drag_move_event(owner, event) -> None:
    # Internal gallery moves: accept + highlight the header under cursor.
    # The empty-state/file chrome stays off (never break external highlight).
    try:
        if has_internal_mime(event.mimeData()):
            if _grid_has_headers(owner):
                event.acceptProposedAction()
                try:
                    _trace_move_positions(owner, event)
                except Exception:
                    pass
                try:
                    _set_series_highlight(owner, _header_at(owner, _owner_hit_pos(owner, event)))
                except Exception:
                    pass
            else:
                event.ignore()
            return
    except Exception:
        pass
    ok = is_acceptable_drop(owner, event)
    # Throttle: log only every 50 events to avoid flood (counter on owner)
    try:
        cnt = getattr(owner, "_dnd_move_cnt", 0) + 1
        owner._dnd_move_cnt = cnt
        if cnt % 50 == 1:
            _dnd_log("dragMoveEvent: is_acceptable=%s (cnt=%d)", ok, cnt)
    except Exception:
        _dnd_log("dragMoveEvent: is_acceptable=%s", ok)
    if ok:
        event.acceptProposedAction()
    else:
        event.ignore()


def _trace_move_positions(owner, event) -> None:
    """Bisection probe (Wave E diagnosis): cursor vs event trajectory.

    Falsifiable hypothesis: during ``QDrag.exec`` the app-visible
    ``QCursor.pos()`` is frozen (drag grab swallows mouse moves on this
    platform) while ``QDragMoveEvent.position()`` advances with the real
    pointer. Every ~10th internal move logs both + the mapped owner-space
    point. Kill condition: cursor advances together with event positions —
    then the freeze theory is dead and the offset is a mapping bug instead.
    Throttled (counter on owner); session-only via the gallery debug flag.
    """
    try:
        from tabs.image_gallery.debug import gallery_dnd_debug_enabled as _gate
        if not _gate():
            return
    except Exception:
        return
    try:
        cnt = getattr(owner, "_dnd_trace_cnt", 0) + 1
        owner._dnd_trace_cnt = cnt
    except Exception:
        cnt = 1
    if cnt % 10 != 1:
        return
    try:
        ev_pos = event.position().toPoint()
    except Exception:
        try:
            ev_pos = event.pos()
        except Exception:
            ev_pos = None
    try:
        from PySide6.QtGui import QCursor as _QCursor

        cursor = _QCursor.pos()
    except Exception:
        cursor = None
    try:
        mapped = owner.mapFromGlobal(cursor) if cursor is not None else None
    except Exception:
        mapped = None
    try:
        recv = type(owner).__name__
        try:
            import PySide6.QtWidgets as _QW

            w = _QW.QApplication.widgetAt(cursor) if cursor is not None else None
            witness = type(w).__name__ if w is not None else "None"
            try:
                wname = str(w.objectName() or "") if w is not None else ""
            except Exception:
                wname = "?"
        except Exception:
            witness, wname = "?", "?"
        _dnd_log(
            "move-trace #%d ev_pos=%s cursor=%s mapped=%s widgetAt=%s(%s)",
            cnt, ev_pos, cursor, mapped, witness, wname,
        )
    except Exception:
        pass


def drag_leave_event(owner, event) -> None:
    _dnd_log("dragLeaveEvent")
    _clear_series_highlight(owner)
    _set_highlight(owner, False)
    try:
        super(type(owner), owner).dragLeaveEvent(event)
    except Exception:
        pass


def _note(owner, text: str) -> None:
    """User-visible one-line note on the gallery folder label.

    Lightweight feedback channel for drop paths that otherwise end
    silently (no paths extracted, missing/empty files): the folder label
    is the gallery's status line and ``set_folder_label`` is its public
    API (controller-owned), so notes never touch card internals.
    """
    try:
        label = getattr(owner, "set_folder_label", None)
        if callable(label):
            label(Path(text))
    except Exception:
        pass


def _explicit_controller(owner, controller=None):
    """Explicit controller first; fail-open legacy reads (no scan, no window walk).

    The widget threads ``self._owner_for_triage()`` from every call site.
    A bare widget threaded pre-attach unwraps to its attachment; direct
    calls without a controller resolve via the owner's triage protocol,
    then a single direct legacy bind (pre-G1 tab wiring, test doubles).
    """
    if controller is not None and hasattr(controller, "_owner_for_triage"):
        try:
            controller = controller._attached_controller
        except Exception:
            controller = None
    if controller is None:
        try:
            resolve = getattr(owner, "_owner_for_triage", None)
            controller = resolve() if callable(resolve) else None
        except Exception:
            controller = None
        if controller is None or controller is owner:
            try:
                controller = owner._controller
            except Exception:
                controller = None
    return controller


def _fallback_folder(paths: list[Path]) -> Path:
    """File-vs-folder fallback shared by zone + widget routing.

    Directories never reach here (the folder branch handles them); files —
    and suffix-less strays — resolve to their parent, never to themselves.
    """
    return paths[0].parent


def _dispatch_drop_pool(owner, *, all_files: bool, has_dir: bool, paths: list[Path], folder: Path | None) -> None:
    """Dispatch the pool action matching this drop (fail-open, Wave 2c).

    Sole-writer failover only: called when no controller synchronously
    consumes the drop (storeless contexts). When a controller takes the drop
    (``_route_paths`` branches below), it emits the pool action itself after
    mirroring — dispatching here too would materialize the same pool twice
    (log-proven: 4 flat-first rebuilds per single drop). Entries are
    ``[(path, mtime_ns), ...]`` — plain scalars per the frozen seam. The
    reducer dedups re-drops, so dispatch is idempotent.
    """
    try:
        from core.state_management.gallery_actions import (
            GalleryPathsAppended,
            GalleryPoolOpened,
            GalleryPoolReplaced,
        )
        from tabs.image_gallery.ui.gallery_store import (
            dispatch_gallery,
            entries_for_folder,
            entries_for_paths,
        )

        if all_files and not has_dir:
            dispatch_gallery(owner, GalleryPathsAppended(entries=entries_for_paths(paths)))
            return
        if folder is None:
            dispatch_gallery(owner, GalleryPathsAppended(entries=entries_for_paths(paths)))
            return
        folder_entries = entries_for_folder(folder)
        try:
            from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS as _EXTS3

            dropped_files = [
                p for p in paths
                if p.is_file() and p.suffix.lower() in _EXTS3
            ]
        except Exception:
            dropped_files = []
        if dropped_files:
            seen: set[str] = set()
            merged: list[tuple[str, int]] = []
            for e in entries_for_paths(dropped_files) + folder_entries:
                if e[0] not in seen:
                    seen.add(e[0])
                    merged.append(e)
            dispatch_gallery(
                owner, GalleryPoolReplaced(folder=str(folder), entries=merged)
            )
        else:
            dispatch_gallery(
                owner, GalleryPoolOpened(folder=str(folder), entries=folder_entries)
            )
    except Exception:
        pass


def _route_paths(owner, paths: list[Path], controller=None) -> bool:
    """Shared routing for widget + zone drops — one rule everywhere.

    *paths* are pre-filtered (existing image files / directories via the
    shared ``image_drop`` check). Batches (the single-image special case is
    n=1 of this branch — open the file, never its parent), folders, and
    mixed folder+files route identically no matter which surface was hit:

    * all image files, no dirs → ``open_paths`` (append to the pool);
    * first directory wins as folder; files alongside it ride along via
      ``open_paths(replace=True)`` (mixed), pure dirs via ``open_folder``;
    * otherwise the file-vs-folder fallback (parent, never itself).

    Returns True when a controller consumed the drop.
    """
    from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS as _EXTS2

    for p in paths[:5]:
        try:
            _dnd_log(
                "  path %s exists=%s is_file=%s is_dir=%s suffix=%s",
                p,
                p.exists(),
                p.is_file(),
                p.is_dir(),
                p.suffix.lower(),
            )
        except Exception:
            pass
    try:
        all_files = all(p.is_file() and p.suffix.lower() in _EXTS2 for p in paths if p.exists()) and any(
            p.is_file() for p in paths
        )
        has_dir = any(p.is_dir() for p in paths)
    except Exception:
        all_files = False
        has_dir = False
    _dnd_log("dropEvent decision: all_files=%s has_dir=%s", all_files, has_dir)
    ctrl = _explicit_controller(owner, controller)
    # Single-writer rule: when the controller synchronously consumes the drop
    # in the branches below, IT dispatches the pool action after mirroring
    # (open_paths / open_folder both emit). The eager _dispatch_drop_pool then
    # stays off — otherwise the same pool materializes twice: widget
    # slot-render + controller external sync each rebuild flat first
    # (headers demolished), then open_* rebuilds a third time before triage
    # regroups a fourth (log-proven: 4 rebuilds per single drop). The eager
    # dispatch stays only as the sole writer when no controller consumes the
    # drop (storeless contexts) or the controller call throws.
    if all_files and not has_dir:
        _dnd_log("dropEvent single/multi image %d files -> open_paths (not parent folder)", len(paths))
        if ctrl is not None and hasattr(ctrl, "open_paths"):
            try:
                ctrl.open_paths(paths)
                return True
            except Exception:
                _dnd_log("open_paths failed", exc_info=True)
        else:
            _dispatch_drop_pool(owner, all_files=all_files, has_dir=has_dir, paths=list(paths), folder=None)
        try:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, lambda ps=list(paths), c=ctrl: try_open_folder(owner, ps[0], c) if len(ps) == 1 else None)
        except Exception:
            pass
        return False
    folder = None
    for p in paths:
        if p.is_dir():
            folder = p
            break
    if folder is None:
        folder = _fallback_folder(paths)
    if folder and folder.is_dir():
        _dbg("dropEvent folder %s", folder)
        dropped_files = [
            p for p in paths
            if p.is_file() and p.suffix.lower() in _EXTS2
        ]
        if dropped_files and ctrl is not None and hasattr(ctrl, "open_paths"):
            # Mixed file-plus-folder drop: open_paths scans the dir AND
            # lists the dropped files (label names them) — open_folder
            # alone would swallow the files silently.
            _dnd_log(
                "dropEvent mixed folder+files -> open_paths (dir %s + %d files)",
                folder, len(dropped_files),
            )
            try:
                ctrl.open_paths(paths, replace=True)
                return True
            except Exception:
                _dnd_log("open_paths (mixed) failed", exc_info=True)
        if ctrl is not None and hasattr(ctrl, "open_folder"):
            try:
                ctrl.open_folder(folder)
                return True
            except Exception:
                _dbg("open_folder failed", exc_info=True)
        if ctrl is None or not (hasattr(ctrl, "open_paths") or hasattr(ctrl, "open_folder")):
            # No controller consumed the drop: eager dispatch is the sole writer.
            _dispatch_drop_pool(owner, all_files=all_files, has_dir=has_dir, paths=list(paths), folder=folder)
        try:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, lambda f=folder, c=ctrl: try_open_folder(owner, f, c))
        except Exception:
            pass
    return False


def on_empty_file_dropped(owner, path_str: str, controller=None) -> None:
    """Empty-state ``fileDropped`` handler — single-path entry to shared routing.

    The zone signal carries one path string; live multi-path zone drops are
    forwarded with their full mime via ``install_zone_drop_forwarding`` so
    they reach ``drop_event`` instead. Whatever arrives here routes through
    the same ``_route_paths`` core: single image → ``open_paths([p])`` (kept
    intentionally — open the file, never its parent), directory → folder.
    Non-image files are noted + ignored, matching the widget accept rule
    (``is_acceptable_drop`` rejects them there too) instead of opening the
    parent folder.
    """
    try:
        p = Path(path_str)
        _dnd_log("on_empty_file_dropped: %s is_dir=%s is_file=%s suffix=%s", p, p.is_dir(), p.is_file(), p.suffix.lower())
        if not p.exists():
            _note(owner, f"Nothing to show — {p.name or path_str} was removed or is unreachable.")
            return
        if p.is_file():
            try:
                empty = p.stat().st_size == 0
            except Exception:
                empty = False
            if empty:
                _note(owner, f"Empty file — {p.name} is 0 bytes, nothing to show.")
                return
        # Directory → open folder (triage 1037)
        if p.is_dir():
            try_open_folder(owner, p, controller)
            return
        # Single image file → shared core (open_paths, 1 image — not parent
        # folder — same branch widget drop_event takes for one file).
        # Use shared accept check so behavior matches widget dropEvent
        if p.is_file() and p.suffix.lower() in _ACCEPTED_EXTS:
            _dnd_log("on_empty_file_dropped: single image -> open_paths %s", p)
            _route_paths(owner, [p], controller)
            return
        if p.is_file():
            # Non-image file: ignore with a note. The widget path rejects
            # these via the shared accept check — never open the parent.
            _dnd_log("on_empty_file_dropped: non-image file ignored %s", p)
            _note(owner, f"Nothing to show — {p.name} is not a supported image.")
            return
        # Non-file, non-dir strays (fifo/socket/…) → same parent fallback
        # the widget path uses, never the path itself.
        try_open_folder(owner, _fallback_folder([p]), controller)
    except Exception as e:
        _dnd_log("on_empty_file_dropped failed: %r", e, exc_info=True)
        pass


def try_open_folder(owner, folder: Path, controller=None) -> None:
    """Open *folder* via the explicit controller, else emit pick request."""
    folder = Path(folder)
    ctrl = _explicit_controller(owner, controller)
    _dnd_log("try_open_folder: %s ctrl=%s", folder, ctrl)
    try:
        from core.state_management.gallery_actions import GalleryPoolOpened
        from tabs.image_gallery.ui.gallery_store import dispatch_gallery, entries_for_folder

        try:
            is_dir = folder.is_dir()
        except Exception:
            is_dir = False
        if is_dir:
            dispatch_gallery(
                owner, GalleryPoolOpened(folder=str(folder), entries=entries_for_folder(folder))
            )
    except Exception:
        pass
    try:
        if ctrl is not None and hasattr(ctrl, "open_folder"):
            ctrl.open_folder(folder)
            return
    except Exception as e:
        _dnd_log("try_open_folder open_folder failed: %r", e, exc_info=True)
        pass
    try:
        owner.folder_pick_requested.emit()
    except Exception:
        pass


def drop_event(owner, event, controller=None) -> None:
    """Widget-level drop — internal gallery mime first, then shared routing."""
    _dnd_log("dropEvent: enter")
    # Internal gallery move: resolve the series under cursor (header, else
    # UNGROUPED tail) and pin via the controller. External file routing
    # never runs for this mime (never open_paths/open_folder).
    try:
        mime = event.mimeData()
    except Exception:
        mime = None
    if has_internal_mime(mime):
        _dnd_log("dropEvent: internal gallery mime -> move_paths_to_series")
        _set_highlight(owner, False)
        try:
            paths = parse_internal_paths(mime)
            handled, series_id = series_target_at(owner, _owner_hit_pos(owner, event))
            ctrl = _explicit_controller(owner, controller)
            move = getattr(ctrl, "move_paths_to_series", None)
            if paths and handled and callable(move):
                try:
                    moved = move(list(paths), series_id)
                except Exception:
                    moved = "error"
                    _dnd_log("move_paths_to_series failed", exc_info=True)
                _dnd_log(
                    "dropEvent: internal drop delivered "
                    "(handled=%s series_id=%s n_paths=%d moved=%s paths=%r)",
                    handled, series_id, len(paths), moved,
                    [str(p) for p in list(paths)[:5]],
                )
                try:
                    event.accept()
                except Exception:
                    pass
            else:
                _dnd_log(
                    "dropEvent: internal drop ignored (paths=%d handled=%s has_move=%s)",
                    len(paths), handled, callable(move),
                )
                try:
                    event.ignore()
                except Exception:
                    pass
        except Exception:
            _dnd_log("dropEvent: internal routing failed", exc_info=True)
        finally:
            _clear_series_highlight(owner)
        return
    if not is_acceptable_drop(owner, event):
        _dnd_log("dropEvent: rejected by is_acceptable_drop -> ignore")
        _set_highlight(owner, False)
        event.ignore()
        return
    _dnd_log("dropEvent: accepted -> acceptProposedAction")
    event.acceptProposedAction()
    try:
        paths = _extract_paths(event.mimeData())
        if not paths:
            _dnd_log("dropEvent: no paths extracted from mime")
            _note(owner, "Nothing to show — the dropped items held no images or folders.")
            return
        _dnd_log("dropEvent: %d paths %r", len(paths), paths[:5])
        if _route_paths(owner, list(paths), controller):
            try:
                event.accept()
            except Exception:
                pass
    except Exception:
        pass
    finally:
        # Drop consumed — chrome goes away; next state (scanning/ready)
        # owns the visuals from here.
        _set_highlight(owner, False)


class _ZoneDropFilter(QObject):
    """Forward zone-surface drag/drop to the unified ``drag_drop`` handlers.

    The empty-state ``DropZoneLabel`` (toolkit) accepts any URL drag and its
    own ``dropEvent`` consumes the event while re-emitting only the FIRST
    path (``file_dropped(str)``) — truncating batches and bypassing the
    shared accept check. Intercepting drag enter/move/drop here routes the
    full mime through ``is_acceptable_drop``/``drop_event`` so zone drops
    behave exactly like widget drops. Consumed events never reach the label
    (no truncated re-emit); other event types pass through untouched.
    """

    def __init__(self, owner, controller=None):
        super().__init__()
        self._owner = owner
        self._controller = controller

    def eventFilter(self, watched, event):  # noqa: N802
        try:
            t = event.type()
        except Exception:
            return False
        try:
            if t == QEvent.Type.DragEnter:
                drag_enter_event(self._owner, event)
                return True
            if t == QEvent.Type.DragMove:
                drag_move_event(self._owner, event)
                return True
            if t == QEvent.Type.Drop:
                drop_event(self._owner, event, _explicit_controller(self._owner, self._controller))
                return True
        except Exception as e:
            _dnd_log("zone drop filter failed: %r", e, exc_info=True)
            return False
        return False


def install_zone_drop_forwarding(owner, controller=None) -> bool:
    """Route drops landing on the empty-state zone through ``drop_event``.
    Called once from ``ImageGalleryWidget.__init__`` (thin owner) and again
    from ``attach_controller`` once the controller is known. Finds the
    zone label by objectName (``gallery_empty_drop_zone``) so this module
    never reaches into ``GalleryEmptyState`` privates. Idempotent; returns
    True when the filter is installed. An explicit *controller* refreshes
    the installed filter's binding (None never clobbers); otherwise the
    filter resolves the triage owner lazily at event time.
    """
    try:
        existing = getattr(owner, "_zone_drop_filter", None)
        if existing is not None:
            if controller is not None:
                try:
                    existing._controller = controller
                except Exception:
                    pass
            # Same install point (attach_controller): refresh the header
            # menu binding too.
            try:
                install_series_header_menu(owner, controller)
            except Exception:
                pass
            return True
        empty = getattr(owner, "_empty_state", None)
        if empty is None:
            return False
        zone = None
        try:
            from PySide6.QtWidgets import QWidget as _QW

            zone = empty.findChild(_QW, "gallery_empty_drop_zone")
        except Exception:
            zone = None
        if zone is None:
            zone = getattr(empty, "_drop_label", None)
        if zone is None:
            return False
        filt = _ZoneDropFilter(owner, controller)
        try:
            zone.installEventFilter(filt)
        except Exception:
            return False
        try:
            owner._zone_drop_filter = filt
        except Exception:
            pass
        # Wave B: the series-header reset menu rides the same install points
        # (init + attach) so no widget.py change is needed. Best-effort —
        # the zone result below is unaffected.
        try:
            install_series_header_menu(owner, controller)
        except Exception:
            _dnd_log("series header menu install failed", exc_info=True)
        return True
    except Exception:
        return False


# -- series-header reset menu (Wave B) --------------------------------------

_SERIES_RESET_ACTION_ID = "gallery.series.reset"
_SERIES_RECLUSTER_ACTION_ID = "gallery.series.recluster"


def _is_series_header(widget) -> bool:
    """True for series/UNGROUPED section header containers."""
    try:
        name = str(widget.objectName() or "")
    except Exception:
        return False
    return name == "GallerySeriesHeader" or name.startswith("GallerySeriesHeader_")


def _open_header_reset_menu(owner, header, event, controller=None) -> bool:
    """Popup the series-header context menu (reset / re-cluster series).

    Single existing-surface affordance for manual-series management:
    right-click on any series/UNGROUPED header → "Reset manual series"
    (``controller.reset_series_overrides()``) and "Re-cluster series"
    (``controller.recluster_series()`` — fresh world, pins kept). Each
    entry appears only when the controller offers it. Toolkit
    ``ContextMenu`` surface (card-menu precedent), fail-soft everywhere.
    Returns True when a menu was shown.
    """
    ctrl = _explicit_controller(owner, controller)
    try:
        reset = getattr(ctrl, "reset_series_overrides", None)
    except Exception:
        reset = None
    try:
        recluster = getattr(ctrl, "recluster_series", None)
    except Exception:
        recluster = None
    has_reset = callable(reset)
    has_recluster = callable(recluster)
    if not (has_reset or has_recluster):
        return False
    try:
        pos = event.globalPosition().toPoint()
    except Exception:
        try:
            pos = event.globalPos()
        except Exception:
            pos = None
    if pos is None:
        try:
            from PySide6.QtGui import QCursor as _QCursor

            pos = _QCursor.pos()
        except Exception:
            return False
    try:
        source = header.window() if hasattr(header, "window") else header
    except Exception:
        source = header
    if source is None:
        source = header

    def _on_triggered(action_id: str, _data: object) -> None:
        try:
            if action_id == _SERIES_RESET_ACTION_ID and has_reset:
                reset()
            elif action_id == _SERIES_RECLUSTER_ACTION_ID and has_recluster:
                recluster()
        except Exception:
            pass

    try:
        from sli_ui_toolkit.widgets import ContextMenu as _CtxMenu
        from sli_ui_toolkit.widgets import ContextMenuAction as _CtxAction
    except Exception:
        return False
    try:
        entries_list = []
        if has_reset:
            entries_list.append(_CtxAction(_SERIES_RESET_ACTION_ID, "Reset manual series"))
        if has_recluster:
            entries_list.append(_CtxAction(_SERIES_RECLUSTER_ACTION_ID, "Re-cluster series"))
        entries = tuple(entries_list)
    except Exception:
        return False
    try:
        try:
            menu = _CtxMenu(source, entries=tuple(entries), on_triggered=_on_triggered, surface="popup")
        except TypeError:
            menu = _CtxMenu(source, entries=tuple(entries), on_triggered=_on_triggered)
    except Exception:
        return False
    try:
        menu.flyout_group = "context_menu"  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        menu.popup_at(pos)
        return True
    except Exception:
        _dnd_log("header reset menu popup failed", exc_info=True)
        return False


class _SeriesHeaderWatcher(QObject):
    """Attach the reset menu to series headers as they are (re)built.

    Installed once on the grid's item host: ``ChildAdded`` hooks each new
    ``GallerySeriesHeader*`` container (headers are reused by position but
    extras are created/destroyed on regroup), and ``ContextMenu`` events on
    hooked headers open the reset menu. Header rebuilds need no re-install.
    """

    def __init__(self, owner, controller=None):
        super().__init__()
        self._owner = owner
        self._controller = controller

    def eventFilter(self, watched, event):  # noqa: N802
        try:
            t = event.type()
        except Exception:
            return False
        try:
            if t == QEvent.Type.ChildAdded:
                try:
                    child = event.child()
                except Exception:
                    child = None
                if child is not None and _is_series_header(child):
                    try:
                        child.installEventFilter(self)
                    except Exception:
                        pass
                return False
            if t == QEvent.Type.ContextMenu:
                if _is_series_header(watched):
                    if _open_header_reset_menu(
                        self._owner, watched, event, self._controller
                    ):
                        return True
                return False
        except Exception as e:
            _dnd_log("series header watcher failed: %r", e, exc_info=True)
            return False
        return False


def install_series_header_menu(owner, controller=None) -> bool:
    """Install the series-header reset-menu watcher (idempotent).

    Called from ``install_zone_drop_forwarding`` so both widget init and
    ``attach_controller`` cover it with no ``widget.py`` change. A passed
    *controller* refreshes the binding (None never clobbers). Returns True
    when the watcher is installed.
    """
    try:
        existing = getattr(owner, "_series_header_watcher", None)
        if existing is not None:
            if controller is not None:
                try:
                    existing._controller = controller
                except Exception:
                    pass
            return True
        grid = getattr(owner, "_grid_view", None)
        if grid is None:
            return False
        host = getattr(grid, "items_host", None) or grid
        watcher = _SeriesHeaderWatcher(owner, controller)
        try:
            host.installEventFilter(watcher)
        except Exception:
            return False
        # Seed headers already built (attach-time installs land here).
        try:
            for hdr in list(getattr(grid, "_series_headers", None) or []):
                if _is_series_header(hdr):
                    try:
                        hdr.installEventFilter(watcher)
                    except Exception:
                        continue
        except Exception:
            pass
        try:
            owner._series_header_watcher = watcher
        except Exception:
            pass
        return True
    except Exception:
        return False


# Canonical mime lives in ``ui/card.py`` (Wave A, defined ONCE). Payload rule
# (verbatim): newline-separated ``file://`` URLs in ``QMimeData.data(mime)``
# PLUS ``setUrls()``.
from tabs.image_gallery.ui.card import GALLERY_PATHS_MIME

_UNGROUPED_HEADER_NAME = "GallerySeriesHeader_ungrouped"


def has_internal_mime(mime) -> bool:
    """True when *mime* carries gallery-internal dragged paths."""
    try:
        return bool(mime is not None and mime.hasFormat(GALLERY_PATHS_MIME))
    except Exception:
        return False


def parse_internal_paths(mime) -> list[Path]:
    """Parse dragged gallery paths from the internal mime (Wave A format).

    Reads newline-separated ``file://`` URLs from ``data(mime)`` and also
    tolerates ``urls()`` (Wave A writes both). Order-preserving, deduped.
    Never raises — corrupt payloads yield whatever parsed.
    """
    seen: set[str] = set()
    out: list[Path] = []

    def _take(candidate) -> None:
        try:
            s = str(candidate)
        except Exception:
            return
        if not s or s in seen:
            return
        seen.add(s)
        try:
            out.append(Path(s))
        except Exception:
            pass

    try:
        raw = bytes(mime.data(GALLERY_PATHS_MIME))
    except Exception:
        raw = b""
    if raw:
        try:
            from PySide6.QtCore import QUrl as _QUrl

            for line in raw.decode("utf-8", "replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    local = _QUrl(line).toLocalFile()
                except Exception:
                    local = ""
                _take(local or line)
        except Exception:
            pass
    try:
        for url in mime.urls():
            try:
                if url.isLocalFile():
                    _take(url.toLocalFile())
            except Exception:
                continue
    except Exception:
        pass
    return out


def _event_pos(event):
    """Cursor position in widget coords (Qt6 position() with Qt5 fallback)."""
    try:
        return event.position().toPoint()
    except Exception:
        pass
    try:
        return event.pos()
    except Exception:
        pass
    try:
        from PySide6.QtCore import QPoint as _QPoint

        return _QPoint(0, 0)
    except Exception:
        return None


def _owner_space_pos(owner, event, receiver=None):
    """Cursor position in OWNER coords (Wave E fix).

    During ``QDrag.exec`` the app-visible ``QCursor.pos()`` is FROZEN on
    this stack (proven by move-trace: cursor fixed while ``QDragMoveEvent``
    positions advance) — every cursor-derived source (``mapFromGlobal``,
    ``widgetAt``) resolves the drag ORIGIN, not the drop point. So no
    cursor source is used here at all: the event position travels with the
    real pointer. When the receiver is known (zone-filter forwarding passes
    ``watched``), map through the receiver chain into owner space (pure
    local mapping — no screen frame, per the maximized-window precedent);
    otherwise the receiver is the owner itself (widget accepts drops
    anywhere) and the event pos is already owner-space.
    """
    try:
        pos = event.position().toPoint()
    except Exception:
        try:
            pos = event.pos()
        except Exception:
            return None
    if pos is None:
        return None
    if receiver is not None:
        try:
            if receiver is not owner:
                return receiver.mapTo(owner, pos)
        except Exception:
            pass
    return pos


def _series_for_card_path(grid, path: str):
    """Cluster series id for a card path (model truth, Wave D helper).

    Returns ``(resolved, series_id)``: membership in ``grid._series``
    clusters first, UNGROUPED-tail membership (None) second. Unplaced paths
    report ``(False, None)`` — callers fall back to the card's live attr.
    """
    try:
        clusters = list(getattr(grid, "_series", None) or [])
    except Exception:
        clusters = []
    for idx, entry in enumerate(clusters):
        try:
            members = list(entry.members) if hasattr(entry, "members") else list(entry)
        except Exception:
            continue
        try:
            hit = any(str(getattr(m, "path", "")) == path for m in members)
        except Exception:
            hit = False
        if not hit:
            continue
        try:
            first_sid = getattr(members[0], "series_id", None)
            sid = str(first_sid) if first_sid is not None else None
        except Exception:
            sid = None
        if sid is None:
            try:
                sid = _series_id_for_index(grid, idx)
            except Exception:
                sid = None
        return (True, sid)
    try:
        tail = list(getattr(grid, "_ungrouped", None) or [])
        if any(str(getattr(m, "path", "")) == path for m in tail):
            return (True, None)
    except Exception:
        pass
    return (False, None)


def _owner_hit_pos(owner, event, receiver=None):
    """Owner-space pos for header hit-testing (Wave E, event-only).

    Cursor sources are poisoned during ``QDrag.exec`` (frozen
    ``QCursor.pos()`` — move-trace proven), so the event position is the
    only live truth. ``receiver`` (when the caller knows it, e.g. zone
    forwarding) is mapped into owner space; otherwise the event pos is
    already owner-space (widget accepts drops anywhere).
    """
    return _owner_space_pos(owner, event, receiver)


def _series_id_for_index(grid, index: int) -> str | None:
    """Series id string for cluster *index* (first member id, else fallback)."""
    try:
        clusters = list(getattr(grid, "_series", None) or [])
        entry = clusters[index] if 0 <= int(index) < len(clusters) else None
    except Exception:
        entry = None
    members: list = []
    try:
        if entry is not None:
            if hasattr(entry, "members"):
                members = list(getattr(entry, "members", None) or [])
            elif isinstance(entry, (list, tuple)):
                members = list(entry)
    except Exception:
        members = []
    for m in members:
        try:
            sid = getattr(m, "series_id", None)
        except Exception:
            sid = None
        if sid is not None:
            try:
                return str(sid)
            except Exception:
                pass
    try:
        return f"series_{int(index) + 1}"
    except Exception:
        return None


def _dump_drop_geometry(owner, grid, headers, pos) -> None:
    """Firehose probe (Wave D diagnosis): headers/cards geometry at drop.

    Session-only, gated by the gallery debug flag (DEBUGGING.md rule 5:
    separate unfiltered flag-lines, never mixed into curated verdicts).
    Hypothesis under test: the drop resolves the wrong series because the
    header/card geometry or name→id mapping does not match the visible
    order. Kill condition: a drop whose dumped matching rect is the header
    the user aimed at, with the expected id.
    """
    try:
        from tabs.image_gallery.debug import gallery_dnd_debug_enabled as _gate
        if not _gate():
            return
    except Exception:
        return
    try:
        from PySide6.QtCore import QPoint as _QPoint
        from PySide6.QtCore import QRect as _QRect

        lines = ["drop-geometry pos=%s" % (pos,)]
        for i, hdr in enumerate(headers or []):
            try:
                top = hdr.mapTo(owner, _QPoint(0, 0))
                rect = _QRect(top, hdr.size())
                lines.append(
                    "hdr[%d] name=%r rect=%s hit=%s visible=%s" % (
                        i, hdr.objectName(),
                        "(%d,%d %dx%d)" % (rect.x(), rect.y(), rect.width(), rect.height()),
                        bool(rect.contains(pos)) if pos is not None else "?",
                        bool(hdr.isVisibleTo(owner)) if hasattr(hdr, "isVisibleTo") else "?",
                    )
                )
            except Exception as e:
                lines.append("hdr[%d] map failed: %r" % (i, e))
        try:
            cards = dict(getattr(grid, "_cards_by_path", None) or {})
        except Exception:
            cards = {}
        for key, card in cards.items():
            try:
                top = card.mapTo(owner, _QPoint(0, 0))
                rect = _QRect(top, card.size())
                lines.append(
                    "card %s rect=%s hit=%s visible=%s" % (
                        str(key).split("/")[-1],
                        "(%d,%d %dx%d)" % (rect.x(), rect.y(), rect.width(), rect.height()),
                        bool(rect.contains(pos)) if pos is not None else "?",
                        bool(card.isVisibleTo(owner)) if hasattr(card, "isVisibleTo") else "?",
                    )
                )
            except Exception as e:
                lines.append("card %s map failed: %r" % (key, e))
        try:
            order = []
            for entry in list(getattr(grid, "_series", None) or []):
                members = (
                    list(entry.members) if hasattr(entry, "members") else list(entry)
                )
                first = getattr(members[0], "series_id", None) if members else None
                order.append("%s:%d" % (first, len(members)))
            lines.append("clusters=%s" % (order,))
        except Exception as e:
            lines.append("clusters unreadable: %r" % e)
        for ln in lines:
            _dnd_log(ln)
    except Exception:
        pass


def series_target_at(owner, pos) -> tuple[bool, str | None]:
    """Resolve the drop-target series under *pos* (OWNER coords).

    *pos* must already be in owner space — callers pass
    ``_owner_hit_pos(owner, event)`` (live cursor mapped into the owner,
    receiver-relative pos as synthetic fallback),
    never the raw receiver-relative ``_event_pos``. Headers are compared via
    ``hdr.mapTo(owner)``, so owner space is the only correct frame.

    Returns ``(handled, series_id)``: ``series_id`` is the header cluster id
    under the cursor, or None for the UNGROUPED tail (forced UNGROUPED —
    also the fallback when the drop lands on no header). ``handled`` False
    means "no series chrome to drop onto" (empty pool / flat grid) — the
    caller must ignore the drop, never route it externally.
    """
    grid = getattr(owner, "_grid_view", None)
    if grid is None:
        # Bare doubles / storeless contexts: no chrome to hit-test, but
        # the controller still filters to pool members — route UNGROUPED.
        return (True, None)
    try:
        headers = list(getattr(grid, "_series_headers", None) or [])
    except Exception:
        headers = []
    if not headers or pos is None:
        return (False, None)
    _dump_drop_geometry(owner, grid, headers, pos)
    try:
        from PySide6.QtCore import QPoint as _QPoint
        from PySide6.QtCore import QRect as _QRect
    except Exception:
        return (False, None)
    for hdr_pos, hdr in enumerate(headers):
        try:
            top = hdr.mapTo(owner, _QPoint(0, 0))
            rect = _QRect(top, hdr.size())
            if not rect.contains(pos):
                continue
        except Exception:
            continue
        try:
            name = str(hdr.objectName() or "")
        except Exception:
            name = ""
        if name == _UNGROUPED_HEADER_NAME or name.endswith("_ungrouped"):
            return (True, None)
        index: int | None = None
        try:
            prefix = "GallerySeriesHeader_"
            if name.startswith(prefix):
                index = int(name[len(prefix):])
        except Exception:
            index = None
        if index is None:
            # Position fallback: series sections precede the UNGROUPED tail.
            try:
                n_series = len(list(getattr(grid, "_series", None) or []))
            except Exception:
                n_series = 0
            if hdr_pos < n_series:
                index = hdr_pos
            else:
                return (True, None)
        return (True, _series_id_for_index(grid, index))
    # No header hit: fall back to the card under the cursor (Wave D). Series
    # bodies are ~99% cards — drops land on cards, not on thin headers.
    try:
        found, card_sid = _card_hit_series(owner, grid, pos)
    except Exception:
        found, card_sid = False, None
    if found:
        return (True, card_sid)
    return (True, None)


def _header_button(header):
    """Header button for drop-target highlight (or None).

    Prefers the toolkit header ``Button`` by object name
    (``GallerySeriesHeaderBtn_*`` — it owns the painter layers, but has no
    Qt ``setDown``); falls back to the first setDown-capable child
    (legacy/PushButton doubles in tests).
    """
    try:
        from PySide6.QtWidgets import QWidget as _QW

        children = list(header.findChildren(_QW))
    except Exception:
        return None
    try:
        for child in children:
            try:
                name = str(child.objectName() or "")
            except Exception:
                continue
            if name.startswith("GallerySeriesHeaderBtn_"):
                return child
    except Exception:
        pass
    try:
        for child in children:
            try:
                if callable(getattr(child, "setDown", None)):
                    return child
            except Exception:
                continue
    except Exception:
        pass
    return None


def _clear_series_highlight(owner) -> None:
    """Drop the series-header drop-target highlight (fail-soft)."""
    try:
        current = getattr(owner, "_series_drop_target", None)
    except Exception:
        current = None
    if current is None:
        return
    try:
        owner._series_drop_target = None
    except Exception:
        pass
    header, btn, was_enabled = current if isinstance(current, tuple) else (current, None, None)
    if btn is None:
        try:
            btn = _header_button(header)
        except Exception:
            btn = None
    try:
        if btn is not None:
            try:
                down = getattr(btn, "setDown", None)
                if callable(down):
                    down(False)
            except Exception:
                pass
            try:
                btn._gallery_drop_target = False  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                btn.update()
            except Exception:
                pass
    except Exception:
        pass
    try:
        if was_enabled is False and btn is not None:
            btn.setEnabled(False)
    except Exception:
        pass


def _set_series_highlight(owner, header) -> None:
    """Highlight *header* as the live drop target (pressed-state accent).

    Reuses the header button's own pressed visuals — no QSS, no colors,
    no new API. Remembers the previous target to restore it. Fail-soft:
    headers whose button cannot render pressed state simply stay plain.
    """
    try:
        current = getattr(owner, "_series_drop_target", None)
        cur_header = current[0] if isinstance(current, tuple) else current
        if cur_header is header:
            return
    except Exception:
        pass
    _clear_series_highlight(owner)
    if header is None:
        return
    try:
        _dnd_log(
            "series highlight -> %s",
            getattr(header, "objectName", lambda: "?")(),
        )
    except Exception:
        pass
    btn = _header_button(header)
    was_enabled: bool | None = None
    try:
        if btn is not None:
            try:
                was_enabled = bool(btn.isEnabled())
            except Exception:
                was_enabled = None
            if was_enabled is False:
                # The UNGROUPED header button is disabled: enable it for the
                # drag duration (clicks cannot land mid-drag) so the pressed
                # state paints, then restore on clear.
                btn.setEnabled(True)
            # setDown is Qt-widget API: toolkit Buttons do not have it —
            # guard so the flag + update below always run (Wave E layer
            # reads the flag, not the pressed state).
            try:
                down = getattr(btn, "setDown", None)
                if callable(down):
                    down(True)
            except Exception:
                pass
            # Wave E color landing indicator (painter layer on the header
            # button reads this flag; reset in _clear_series_highlight).
            try:
                btn._gallery_drop_target = True  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                btn.update()
            except Exception:
                pass
    except Exception:
        pass
    try:
        owner._series_drop_target = (header, btn, was_enabled)
    except Exception:
        pass


def _card_path(card, fallback_key=None):
    """Filesystem path string for a gallery card (duck-typed, never raises)."""
    try:
        item = getattr(card, "_gallery_item", None)
        path = getattr(item, "path", None) if item is not None else None
        if path is None and card is not None and hasattr(card, "property"):
            try:
                path = card.property("gallery_path")
            except Exception:
                path = None
        if path is None or (not str(path) and fallback_key is not None):
            path = fallback_key
        return str(path) if path is not None else ""
    except Exception:
        try:
            return str(fallback_key) if fallback_key is not None else ""
        except Exception:
            return ""


def _card_hit_series(owner, grid, pos) -> tuple[bool, str | None]:
    """Series id of the card under *pos* (OWNER coords).

    Returns ``(found, series_id)``: ``series_id`` is the owning cluster id,
    or None for UNGROUPED-tail cards. ``found`` False means no card under
    the cursor. Model truth first (cluster membership by path in
    ``grid._series`` / ``grid._ungrouped``), live card attr second. Dropping
    onto a dragged card itself resolves its own series — the controller
    no-op guard then skips the retriage, so no exclusion is needed here.
    """
    if grid is None or pos is None:
        return (False, None)
    try:
        cards = getattr(grid, "_cards_by_path", None) or {}
        cards = dict(cards)
    except Exception:
        return (False, None)
    if not cards:
        return (False, None)
    try:
        from PySide6.QtCore import QPoint as _QPoint
        from PySide6.QtCore import QRect as _QRect

        for key, card in cards.items():
            try:
                top = card.mapTo(owner, _QPoint(0, 0))
                if not _QRect(top, card.size()).contains(pos):
                    continue
            except Exception:
                continue
            path = _card_path(card, key)
            sid: str | None = None
            resolved = False
            try:
                resolved, sid = _series_for_card_path(grid, path)
            except Exception:
                resolved, sid = False, None
            if not resolved:
                try:
                    item = getattr(card, "_gallery_item", None)
                    live = getattr(item, "series_id", None)
                    sid = str(live) if live is not None else None
                    resolved = True
                except Exception:
                    pass
            if resolved:
                return (True, sid)
            return (True, None)
    except Exception:
        pass
    return (False, None)


def _header_for_series(grid, headers, series_id):
    """Header widget for *series_id* (None = UNGROUPED header), or None."""
    try:
        headers = list(headers or [])
    except Exception:
        return None
    if not headers:
        return None
    try:
        target = str(series_id) if series_id is not None else None
    except Exception:
        target = None
    for hdr in headers:
        try:
            name = str(getattr(hdr, "objectName", lambda: "")() or "")
        except Exception:
            name = ""
        if target is None:
            if name == _UNGROUPED_HEADER_NAME or name.endswith("_ungrouped"):
                return hdr
        else:
            try:
                idx = headers.index(hdr)
            except Exception:
                continue
            try:
                if _series_id_for_index(grid, idx) == target:
                    return hdr
            except Exception:
                continue
    return None


def _header_at(owner, pos):
    """Header widget under *pos* (OWNER coords, see ``series_target_at``).

    Headers first; on a miss, the card under the cursor resolves to its
    series' header (Wave D — drops land on cards, highlight must follow).
    """
    grid = getattr(owner, "_grid_view", None)
    if grid is None or pos is None:
        return None
    try:
        headers = list(getattr(grid, "_series_headers", None) or [])
    except Exception:
        headers = []
    if headers:
        try:
            from PySide6.QtCore import QPoint as _QPoint
            from PySide6.QtCore import QRect as _QRect

            for hdr in headers:
                try:
                    top = hdr.mapTo(owner, _QPoint(0, 0))
                    if _QRect(top, hdr.size()).contains(pos):
                        return hdr
                except Exception:
                    continue
        except Exception:
            pass
    try:
        found, card_sid = _card_hit_series(owner, grid, pos)
    except Exception:
        return None
    if not found:
        return None
    try:
        return _header_for_series(grid, headers, card_sid)
    except Exception:
        return None


def _grid_has_headers(owner) -> bool:
    try:
        grid = getattr(owner, "_grid_view", None)
        return bool(grid is not None and list(getattr(grid, "_series_headers", None) or []))
    except Exception:
        return False
