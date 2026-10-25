"""One-time import of the pre-rename log directory.

``setup_logging`` derives its per-OS log directory from the app name, so the
``APP_LOGGER_NAME`` rename (``core.log_names``) silently moves
``log.txt``/``trace.jsonl`` to a fresh directory and orphans the one users and
support scripts already have. This module runs once at startup, *before*
logging is configured, and makes the new directory an alias of the old one:

* new absent, old present, POSIX → ``new`` becomes a **symlink** to ``old``
  (``linked``). The old directory is never moved: a live process — or the
  user's shell — may have it open.
* new absent, old present, Windows → ``old`` is **renamed** to ``new``
  (``renamed``); symlinks need privileges there and the app is not running
  with the old path open at this point.
* new present → left untouched (``kept``): a real directory from an earlier
  run always wins over aliasing.
* nothing to do, or anything failed → ``none``.

The function never raises and never deletes or overwrites anything — a failed
migration only means the next run starts with a fresh log directory.
"""

from __future__ import annotations

import logging
import os
import sys

from core.log_names import APP_LOGGER_NAME, LEGACY_LOG_DIR_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: Actions returned by :func:`migrate_log_directory_once`.
LINKED = "linked"
RENAMED = "renamed"
KEPT = "kept"
NONE = "none"


def migrate_log_directory_once() -> str:
    """Alias the legacy app-data log directory to the new one, once.

    Idempotent by filesystem state: after the first successful run the new path
    exists, so later calls return ``"kept"``. Callers may invoke it on every
    start (``core.bootstrap:_configure_logging`` does, before
    ``setup_logging``).
    """
    try:
        from sli_ui_toolkit.core.logging import get_log_directory

        new_dir = get_log_directory(APP_LOGGER_NAME)
        old_dir = get_log_directory(LEGACY_LOG_DIR_NAME)
    except Exception:  # windowless/partial installs must still boot
        return NONE

    try:
        if not new_dir or not old_dir:
            return NONE
        if os.path.lexists(new_dir):
            if os.path.exists(new_dir):
                return KEPT
            # Dangling alias: the legacy directory it pointed at is gone, so a
            # later ``setup_logging`` could not create a file behind the dead
            # link. Dropping the link is not data loss (its target no longer
            # exists) and lets the fresh directory be created below/next start.
            os.unlink(new_dir)
        if not os.path.isdir(old_dir):
            return NONE

        if sys.platform == "win32":
            # Only ever when the destination is absent (checked above): a
            # rename onto an existing directory would fail, and a copy is not
            # wanted — the old tree must stay a single source of truth.
            os.rename(old_dir, new_dir)
            return RENAMED

        os.makedirs(os.path.dirname(new_dir), exist_ok=True)
        os.symlink(old_dir, new_dir, target_is_directory=True)
        return LINKED
    except OSError as exc:
        logger.debug("log directory migration skipped: %s", exc)
        return NONE
    except Exception as exc:  # never let startup fail over a log path
        logger.debug("log directory migration failed: %s", exc)
        return NONE
