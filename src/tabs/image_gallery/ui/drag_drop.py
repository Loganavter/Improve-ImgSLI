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


def on_empty_file_dropped(owner, path_str: str) -> None:
    """Empty-state ``fileDropped`` handler — file vs folder."""
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
        # Single image file → open_paths (1 image), not parent folder (bug 2026-08-26)
        # Use shared accept check so behavior matches widget dropEvent
        if p.is_file() and p.suffix.lower() in _ACCEPTED_EXTS:
            ctrl = getattr(owner, "_controller", None)
            if ctrl is not None and hasattr(ctrl, "open_paths"):
                _dnd_log("on_empty_file_dropped: single image -> open_paths %s", p)
                ctrl.open_paths([p])
                return
        # Fallback: try as folder (e.g. dropped file without extension → parent)
        if p.is_file():
            _dnd_log("on_empty_file_dropped: fallback parent for %s", p)
            try_open_folder(owner, p.parent)
        else:
            try_open_folder(owner, p)
    except Exception as e:
        _dnd_log("on_empty_file_dropped failed: %r", e, exc_info=True)
        pass


def try_open_folder(owner, folder: Path) -> None:
    """Open *folder* via the widget's controller, else emit pick request."""
    folder = Path(folder)
    _dnd_log("try_open_folder: %s ctrl=%s", folder, getattr(owner, "_controller", None))
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
        all_files = all(p.is_file() and p.suffix.lower() in _EXTS2 for p in paths if p.exists()) and any(
            p.is_file() for p in paths
        )
        has_dir = any(p.is_dir() for p in paths)
        _dnd_log("dropEvent decision: all_files=%s has_dir=%s", all_files, has_dir)
        ctrl = None
        try:
            ctrl = owner._controller
        except AttributeError:
            ctrl = None
        except Exception:
            ctrl = None
        if all_files and not has_dir:
            _dnd_log("dropEvent single/multi image %d files -> open_paths (not parent folder)", len(paths))
            if ctrl is not None and hasattr(ctrl, "open_paths"):
                try:
                    ctrl.open_paths(paths)
                    event.accept()
                    return
                except Exception:
                    _dnd_log("open_paths failed", exc_info=True)
            try:
                from PySide6.QtCore import QTimer

                QTimer.singleShot(0, lambda ps=list(paths): try_open_folder(owner, ps[0]) if len(ps) == 1 else None)
            except Exception:
                pass
            return
        folder = None
        for p in paths:
            if p.is_dir():
                folder = p
                break
        if folder is None:
            first = paths[0]
            folder = first.parent if first.is_file() or first.suffix else first.parent
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
                    ctrl.open_paths(paths)
                    event.accept()
                    return
                except Exception:
                    _dnd_log("open_paths (mixed) failed", exc_info=True)
            if ctrl is not None and hasattr(ctrl, "open_folder"):
                try:
                    ctrl.open_folder(folder)
                    event.accept()
                    return
                except Exception:
                    _dbg("open_folder failed", exc_info=True)
            try:
                from PySide6.QtCore import QTimer

                QTimer.singleShot(0, lambda f=folder: try_open_folder(owner, f))
            except Exception:
                pass
    except Exception:
        pass
