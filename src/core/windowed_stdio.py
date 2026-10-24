"""Stdio / faulthandler bootstrap for windowed (no-console) frozen apps.

PyInstaller ``--noconsole`` / ``pythonw`` leave ``sys.stdin`` / ``stdout`` /
``stderr`` as ``None``. Calling ``faulthandler.enable()`` then raises
``RuntimeError: sys.stderr is None`` and aborts startup before Qt.

The same startup-position hazard applies to the opt-in fault dump: it is
armed from ``__main__`` before Qt exists, so an unwritable path (Windows
``%TEMP%`` policies, a read-only dir, a directory where the log file should
be) must *disable the dump*, never kill startup.
"""

from __future__ import annotations

import faulthandler
import logging
import os
import sys
import tempfile

from shared.debug_flags import env_flag as _env_flag

logger = logging.getLogger("ImproveImgSLI")


def ensure_stdio() -> None:
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8", errors="replace")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")


def enable_faulthandler() -> None:
    # Opt-in hang dumps: set IMGSLI_FAULT_DUMP=1 (optional IMGSLI_FAULT_DUMP_FILE /
    # IMGSLI_FAULT_DUMP_INTERVAL). The default lands in the system temp dir
    # (portable — Windows has no POSIX temp dir); an explicit _FILE is used
    # verbatim.
    # Never raises — a path problem disables the dump with one warning instead
    # of aborting startup before Qt (call order in ``__main__``).
    if _env_flag("IMGSLI_FAULT_DUMP"):
        fault_dump_path = os.environ.get(
            "IMGSLI_FAULT_DUMP_FILE",
            os.path.join(tempfile.gettempdir(), "imgsli_fault_dump.log"),
        )
        try:
            fault_dump_file = open(fault_dump_path, "w", encoding="utf-8")
            faulthandler.enable(file=fault_dump_file, all_threads=True)
            try:
                fault_dump_interval = int(
                    os.environ.get("IMGSLI_FAULT_DUMP_INTERVAL", "15")
                )
            except (TypeError, ValueError):
                fault_dump_interval = 15
            faulthandler.dump_traceback_later(
                fault_dump_interval,
                repeat=True,
                file=fault_dump_file,
            )
        except Exception as exc:  # noqa: BLE001 (startup must survive any path error)
            logger.warning(
                "Fault dump disabled: cannot open/wire %s (%s: %s)",
                fault_dump_path,
                type(exc).__name__,
                exc,
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
