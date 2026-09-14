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


def pick_folder_dialog(owner, start_dir: str = "") -> str | None:  # type: ignore[no-untyped-def]
    """Allow picking either a folder or an image file.

    Returns the chosen file or folder path as string, or None if cancelled.
    Uses ``owner.window()`` as dialog parent and
    ``shared.image_extensions.ACCEPTED_IMAGE_EXTENSIONS`` for the image filter.
    """
    QFileDialog = _resolve_qfiledialog()
    base = owner.window() or owner
    try:
        from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS as _EXTS

        filt = "Images ("
        filt += " ".join(f"*{e}" for e in sorted(_EXTS))
        filt += ");;All files (*)"
        dlg = QFileDialog(base, "Pick folder or image", start_dir, filt)
        try:
            dlg.setFileMode(QFileDialog.FileMode.ExistingFiles)
            dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        except Exception:
            pass
        if dlg.exec():
            files = dlg.selectedFiles()
            if files:
                p = Path(files[0])
                return str(p)
        directory = QFileDialog.getExistingDirectory(base, "Pick folder", start_dir)
        return directory or None
    except Exception:
        try:
            directory = QFileDialog.getExistingDirectory(base, "Pick folder", start_dir)
            return directory or None
        except Exception:
            return None
