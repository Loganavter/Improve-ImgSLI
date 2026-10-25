"""The one spelling of the application's identity for logging.

``setup_logging`` in ``sli_ui_toolkit`` attaches its handlers to the logger
literally named after the app **and** derives the per-OS log directory from
that same string, so the name below is the single source of truth for both:
renaming it here renames the logger *and* moves the log directory.

The application was called ``ImproveImgSLI`` until the BlinkTable rename. The
old strings survive only as ``LEGACY_*``: the app-data directory users already
have on disk is imported (symlinked) once at startup by
``core.log_dir_migration.migrate_log_directory_once`` so an upgrade does not
orphan the existing ``log.txt``/``trace.jsonl``. Do not reintroduce the old
name as a logger id anywhere — every ``getLogger`` call site goes through
``APP_LOGGER_NAME`` and ``tests/runtime/test_log_identity.py`` scans the
source tree for the legacy literal.
"""

from __future__ import annotations

#: Product name shown to the user (window titles, About, dialogs).
APP_NAME = "BlinkTable"

#: Logger name handed to ``setup_logging`` and every ``getLogger`` call site.
APP_LOGGER_NAME = "BlinkTable"

#: Logger name used before the rename — read only by the log-dir migration.
LEGACY_LOGGER_NAME = "ImproveImgSLI"

#: Per-OS app-data directory the pre-rename builds wrote logs into.
LEGACY_LOG_DIR_NAME = "ImproveImgSLI"
