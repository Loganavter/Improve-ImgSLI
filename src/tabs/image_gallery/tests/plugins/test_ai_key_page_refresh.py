"""The AI page's key row shows the key the secret store can see *now*.

``core.secret_store`` resolves its backend once per process
(``active_mode`` caches ``_resolved_mode``, ``_session`` caches the value) and
nothing in the app ever re-probed it, while the settings page is built once per
dialog (``build`` reads ``store.load()`` once). Together they made a key that
the keyring only started answering for *after* app boot invisible for the rest
of the run — an empty field, and HTTP 401 "Missing Authentication header" on
every AI call — until the app was restarted. Entering the page re-probes and
re-reads.

RED BEFORE: ``_on_settings_section_shown`` refreshed only the model catalog, so
``test_page_entry_fills_a_stale_empty_key`` read an empty field, and no
production code called ``secret_store.reset_backend_probe()`` at all.

The read-back is one-way on purpose: ``AiSettingsStore.save_field("api_key",
"")`` routes to ``secret_store.store("")`` → ``clear()``, which wipes BOTH
keyring identities and the encrypted file. A programmatic fill that happened to
read empty would therefore destroy the user's stored key — that is what the
``no clear`` / ``no store`` assertions below pin.

Offscreen, and hermetic: the keyring is a fake ``secret-tool`` on ``PATH`` that
records every call, ``XDG_DATA_HOME`` is a throwaway dir, both QSettings groups
are redirected, the discovery seam is injected (no network) and the worker seam
runs inline (no thread).
"""

from __future__ import annotations

import os
import stat
import textwrap
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from core import secret_store
from tabs.image_gallery.services import ai_models
from tabs.image_gallery.services import ai_settings_store as store_module

#: A key length in the range the live report named (73 chars), so a truncated
#: read would not pass by accident.
KEY = "sk-live-0123456789abcdef" * 3

_STORE_GROUP = "image_gallery_ai_test_key_page"
_MODELS_GROUP = "image_gallery_ai_models_test_key_page"


