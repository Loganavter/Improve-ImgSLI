"""Encrypted-at-rest storage for the few secrets the app persists.

Why this module exists: the AI provider key used to be written into the AI
settings group of ``QSettings`` — a plaintext INI under the user's Qt config
directory — so it was readable by anything
that could read the file (backups, synced folders, a screenshot of the config)
and the settings page had to warn about it. A warning is not a fix, so the key
moved here and the warning is gone.

Three backends, chosen at runtime in this order:

1. **OS keyring** (``secret-tool``, libsecret/Secret Service) — the desktop
   case: the secret is owned by the login keyring and never touches our files.
2. **Encrypted file** — ``cryptography`` present but no keyring: a Fernet key
   in ``<app data>/secrets/api_key.key`` (0600) encrypts the value, and the
   *effective* key is bound to this machine (``/etc/machine-id`` on POSIX, the
   ``Cryptography\\MachineGuid`` registry value on Windows). Copying the two
   files to another machine therefore fails closed: the value decrypts to
   nothing and the user is asked for the key again.
3. **Session only** — neither available (a headless box, a container): the key
   is kept in memory for this process and never written to disk. That is the
   honest choice: no plaintext, and the cost is re-entering the key per run.

``active_mode()`` reports which backend serves the running process, so callers
(and the log) can tell the difference instead of assuming encryption.
"""

from __future__ import annotations

from shared.hidden_process import hidden_process_kwargs

import base64
import hashlib
import logging
import os
import platform
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MODE_KEYRING = "keyring"
MODE_ENCRYPTED_FILE = "encrypted-file"
MODE_SESSION = "session"

#: ``secret-tool`` attributes identifying our secret in the login keyring.
#: The pre-rename attributes are still *read* (and cleared) so an upgrade finds
#: the key the user already granted; only writes move to the new identity.
_KEYRING_SCHEMA = (("application", "blinktable"), ("key", "ai-api-key"))
_LEGACY_KEYRING_SCHEMA = (("application", "improve-imgsli"), ("key", "ai-api-key"))
_KEYRING_LABEL = "BlinkTable — AI provider API key"

#: App-data directory names. The pre-rename one is a read-only fallback: an
#: upgrade must keep the stored key instead of asking for it again.
_APP_DIR_NAME = "BlinkTable"
_LEGACY_APP_DIR_NAME = "ImproveImgSLI"

_SECRET_NAME = "ai_api_key"
_BACKEND_TIMEOUT_S = 5.0

#: Machine-id files, POSIX only. Windows has neither, so it reads the registry.
_MACHINE_ID_FILES = ("/etc/machine-id", "/var/lib/dbus/machine-id")
#: Windows analogue of ``/etc/machine-id``: a per-install GUID.
_WINDOWS_MACHINE_GUID_SUBKEY = r"SOFTWARE\Microsoft\Cryptography"
_WINDOWS_MACHINE_GUID_VALUE = "MachineGuid"

#: Where ``_machine_id()`` got its value from — logged so a later reader can
#: tell which machine a stored key was bound to without seeing the id itself.
MACHINE_ID_SOURCE_REGISTRY = "registry"
MACHINE_ID_SOURCE_FILE = "machine-id-file"
MACHINE_ID_SOURCE_NODE = "node-only"
MACHINE_ID_SOURCE_POSIX_FALLBACK = "posix-fallback"

#: Per-process values for the session backend (and the decrypted cache).
_session: dict[str, str] = {}
_resolved_mode: str | None = None
_session_notice_emitted = False


def _app_data_dir(app_name: str) -> Path:
    """Per-OS app-data directory for *app_name* (no Qt import)."""
    if sys_platform().startswith("linux"):
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    elif sys_platform() == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:  # pragma: no cover - Windows
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / app_name


def sys_platform() -> str:  # pragma: no cover - trivial seam for tests
    return platform.system().lower()


def secrets_dir() -> Path:
    """Where the encrypted pair is written: the current app-data directory."""
    return _app_data_dir(_APP_DIR_NAME) / "secrets"


def legacy_secrets_dir() -> Path:
    """Pre-rename location of the same pair — read and cleared, never written."""
    return _app_data_dir(_LEGACY_APP_DIR_NAME) / "secrets"


def _windows_machine_guid() -> str:
    """``HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid``, or ``""``.

    Imported lazily: ``winreg`` only exists on Windows, and this module is
    imported on every platform. Any failure (module absent, key unreadable,
    policy-restricted registry) degrades to the caller's node-name fallback —
    a key that is bound slightly less uniquely is better than one that cannot
    be stored at all.
    """
    try:
        import winreg as _winreg
    except ImportError:
        return ""
    # Off Windows, typeshed stubs ``winreg`` as an empty module, so every
    # attribute access is a false positive (TESTING.md, "Static type checking"
    # → platform quirks). An ``Any`` alias keeps mypy honest without a
    # module-wide suppression that would also hide real attribute typos here.
    winreg: Any = _winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _WINDOWS_MACHINE_GUID_SUBKEY) as key:
            value, _kind = winreg.QueryValueEx(key, _WINDOWS_MACHINE_GUID_VALUE)
    except Exception:
        return ""
    return str(value or "").strip()


