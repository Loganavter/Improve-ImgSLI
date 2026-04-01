import os
import sys
from pathlib import Path


def _existing_dirs(candidates):
    for candidate in candidates:
        if candidate and candidate.is_dir():
            yield candidate


def _register_windows_dll_dirs():
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return

    roots = []
    if getattr(sys, "frozen", False):
        roots.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)))
        roots.append(Path(sys.executable).resolve().parent)
    else:
        try:
            import PyQt6  # pylint: disable=import-outside-toplevel

            roots.append(Path(PyQt6.__file__).resolve().parent)
        except Exception:
            pass

    candidates = []
    for root in roots:
        candidates.extend(
            [
                root,
                root / "PyQt6",
                root / "PyQt6" / "Qt6" / "bin",
                root / "Qt6" / "bin",
                root / "plugins",
                root / "platforms",
            ]
        )

    seen = set()
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    for directory in _existing_dirs(candidates):
        resolved = str(directory.resolve())
        key = resolved.lower()
        if key in seen:
            continue
        seen.add(key)
        os.add_dll_directory(resolved)
        if resolved not in path_entries:
            path_entries.insert(0, resolved)

    os.environ["PATH"] = os.pathsep.join(path_entries)

    if roots:
        primary = next(_existing_dirs([roots[0] / "PyQt6" / "Qt6" / "plugins", roots[0] / "Qt6" / "plugins", roots[0] / "plugins"]), None)
        platforms = next(
            _existing_dirs(
                [
                    roots[0] / "PyQt6" / "Qt6" / "plugins" / "platforms",
                    roots[0] / "Qt6" / "plugins" / "platforms",
                    roots[0] / "platforms",
                ]
            ),
            None,
        )
        if primary:
            os.environ.setdefault("QT_PLUGIN_PATH", str(primary.resolve()))
        if platforms:
            os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(platforms.resolve()))


_register_windows_dll_dirs()
