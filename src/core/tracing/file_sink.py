from __future__ import annotations

import json
import logging
import os
import threading
from typing import Optional

from sli_ui_toolkit.core.logging import get_log_directory

from .records import TraceRecord
from .tracer import Tracer

logger = logging.getLogger("ImproveImgSLI")

_INSTALLED = False
_FILE_LOCK = threading.Lock()
_FILE_HANDLE: Optional["object"] = None
_FILE_PATH: Optional[str] = None

def install_file_sink(app_name: str = "ImproveImgSLI", filename: str = "trace.jsonl") -> Optional[str]:
    """
    Subscribe to the Tracer and append every record as a JSON line to
    <log_dir>/<filename>. Truncates the file on each app start so the file
    only contains records from the current session.

    Returns the absolute path, or None if the sink could not be installed.
    """
    global _INSTALLED, _FILE_HANDLE, _FILE_PATH
    if _INSTALLED:
        return _FILE_PATH

    try:
        log_dir = get_log_directory(app_name)
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, filename)
        _FILE_HANDLE = open(path, "w", encoding="utf-8", buffering=1)
        _FILE_PATH = path
    except OSError as exc:
        logger.warning("trace file sink install failed: %s", exc)
        return None

    Tracer.instance().subscribe(_on_record)
    _INSTALLED = True
    logger.info("trace file sink active: %s", path)
    return path

def _on_record(rec: TraceRecord) -> None:
    handle = _FILE_HANDLE
    if handle is None:
        return
    try:
        line = json.dumps(rec.to_dict(), default=str, ensure_ascii=False)
    except Exception:
        return
    with _FILE_LOCK:
        try:
            handle.write(line)
            handle.write("\n")
        except (OSError, ValueError):
            pass
