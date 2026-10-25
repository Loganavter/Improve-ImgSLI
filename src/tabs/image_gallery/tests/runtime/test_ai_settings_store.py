"""``AiSettingsStore`` field round trips.

The key field goes through ``core.secret_store``, which on a desktop answers
from the login keyring by exec'ing ``secret-tool``. This module used to call
``save_field("api_key", …)`` with no isolation, so
``test_save_and_load_round_trip`` wrote an 11-char stub over the owner's real
73-char provider key in the SHARED keyring entry (measured 2026-10-25) and the
suite stayed green. The key test now asks for the sandboxed keyring
(``secret_store_keyring``: a recording fake ``secret-tool`` + throwaway data
dir, from ``tests/helpers/secret_store_isolation.py``) and clears through the
store on the way out, so even a mis-isolated future run leaves no stub behind.

The second half of the module pins the load-time SELF-HEAL: ``core.secret_store``
caches its backend probe for the process, so a key that lands after boot used to
be invisible to ``AiSettingsStore.load()`` for the whole session (HTTP 401 on
every AI call until restart, measured 2026-10-25). A failing cached state is now
re-probed once per load — and a healthy one is never re-probed.
"""

from __future__ import annotations

import logging
import os
import stat
import textwrap
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from core import secret_store
from tabs.image_gallery.services import ai_settings_store as store_module
from tabs.image_gallery.services.ai_settings_store import AiSettings, AiSettingsStore, DEFAULT_BASE_URL


@pytest.fixture
def isolated_key_store(secret_store_keyring):
    """A disposable keyring for the ``api_key`` round trip, cleared afterwards.

    ``secret_store_keyring`` pins the backend to the sandbox (the host's login
    keyring is never exec'd) and empties the entry at test start. The teardown
    below clears through the same store that wrote the value: if the sandbox
    ever fails to apply, the stub this test writes still does not survive it.
    """
    secret_store.forget_session_cache()
    secret_store.reset_backend_probe()
    try:
        yield
    finally:
        secret_store.clear()
        secret_store.forget_session_cache()
        secret_store.reset_backend_probe()


def test_load_defaults_when_unset(monkeypatch):
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_defaults")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove("image_gallery_ai_test_defaults")

    result = AiSettingsStore().load()

    assert result == AiSettings(enabled=False, base_url=DEFAULT_BASE_URL, api_key="", model="")
    settings.remove("image_gallery_ai_test_defaults")


def test_save_and_load_round_trip(monkeypatch, isolated_key_store):
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_roundtrip")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove("image_gallery_ai_test_roundtrip")

    store = AiSettingsStore()
    store.save_field("enabled", True)
    store.save_field("base_url", "https://example.test/v1")
    store.save_field("api_key", "sk-test-123")
    store.save_field("model", "some/model")

    # Drop the in-memory copy so the key has to come back out of the backend
    # itself — a cache hit would make this pass without a real round trip.
    secret_store.forget_session_cache()
    loaded = store.load()

    # No stored ``provider_id``: a pre-provider config loads as ``custom`` and
    # keeps its own URL verbatim (the user's endpoint is not re-written to a
    # preset they never chose).
    assert loaded == AiSettings(
        enabled=True,
        base_url="https://example.test/v1",
        api_key="sk-test-123",
        model="some/model",
        provider_id="custom",
    )
    settings.remove("image_gallery_ai_test_roundtrip")


def test_save_and_load_ask_budget_and_effort(monkeypatch):
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_ask")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove("image_gallery_ai_test_ask")

    store = AiSettingsStore()
    store.save_field("ask_max_tokens", 2048)
    store.save_field("reasoning_effort", "high")

    loaded = store.load()
    assert loaded.ask_max_tokens == 2048
    assert loaded.reasoning_effort == "high"
    settings.remove("image_gallery_ai_test_ask")


def test_load_sanitizes_invalid_ask_settings(monkeypatch):
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_ask_bad")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove("image_gallery_ai_test_ask_bad")

    store = AiSettingsStore()
    store.save_field("ask_max_tokens", -5)
    store.save_field("reasoning_effort", "bogus")

    loaded = store.load()
    assert loaded.ask_max_tokens == 0
    assert loaded.reasoning_effort == "auto"
    settings.remove("image_gallery_ai_test_ask_bad")


