"""The machine identity behind the encrypted-file secret backend works on Windows.

``core.secret_store`` binds the Fernet key to this machine so the two files
cannot be copied elsewhere and decrypted (see the module docstring of
``src/core/secret_store.py``). That binding used ``os.getuid()`` in its last
resort, and Windows has no ``os.getuid``: both machine-id files are absent
there too, so the call raised ``AttributeError``, every caller swallowed it and
the backend silently degraded to "re-enter the key on every launch".

The platform is selected through the module's existing ``sys_platform()`` seam
so the Windows branch is exercisable on Linux; the POSIX chain is unchanged and
still reads a machine-id file first.
"""

from __future__ import annotations

import logging
import os
import platform
import sys
import types

import pytest

from core import secret_store

KEY = "sk-live-0123456789abcdef"
GUID = "3f8a1c9e-7b2d-4e6a-9c11-5d0b8a2f4c77"


def _no_getuid() -> int:
    """What ``os.getuid`` looks like on Windows: the attribute is not there."""
    raise AttributeError("module 'os' has no attribute 'getuid'")


class _MissingFile:
    """Stand-in for ``Path`` that makes every machine-id candidate absent."""

    def __init__(self, path: object) -> None:
        self._path = path

    def read_text(self, encoding: str = "utf-8") -> str:
        raise FileNotFoundError(str(self._path))


def _fake_winreg(guid: str, *, failure: BaseException | None = None) -> types.SimpleNamespace:
    """A minimal ``winreg`` whose Cryptography key yields *guid* (or raises)."""
    opened: list[str] = []

    class _Key:
        def __enter__(self) -> _Key:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

    def open_key(root: object, subkey: str) -> _Key:
        if failure is not None:
            raise failure
        opened.append(subkey)
        return _Key()

    def query_value_ex(key: _Key, name: str) -> tuple[str, int]:
        return guid, 1

    module = types.SimpleNamespace(
        HKEY_LOCAL_MACHINE=object(),
        OpenKey=open_key,
        QueryValueEx=query_value_ex,
        opened=opened,
    )
    return module


def _windows(monkeypatch: pytest.MonkeyPatch, registry: types.SimpleNamespace) -> None:
    monkeypatch.setattr(secret_store, "sys_platform", lambda: "windows")
    monkeypatch.setattr(os, "getuid", _no_getuid, raising=False)
    monkeypatch.setitem(sys.modules, "winreg", registry)


def test_windows_without_getuid_returns_a_stable_id(monkeypatch) -> None:
    """No ``os.getuid`` and no machine-id files: the id must not raise."""
    _windows(monkeypatch, _fake_winreg(GUID))
    monkeypatch.setattr(secret_store, "Path", _MissingFile)

    first = secret_store._machine_id()
    second = secret_store._machine_id()

    assert first == second
    assert GUID.encode("utf-8") in first


def test_windows_registry_machine_guid_is_combined_with_the_node_name(monkeypatch) -> None:
    registry = _fake_winreg(GUID)
    _windows(monkeypatch, registry)

    assert secret_store._machine_id() == f"{GUID}:{platform.node()}".encode("utf-8")
    assert registry.opened and "Cryptography" in registry.opened[0]


@pytest.mark.parametrize(
    "registry",
    [None, "registry-error"],
    ids=["winreg-module-absent", "registry-read-error"],
)
def test_windows_without_a_readable_registry_uses_the_node_name(monkeypatch, registry) -> None:
    if registry is None:
        monkeypatch.setattr(secret_store, "sys_platform", lambda: "windows")
        monkeypatch.setattr(os, "getuid", _no_getuid, raising=False)
        monkeypatch.setitem(sys.modules, "winreg", None)  # import fails, as on Linux
    else:
        _windows(monkeypatch, _fake_winreg(GUID, failure=OSError("access denied")))

    assert secret_store._machine_id() == platform.node().encode("utf-8")


def test_posix_still_reads_the_machine_id_file(tmp_path, monkeypatch) -> None:
    """The POSIX chain is unchanged: a machine-id file wins over node+uid."""
    present = tmp_path / "machine-id"
    present.write_text("0123456789abcdef0123456789abcdef\n", encoding="utf-8")
    monkeypatch.setattr(secret_store, "sys_platform", lambda: "linux")
    monkeypatch.setattr(
        secret_store,
        "_MACHINE_ID_FILES",
        (str(tmp_path / "absent"), str(present)),
    )

    assert secret_store._machine_id() == b"0123456789abcdef0123456789abcdef"


def test_posix_fallback_is_still_node_and_uid(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(secret_store, "sys_platform", lambda: "linux")
    monkeypatch.setattr(
        secret_store,
        "_MACHINE_ID_FILES",
        (str(tmp_path / "absent-1"), str(tmp_path / "absent-2")),
    )
    monkeypatch.setattr(os, "getuid", lambda: 4242)

    assert secret_store._machine_id() == f"{platform.node()}:4242".encode("utf-8")


def test_debug_log_names_the_source_but_not_the_id(monkeypatch, caplog) -> None:
    """The log says where the id came from; the fingerprint itself stays out."""
    _windows(monkeypatch, _fake_winreg(GUID))
    with caplog.at_level(logging.DEBUG, logger="core.secret_store"):
        machine_id = secret_store._machine_id()

    text = "\n".join(record.getMessage() for record in caplog.records)
    assert secret_store.MACHINE_ID_SOURCE_REGISTRY in text
    assert GUID not in text
    assert machine_id.decode("utf-8") not in text
    assert all(record.levelno <= logging.DEBUG for record in caplog.records)


def test_encrypted_file_backend_persists_across_processes_on_windows(
    tmp_path, monkeypatch
) -> None:
    """The payoff: the key is read back from disk with no ``os.getuid`` around."""
    pytest.importorskip("cryptography.fernet")
    _windows(monkeypatch, _fake_winreg(GUID))
    # Neither machine-id file exists on Windows.
    monkeypatch.setattr(
        secret_store,
        "_MACHINE_ID_FILES",
        (str(tmp_path / "absent-1"), str(tmp_path / "absent-2")),
    )
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(secret_store, "keyring_available", lambda: False)
    monkeypatch.setattr(secret_store, "cryptography_available", lambda: True)
    secret_store.reset_backend_probe()
    secret_store.forget_session_cache()
    try:
        assert secret_store.store(KEY) == secret_store.MODE_ENCRYPTED_FILE
        secret_store.forget_session_cache()  # as if this were a fresh launch
        assert secret_store.load() == KEY
    finally:
        secret_store.forget_session_cache()
        secret_store.reset_backend_probe()
