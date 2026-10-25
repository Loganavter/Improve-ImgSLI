"""One-way startup copy of the persisted settings identity (old -> new).

The product is now BlinkTable, but releases up to this one persisted every
user preference under the legacy identity (``LEGACY_SETTINGS_ORG`` /
``LEGACY_SETTINGS_APP`` below — the pre-rename ``improve-imgsli`` pair). This
module copies that store into the new namespace **once**, before any code can
read the new namespace, so an upgrade keeps every preference.

Rules (deliberate, do not "improve" them into a two-way sync):

* new namespace EMPTY and old namespace populated -> copy every key/group once.
  QSettings arrays are child keys (``name/1..n`` + ``name/size``); they are
  copied key by key, never collapsed into a list.
* the OLD namespace is never written, renamed or deleted in this release — it
  is the one-way fallback if the new namespace turns out to be wrong.
* both populated -> the new namespace wins; nothing is copied, the old store
  is not touched (a downgrade-then-upgrade keeps whatever the user has now).
* old namespace empty/absent -> no writes anywhere (a genuinely fresh install
  must not get an empty BlinkTable config out of nowhere).
* idempotent per process: the first call does the work, every later call
  returns the cached report. ``reset_migration_cache`` exists only for tests.
* fail-open: a corrupt/partially readable old store, a read-only config dir or
  any other failure is logged once and startup continues with defaults.

What this module deliberately does NOT touch: the log directory. Logging is
configured through the toolkit's ``setup_logging(app_name, ...)``, which uses
ONE name for both the logger and the directory, so moving the directory needs
the logger rename plus a toolkit change — not a half-rename here. Logger names,
env vars, package ids and the log directory stay as they are.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QSettings
from core.log_names import APP_LOGGER_NAME

#: Persisted identity used by every release before the BlinkTable rename.
#: The single home of these literals — ``core.plugin_system.settings``
#: re-exports them, and no other module may spell them out again.
LEGACY_SETTINGS_ORG = "improve-imgsli"
LEGACY_SETTINGS_APP = "improve-imgsli"

logger = logging.getLogger(APP_LOGGER_NAME)

#: ``None`` = not attempted yet in this process; a dict is the finished report.
_report: dict[str, Any] | None = None


def _target_pair() -> tuple[str, str]:
    """The canonical (org, app) pair, resolved lazily to avoid an import cycle.

    ``core.plugin_system.settings`` imports the legacy constants from this
    module, so the new pair is read at call time instead of at import time.
    """
    from core.plugin_system.settings import SETTINGS_APP, SETTINGS_ORG

    return SETTINGS_ORG, SETTINGS_APP


def _make_report(
    status: str,
    reason: str,
    *,
    org: str = "",
    app: str = "",
    legacy_keys: int = 0,
    new_keys: int = 0,
    copied_keys: int = 0,
    failed_keys: int = 0,
) -> dict[str, Any]:
    """Build the small report every caller (and every test) reads."""
    return {
        "status": status,  # "copied" | "kept" | "skipped"
        "reason": reason,
        "org": org,
        "app": app,
        "legacy_org": LEGACY_SETTINGS_ORG,
        "legacy_app": LEGACY_SETTINGS_APP,
        "legacy_keys": legacy_keys,
        "new_keys": new_keys,
        "copied_keys": copied_keys,
        "failed_keys": failed_keys,
    }


def _copy_all_keys(legacy: QSettings, new: QSettings) -> tuple[int, int]:
    """Copy every leaf key of *legacy* into *new*; return (copied, failed).

    Copies ``allKeys()`` one key at a time so QSettings array children
    (``name/1..n`` + ``name/size``) keep their shape. A single unreadable or
    unwritable key is counted and skipped — the copy is best-effort, never
    all-or-nothing, because blocking startup is the worse failure.
    """
    copied = 0
    failed = 0
    for key in legacy.allKeys():
        try:
            value = legacy.value(key)
        except Exception:  # unreadable value: never block startup over it
            failed += 1
            continue
        try:
            new.setValue(key, value)
        except Exception:  # read-only config dir, quota, …
            failed += 1
            continue
        copied += 1
    if copied:
        new.sync()
    return copied, failed


def _migrate() -> dict[str, Any]:
    """Run the one-way copy. Any exception propagates to the fail-open caller."""
    org, app = _target_pair()
    if (org, app) == (LEGACY_SETTINGS_ORG, LEGACY_SETTINGS_APP):
        # Defensive: identical identities would make the copy a self-write.
        return _make_report(
            "skipped",
            "canonical and legacy identity are the same; nothing to migrate",
            org=org,
            app=app,
        )

    new = QSettings(org, app)
    new_keys = new.allKeys()
    if new_keys:
        return _make_report(
            "kept",
            "new namespace already populated; old namespace left untouched",
            org=org,
            app=app,
            new_keys=len(new_keys),
        )

    legacy = QSettings(LEGACY_SETTINGS_ORG, LEGACY_SETTINGS_APP)
    legacy_keys = legacy.allKeys()
    if not legacy_keys:
        return _make_report(
            "skipped",
            "old namespace holds no keys; nothing to copy",
            org=org,
            app=app,
        )

    copied, failed = _copy_all_keys(legacy, new)
    if failed:
        return _make_report(
            "copied",
            f"copied {copied} of {len(legacy_keys)} legacy keys; "
            f"{failed} unreadable/unwritable (old namespace untouched)",
            org=org,
            app=app,
            legacy_keys=len(legacy_keys),
            new_keys=len(new.allKeys()),
            copied_keys=copied,
            failed_keys=failed,
        )
    return _make_report(
        "copied",
        f"copied {copied} legacy keys into the new namespace",
        org=org,
        app=app,
        legacy_keys=len(legacy_keys),
        new_keys=len(new.allKeys()),
        copied_keys=copied,
    )


def migrate_settings_once() -> dict[str, Any]:
    """Run the legacy-namespace copy once per process and report what happened.

    Wired from ``core.plugin_system.settings.canonical_settings`` and from
    ``SettingsManager.__init__``, so it cannot be skipped by a caller that
    reads the new namespace first. Safe to call anywhere, any number of times.
    """
    global _report
    if _report is not None:
        return dict(_report)

    try:
        report = _migrate()
    except Exception as exc:  # corrupt store, permissions, backend failure
        logger.warning(
            "[settings] legacy settings migration failed (%s); continuing with "
            "defaults — the old namespace is untouched",
            exc,
        )
        report = _make_report("skipped", f"migration failed: {exc}")

    _report = report
    if report["status"] == "copied":
        level = logging.WARNING if report["failed_keys"] else logging.INFO
        logger.log(
            level,
            "[settings] settings identity migrated %s/%s -> %s/%s: %s",
            report["legacy_org"],
            report["legacy_app"],
            report["org"],
            report["app"],
            report["reason"],
        )
    else:
        logger.debug(
            "[settings] settings migration %s: %s", report["status"], report["reason"]
        )
    return dict(report)


def reset_migration_cache() -> None:
    """Forget the per-process result so the next call runs again (tests only)."""
    global _report
    _report = None
