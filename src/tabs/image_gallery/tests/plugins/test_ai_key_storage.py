"""The gallery AI provider key: never plaintext on disk.

``AiSettingsStore`` routes the key through ``core.secret_store`` (OS keyring →
encrypted machine-bound file → memory for the session) and drops a plaintext
row left by an older build on first load. Gallery-owned: the store, the
gallery's locale catalog and the fallback chain all live under this tab, so
the cases live here (root ``tests/`` must not deep-import tab internals).

The host-side half (the settings page no longer warns about "unencrypted"
storage) stays a root test: `tests/plugins/test_settings_ai_key_warning_removed.py`.
"""

from __future__ import annotations

import json
import os
import stat
import textwrap
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from core import secret_store
from tabs.image_gallery.services import ai_settings_store as store_module
from tabs.image_gallery.services.ai_settings_store import AiSettingsStore

# From `src/tabs/image_gallery/tests/plugins/` -> the tab package.
I18N_DIR = Path(__file__).parents[2] / "resources" / "i18n"
LOCALES = ("en", "ru", "zh", "pt_BR")
KEY = "sk-live-0123456789abcdef"


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Session-mode secret store in a throwaway data dir + a throwaway QSettings group."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(secret_store, "keyring_available", lambda: False)
    monkeypatch.setattr(secret_store, "cryptography_available", lambda: False)
    secret_store.reset_backend_probe()
    secret_store.forget_session_cache()
    group = "image_gallery_ai_test_secret"
    monkeypatch.setattr(store_module, "_QS_GROUP", group)
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove(group)
    yield group
    secret_store.forget_session_cache()
    secret_store.reset_backend_probe()
    settings.remove(group)


def _ini_text() -> str:
    """Every QSettings file this process could have written, concatenated."""
    text = []
    for base in {os.environ.get("XDG_CONFIG_HOME"), str(Path.home() / ".config")}:
        if not base:
            continue
        root = Path(base)
        if root.is_dir():
            for path in root.rglob("*.conf"):
                try:
                    text.append(path.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass
    return "\n".join(text)



def test_no_locale_carries_the_removed_warning_key():
    for locale in LOCALES:
        data = json.loads(
            (I18N_DIR / locale / "image_gallery.json").read_text(encoding="utf-8")
        )
        assert "api_key_warning" not in data["image_gallery"]["settings"], locale


# ---------------------------------------------------------------------------
# 2. the key never lands in the INI
# ---------------------------------------------------------------------------


def test_saving_the_key_writes_nothing_plaintext_to_the_ini(sandbox):
    store = AiSettingsStore()
    store.save_field("api_key", KEY)
    store.save_field("model", "some/model")

    assert store.load().api_key == KEY
    ini = _ini_text()
    assert KEY not in ini, "the provider key must never be written to QSettings"
    assert "some/model" in ini, "other settings still live in QSettings"


def test_a_plaintext_key_from_an_older_build_is_migrated_out(sandbox):
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.beginGroup(sandbox)
    settings.setValue("api_key", KEY)
    settings.setValue("model", "legacy/model")
    settings.endGroup()
    settings.sync()
    assert KEY in _ini_text(), "precondition: the legacy row is in the INI"

    loaded = AiSettingsStore().load()

    assert loaded.api_key == KEY, "the user must not lose the key on upgrade"
    assert KEY not in _ini_text(), "the plaintext row must be dropped after migration"
    assert AiSettingsStore().load().api_key == KEY, "and the migrated value keeps loading"


def test_clearing_the_key_removes_it_everywhere(sandbox):
    store = AiSettingsStore()
    store.save_field("api_key", KEY)
    store.save_field("api_key", "")

    assert store.load().api_key == ""
    assert KEY not in _ini_text()


# ---------------------------------------------------------------------------
# 3. the backend chain
# ---------------------------------------------------------------------------


def test_session_backend_is_memory_only(sandbox):
    assert secret_store.active_mode() == secret_store.MODE_SESSION
    assert secret_store.store(KEY) == secret_store.MODE_SESSION
    assert secret_store.load() == KEY

    secret_store.forget_session_cache()
    assert secret_store.load() == "", "a fresh process must not find the key on disk"


def test_the_keyring_is_used_when_the_tool_answers(sandbox, monkeypatch, tmp_path):
    fake = tmp_path / "secret-tool"
    store_file = tmp_path / "keyring.txt"
    fake.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import pathlib, sys
            store = pathlib.Path({str(store_file)!r})
            cmd = sys.argv[1]
            if cmd == "store":
                store.write_text(sys.stdin.read())
            elif cmd == "lookup":
                sys.stdout.write(store.read_text() if store.exists() else "")
                sys.exit(0 if store.exists() else 1)
            elif cmd == "clear":
                store.unlink(missing_ok=True)
            """
        ),
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ.get('PATH','')}")
    monkeypatch.setattr(secret_store, "keyring_available", lambda: True)
    secret_store.reset_backend_probe()

    assert secret_store.active_mode() == secret_store.MODE_KEYRING
    assert secret_store.store(KEY) == secret_store.MODE_KEYRING
    assert KEY in store_file.read_text(encoding="utf-8")

    secret_store.forget_session_cache()
    assert secret_store.load() == KEY, "a fresh process reads it back from the keyring"
    assert KEY not in _ini_text()


@pytest.mark.skipif(
    not secret_store.cryptography_available(), reason="cryptography is not installed here"
)
def test_encrypted_file_backend_is_machine_bound(sandbox, monkeypatch, tmp_path):
    monkeypatch.setattr(secret_store, "keyring_available", lambda: False)
    monkeypatch.setattr(secret_store, "cryptography_available", lambda: True)
    secret_store.reset_backend_probe()

    assert secret_store.store(KEY) == secret_store.MODE_ENCRYPTED_FILE
    enc = secret_store.secrets_dir() / "ai_api_key.enc"
    assert enc.is_file() and KEY.encode() not in enc.read_bytes()

    secret_store.forget_session_cache()
    assert secret_store.load() == KEY

    # A different machine id must fail closed, not hand back garbage.
    monkeypatch.setattr(secret_store, "_machine_id", lambda: b"another-machine")
    secret_store.forget_session_cache()
    assert secret_store.load() == ""