def test_save_and_load_vlm_max_edge(monkeypatch):
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_vlm_edge")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove("image_gallery_ai_test_vlm_edge")

    store = AiSettingsStore()
    store.save_field("vlm_max_edge_px", 768)
    assert store.load().vlm_max_edge_px == 768
    store.save_field("vlm_max_edge_px", 999)
    assert store.load().vlm_max_edge_px == 1024
    store.save_field("vlm_max_edge_px", 0)
    assert store.load().vlm_max_edge_px == 0
    settings.remove("image_gallery_ai_test_vlm_edge")


def test_save_field_rejects_unknown_name():
    store = AiSettingsStore()
    try:
        store.save_field("not_a_real_field", "x")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown field name")


# ---------------------------------------------------------------------------
# Load-time self-heal: a "no key" answer must not stick for the whole session
# ---------------------------------------------------------------------------
#
# ``core.secret_store`` caches its backend choice for the process and the two
# non-keyring backends answer "" without re-checking: a process that booted
# before the keyring answered kept reporting no key (HTTP 401 on every AI call)
# until a restart, measured 2026-10-25. ``load()`` now re-probes ONCE when the
# cached state is the failing one. The keyring here is a fake ``secret-tool``
# from ``tmp_path`` (a read-only one: these tests never store or clear through
# the store); the autouse guard in ``tests/helpers/secret_store_isolation.py``
# fails the test if the host keyring is ever reached.

_KEY = "sk-live-0123456789abcdef" * 3


class _FakeKeyring:
    """A keyring file plus the list of commands the fake tool received."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def seed(self, value: str) -> None:
        """Put *value* in the keyring the way another process would."""
        (self._root / "keyring.txt").write_text(value, encoding="utf-8")

    def calls(self) -> list[str]:
        path = self._root / "calls.txt"
        return path.read_text(encoding="utf-8").split() if path.exists() else []


@pytest.fixture
def fake_keyring(tmp_path, monkeypatch):
    """A recording, initially EMPTY ``secret-tool`` on ``PATH``."""
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
            cmd = sys.argv[1]
            with (root / "calls.txt").open("a", encoding="utf-8") as handle:
                handle.write(cmd + "\\n")
            if cmd == "lookup":
                sys.stdout.write(store.read_text() if store.exists() else "")
                sys.exit(0 if store.exists() else 1)
            sys.exit(2)
            """
        ),
        encoding="utf-8",
    )
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{root}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    secret_store.reset_backend_probe()
    secret_store.forget_session_cache()
    return _FakeKeyring(root)


@pytest.fixture
def stale_boot(monkeypatch):
    """The measured boot state: no keyring binary, no cryptography either.

    ``active_mode`` resolves to ``MODE_SESSION`` and caches it, which is the
    state that used to answer "" for the rest of the run.
    """
    monkeypatch.setattr(secret_store, "keyring_available", lambda: False)
    monkeypatch.setattr(secret_store, "cryptography_available", lambda: False)
    secret_store.reset_backend_probe()
    secret_store.forget_session_cache()
    assert secret_store.active_mode() == secret_store.MODE_SESSION
    assert secret_store.load() == "", "precondition: the key is invisible"
    yield
    secret_store.forget_session_cache()
    secret_store.reset_backend_probe()


@pytest.fixture
def ai_settings_group(monkeypatch):
    """A throwaway AI-settings group: the user's real config is untouched."""
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_selfheal")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove("image_gallery_ai_test_selfheal")
    yield
    settings.remove("image_gallery_ai_test_selfheal")


def _reprobe_spy(monkeypatch) -> dict[str, int]:
    """Count ``secret_store.reset_backend_probe`` calls (install AFTER setup)."""
    counter = {"n": 0}
    original = secret_store.reset_backend_probe

    def counting() -> None:
        counter["n"] += 1
        original()

    monkeypatch.setattr(secret_store, "reset_backend_probe", counting)
    return counter


