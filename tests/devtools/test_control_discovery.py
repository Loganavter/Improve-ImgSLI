"""``core.control.discovery`` — runtime dir, pointer, socket, peer-uid checks.

Falsification: ``core.control`` is new; a base checkout has no
``src/core/control/`` and these imports fail. The peer-uid test would also fail
on a naive implementation that closed Qt's socket fd while wrapping it.

The last section is a **cross-side contract**: the host MCP server
(``mcp-server/app/live.py``) re-derives the same control dir with its own copy
of the rule (it is stdlib-only and cannot import ``core.control``, which pulls
in PySide6). Two copies of one rule drift silently — 2026-10-21 they did: the
app refused a non-private ``$XDG_RUNTIME_DIR`` while the MCP accepted any
writable one, so under the default env the MCP found no socket and fell back to
headless without a word. These tests pin the two derivations to each other.
"""

from __future__ import annotations

import os
import socket
import stat
import subprocess
import sys
import types
from pathlib import Path

import pytest

from PySide6.QtWidgets import QApplication, QWidget

from core.control import discovery

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = REPO_ROOT / "mcp-server"


def _mcp_live():
    """The MCP side imported in-process (``mcp-server/app/live.py``).

    The MCP is driven as a standalone stdio script, but it is importable from
    a test without any packaging change — ``tests/devtools/test_mcp_live_attach.py``
    already puts ``mcp-server`` on ``sys.path`` the same way.
    """
    if str(MCP_DIR) not in sys.path:
        sys.path.insert(0, str(MCP_DIR))
    from app import live  # noqa: PLC0415 - deliberately late (path set above)

    return live


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _listen(path: Path) -> socket.socket:
    """A real unix socket with a listener — enough for a discovery probe."""
    path.parent.mkdir(parents=True, exist_ok=True)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(4)
    return listener


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


# --------------------------------------------------------------------------
# live-proof 2026-10-17: the list advertises kinds that are not capturable yet
# --------------------------------------------------------------------------


def test_live_surfaces_marks_capturable_only_for_open_tabs():
    tabs = [
        ("image_gallery", types.SimpleNamespace(display_name="Image Gallery")),
        ("image_compare", types.SimpleNamespace(display_name="Image Compare")),
    ]

    rows = {r["name"]: r for r in discovery.live_surfaces(tabs, page_of=lambda st: st == "image_gallery")["surfaces"]}

    assert rows["image_gallery"]["capturable"] is True and rows["image_gallery"]["live"] is True
    assert rows["image_compare"]["capturable"] is False, (
        "a registered but CLOSED kind is drivable (open_tab) yet not capturable"
    )
    # Devtool demo names are fallback-only: never capturable on the live path.
    demo = [r for r in rows.values() if r.get("live") is False]
    assert demo and all(r["capturable"] is False for r in demo)
    # No page_of at all => nothing is claimed capturable.
    bare = discovery.live_surfaces(tabs)["surfaces"]
    assert all(r["capturable"] is False for r in bare if r.get("live") is True)


def test_resolve_capture_target_tells_closed_apart_from_unknown(monkeypatch):
    from tabs.registry import TabRegistry

    monkeypatch.setattr(TabRegistry, "get_page", lambda self, st: None, raising=False)
    monkeypatch.setattr(TabRegistry, "registered_types", ("image_compare",), raising=False)

    with pytest.raises(discovery.MethodError) as closed:
        discovery.resolve_capture_target(None, None, "image_compare")
    assert "is not open" in str(closed.value)
    assert "open_tab" in str(closed.value.hint)

    with pytest.raises(discovery.MethodError) as unknown:
        discovery.resolve_capture_target(None, None, "no_such_surface")
    assert "unknown surface" in str(unknown.value)
    assert "capturable" in str(unknown.value.hint)


def test_parse_key_sequence_types_a_path_by_keystroke():
    """A path must be typeable into a text field: ``/`` and ``.`` are keys.

    Falsification: before this, the parser accepted only named keys plus
    single letters/digits, so no client could type ``/tmp/a.png`` — the one
    gap that made a headless file dialog undriveable.
    """
    keys = discovery.parse_key_sequence("/,t,m,p,/,a,.,p,n,g")

    assert [label for _key, _mods, label in keys] == [
        "/", "t", "m", "p", "/", "a", ".", "p", "n", "g",
    ]


def test_parse_key_sequence_still_rejects_an_unknown_name():
    with pytest.raises(discovery.MethodError) as exc:
        discovery.parse_key_sequence("wibble")

    assert "unknown key" in exc.value.message
    assert "/" in exc.value.hint and "f12" in exc.value.hint
# --------------------------------------------------------------------------
# cross-side contract: the MCP derives the SAME control dir as the app
# --------------------------------------------------------------------------


