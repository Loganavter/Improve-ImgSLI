"""Stdio / faulthandler bootstrap for windowed (no-console) frozen apps.

PyInstaller ``--noconsole`` / ``pythonw`` leave ``sys.stdin`` / ``stdout`` /
``stderr`` as ``None``. Calling ``faulthandler.enable()`` then raises
``RuntimeError: sys.stderr is None`` and aborts startup before Qt.
"""

from __future__ import annotations

import faulthandler
import os
import sys


def ensure_stdio() -> None:
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8", errors="replace")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")


def enable_faulthandler() -> None:
    # Opt-in hang dumps: set IMGSLI_FAULT_DUMP=1 (optional IMGSLI_FAULT_DUMP_FILE /
    # IMGSLI_FAULT_DUMP_INTERVAL).
    if os.environ.get("IMGSLI_FAULT_DUMP"):
        fault_dump_path = os.environ.get(
            "IMGSLI_FAULT_DUMP_FILE", "/tmp/imgsli_fault_dump.log"
        )
        fault_dump_file = open(fault_dump_path, "w")
        faulthandler.enable(file=fault_dump_file, all_threads=True)
        faulthandler.dump_traceback_later(
            int(os.environ.get("IMGSLI_FAULT_DUMP_INTERVAL", "15")),
            repeat=True,
            file=fault_dump_file,
        )
        return

    try:
        # Needs a real OS fileno; skip quietly when stdio is a non-fd sink.
        if sys.stderr is None or not hasattr(sys.stderr, "fileno"):
            return
        sys.stderr.fileno()
        faulthandler.enable()
    except Exception:
        pass
