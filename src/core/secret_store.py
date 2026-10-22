"""Encrypted-at-rest storage for the few secrets the app persists.

Why this module exists: the AI provider key used to be written into the AI
settings group of ``QSettings`` — a plaintext INI under
``~/.config/ImproveImgSLI/ImproveImgSLI.conf`` — so it was readable by anything
that could read the file (backups, synced folders, a screenshot of the config)
and the settings page had to warn about it. A warning is not a fix, so the key
moved here and the warning is gone.

Three backends, chosen at runtime in this order:

1. **OS keyring** (``secret-tool``, libsecret/Secret Service) — the desktop
   case: the secret is owned by the login keyring and never touches our files.
2. **Encrypted file** — ``cryptography`` present but no keyring: a Fernet key
   in ``<app data>/secrets/api_key.key`` (0600) encrypts the value, and the
   *effective* key is bound to this machine (``/etc/machine-id``). Copying the
   two files to another machine therefore fails closed: the value decrypts to
   nothing and the user is asked for the key again.
3. **Session only** — neither available (a headless box, a container): the key
   is kept in memory for this process and never written to disk. That is the
   honest choice: no plaintext, and the cost is re-entering the key per run.

``active_mode()`` reports which backend serves the running process, so callers
(and the log) can tell the difference instead of assuming encryption.
"""

from __future__ import annotations

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
_KEYRING_SCHEMA = (("application", "improve-imgsli"), ("key", "ai-api-key"))
_KEYRING_LABEL = "Improve-ImgSLI — AI provider API key"

_SECRET_NAME = "ai_api_key"
_BACKEND_TIMEOUT_S = 5.0

#: Per-process values for the session backend (and the decrypted cache).
_session: dict[str, str] = {}
_resolved_mode: str | None = None
_session_notice_emitted = False


def _app_data_dir() -> Path:
    """Mirror ``core.control.discovery.app_data_dir`` without importing Qt."""
    if sys_platform().startswith("linux"):
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    elif sys_platform() == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:  # pragma: no cover - Windows
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "ImproveImgSLI"


def sys_platform() -> str:  # pragma: no cover - trivial seam for tests
    return platform.system().lower()


def secrets_dir() -> Path:
    return _app_data_dir() / "secrets"


def _machine_id() -> bytes:
    for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            value = Path(candidate).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value.encode("utf-8")
    return f"{platform.node()}:{os.getuid()}".encode("utf-8")


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


def keyring_available() -> bool:
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
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def _keyring_load() -> str:
    tool = _secret_tool()
    if tool is None:
        return ""
    argv = [tool, "lookup"]
    for key, attr in _KEYRING_SCHEMA:
        argv += [key, attr]
    try:
        done = subprocess.run(
            argv, capture_output=True, timeout=_BACKEND_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if done.returncode != 0:
        return ""
    return done.stdout.decode("utf-8", errors="replace").strip()


def _keyring_clear() -> None:
    tool = _secret_tool()
    if tool is None:
        return
    argv = [tool, "clear"]
    for key, attr in _KEYRING_SCHEMA:
        argv += [key, attr]
    try:
        subprocess.run(argv, capture_output=True, timeout=_BACKEND_TIMEOUT_S, check=False)
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
    return secrets_dir() / f"{_SECRET_NAME}.key"


def _file_value_path() -> Path:
    return secrets_dir() / f"{_SECRET_NAME}.enc"


def _load_base_key(create: bool) -> bytes | None:
    path = _file_key_path()
    try:
        return path.read_bytes().strip()
    except OSError:
        if not create:
            return None
    Fernet = _fernet()
    key = Fernet.generate_key()
    _mkdir_private(secrets_dir())
    _write_private(path, key)
    return key


def _file_store(value: str) -> bool:
    try:
        Fernet = _fernet()
    except Exception:
        return False
    base = _load_base_key(create=True)
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
    base = _load_base_key(create=False)
    if not base:
        return ""
    try:
        token = _file_value_path().read_bytes()
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
    for path in (_file_value_path(),):
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