def test_load_sees_a_key_that_appeared_after_a_stale_probe(
    ai_settings_group, fake_keyring, stale_boot, monkeypatch
):
    """A key stored after boot is visible to the NEXT load, no restart.

    RED BEFORE (old ``_load_api_key``: a bare ``secret_store.load()``): the
    cached ``MODE_SESSION`` answer is "" and nothing re-probes, so the second
    load still reports no key — the 401-for-the-session symptom.
    """
    store = AiSettingsStore()
    assert store.load().api_key == "", "precondition: no key yet"

    # The keyring starts answering between the two loads.
    fake_keyring.seed(_KEY)
    monkeypatch.setattr(secret_store, "keyring_available", lambda: True)

    assert store.load().api_key == _KEY
    assert secret_store.active_mode() == secret_store.MODE_KEYRING


def test_the_heal_is_logged_once_and_only_when_it_changes_the_answer(
    ai_settings_group, fake_keyring, stale_boot, monkeypatch, caplog
):
    store = AiSettingsStore()
    with caplog.at_level(logging.INFO, logger=store_module.__name__):
        assert store.load().api_key == "", "an empty store stays empty"
        assert not caplog.messages, "no heal, no log line"

        fake_keyring.seed(_KEY)
        monkeypatch.setattr(secret_store, "keyring_available", lambda: True)
        assert store.load().api_key == _KEY
        healed = [m for m in caplog.messages if "appeared after a stale" in m]
        assert len(healed) == 1

        caplog.clear()
        # Now healthy: the value is cached, so further loads neither probe nor log.
        for _ in range(3):
            assert store.load().api_key == _KEY
        assert not caplog.messages


def test_a_healthy_store_never_re_probes(
    ai_settings_group, fake_keyring, monkeypatch
):
    """A store that has a key pays no probe and no extra keyring exec per load."""
    fake_keyring.seed(_KEY)
    secret_store.reset_backend_probe()
    secret_store.forget_session_cache()
    store = AiSettingsStore()
    assert store.load().api_key == _KEY

    probes = _reprobe_spy(monkeypatch)
    lookups = len(fake_keyring.calls())
    for _ in range(3):
        assert store.load().api_key == _KEY

    assert probes["n"] == 0, "a healthy store must not re-probe"
    assert len(fake_keyring.calls()) == lookups, "the value is memoized, not re-read"


def test_a_keyring_store_with_no_value_needs_no_re_probe(
    ai_settings_group, fake_keyring, monkeypatch
):
    """Keyring backend + no stored key: the entry is re-read, no probe on top.

    ``secret_store.load()`` already execs the lookup on every call in this mode,
    so it cannot cache a negative — a key stored later is visible without any
    re-probe. Re-probing here would only add a ``shutil.which`` per load.
    """
    secret_store.reset_backend_probe()
    secret_store.forget_session_cache()
    assert secret_store.active_mode() == secret_store.MODE_KEYRING

    probes = _reprobe_spy(monkeypatch)
    store = AiSettingsStore()
    for _ in range(3):
        assert store.load().api_key == ""
    assert probes["n"] == 0, (
        "a keyring-backed store re-reads the entry on every load; it must not "
        "re-probe the backend on top of that"
    )


def test_the_stale_state_re_probe_is_bounded_per_load(
    ai_settings_group, fake_keyring, stale_boot, monkeypatch
):
    """Session-only state, no key anywhere: one re-probe per load, never a loop."""
    probes = _reprobe_spy(monkeypatch)
    store = AiSettingsStore()
    for expected in (1, 2, 3):
        assert store.load().api_key == ""
        assert probes["n"] == expected


def test_the_host_keyring_is_never_touched(
    ai_settings_group, fake_keyring, stale_boot, monkeypatch, secret_store_isolation
):
    """The guard's own evidence: every exec went to the sandboxed fake tool."""
    box = secret_store_isolation
    store = AiSettingsStore()
    store.load()
    fake_keyring.seed(_KEY)
    monkeypatch.setattr(secret_store, "keyring_available", lambda: True)
    assert store.load().api_key == _KEY

    assert fake_keyring.calls(), "the fake keyring must actually have been asked"
    assert box.problems() == [], "the guard must find no host-keyring access"
    tools = [event.get("tool") for event in box.events() if "argv" in event]
    assert tools
    assert all(box.is_sandboxed_path(path) for path in tools)