class FakeKeyring:
    """The fake ``secret-tool``'s state: the value, and the calls made."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def seed(self, value: str) -> None:
        """Store *value* the way a previous app run would have."""
        (self._root / "keyring.txt").write_text(value, encoding="utf-8")

    def value(self) -> str:
        path = self._root / "keyring.txt"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def calls(self) -> list[str]:
        path = self._root / "calls.txt"
        return path.read_text(encoding="utf-8").split() if path.exists() else []

    def reset_calls(self) -> None:
        (self._root / "calls.txt").unlink(missing_ok=True)


@pytest.fixture
def page_store(monkeypatch):
    """Throwaway AI-settings + model-catalog groups; the real config is untouched."""
    monkeypatch.setattr(store_module, "_QS_GROUP", _STORE_GROUP)
    monkeypatch.setattr(ai_models, "_QS_GROUP", _MODELS_GROUP)
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    for group in (_STORE_GROUP, _MODELS_GROUP):
        settings.remove(group)
    yield
    for group in (_STORE_GROUP, _MODELS_GROUP):
        settings.remove(group)
    # Module-level process state: never leave a resolved backend behind.
    secret_store.forget_session_cache()
    secret_store.reset_backend_probe()


@pytest.fixture
def fake_keyring(tmp_path, monkeypatch):
    """A recording ``secret-tool`` on ``PATH`` plus a throwaway secret data dir."""
    root = tmp_path / "keyring"
    root.mkdir()
    tool = root / "secret-tool"
    tool.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import pathlib, sys
            root = pathlib.Path({str(root)!r})
            store = root / "keyring.txt"
            calls = root / "calls.txt"
            cmd = sys.argv[1]
            with calls.open("a", encoding="utf-8") as handle:
                handle.write(cmd + "\\n")
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
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{root}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    keyring = FakeKeyring(root)
    secret_store.reset_backend_probe()
    secret_store.forget_session_cache()
    return keyring


@pytest.fixture
def build_page(qapp, page_store, fake_keyring, monkeypatch):
    """Build a real ``SettingsDialog`` carrying only the gallery-AI page."""
    created = []

    def _build():
        widget = _build_dialog(monkeypatch)
        created.append(widget)
        return widget

    yield _build
    for widget in created:
        widget.close()
        widget.deleteLater()


def _build_dialog(monkeypatch):
    from plugins.settings.dialog import SettingsDialog
    from plugins.settings.registry import (
        ensure_tab_settings_contributions,
        get_settings_registry,
    )
    from tabs.image_gallery.ui import settings_ai
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()
    registry.contribute_all_settings()
    ensure_tab_settings_contributions()
    assert "image_gallery.ai" in {
        section.section_id for section in get_settings_registry().all_sections()
    }

    def _fake_models_for(provider, api_key, *, refresh=False, report=None):
        if report is not None:
            report["reason"] = ai_models.REASON_OK
        return ("fake/model-one",), ai_models.SOURCE_NETWORK

    monkeypatch.setattr(settings_ai, "MODELS_FOR", _fake_models_for)
    monkeypatch.setattr(
        settings_ai, "START_TASK", lambda task, on_done: on_done(task())
    )
    # No live gallery tab: the Apply-time re-analysis offer stays out of the way.
    monkeypatch.setattr(settings_ai, "GALLERY_OWNER", lambda: None)

    return SettingsDialog(
        current_language="en",
        current_theme="dark",
        current_max_length=30,
        min_limit=1,
        max_limit=9999,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        active_tab="image_gallery",
    )


# ---------------------------------------------------------------------------
# The refresh: a key the keyring only started answering for after boot
# ---------------------------------------------------------------------------


def test_page_entry_fills_a_stale_empty_key(build_page, fake_keyring, monkeypatch):
    fake_keyring.seed(KEY)
    # Boot state: the keyring was not reachable, so the process resolved to the
    # encrypted-file backend and never asked the keyring again.
    monkeypatch.setattr(secret_store, "keyring_available", lambda: False)
    monkeypatch.setattr(secret_store, "cryptography_available", lambda: True)
    secret_store.reset_backend_probe()
    secret_store.forget_session_cache()
    assert secret_store.active_mode() == secret_store.MODE_ENCRYPTED_FILE
    assert secret_store.load() == "", "precondition: the key is invisible"

    dialog = build_page()
    assert dialog.gallery_ai_api_key.text() == "", "precondition: the field is empty"
    fake_keyring.reset_calls()

    # The keyring answers now — no restart.
    monkeypatch.setattr(secret_store, "keyring_available", lambda: True)
    dialog.section_shown.emit("image_gallery.ai")

    assert secret_store.active_mode() == secret_store.MODE_KEYRING
    assert dialog.gallery_ai_api_key.text() == KEY
    assert "clear" not in fake_keyring.calls(), "a read-back must never clear"
    assert "store" not in fake_keyring.calls(), "a read-back must never write"
    assert fake_keyring.value() == KEY


def test_page_entry_without_a_stored_key_never_clears(build_page, fake_keyring):
    assert secret_store.load() == "", "precondition: nothing is stored"

    dialog = build_page()
    fake_keyring.reset_calls()

    dialog.section_shown.emit("image_gallery.ai")

    assert dialog.gallery_ai_api_key.text() == ""
    assert "clear" not in fake_keyring.calls(), "an empty read must not clear"
    assert "store" not in fake_keyring.calls(), "an empty read must not write"


def test_page_entry_does_not_overwrite_a_key_being_typed(build_page, fake_keyring):
    fake_keyring.seed("sk-from-the-keyring-text")
    dialog = build_page()

    dialog.gallery_ai_api_key.setText("sk-typing-right-now")
    dialog.section_shown.emit("image_gallery.ai")

    assert dialog.gallery_ai_api_key.text() == "sk-typing-right-now"


def test_page_entry_keeps_a_session_only_key(build_page, fake_keyring, monkeypatch):
    """MODE_SESSION has no disk backup: the in-memory copy is the only one."""
    monkeypatch.setattr(secret_store, "keyring_available", lambda: False)
    monkeypatch.setattr(secret_store, "cryptography_available", lambda: False)
    secret_store.reset_backend_probe()
    secret_store.forget_session_cache()
    assert secret_store.store(KEY) == secret_store.MODE_SESSION

    dialog = build_page()
    dialog.section_shown.emit("image_gallery.ai")

    assert secret_store.load() == KEY, "a memory-only key must survive a page visit"
    assert dialog.gallery_ai_api_key.text() == KEY


# ---------------------------------------------------------------------------
# The edit path is unchanged: the user's own write and clear still land
# ---------------------------------------------------------------------------


def test_the_user_edit_still_saves_and_the_user_clear_still_clears(
    build_page, fake_keyring
):
    dialog = build_page()
    fake_keyring.reset_calls()

    dialog.gallery_ai_api_key.setText(KEY)  # what typing does
    assert "store" in fake_keyring.calls()
    assert fake_keyring.value() == KEY

    fake_keyring.reset_calls()
    dialog.gallery_ai_api_key.setText("")  # the user empties the field
    assert "clear" in fake_keyring.calls()
    assert fake_keyring.value() == ""
