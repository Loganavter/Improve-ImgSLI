"""Drag & drop orchestration for ``ImageGalleryWidget`` — thin-owner split.

Split out of ``widget.py`` per ``CODE_PATTERNS.md`` thin owner + ``ui/`` use_cases:
``ImageGalleryWidget`` keeps Qt-required method names (``dragEnterEvent`` etc.)
as one-liners that delegate here. All logic lives as plain functions taking
the owning widget as first argument, reading/writing its instance state
(``_empty_state``, ``_controller``, ``folder_pick_requested``) directly.

Public imports only; no ``setStyleSheet`` — painter pipeline owns visuals.
Controller dependency is explicit via ``owner._controller`` (no ``getattr``
lookups / window fallback) so tests can inject a fake owner.

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


def drag_enter_event(owner, event) -> None:
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
    else:
        event.ignore()


def drag_move_event(owner, event) -> None:
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


def drag_leave_event(owner, event) -> None:
    _dnd_log("dragLeaveEvent")
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


def _controller_of(owner):
    """Explicit controller lookup — no ``getattr`` fallbacks (see module docstring)."""
    try:
        return owner._controller
    except AttributeError:
        return None
    except Exception:
        return None


def _fallback_folder(paths: list[Path]) -> Path:
    """File-vs-folder fallback shared by zone + widget routing.

    Directories never reach here (the folder branch handles them); files —
    and suffix-less strays — resolve to their parent, never to themselves.
    """
    return paths[0].parent


def _dispatch_drop_pool(owner, *, all_files: bool, has_dir: bool, paths: list[Path], folder: Path | None) -> None:
    """Dispatch the pool action matching this drop (fail-open, Wave 2c).

    Mirrors the routing below: file-only drops append, mixed folder+files
    replace, pure folders open. Entries are ``[(path, mtime_ns), ...]`` —
    plain scalars per the frozen seam. The legacy ``ctrl.open_*`` calls
    stay (controller-owned thumbnail/triage side-effects until W2b reads
    the slot); the reducer dedups re-drops, so dispatch is idempotent.
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


def _route_paths(owner, paths: list[Path]) -> bool:
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
    ctrl = _controller_of(owner)
    # Redux first (fail-open): the gesture's state change is a dispatched
    # pool action; the controller calls below stay for pixmap/thumbnail
    # side-effects until the controller reads the slot (W2b).
    _folder_hint: Path | None = None
    for p in paths:
        try:
            if p.is_dir():
                _folder_hint = p
                break
        except Exception:
            continue
    if _folder_hint is None and not (all_files and not has_dir):
        try:
            _folder_hint = _fallback_folder(paths)
        except Exception:
            _folder_hint = None
    _dispatch_drop_pool(owner, all_files=all_files, has_dir=has_dir, paths=list(paths), folder=_folder_hint)
    if all_files and not has_dir:
        _dnd_log("dropEvent single/multi image %d files -> open_paths (not parent folder)", len(paths))
        if ctrl is not None and hasattr(ctrl, "open_paths"):
            try:
                ctrl.open_paths(paths)
                return True
            except Exception:
                _dnd_log("open_paths failed", exc_info=True)
        try:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, lambda ps=list(paths): try_open_folder(owner, ps[0]) if len(ps) == 1 else None)
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
        try:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, lambda f=folder: try_open_folder(owner, f))
        except Exception:
            pass
    return False


def on_empty_file_dropped(owner, path_str: str) -> None:
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
            try_open_folder(owner, p)
            return
        # Single image file → shared core (open_paths, 1 image — not parent
        # folder — same branch widget drop_event takes for one file).
        # Use shared accept check so behavior matches widget dropEvent
        if p.is_file() and p.suffix.lower() in _ACCEPTED_EXTS:
            _dnd_log("on_empty_file_dropped: single image -> open_paths %s", p)
            _route_paths(owner, [p])
            return
        if p.is_file():
            # Non-image file: ignore with a note. The widget path rejects
            # these via the shared accept check — never open the parent.
            _dnd_log("on_empty_file_dropped: non-image file ignored %s", p)
            _note(owner, f"Nothing to show — {p.name} is not a supported image.")
            return
        # Non-file, non-dir strays (fifo/socket/…) → same parent fallback
        # the widget path uses, never the path itself.
        try_open_folder(owner, _fallback_folder([p]))
    except Exception as e:
        _dnd_log("on_empty_file_dropped failed: %r", e, exc_info=True)
        pass


def try_open_folder(owner, folder: Path) -> None:
    """Open *folder* via the widget's controller, else emit pick request."""
    folder = Path(folder)
    _dnd_log("try_open_folder: %s ctrl=%s", folder, getattr(owner, "_controller", None))
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
        ctrl = owner._controller
        if ctrl is not None and hasattr(ctrl, "open_folder"):
            ctrl.open_folder(folder)
            return
    except AttributeError:
        pass
    except Exception as e:
        _dnd_log("try_open_folder open_folder failed: %r", e, exc_info=True)
        pass
    try:
        owner.folder_pick_requested.emit()
    except Exception:
        pass


def drop_event(owner, event) -> None:
    """Widget-level drop — shared accept check, then shared routing."""
    _dnd_log("dropEvent: enter")
    if not is_acceptable_drop(owner, event):
        _dnd_log("dropEvent: rejected by is_acceptable_drop -> ignore")
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
        if _route_paths(owner, list(paths)):
            try:
                event.accept()
            except Exception:
                pass
    except Exception:
        pass


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

    def __init__(self, owner):
        super().__init__()
        self._owner = owner

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
                drop_event(self._owner, event)
                return True
        except Exception as e:
            _dnd_log("zone drop filter failed: %r", e, exc_info=True)
            return False
        return False


def install_zone_drop_forwarding(owner) -> bool:
    """Route drops landing on the empty-state zone through ``drop_event``.

    Called once from ``ImageGalleryWidget.__init__`` (thin owner). Finds the
    zone label by objectName (``gallery_empty_drop_zone``) so this module
    never reaches into ``GalleryEmptyState`` privates. Idempotent; returns
    True when the filter is installed.
    """
    try:
        if getattr(owner, "_zone_drop_filter", None) is not None:
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
        filt = _ZoneDropFilter(owner)
        try:
            zone.installEventFilter(filt)
        except Exception:
            return False
        try:
            owner._zone_drop_filter = filt
        except Exception:
            pass
        return True
    except Exception:
        return False