def _apply_case(case: str, tmp_path, monkeypatch) -> Path:
    """Lay out one env of the matrix; return the dir BOTH sides must pick.

    Every case points ``XDG_DATA_HOME`` at the tmp tree, so a forgotten variable
    can never touch the real ``~/.local/share/ImproveImgSLI``. The overrides are
    cleared because a live-proof shell may carry them.
    """
    data_home = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.delenv("IMGSLI_CONTROL_DIR", raising=False)
    monkeypatch.delenv("IMGSLI_MCP_CONTROL_SOCKET", raising=False)
    fallback = data_home / "ImproveImgSLI" / "run"

    if case == "no-runtime-dir":
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
        return fallback

    if case == "private-runtime-dir":
        xdg = tmp_path / "xdg-private"
        xdg.mkdir()
        os.chmod(xdg, 0o700)
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg))
        return xdg

    if case == "shared-runtime-dir":
        xdg = tmp_path / "xdg-shared"
        xdg.mkdir()
        os.chmod(xdg, 0o755)
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg))
        return fallback

    if case == "runtime-dir-is-a-file":
        not_a_dir = tmp_path / "not-a-dir"
        not_a_dir.write_text("", encoding="utf-8")
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(not_a_dir))
        return fallback

    raise AssertionError(f"unknown case {case!r}")


_MATRIX = [
    "no-runtime-dir",
    "private-runtime-dir",
    "shared-runtime-dir",
    "runtime-dir-is-a-file",
]


@pytest.mark.parametrize("case", _MATRIX)
def test_mcp_probes_the_same_control_dir_the_app_publishes(
    case, tmp_path, monkeypatch
):
    """One derivation rule, two implementations: the MCP's first probe is the
    app's chosen dir for every env in the matrix.

    Falsification: before this, ``XDG_RUNTIME_DIR`` was accepted on the MCP side
    on ``isdir + W_OK`` alone, so a ``0755`` runtime dir made the MCP probe a
    dir the app refuses to publish in (``shared-runtime-dir``).
    """
    live = _mcp_live()
    expected = _apply_case(case, tmp_path, monkeypatch)

    app_dir = discovery.runtime_dir()

    assert app_dir == expected
    assert live.control_dirs(dict(os.environ))[0] == app_dir


@pytest.mark.parametrize("case", ["no-runtime-dir", "private-runtime-dir"])
def test_mcp_finds_the_socket_where_the_app_publishes_it(
    case, tmp_path, monkeypatch
):
    """The positive half: a socket in the app's dir is the MCP's answer."""
    live = _mcp_live()
    expected = _apply_case(case, tmp_path, monkeypatch)

    app_dir = discovery.runtime_dir()  # creates the dir when it falls back
    listener = _listen(app_dir / "control.sock")
    try:
        assert discovery.socket_path() == expected / "control.sock"
        assert live.discover_socket(dict(os.environ)) == discovery.socket_path()
    finally:
        listener.close()


def test_a_shared_runtime_dir_is_invisible_to_both_sides(tmp_path, monkeypatch):
    """Symmetric refusal: neither side treats a ``0755`` dir as the channel.

    Falsification: this is the measured defect — the app refused the dir while
    the MCP discovered in it, so the same machine had two different answers to
    "where is the control socket".
    """
    live = _mcp_live()
    _apply_case("shared-runtime-dir", tmp_path, monkeypatch)
    shared = tmp_path / "xdg-shared"
    listener = _listen(shared / "control.sock")
    try:
        assert discovery.runtime_dir() != shared
        assert discovery.socket_path().parent != shared
        assert live.discover_socket(dict(os.environ)) is None
    finally:
        listener.close()


def test_both_sides_honour_the_explicit_control_dir_override(tmp_path, monkeypatch):
    """``IMGSLI_CONTROL_DIR`` is the override every live proof relies on."""
    live = _mcp_live()
    monkeypatch.delenv("IMGSLI_MCP_CONTROL_SOCKET", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    override = tmp_path / "ctrl"
    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(override))

    assert discovery.runtime_dir() == override
    listener = _listen(discovery.socket_path())
    try:
        assert live.discover_socket(dict(os.environ)) == discovery.socket_path()
    finally:
        listener.close()


def test_the_mcp_socket_override_wins_without_moving_the_app_dir(
    tmp_path, monkeypatch
):
    """``IMGSLI_MCP_CONTROL_SOCKET`` is MCP-side only; the app never reads it.

    Pinned so a future "unify the env vars" change cannot quietly make the app
    honour a variable only the client sets.
    """
    live = _mcp_live()
    monkeypatch.delenv("IMGSLI_CONTROL_DIR", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    app_dir = discovery.runtime_dir()

    explicit = tmp_path / "elsewhere" / "explicit.sock"
    listener = _listen(explicit)
    try:
        monkeypatch.setenv("IMGSLI_MCP_CONTROL_SOCKET", str(explicit))
        assert live.discover_socket(dict(os.environ)) == explicit
        assert discovery.runtime_dir() == app_dir
        assert discovery.socket_path().parent == app_dir
    finally:
        listener.close()
