"""Spawn console child processes without a flashing console window.

The 2026-10-24 report this module exists for: opening the video editor
flashed a ``cmd`` window for a couple of frames on Windows. Cause: the app is
built as a **windowed** (GUI-subsystem) executable, so it owns no console; when
it spawns a console-subsystem child (``ffmpeg.exe`` for the encoder probe), the
child gets a fresh console window allocated by Windows. The export path already
passed ``CREATE_NO_WINDOW``; the probe on dialog open did not.

Qt does not abstract this, and neither does ``subprocess``: every spawn of a
console tool has to opt out explicitly on Windows. One helper, one truth:

    subprocess.run([ffmpeg, "-encoders"], **hidden_process_kwargs())

``tests/contracts/test_hidden_console_spawns.py`` fails any other
``subprocess`` spawn under ``src/`` that does not go through this helper (with
an allowlist for developer tools, which are meant to run in a terminal), so the
flash cannot come back through a new call site.
"""

from __future__ import annotations

import os
import subprocess

#: ``CREATE_NO_WINDOW`` -- the child runs without a console window. Present on
#: Windows only; spelled as a literal so this module imports on any host.
_CREATE_NO_WINDOW = int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))


def hidden_process_kwargs() -> dict[str, object]:
    """Keyword args for ``subprocess.Popen/run/call`` that keep it invisible.

    Returns ``{}`` on non-Windows hosts (no console is ever created there), and
    ``{"creationflags": CREATE_NO_WINDOW}`` on Windows. Merge it last::

        subprocess.run(argv, capture_output=True, **hidden_process_kwargs())
    """
    if os.name != "nt":
        return {}
    return {"creationflags": _CREATE_NO_WINDOW}
