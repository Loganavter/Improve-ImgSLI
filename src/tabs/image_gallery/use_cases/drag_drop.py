"""External file-drop handling for ``ImageGalleryTab`` -- split out of
``tab.py`` (G4) to keep that class down to the ``TabContract`` surface
itself, mirroring ``tabs.image_compare.use_cases.drag_drop``.
``accepts_drop``/``handle_drop`` are required ``TabContract`` method names,
so ``tab.py`` keeps thin delegators of those exact names; the bodies live
here as plain functions taking the tab as first argument (``accepts_drop``
is tab-free: the accept rule depends only on the dropped paths).
"""

from __future__ import annotations

import logging
from pathlib import Path

from shared.image_extensions import is_accepted_image_path, is_loadable_image_path
from tabs.image_gallery.debug import gallery_debug as _dbg
from tabs.image_gallery.debug import gallery_dnd_debug as _dnd_log

logger = logging.getLogger("ImproveImgSLI")


def accepts_drop(paths: list[Path]) -> bool:
    _dnd_log("accepts_drop: %d paths %r", len(paths), paths[:3])
    # Accept both image files and directories (for folder triage) — fixes folder DnD
    for p in paths:
        pp = Path(p)
        try:
            ok = is_accepted_image_path(pp) or pp.is_dir()
        except Exception:
            ok = False
        _dnd_log("  accepts_drop check %s suffix=%s is_dir=%s -> %s", p, pp.suffix.lower(), pp.is_dir() if p.exists() else "?", ok)
        if ok:
            return True
        # also accept url string that may be dir without suffix
        try:
            if Path(str(p)).is_dir():
                return True
        except Exception:
            pass
    return False


def handle_drop(tab, paths: list[Path], hint: dict | None = None) -> bool:
    _dnd_log("handle_drop: ENTER %d paths %r hint=%r", len(paths), paths[:5], hint)
    if tab._widget is None or tab._controller is None:
        _dnd_log("handle_drop: no widget/controller -> False")
        return False
    _dnd_log("handle_drop: %d paths %r", len(paths), paths[:5])
    for p in paths[:5]:
        try:
            _dnd_log("  handle_drop path %s exists=%s is_file=%s is_dir=%s suffix=%s", p, p.exists(), p.is_file(), p.is_dir(), p.suffix.lower())
        except Exception:
            pass
    # Accept if at least one path is a supported image or a directory.
    accepted = [Path(p) for p in paths if is_accepted_image_path(Path(p)) or Path(p).is_dir()]
    if not accepted:
        if not accepts_drop([Path(p) for p in paths]):
            _dbg("handle_drop: no accepted paths")
            return False
        accepted = [Path(p) for p in paths if is_accepted_image_path(Path(p))]
        if not accepted:
            return False
    # If all dropped are image files (single or multiple), open just them — don't scan parent
    try:
        all_files = all(is_loadable_image_path(p) for p in accepted if p.exists()) and any(
            p.is_file() for p in accepted
        )
        has_dir = any(p.is_dir() for p in accepted)
    except Exception:
        all_files = False
        has_dir = False
    if all_files and not has_dir:
        _dbg("handle_drop: single/multi image %d -> open_paths", len(accepted))
        from tabs.image_gallery.use_cases.large_drop_guard import guard_large_drop

        if not guard_large_drop(tab._widget, tab._controller, len(accepted)):
            _dbg("handle_drop: large AI-drop warning declined -> nothing added")
            return True
        try:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, lambda ps=list(accepted): tab._controller.open_paths(ps))
            return True
        except Exception:
            try:
                tab._controller.open_paths(list(accepted))
                return True
            except Exception:
                _dbg("open_paths failed", exc_info=True)
                return False
    # Prefer a dropped directory; otherwise open the parent of the first image.
    folder: Path | None = None
    for p in accepted:
        if p.is_dir():
            folder = p
            break
    if folder is None:
        first = accepted[0]
        folder = first.parent if first.is_file() or first.suffix else first.parent
    if folder is None or not folder.is_dir():
        _dbg("handle_drop: no folder found")
        return False
    _dbg("handle_drop: folder %s", folder)
    try:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, lambda f=folder: tab._controller.open_folder(f))
    except Exception:
        try:
            tab._controller.open_folder(folder)
        except Exception:
            _dbg("open_folder failed", exc_info=True)
            return False
    return True
