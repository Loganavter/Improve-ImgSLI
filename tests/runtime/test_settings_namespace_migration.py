"""One-way settings-identity migration (``improve-imgsli`` -> ``BlinkTable``).

The product renamed; releases before it persisted under
``QSettings("improve-imgsli", "improve-imgsli")``. A user must not lose a single
preference on upgrade, and the old namespace must survive this release intact
as the one-way fallback.

Every test redirects BOTH QSettings format paths at a temp directory (the
2-arg constructor resolves with the Native format on Linux, so redirecting
only ``IniFormat`` — or only ``setDefaultFormat`` — would still read/write the
real user config at ``~/.config/improve-imgsli``) and resets the per-process
migration cache around each test.
"""

from __future__ import annotations

import ast
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, QStandardPaths

import core.settings_migration as migration
from core.plugin_system.settings import (
    LEGACY_SETTINGS_APP,
    LEGACY_SETTINGS_ORG,
    SETTINGS_APP,
    SETTINGS_ORG,
    canonical_settings,
)
from core.settings_migration import (
    migrate_settings_once,
    reset_migration_cache,
)
from plugins.settings.manager import SettingsManager

_SRC = Path(__file__).resolve().parents[2] / "src"


# ---------------------------------------------------------------------------
# Isolation: QSettings -> a temp config root, migration cache -> fresh
# ---------------------------------------------------------------------------