def _machine_id_with_source() -> tuple[bytes, str]:
    """The machine identity and the kind of source that produced it.

    Windows has no ``/etc/machine-id`` and no ``os.getuid``: the previous
    fallback raised ``AttributeError`` there, callers swallowed it and the
    encrypted-file backend quietly became memory-only (re-enter the AI key on
    every launch). The registry GUID + node name is the Windows equivalent of
    the POSIX chain; the POSIX branch is unchanged.
    """
    if sys_platform() == "windows":
        node = platform.node()
        guid = _windows_machine_guid()
        if guid:
            return f"{guid}:{node}".encode("utf-8"), MACHINE_ID_SOURCE_REGISTRY
        return node.encode("utf-8"), MACHINE_ID_SOURCE_NODE
    for candidate in _MACHINE_ID_FILES:
        try:
            value = Path(candidate).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value.encode("utf-8"), MACHINE_ID_SOURCE_FILE
    return f"{platform.node()}:{os.getuid()}".encode("utf-8"), MACHINE_ID_SOURCE_POSIX_FALLBACK


def _machine_id() -> bytes:
    """Bind the file backend to this machine.

    The debug line records the *source*, never the id: the id is a machine
    fingerprint and the log tail travels into the diagnostics report.
    """
    value, source = _machine_id_with_source()
    logger.debug("AI secret store: machine identity from %s", source)
    return value


def _mkdir_private(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, stat.S_IRWXU)
    except OSError:
        pass
    return path


