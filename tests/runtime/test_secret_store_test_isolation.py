"""A test run must never reach the host keyring by accident.

Measured twice: 2026-10-25 (the shared ``blinktable`` keyring entry was replaced
by a stub) and 2026-10-26 (an un-sandboxed gallery-tier run). Relying on every
test tree importing an autouse sandbox fixture is not a guard — a single
``pytest src/tabs/<tab>/tests`` that does not load the root conftest is enough.

``core.secret_store`` now fails closed: inside pytest, without the sandbox
marker, the keyring backend reports unavailable and the store degrades to the
session / throwaway encrypted-file path.
"""

from __future__ import annotations

import subprocess
import sys

from core import secret_store


def test_bare_pytest_run_cannot_use_the_keyring(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/probe.py::test_probe (call)")
    monkeypatch.delenv(secret_store.SANDBOX_MARKER_ENV, raising=False)
    assert secret_store._pytest_without_sandbox() is True
    assert secret_store.keyring_available() is False


def test_the_sandbox_marker_restores_the_backend(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/probe.py::test_probe (call)")
    monkeypatch.setenv(secret_store.SANDBOX_MARKER_ENV, "/tmp/sandbox")
    assert secret_store._pytest_without_sandbox() is False
    # Only the guard is under test here; whether a (fake) secret-tool exists is
    # the sandbox fixture's business.
    assert secret_store.keyring_available() is (secret_store._secret_tool() is not None)


def test_production_behaviour_is_unchanged(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv(secret_store.SANDBOX_MARKER_ENV, raising=False)
    assert secret_store._pytest_without_sandbox() is False


def test_a_child_process_without_the_sandbox_cannot_open_the_keyring(tmp_path):
    """The guard survives a fresh interpreter (the cells' shape)."""
    code = (
        "import os;"
        "from core import secret_store;"
        "print(secret_store.keyring_available())"
    )
    env = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": "src",
        "PYTEST_CURRENT_TEST": "subprocess-probe",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd="."
    )
    assert out.stdout.strip() == "False", out.stderr


import os  # noqa: E402  (used by the subprocess test's env)
