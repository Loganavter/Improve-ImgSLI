"""``core.control.discovery`` — runtime dir, pointer, socket, peer-uid checks.

Falsification: ``core.control`` is new; a base checkout has no
``src/core/control/`` and these imports fail. The peer-uid test would also fail
on a naive implementation that closed Qt's socket fd while wrapping it.
"""

from __future__ import annotations

import os
import socket
import stat
import subprocess
import sys
import types

import pytest

from PySide6.QtWidgets import QApplication, QWidget

from core.control import discovery


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_runtime_dir_override_is_created_private(tmp_path, monkeypatch):
    target = tmp_path / "ctrl"
    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(target))

    resolved = discovery.runtime_dir()

    assert resolved == target
    assert resolved.is_dir()
    assert stat.S_IMODE(resolved.stat().st_mode) == 0o700


def test_runtime_dir_falls_back_to_app_data_run(tmp_path, monkeypatch):
    monkeypatch.delenv("IMGSLI_CONTROL_DIR", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    resolved = discovery.runtime_dir()

    assert resolved == tmp_path / "data" / "ImproveImgSLI" / "run"
    assert stat.S_IMODE(resolved.stat().st_mode) == 0o700


def test_runtime_dir_prefers_a_private_xdg_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("IMGSLI_CONTROL_DIR", raising=False)
    xdg = tmp_path / "xdg"
    xdg.mkdir()
    os.chmod(xdg, 0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    assert discovery.runtime_dir() == xdg


def test_runtime_dir_rejects_a_world_readable_xdg_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("IMGSLI_CONTROL_DIR", raising=False)
    xdg = tmp_path / "public"
    xdg.mkdir()
    os.chmod(xdg, 0o755)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    resolved = discovery.runtime_dir()

    assert resolved != xdg, "a shared XDG_RUNTIME_DIR must not host the channel"
    assert resolved == tmp_path / "data" / "ImproveImgSLI" / "run"
    assert stat.S_IMODE(resolved.stat().st_mode) == 0o700


def test_socket_and_pointer_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "ctrl"))
    directory = discovery.runtime_dir()

    assert discovery.socket_path() == directory / "control.sock"
    assert discovery.pointer_path() == directory / "instance.json"
    assert discovery.socket_path(tmp_path / "explicit") == tmp_path / "explicit" / "control.sock"
    assert discovery.pointer_path(tmp_path / "explicit") == tmp_path / "explicit" / "instance.json"


def test_pointer_round_trip_is_private_and_clearable(tmp_path, monkeypatch):
    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "ctrl"))

    written = discovery.write_pointer(
        pid=os.getpid(),
        socket=discovery.socket_path(),
        version="9.9-test",
    )

    assert written == discovery.pointer_path()
    assert stat.S_IMODE(written.stat().st_mode) == 0o600
    data = discovery.read_pointer()
    assert data is not None
    assert data["pid"] == os.getpid()
    assert data["socket"].endswith("control.sock")
    assert data["version"] == "9.9-test"
    assert data["uid"] == os.getuid()

    discovery.clear_pointer()
    assert discovery.read_pointer() is None


def test_read_pointer_returns_none_on_corruption(tmp_path, monkeypatch):
    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "ctrl"))
    path = discovery.pointer_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not json", encoding="utf-8")

    assert discovery.read_pointer() is None
    assert discovery.stale_pointer_alive() is False


def test_stale_pointer_detection(tmp_path, monkeypatch):
    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "ctrl"))
    assert discovery.stale_pointer_alive() is False, "no pointer is not alive"

    discovery.write_pointer(
        pid=os.getpid(), socket=discovery.socket_path(), version="1"
    )
    assert discovery.stale_pointer_alive() is True, "our own pid is alive"

    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    discovery.write_pointer(
        pid=dead.pid, socket=discovery.socket_path(), version="1"
    )
    assert discovery.stale_pointer_alive() is False, "a reaped pid is stale"


@pytest.mark.skipif(
    not hasattr(socket, "SO_PEERCRED"), reason="SO_PEERCRED is Linux-only"
)
def test_peer_uid_ok_accepts_self_without_closing_the_descriptor():
    left, right = socket.socketpair()
    try:
        assert discovery.peer_uid_ok(left.fileno()) is True
        # The wrapper must detach, not close, the descriptor it borrowed.
        assert left.fileno() != -1
        assert left.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) == socket.SOCK_STREAM
    finally:
        left.close()
        right.close()


def test_peer_uid_ok_refuses_bad_descriptors():
    assert discovery.peer_uid_ok(-1) is False
    assert discovery.peer_uid_ok(10**9) is False


def test_capture_label_prefers_the_widget_object_name():
    # ``objectName`` is a method on PySide6 widgets; a naive getattr would
    # stringify the bound method (bug found in the live :99 proof).
    app = _qapp()
    named = QWidget()
    named.setObjectName("my_surface")
    fake = types.SimpleNamespace(activeWindow=lambda: named)
    target, label = discovery.resolve_capture_target(fake, None, None)
    assert target is named and label == "my_surface"

    anonymous = QWidget()
    fake2 = types.SimpleNamespace(activeWindow=lambda: anonymous)
    _target, label2 = discovery.resolve_capture_target(fake2, None, None)
    assert label2 == "QWidget"
    assert app is not None
