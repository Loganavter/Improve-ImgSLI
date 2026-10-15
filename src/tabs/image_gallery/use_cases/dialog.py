"""Folder/image pick dialog — thin owner helper for ``ImageGalleryWidget``.

Plain function taking owner (widget) as first argument per CODE_PATTERNS.md.
Explicit dependencies: ``owner.window()`` for dialog parent and
``shared.image_extensions.ACCEPTED_IMAGE_EXTENSIONS`` for filter.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog as _RealQFileDialog

# Public alias — so tests can monkeypatch either widget or this module.
QFileDialog = _RealQFileDialog


def _resolve_qfiledialog():  # type: ignore[no-untyped-def]
    """Resolve QFileDialog class, honoring monkeypatch on widget or dialog module for tests.

    Tests patch ``tabs.image_gallery.widget.QFileDialog``; dialog logic lives
    in this module after refactor. To keep that patch effective without an
    implied widget lookup for real code, check both modules at call time
    and use the patched attribute if it has been replaced (fake dialog).
    """
    try:
        import sys

        # Prefer widget patch (legacy test path)
        mod = sys.modules.get("tabs.image_gallery.widget")
        if mod is not None:
            cand = getattr(mod, "QFileDialog", None)
            if cand is not None and cand is not _RealQFileDialog:
                return cand
        # Also honor direct patch on this module
        mod2 = sys.modules.get("tabs.image_gallery.use_cases.dialog")
        if mod2 is not None:
            cand2 = getattr(mod2, "QFileDialog", None)
            if cand2 is not None and cand2 is not _RealQFileDialog:
                return cand2
    except Exception:
        pass
    return _RealQFileDialog


def _dispatch_pick(owner, chosen: str) -> None:
    """Dispatch the pool action for an explicit folder/file pick (fail-open).

    Dirs open the pool (``GalleryPoolOpened`` with scanned entries), files
    replace it (``GalleryPoolReplaced``, explicit-pick semantics mirroring
    ``controller._on_pick_folder``). The controller call that follows stays
    for thumbnail/triage side-effects until W2b reads the slot.
    """
    try:
        from core.state_management.gallery_actions import (
            GalleryPoolOpened,
            GalleryPoolReplaced,
        )
        from tabs.image_gallery.ui.gallery_store import (
            dispatch_gallery,
            entries_for_folder,
            entries_for_paths,
        )

        p = Path(chosen)
        try:
            if p.is_dir():
                dispatch_gallery(
                    owner, GalleryPoolOpened(folder=str(p), entries=entries_for_folder(p))
                )
            elif p.is_file():
                dispatch_gallery(
                    owner, GalleryPoolReplaced(folder=None, entries=entries_for_paths([p]))
                )
        except Exception:
            pass
    except Exception:
        pass


def _owner_translate(owner):  # type: ignore[no-untyped-def]
    """Tab translator reachable from the owning widget (fail-open to EN).

    ``ImageGalleryWidget`` exposes ``_tr_ui(key, default)`` (its context
    translator); test doubles only have ``window()``, so a missing
    attribute degrades to the English defaults instead of raising.
    """
    tr = getattr(owner, "_tr_ui", None)
    if not callable(tr):
        tr = getattr(owner, "_tr", None)
    return tr if callable(tr) else None


def _tr(tr, key: str, default: str) -> str:  # type: ignore[no-untyped-def]
    """Gallery i18n lookup — EN ``default`` when no translator is reachable."""
    if tr is None:
        return default
    try:
        return str(tr(key, default))
    except Exception:
        return default


def pick_folder_dialog(owner, start_dir: str = "") -> str | None:  # type: ignore[no-untyped-def]
    """Allow picking either a folder or an image file.

    Returns the chosen file or folder path as string, or None if cancelled.
    Uses ``owner.window()`` as dialog parent and
    ``shared.image_extensions.ACCEPTED_IMAGE_EXTENSIONS`` for the image filter.
    """
    QFileDialog = _resolve_qfiledialog()
    tr = _owner_translate(owner)
    base = owner.window() or owner
    try:
        from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS as _EXTS

        # The group label and its trailing ");;" stay literal — Qt filter
        # syntax, not prose. Only the two user-visible labels are keyed.
        filt = _tr(tr, "image_gallery.toolbar.filter_images", "Images (")
        filt += " ".join(f"*{e}" for e in sorted(_EXTS))
        filt += ");;"
        filt += _tr(tr, "image_gallery.toolbar.filter_all_files", "All files (*)")
        dlg = QFileDialog(
            base,
            _tr(tr, "image_gallery.toolbar.pick_title", "Pick folder or image"),
            start_dir,
            filt,
        )
        # Native dialog like everywhere else in the app (export, project
        # open/save, video editor): no DontUseNativeDialog — the gallery
        # was the only non-native outlier. Folder picking stays on the
        # getExistingDirectory fallback below.
        try:
            dlg.setFileMode(QFileDialog.FileMode.ExistingFiles)
        except Exception:
            pass
        if dlg.exec():
            files = dlg.selectedFiles()
            if files:
                p = Path(files[0])
                _dispatch_pick(owner, str(p))
                return str(p)
        directory = QFileDialog.getExistingDirectory(
            base,
            _tr(tr, "image_gallery.toolbar.pick_folder", "Pick folder"),
            start_dir,
        )
        if directory:
            _dispatch_pick(owner, directory)
        return directory or None
    except Exception:
        try:
            directory = QFileDialog.getExistingDirectory(
                base,
                _tr(tr, "image_gallery.toolbar.pick_folder", "Pick folder"),
                start_dir,
            )
            return directory or None
        except Exception:
            return None
