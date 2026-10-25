"""The frozen-build PySide feature-check guard in ``core.bootstrap``.

PySide6's feature hook runs after every import once PySide is loaded and asks
"does this module use Qt for Python?" by scanning the module's source with
``inspect.getsource``. In a PyInstaller bundle that read goes through the PYZ
archive, so it costs archive I/O per newly imported module (measured: a 105 ms
GUI block inside a ``numpy._typing`` import). ``core.bootstrap`` neutralises the
scan in frozen builds only.

These tests drive the guard with synthetic feature modules, so they never
depend on PySide's own feature hook being installed (the 6.11 Linux wheel does
not ship its sources; the owner's frozen bundle does). The guard file itself is
executed as a throwaway module, so the app's real ``core.bootstrap`` (and the
real feature hook PySide may have installed) is never mutated.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import re
import sys
import types
from pathlib import Path

import pytest

from core.log_names import APP_LOGGER_NAME

_FEATURE_MODULE_ALIASES = (
    "shibokensupport.feature",
    "PySide6.support.feature",
    "__feature__",
)

#: Names the fixture takes over wholesale (the package and its aliases).
_TAKEN_OVER = ("shibokensupport",) + _FEATURE_MODULE_ALIASES

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
_BOOTSTRAP_PATH = _SRC_ROOT / "core" / "bootstrap.py"

#: Any ``import __feature__`` / ``from __feature__ import ...`` in app code.
_FEATURE_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+__feature__\b", re.MULTILINE)

#: Source the stubbed lookup returns, so the ORIGINAL check reads as "this
#: module uses PySide6" (i.e. it would run the real source scan).
_SYNTHETIC_SOURCE = "import PySide6\n\nfrom PySide6.QtCore import QObject\n"


@pytest.fixture
def feature_modules():
    """Synthetic ``shibokensupport`` + ``shibokensupport.feature`` in sys.modules.

    ``feature_imported`` mirrors PySide's shape: it looks the helper up on the
    feature module at CALL time, so replacing the module attribute is observable
    exactly as it is with the real module.
    """
    calls = {"mod_uses_pyside": 0, "getsource": 0}

    feature = types.ModuleType("shibokensupport.feature")

    def _mod_uses_pyside(module: object) -> bool:
        calls["mod_uses_pyside"] += 1
        return "PySide6" in inspect.getsource(module)  # type: ignore[arg-type]

    def feature_imported(module: object) -> bool:
        return feature._mod_uses_pyside(module)  # type: ignore[attr-defined]

    original = _mod_uses_pyside
    feature._mod_uses_pyside = original  # type: ignore[attr-defined]
    feature.feature_imported = feature_imported  # type: ignore[attr-defined]
    feature.unrelated_marker = "kept"  # type: ignore[attr-defined]

    package = types.ModuleType("shibokensupport")
    package.feature = feature  # type: ignore[attr-defined]

    real_getsource = inspect.getsource
    saved_modules = {name: sys.modules.get(name) for name in _TAKEN_OVER}
    # Real aliases (on hosts whose wheel DOES ship the hook) must go, otherwise
    # the guard patches them too and the counter proves nothing.
    for name in _TAKEN_OVER:
        sys.modules.pop(name, None)
    sys.modules["shibokensupport"] = package
    sys.modules["shibokensupport.feature"] = feature

    def _counting_getsource(obj: object, *args: object, **kwargs: object) -> str:
        calls["getsource"] += 1
        return _SYNTHETIC_SOURCE

    inspect.getsource = _counting_getsource  # type: ignore[assignment]
    try:
        yield types.SimpleNamespace(module=feature, calls=calls, original=original)
    finally:
        inspect.getsource = real_getsource  # type: ignore[assignment]
        for name in _TAKEN_OVER:
            sys.modules.pop(name, None)
        for name, module in saved_modules.items():
            if module is not None:
                sys.modules[name] = module


def _exec_bootstrap():
    """Execute bootstrap.py as a throwaway module (the guard is module-body)."""
    spec = importlib.util.spec_from_file_location(
        "_pyside_feature_guard_probe", _BOOTSTRAP_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _clear_feature_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IMGSLI_PYSIDE_FEATURE_CHECK", raising=False)
    monkeypatch.delenv("BLINKTABLE_PYSIDE_FEATURE_CHECK", raising=False)


def _delta(calls: dict[str, int], before: dict[str, int]) -> dict[str, int]:
    """Calls made by ONE feature check.

    Measured as a delta because the host's real feature hook (when it exists)
    also scans the sources of the app's own imports during the guard's import.
    """
    return {key: calls[key] - before[key] for key in calls}


def test_frozen_guard_removes_the_source_scan(feature_modules, monkeypatch):
    """Frozen build: no getsource during a feature check; install is idempotent."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    _clear_feature_env(monkeypatch)

    bootstrap = _exec_bootstrap()

    assert "shibokensupport.feature" in bootstrap._pyside_feature_guard_targets
    assert feature_modules.module._mod_uses_pyside is not feature_modules.original
    # Only the scan helper is replaced; sibling attributes stay untouched.
    assert feature_modules.module.unrelated_marker == "kept"
    assert callable(feature_modules.module.feature_imported)

    target = types.ModuleType("synthetic_pyside_user")
    before = dict(feature_modules.calls)
    assert feature_modules.module.feature_imported(target) is False
    assert _delta(feature_modules.calls, before) == {"mod_uses_pyside": 0, "getsource": 0}

    # Second install: same patched object, nothing re-patched, behaviour equal.
    patched = feature_modules.module._mod_uses_pyside
    assert bootstrap._install_pyside_feature_guard() == ()
    assert feature_modules.module._mod_uses_pyside is patched
    before = dict(feature_modules.calls)
    assert feature_modules.module.feature_imported(target) is False
    assert _delta(feature_modules.calls, before) == {"mod_uses_pyside": 0, "getsource": 0}


