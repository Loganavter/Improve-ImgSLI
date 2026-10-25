"""The secret-store sandbox must actually discriminate, not just exist.

``tests/helpers/secret_store_isolation.py`` pins every keyring call into a fake
``secret-tool`` and fails a test that mutates one without declaring it. A guard
that cannot distinguish a sandboxed call from a host one would be green while
the old bug (an unisolated ``save_field("api_key", …)`` overwriting the owner's
login-keyring entry) recurs, so these cases exercise the three decisions that
matter:

* the fake tool answers ``store`` → ``lookup`` → ``clear`` for real;
* a ``PATH`` that resolves to the host binary is REFUSED and substituted;
* an undeclared mutation and a foreign-marker invocation are both reported.

Each case builds its own box under ``tmp_path``: the session sandbox is still
installed underneath, and a second box's log never mixes with it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from core import secret_store
from tests.helpers.secret_store_isolation import (
    MARKER_ENV,
    SANDBOX_ENV,
    KEYRING_OPT_IN_FIXTURE,
    SecretStoreSandbox,
    module_installs_own_tool,
    sandboxed_resolution,
)

KEY = "sk-sandbox-0123456789abcdef"


def _box(tmp_path: Path, name: str) -> SecretStoreSandbox:
    return SecretStoreSandbox(tmp_path / name)


def _invoke(box: SecretStoreSandbox, *argv: str, marker: str | None = None) -> None:
    """Run the fake tool the way ``core.secret_store`` would."""
    env = {**os.environ, SANDBOX_ENV: str(box.root)}
    if marker is not None:
        env[MARKER_ENV] = marker
    payload = "sk-stub" if argv and argv[0] == "store" else None
    subprocess.run(
        [sys.executable, str(box.tool_path), *argv],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_the_fake_tool_round_trips_a_value(tmp_path, monkeypatch):
    box = _box(tmp_path, "round-trip").install(monkeypatch)

    assert secret_store.store(KEY) == secret_store.MODE_KEYRING
    secret_store.forget_session_cache()
    assert secret_store.load() == KEY, "the value must come back out of the fake keyring"

    secret_store.clear()
    secret_store.forget_session_cache()
    assert secret_store.load() == ""
    commands = [event["argv"][0] for event in box.events() if event.get("argv")]
    # ``clear()`` wipes BOTH keyring identities and ``load()`` probes both, so
    # the exact sequence is part of what the fake must reproduce faithfully.
    assert commands == ["store", "lookup", "clear", "clear", "lookup", "lookup"], commands


def test_a_reordered_path_is_refused_and_substituted(tmp_path):
    box = _box(tmp_path, "refusal")
    box.tool_path.parent.mkdir(parents=True, exist_ok=True)
    box.tool_path.write_text("#!/bin/sh\n", encoding="utf-8")
    box.log_path.touch()

    resolve = sandboxed_resolution(box, lambda: "/usr/bin/secret-tool")

    assert resolve() == str(box.tool_path), "the host binary must never be handed out"
    refusals = [event for event in box.events() if event.get("kind") == "refused"]
    assert [event["path"] for event in refusals] == ["/usr/bin/secret-tool"]


def test_a_sandboxed_binary_passes_through_untouched(tmp_path):
    box = _box(tmp_path, "pass-through")
    sandboxed = str(box.tool_path)
    own_fake = str(tmp_path / "test-owned" / "secret-tool")

    assert sandboxed_resolution(box, lambda: sandboxed)() == sandboxed
    assert sandboxed_resolution(box, lambda: own_fake)() == own_fake, (
        "a test's own fake (under pytest's tmp tree) must win, unchanged"
    )
    assert box.events() == [], "a sandboxed binary must not be recorded as a refusal"


def test_an_undeclared_mutation_is_reported(tmp_path):
    box = _box(tmp_path, "undeclared").install(pytest.MonkeyPatch())
    try:
        box.begin_test("tests/example.py::test_writes_a_key")
        _invoke(
            box,
            "store",
            "application",
            "blinktable",
            "key",
            "ai-api-key",
            marker="tests/example.py::test_writes_a_key",
        )

        problems = box.problems()

        assert len(problems) == 1, problems
        assert KEYRING_OPT_IN_FIXTURE in problems[0], problems[0]
    finally:
        box.reset_caches()


def test_a_declared_mutation_is_allowed(tmp_path):
    box = _box(tmp_path, "declared").install(pytest.MonkeyPatch())
    try:
        box.begin_test("tests/example.py::test_writes_a_key")
        box.allow_keyring()
        _invoke(
            box,
            "store",
            "application",
            "blinktable",
            "key",
            "ai-api-key",
            marker="tests/example.py::test_writes_a_key",
        )

        assert box.problems() == []
    finally:
        box.reset_caches()


def test_an_invocation_from_another_test_is_reported(tmp_path):
    box = _box(tmp_path, "foreign").install(pytest.MonkeyPatch())
    try:
        box.begin_test("tests/example.py::test_two")
        box.allow_keyring()
        _invoke(
            box,
            "lookup",
            "application",
            "blinktable",
            "key",
            "ai-api-key",
            marker="tests/example.py::test_one",
        )

        problems = box.problems()

        assert len(problems) == 1, problems
        assert "tests/example.py::test_one" in problems[0]
    finally:
        box.reset_caches()


def test_module_installs_own_tool_reads_the_division_not_prose(tmp_path):
    own = tmp_path / "test_own_fake.py"
    own.write_text(
        'def fixture(tmp_path):\n    return tmp_path / "secret-tool"\n', encoding="utf-8"
    )
    prose = tmp_path / "test_prose_only.py"
    prose.write_text(
        '"""This test talks about a secret-tool without building one."""\n', encoding="utf-8"
    )

    assert module_installs_own_tool(type("M", (), {"__file__": str(own)})) is True
    assert module_installs_own_tool(type("M", (), {"__file__": str(prose)})) is False


def test_a_write_into_a_real_app_data_dir_is_reported(tmp_path):
    box = _box(tmp_path, "data-write").install(pytest.MonkeyPatch())
    try:
        box.begin_test("tests/example.py::test_writes")
        box.allow_keyring()
        box.record_data_write("/home/someone/.local/share/BlinkTable/secrets")

        problems = box.problems()

        assert len(problems) == 1, problems
        assert "outside the sandbox" in problems[0], problems[0]
    finally:
        box.reset_caches()


def test_the_encrypted_file_backend_write_is_recorded(tmp_path, monkeypatch):
    """The other writer: force the file backend and watch the directory it uses."""
    pytest.importorskip("cryptography.fernet")
    box = _box(tmp_path, "file-backend").install(monkeypatch)
    try:
        monkeypatch.setattr(secret_store, "keyring_available", lambda: False)
        monkeypatch.setattr(secret_store, "cryptography_available", lambda: True)
        box.begin_test("tests/example.py::test_writes")
        box.allow_keyring()

        assert secret_store.store(KEY) == secret_store.MODE_ENCRYPTED_FILE
        assert "data-write" in [event.get("kind") for event in box.events()]
        assert box.problems() == [], "the sandbox's own data dir must be accepted"
    finally:
        box.reset_caches()


def test_a_data_dir_outside_the_sandbox_is_reported(tmp_path, monkeypatch):
    box = _box(tmp_path, "data-home")
    installed = os.environ["XDG_DATA_HOME"]

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "still-disposable"))
    assert box.data_home_is_disposable() is True

    # No XDG_DATA_HOME at all: ``secret_store`` falls back to the real
    # ``~/.local/share`` — that is what the guard exists to catch.
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert box.data_home_is_disposable() is False

    # Hand the session's own value back before the per-test guard reads it: it
    # checks the live environment, not the fixture's undo stack.
    os.environ["XDG_DATA_HOME"] = installed