def _write_private(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


def _secret_tool() -> str | None:
    return shutil.which("secret-tool")


#: Set by ``tests/helpers/secret_store_isolation.py`` when it installs the fake
#: ``secret-tool``; its absence under pytest means "not sandboxed".
SANDBOX_MARKER_ENV = "IMGLSI_TEST_SECRET_TOOL_SANDBOX"


def _pytest_without_sandbox() -> bool:
    """True inside a pytest run that did NOT install the secret-store sandbox.

    A test that reaches the host keyring can read, overwrite or clear a real
    user's provider key — measured 2026-10-25 (the shared ``blinktable`` entry
    was replaced by a stub) and again 2026-10-26 (an un-sandboxed gallery-tier
    run). Relying on every test tree importing an autouse fixture is not a
    guard: a single ``pytest src/tabs/<tab>/tests`` without the sandbox is
    enough. Without the marker the keyring backend reports unavailable, so the
    store degrades to the isolated session/encrypted-file path instead of
    touching the login keyring.
    """
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return not os.environ.get(SANDBOX_MARKER_ENV)


def keyring_available() -> bool:
    if _pytest_without_sandbox():
        return False
    return _secret_tool() is not None


def cryptography_available() -> bool:
    try:
        import cryptography.fernet  # noqa: F401
    except Exception:
        return False
    return True


def _keyring_store(value: str) -> bool:
    tool = _secret_tool()
    if tool is None:
        return False
    argv = [tool, "store", "--label", _KEYRING_LABEL]
    for key, attr in _KEYRING_SCHEMA:
        argv += [key, attr]
    try:
        done = subprocess.run(
            argv,
            input=value.encode("utf-8"),
            capture_output=True,
            timeout=_BACKEND_TIMEOUT_S,
            check=False,
            **hidden_process_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def _keyring_lookup(schema: tuple[tuple[str, str], ...]) -> str:
    tool = _secret_tool()
    if tool is None:
        return ""
    argv = [tool, "lookup"]
    for key, attr in schema:
        argv += [key, attr]
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            timeout=_BACKEND_TIMEOUT_S,
            check=False,
            **hidden_process_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if done.returncode != 0:
        return ""
    return done.stdout.decode("utf-8", errors="replace").strip()


def _keyring_load() -> str:
    """Read the current entry, else the pre-rename one (upgrade migration)."""
    value = _keyring_lookup(_KEYRING_SCHEMA)
    if value:
        return value
    return _keyring_lookup(_LEGACY_KEYRING_SCHEMA)


def _keyring_clear() -> None:
    tool = _secret_tool()
    if tool is None:
        return
    # Both identities: clearing only the current one would let a pre-rename
    # entry resurrect the secret on the next launch.
    for schema in (_KEYRING_SCHEMA, _LEGACY_KEYRING_SCHEMA):
        argv = [tool, "clear"]
        for key, attr in schema:
            argv += [key, attr]
        try:
            subprocess.run(
                argv,
                capture_output=True,
                timeout=_BACKEND_TIMEOUT_S,
                check=False,
                **hidden_process_kwargs(),
            )
        except (OSError, subprocess.SubprocessError):
            pass


def _fernet() -> Any:
    from cryptography.fernet import Fernet

    return Fernet


def _effective_key(base_key: bytes) -> bytes:
    """Bind the stored Fernet key to this machine."""
    digest = hashlib.sha256(base_key + b"|" + _machine_id()).digest()
    return base64.urlsafe_b64encode(digest)


def _file_key_path() -> Path:
    """Write location of the Fernet key (always the current directory)."""
    return secrets_dir() / f"{_SECRET_NAME}.key"


def _file_value_path() -> Path:
    """Write location of the encrypted value (always the current directory)."""
    return secrets_dir() / f"{_SECRET_NAME}.enc"


def _stored_pair() -> tuple[Path, Path] | None:
    """The ``(key, value)`` files to READ: current directory, else pre-rename.

    The app-data directory moved with the rename, and orphaning a key the user
    already stored would mean asking for it again. So when the current
    directory holds no encrypted value the pre-rename one is read instead.
    Writes always target the current directory, which re-encrypts an old pair
    there on the next save.
    """
    for directory in (secrets_dir(), legacy_secrets_dir()):
        value_path = directory / f"{_SECRET_NAME}.enc"
        if value_path.is_file():
            return directory / f"{_SECRET_NAME}.key", value_path
    return None


def _read_base_key() -> bytes | None:
    try:
        return _file_key_path().read_bytes().strip()
    except OSError:
        return None


def _create_base_key() -> bytes | None:
    try:
        Fernet = _fernet()
    except Exception:
        return None
    key = Fernet.generate_key()
    _mkdir_private(secrets_dir())
    _write_private(_file_key_path(), key)
    return key


def _file_store(value: str) -> bool:
    try:
        Fernet = _fernet()
    except Exception:
        return False
    base = _read_base_key() or _create_base_key()
    if not base:
        return False
    try:
        token = Fernet(_effective_key(base)).encrypt(value.encode("utf-8"))
    except Exception:
        return False
    _mkdir_private(secrets_dir())
    _write_private(_file_value_path(), token)
    return True


def _file_load() -> str:
    try:
        Fernet = _fernet()
    except Exception:
        return ""
    pair = _stored_pair()
    if pair is None:
        return ""
    key_path, value_path = pair
    try:
        base = key_path.read_bytes().strip()
    except OSError:
        return ""
    if not base:
        return ""
    try:
        token = value_path.read_bytes()
    except OSError:
        return ""
    try:
        return Fernet(_effective_key(base)).decrypt(token).decode("utf-8")
    except Exception:
        # Wrong machine, tampered file, rotated key: fail closed to "no key".
        logger.warning(
            "AI API key could not be decrypted on this machine; treating it as unset"
        )
        return ""


def _file_clear() -> None:
    """Remove the encrypted value everywhere; a cleared key must not return."""
    for directory in (secrets_dir(), legacy_secrets_dir()):
        for path in (
            directory / f"{_SECRET_NAME}.enc",
            directory / f"{_SECRET_NAME}.key",
        ):
            try:
                path.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def active_mode() -> str:
    """Which backend this process uses (resolved once)."""
    global _resolved_mode
    if _resolved_mode is None:
        if keyring_available():
            _resolved_mode = MODE_KEYRING
        elif cryptography_available():
            _resolved_mode = MODE_ENCRYPTED_FILE
        else:
            _resolved_mode = MODE_SESSION
    return _resolved_mode


def reset_backend_probe() -> None:
    """Forget the cached backend choice (tests, and after an env change)."""
    global _resolved_mode
    _resolved_mode = None


def store(secret: str) -> str:
    """Persist *secret* with the best available backend; returns the mode used.

    ``""`` clears the stored value. Never writes plaintext to disk.
    """
    global _session_notice_emitted
    secret = str(secret or "")
    if not secret:
        clear()
        return active_mode()

    mode = active_mode()
    if mode == MODE_KEYRING:
        if _keyring_store(secret):
            _session[_SECRET_NAME] = secret
            return mode
        # A keyring that refuses (locked, no session bus): fall through rather
        # than write plaintext.
        mode = MODE_ENCRYPTED_FILE if cryptography_available() else MODE_SESSION
    if mode == MODE_ENCRYPTED_FILE and _file_store(secret):
        _session[_SECRET_NAME] = secret
        return MODE_ENCRYPTED_FILE

    _session[_SECRET_NAME] = secret
    if not _session_notice_emitted:
        _session_notice_emitted = True
        logger.info(
            "AI API key will not be persisted: no OS keyring and no 'cryptography' "
            "module here, so it is kept in memory for this run only"
        )
    return MODE_SESSION


def load() -> str:
    """The stored secret, or ``""`` when none is available."""
    if _SECRET_NAME in _session:
        return _session[_SECRET_NAME]
    mode = active_mode()
    if mode == MODE_KEYRING:
        value = _keyring_load()
        if value:
            _session[_SECRET_NAME] = value
            return value
        if cryptography_available():
            value = _file_load()
            if value:
                _session[_SECRET_NAME] = value
                return value
        return ""
    if mode == MODE_ENCRYPTED_FILE:
        value = _file_load()
        if value:
            _session[_SECRET_NAME] = value
        return value
    return ""


def clear() -> None:
    _session.pop(_SECRET_NAME, None)
    _keyring_clear()
    _file_clear()


def forget_session_cache() -> None:
    """Drop the in-memory copy (tests, and after a settings reset)."""
    _session.pop(_SECRET_NAME, None)