def test_frozen_guard_reports_lazily(feature_modules, monkeypatch):
    """The one DEBUG line names the patched modules and is emitted on demand."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    _clear_feature_env(monkeypatch)
    bootstrap = _exec_bootstrap()

    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    previous_level = app_logger.level
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.DEBUG)
    try:
        bootstrap._pyside_feature_guard_reported = False
        bootstrap._report_pyside_feature_guard()
        # Idempotent: a second call stays silent, so startup logs it once.
        bootstrap._report_pyside_feature_guard()
    finally:
        app_logger.removeHandler(handler)
        app_logger.setLevel(previous_level)

    assert len(records) == 1
    assert "shibokensupport.feature" in records[0].getMessage()


@pytest.mark.parametrize(
    "env_var",
    [None, "IMGSLI_PYSIDE_FEATURE_CHECK", "BLINKTABLE_PYSIDE_FEATURE_CHECK"],
)
def test_stock_behaviour_in_dev_and_behind_the_escape_hatch(
    feature_modules, monkeypatch, env_var
):
    """Dev run, or the A/B escape hatch: the original check stays in place."""
    if env_var is None:
        monkeypatch.delattr(sys, "frozen", raising=False)
    else:
        monkeypatch.setattr(sys, "frozen", True, raising=False)
    _clear_feature_env(monkeypatch)
    if env_var is not None:
        monkeypatch.setenv(env_var, "1")

    bootstrap = _exec_bootstrap()

    assert bootstrap._pyside_feature_guard_targets == ()
    assert feature_modules.module._mod_uses_pyside is feature_modules.original

    target = types.ModuleType("synthetic_pyside_user")
    before = dict(feature_modules.calls)
    assert feature_modules.module.feature_imported(target) is True
    assert _delta(feature_modules.calls, before) == {"mod_uses_pyside": 1, "getsource": 1}


def test_every_present_alias_is_named_and_patched_once(feature_modules, monkeypatch):
    """One module object under several names: all names patched, named, once."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    _clear_feature_env(monkeypatch)
    for alias in ("PySide6.support.feature", "__feature__"):
        monkeypatch.setitem(sys.modules, alias, feature_modules.module)

    bootstrap = _exec_bootstrap()

    assert set(bootstrap._pyside_feature_guard_targets) == set(_FEATURE_MODULE_ALIASES)
    patched = feature_modules.module._mod_uses_pyside
    assert patched is not feature_modules.original
    assert bootstrap._install_pyside_feature_guard() == ()
    assert feature_modules.module._mod_uses_pyside is patched


def test_absent_feature_module_is_a_silent_no_op(monkeypatch):
    """No shibokensupport at all: import works and sys.modules is untouched."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    _clear_feature_env(monkeypatch)

    importlib.import_module("core.bootstrap")
    removed = {name: sys.modules.pop(name, None) for name in _FEATURE_MODULE_ALIASES}
    try:
        before = set(sys.modules)
        bootstrap = _exec_bootstrap()
        assert bootstrap._pyside_feature_guard_targets == ()
        assert set(sys.modules) == before
    finally:
        for name, module in removed.items():
            if module is not None:
                sys.modules[name] = module


def test_no_app_module_imports_the_feature_pseudo_module():
    """Machine-checked justification: the lost per-module default is unreachable.

    The guard drops only the value the pseudo-module would use as a per-module
    default; that value is never read unless app code imports the pseudo-module.
    """
    offenders = sorted(
        path.relative_to(_SRC_ROOT).as_posix()
        for path in _SRC_ROOT.rglob("*.py")
        if _FEATURE_IMPORT_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    )
    assert offenders == []

    # One implementation only: bootstrap.py is the sole file naming it.
    mentioned = sorted(
        path.relative_to(_SRC_ROOT).as_posix()
        for path in _SRC_ROOT.rglob("*.py")
        if "__feature__" in path.read_text(encoding="utf-8", errors="replace")
    )
    assert mentioned == ["core/bootstrap.py"]