@pytest.fixture
def qsettings_home(tmp_path):
    """Point every org/app QSettings at ``tmp_path`` and restore afterwards."""
    previous_format = QSettings.defaultFormat()
    previous_path = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.ConfigLocation
    )
    QSettings.setPath(
        QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    try:
        yield tmp_path
    finally:
        QSettings.setDefaultFormat(previous_format)
        QSettings.setPath(
            QSettings.Format.NativeFormat, QSettings.Scope.UserScope, previous_path
        )
        QSettings.setPath(
            QSettings.Format.IniFormat, QSettings.Scope.UserScope, previous_path
        )


@pytest.fixture(autouse=True)
def fresh_migration_state():
    """No migration result leaks in from an earlier test (or to a later one)."""
    reset_migration_cache()
    yield
    reset_migration_cache()


def _legacy() -> QSettings:
    return QSettings(LEGACY_SETTINGS_ORG, LEGACY_SETTINGS_APP)


def _new() -> QSettings:
    return QSettings(SETTINGS_ORG, SETTINGS_APP)


def _legacy_path(tmp_path) -> Path:
    path = Path(_legacy().fileName())
    # Safety net: a broken redirect must fail loudly instead of writing the
    # developer's real config store.
    assert str(tmp_path) in str(path), f"test would touch the real store: {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _seed_legacy(tmp_path, **values) -> Path:
    path = _legacy_path(tmp_path)
    settings = _legacy()
    for key, value in values.items():
        settings.setValue(key.replace("__", "/"), value)
    settings.sync()
    return path


# ---------------------------------------------------------------------------
# Old-only profile: the upgrade case
# ---------------------------------------------------------------------------


def test_old_only_profile_is_copied_and_readable_through_new_pair(
    qsettings_home, tmp_path
):
    _seed_legacy(tmp_path, theme="dark", language="ru", ui_scale_factor=1.25)

    report = migrate_settings_once()

    assert report["status"] == "copied", report
    assert report["legacy_keys"] == 3
    assert report["copied_keys"] == 3
    assert report["failed_keys"] == 0

    copied = _new()
    assert copied.value("theme") == "dark"
    assert copied.value("language") == "ru"
    assert float(copied.value("ui_scale_factor")) == 1.25


def test_groups_and_arrays_are_copied_without_collapsing(qsettings_home, tmp_path):
    """A QSettings array is child keys (name/1..n + name/size), not a list."""
    legacy = _legacy()
    for key, value in {
        "recent_paths/size": 3,
        "recent_paths/1": "/a.png",
        "recent_paths/2": "/b.png",
        "recent_paths/3": "/c.png",
        "image_gallery_ai/model": "demo-model",
        "string_list": ["/x.png", "/y.png"],
    }.items():
        legacy.setValue(key, value)
    legacy.sync()

    report = migrate_settings_once()
    assert report["status"] == "copied", report

    copied = _new()
    keys = copied.allKeys()
    assert {
        "recent_paths/size",
        "recent_paths/1",
        "recent_paths/2",
        "recent_paths/3",
        "image_gallery_ai/model",
    } <= set(keys), keys
    assert copied.value("recent_paths/size") == 3
    assert copied.value("recent_paths/2") == "/b.png"
    assert copied.value("image_gallery_ai/model") == "demo-model"
    # A list-typed value round-trips as a list, not as a stringified blob.
    assert copied.value("string_list") == ["/x.png", "/y.png"]


# ---------------------------------------------------------------------------
# Both populated: the new namespace wins, old store is never touched
# ---------------------------------------------------------------------------


def test_both_populated_new_wins_and_old_store_is_byte_identical(
    qsettings_home, tmp_path
):
    legacy_path = _seed_legacy(tmp_path, theme="dark", language="ru")
    new = _new()
    new.setValue("theme", "light")
    new.sync()
    before = legacy_path.read_bytes()

    report = migrate_settings_once()

    assert report["status"] == "kept", report
    assert report["copied_keys"] == 0
    assert _new().value("theme") == "light", "new namespace must not be clobbered"
    assert _new().value("language") is None, "nothing may be copied over it"
    assert legacy_path.read_bytes() == before, "old store must stay byte-identical"


# ---------------------------------------------------------------------------
# Nothing to migrate: no writes anywhere
# ---------------------------------------------------------------------------


def test_missing_old_namespace_writes_nothing(qsettings_home, tmp_path):
    legacy_path = _legacy_path(tmp_path)
    new_path = Path(_new().fileName())
    assert not legacy_path.exists()
    assert not new_path.exists()

    report = migrate_settings_once()

    assert report["status"] == "skipped", report
    assert "no keys" in report["reason"]
    assert not legacy_path.exists(), "a copy must not materialize the old store"
    assert not new_path.exists(), "a fresh install must not get an empty config"
    assert _new().allKeys() == []


def test_empty_old_file_is_not_migrated(qsettings_home, tmp_path):
    legacy_path = _legacy_path(tmp_path)
    legacy_path.write_text("[General]\n")
    _legacy().sync()

    report = migrate_settings_once()

    assert report["status"] == "skipped", report
    assert _new().allKeys() == []


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------


def test_second_call_is_a_no_op(qsettings_home, tmp_path):
    _seed_legacy(tmp_path, theme="dark")

    first = migrate_settings_once()
    assert first["status"] == "copied", first

    # A key written to the old namespace AFTER the copy must not appear: the
    # migration runs once per process, not as a watcher.
    _seed_legacy(tmp_path, late_key="late")
    second = migrate_settings_once()

    assert second == first, "the cached report must be returned unchanged"
    assert _new().value("late_key") is None


def test_reset_cache_reruns_and_new_namespace_still_wins(qsettings_home, tmp_path):
    _seed_legacy(tmp_path, theme="dark")
    assert migrate_settings_once()["status"] == "copied"
    _seed_legacy(tmp_path, late_key="late")

    reset_migration_cache()
    rerun = migrate_settings_once()

    assert rerun["status"] == "kept", rerun
    assert _new().value("theme") == "dark"
    assert _new().value("late_key") is None


# ---------------------------------------------------------------------------
# Fail-open
# ---------------------------------------------------------------------------


def test_corrupt_old_store_does_not_block_startup(qsettings_home, tmp_path):
    _legacy_path(tmp_path).write_bytes(
        b"\x00\xff\xfe not ini \n[broken\nkey without value =\n\xff"
    )

    report = migrate_settings_once()  # must not raise

    assert report["status"] in {"skipped", "copied"}, report
    # The app can still open its usual store and build a manager.
    assert canonical_settings() is not None
    SettingsManager(SETTINGS_ORG, SETTINGS_APP)


def test_migration_failure_is_reported_skipped_not_raised(
    qsettings_home, tmp_path, monkeypatch
):
    _seed_legacy(tmp_path, theme="dark")

    def _broken_qsettings(*_args, **_kwargs):
        raise RuntimeError("backend exploded")

    monkeypatch.setattr(migration, "QSettings", _broken_qsettings)

    report = migrate_settings_once()

    assert report["status"] == "skipped", report
    assert "migration failed" in report["reason"]


# ---------------------------------------------------------------------------
# Wiring: the copy runs before any read of the new namespace
# ---------------------------------------------------------------------------


def test_canonical_settings_triggers_the_migration(qsettings_home, tmp_path):
    _seed_legacy(tmp_path, theme="dark")

    settings = canonical_settings()

    assert settings.organizationName() == SETTINGS_ORG
    assert settings.applicationName() == SETTINGS_APP
    assert settings.value("theme") == "dark", (
        "reading through the canonical factory must see migrated values"
    )


def test_settings_manager_triggers_the_migration(qsettings_home, tmp_path):
    _seed_legacy(tmp_path, language="ru")

    manager = SettingsManager(SETTINGS_ORG, SETTINGS_APP)

    assert manager.settings.value("language") == "ru"


def test_legacy_literals_have_one_home():
    assert (LEGACY_SETTINGS_ORG, LEGACY_SETTINGS_APP) == (
        migration.LEGACY_SETTINGS_ORG,
        migration.LEGACY_SETTINGS_APP,
    )
    assert (SETTINGS_ORG, SETTINGS_APP) == ("BlinkTable", "BlinkTable")


# ---------------------------------------------------------------------------
# Structural: no second hardcoded pair in the migrated call sites
# ---------------------------------------------------------------------------

_MIGRATED_FILES = (
    "core/plugin_system/settings.py",
    "plugins/settings/manager.py",
    "services/io/recent_projects.py",
    "core/control/live_verbs.py",
    "plugins/diagnostics/collect.py",
    "ui/canvas_infra/rhi/rhi_backend.py",
    "ui/main_window/project/paths.py",
    "tabs/image_gallery/services/ai_models.py",
    "tabs/image_gallery/services/ai_settings_store.py",
    "tabs/use_cases/session_state.py",
)
# ``__main__.py`` is covered by the constructor check below instead: it keeps
# non-settings ids on the old name (RESOURCE_NAME, argv[0]) that this release
# must not rename.


def _string_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_no_hardcoded_identity_in_migrated_sites():
    for relative in _MIGRATED_FILES:
        literals = _string_constants(_SRC / relative)
        assert "improve-imgsli" not in literals, (
            f"{relative} spells the legacy identity out again; import it from "
            "core.settings_migration instead"
        )


def test_bootstrap_and_main_use_the_canonical_pair():
    """The two manager constructions must not pass the legacy pair by hand."""
    for relative in ("core/bootstrap.py", "__main__.py"):
        tree = ast.parse((_SRC / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name != "SettingsManager":
                continue
            args = [
                arg.value
                for arg in node.args
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            ]
            assert "improve-imgsli" not in args, (
                f"{relative}:{node.lineno} still constructs SettingsManager with "
                "the legacy pair"
            )
