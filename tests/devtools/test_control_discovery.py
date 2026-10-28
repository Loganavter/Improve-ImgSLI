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

import ctypes
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
from core.log_names import APP_NAME, LEGACY_LOG_DIR_NAME

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


def _mcp_backend():
    """The MCP's tool layer (``mcp-server/app/backend.py``) — dir derivation only.

    ``backend`` is stdlib-only (it shells out for the heavy work), so importing
    it here costs nothing and lets the artifacts/data-dir rules be compared
    against the app's instead of assumed equal.
    """
    if str(MCP_DIR) not in sys.path:
        sys.path.insert(0, str(MCP_DIR))
    from app import backend  # noqa: PLC0415 - deliberately late (path set above)

    return backend


@pytest.fixture
def short_tmp():
    """A SHORT temp root for unix-socket tests.

    ``AF_UNIX`` paths are capped at ~108 bytes. A CI runner's ``tmp_path``
    (``/tmp/pytest-of-runner/pytest-0/test_<name>0/data/ImproveImgSLI/run/
    control.sock``) overflows that and ``bind()`` raises
    ``OSError: AF_UNIX path too long`` — a runner-plane failure that says nothing
    about discovery, which is what these tests measure.
    """
    import pathlib as _pathlib
    import shutil
    import tempfile

    path = _pathlib.Path(tempfile.mkdtemp(dir="/tmp", prefix="sli-t"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


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

    assert resolved == tmp_path / "data" / "BlinkTable" / "run"
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
    assert resolved == tmp_path / "data" / "BlinkTable" / "run"
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


# --- liveness probe: the platform seam -----------------------------------
#
# On Windows CPython lowers any ``os.kill`` signal except CTRL_C_EVENT /
# CTRL_BREAK_EVENT to ``OpenProcess`` + ``TerminateProcess(handle, sig)``, so the
# POSIX "signal 0 is a probe" idiom *kills* the target (exit code 0). These
# tests drive the Windows arm on POSIX with a fake ``kernel32`` and a poisoned
# ``os.kill``: reaching the POSIX probe is the bug, regardless of the answer.

#: ``STILL_ACTIVE`` — ``GetExitCodeProcess``'s value for a running process.
_STILL_ACTIVE = 259
_ERROR_ACCESS_DENIED = 5
_ERROR_INVALID_PARAMETER = 87
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class _FakeKernel32:
    """The minimal Win32 surface the Windows arm is allowed to touch."""

    def __init__(self, *, handle=0, last_error=0, exit_code=_STILL_ACTIVE):
        self._handle = handle
        self._last_error = last_error
        self._exit_code = exit_code
        self.opened: list[tuple[int, bool, int]] = []
        self.closed: list[int] = []

    def OpenProcess(self, access, inherit, pid):
        self.opened.append((access, inherit, pid))
        return self._handle

    def GetLastError(self):
        return self._last_error

    def GetExitCodeProcess(self, handle, code_ptr):
        code_ptr._obj.value = self._exit_code
        return 1

    def CloseHandle(self, handle):
        self.closed.append(handle)
        return 1


@pytest.fixture
def fake_windows(monkeypatch):
    """Install a fake ``ctypes.windll.kernel32`` and select the Windows arm."""

    def _install(**kwargs):
        kernel32 = _FakeKernel32(**kwargs)

        def _os_kill_is_the_bug(*args, **kwargs):  # pragma: no cover - red path
            raise AssertionError(
                f"os.kill{args!r} must never run on Windows: it terminates the pid"
            )

        monkeypatch.setattr(discovery, "_IS_WINDOWS", True)
        monkeypatch.setattr(os, "kill", _os_kill_is_the_bug)
        monkeypatch.setattr(
            ctypes, "windll", types.SimpleNamespace(kernel32=kernel32), raising=False
        )
        return kernel32

    return _install


@pytest.mark.parametrize(
    "case,pid,kwargs,expected",
    [
        ("running", 4242, {"handle": 0x100, "exit_code": _STILL_ACTIVE}, True),
        ("already-exited", 4242, {"handle": 0x100, "exit_code": 0}, False),
        ("access-denied", 4242, {"handle": 0, "last_error": _ERROR_ACCESS_DENIED}, True),
        (
            "no-such-pid",
            4242,
            {"handle": 0, "last_error": _ERROR_INVALID_PARAMETER},
            False,
        ),
        ("pid-zero", 0, {}, False),
        ("pid-negative", -3, {}, False),
        ("garbage", "not-a-pid", {}, False),
        ("none", None, {}, False),
    ],
)
def test_windows_liveness_never_calls_os_kill(
    case, pid, kwargs, expected, fake_windows
):
    """Access-denied means alive; any other open failure means gone."""
    kernel32 = fake_windows(**kwargs)

    assert discovery.is_pid_alive(pid) is expected

    if not kwargs:
        assert kernel32.opened == [], "an invalid pid never reaches OpenProcess"
        return
    assert kernel32.opened == [(_PROCESS_QUERY_LIMITED_INFORMATION, False, 4242)]
    if kwargs.get("handle"):
        assert kernel32.closed == [kwargs["handle"]], "the handle must be closed"
    else:
        assert kernel32.closed == [], "there is no handle to close"


def test_posix_liveness_keeps_kill_zero_semantics(monkeypatch):
    """POSIX is unchanged: 0 signal probes, PermissionError still means alive."""
    calls: list[tuple[int, int]] = []

    def _fake_kill(pid, sig):
        calls.append((pid, sig))
        if pid == 111:
            raise ProcessLookupError
        if pid == 222:
            raise PermissionError

    monkeypatch.setattr(discovery, "_IS_WINDOWS", False)
    monkeypatch.setattr(os, "kill", _fake_kill)

    assert discovery.is_pid_alive(4242) is True
    assert discovery.is_pid_alive(111) is False
    assert discovery.is_pid_alive(222) is True
    assert calls == [(4242, 0), (111, 0), (222, 0)]


def test_stale_pointer_alive_routes_through_the_probe(tmp_path, monkeypatch, fake_windows):
    """The pointer check has no second copy of the probe (Windows arm)."""
    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "ctrl"))
    kernel32 = fake_windows(handle=0x100, exit_code=_STILL_ACTIVE)
    discovery.write_pointer(
        pid=4242, socket=discovery.socket_path(), version="1"
    )

    assert discovery.stale_pointer_alive() is True
    assert kernel32.opened == [(_PROCESS_QUERY_LIMITED_INFORMATION, False, 4242)]


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
    can never touch the real ``~/.local/share/BlinkTable``. The overrides are
    cleared because a live-proof shell may carry them.
    """
    data_home = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.delenv("IMGSLI_CONTROL_DIR", raising=False)
    monkeypatch.delenv("IMGSLI_MCP_CONTROL_SOCKET", raising=False)
    fallback = data_home / "BlinkTable" / "run"

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


# --------------------------------------------------------------------------
# identity: names derive from APP_NAME, and a pre-rename tree stays reachable
# --------------------------------------------------------------------------


def test_the_control_dir_is_named_after_the_app(tmp_path, monkeypatch):
    """The published dir follows ``core.log_names.APP_NAME``, not the old name.

    Falsification: before this the app-data dir was a second literal
    (``ImproveImgSLI``) next to ``APP_NAME``, so the rename stopped at the log
    directory and left the control channel under the old name.
    """
    monkeypatch.delenv("IMGSLI_CONTROL_DIR", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    assert APP_NAME == "BlinkTable"
    assert discovery.app_data_dir() == tmp_path / "data" / "BlinkTable"
    assert discovery.runtime_dir() == tmp_path / "data" / "BlinkTable" / "run"
    # One legacy spelling, imported from ``core.log_names`` — never re-written.
    assert discovery.LEGACY_APP_DATA_DIR_NAME == LEGACY_LOG_DIR_NAME
    assert discovery.legacy_app_data_dir() == tmp_path / "data" / "ImproveImgSLI"


def test_the_mcp_reads_the_same_identity_constant():
    """The stdlib-only MCP reads ``log_names.py`` — it must not drift from it.

    ``mcp-server`` cannot import ``core`` (PySide6), so it parses the constant
    out of the one file that owns it; this pin is what makes that safe.
    """
    live = _mcp_live()

    assert live.APP_NAME == APP_NAME
    assert live.LEGACY_APP_DATA_DIR_NAME == LEGACY_LOG_DIR_NAME


def test_runtime_dir_never_publishes_into_a_legacy_run_dir(tmp_path, monkeypatch):
    """A leftover pre-rename ``run/`` does not capture the current build.

    The legacy tree is a *client* fallback only: the server writes one dir, and
    a socket left there belongs to a different build (possibly a live one, which
    must not be trampled). Nothing in the old tree is moved or removed.
    """
    monkeypatch.delenv("IMGSLI_CONTROL_DIR", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    legacy_run = tmp_path / "data" / "ImproveImgSLI" / "run"
    legacy_run.mkdir(parents=True)
    leftover = legacy_run / "control.sock"
    leftover.write_text("", encoding="utf-8")

    assert discovery.runtime_dir() == tmp_path / "data" / "BlinkTable" / "run"
    assert leftover.is_file(), "the legacy tree must never be cleaned up"


def test_mcp_falls_back_to_a_pre_rename_instance(short_tmp, monkeypatch):
    """A still-running pre-rename build stays attachable after the rename.

    Falsification: with only the current dir probed, an instance started before
    the upgrade became invisible to the MCP while its socket kept listening.
    """
    live = _mcp_live()
    _apply_case("no-runtime-dir", short_tmp, monkeypatch)
    legacy_run = short_tmp / "data" / "ImproveImgSLI" / "run"
    listener = _listen(legacy_run / "control.sock")
    try:
        assert discovery.runtime_dir() == short_tmp / "data" / "BlinkTable" / "run"
        assert live.discover_socket(dict(os.environ)) == legacy_run / "control.sock"
    finally:
        listener.close()


def test_the_current_dir_wins_over_a_pre_rename_one(short_tmp, monkeypatch):
    """Preference order, not just reachability: current first, legacy second."""
    live = _mcp_live()
    _apply_case("no-runtime-dir", short_tmp, monkeypatch)
    current_run = short_tmp / "data" / "BlinkTable" / "run"
    legacy_run = short_tmp / "data" / "ImproveImgSLI" / "run"
    current = _listen(current_run / "control.sock")
    legacy = _listen(legacy_run / "control.sock")
    try:
        assert live.control_dirs(dict(os.environ)) == [current_run, legacy_run]
        assert live.discover_socket(dict(os.environ)) == current_run / "control.sock"
    finally:
        current.close()
        legacy.close()


def test_the_control_dir_override_still_beats_both_defaults(tmp_path, monkeypatch):
    """``IMGSLI_CONTROL_DIR`` (what ``live-lease`` exports) wins over both names."""
    live = _mcp_live()
    monkeypatch.delenv("IMGSLI_MCP_CONTROL_SOCKET", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    (tmp_path / "data" / "ImproveImgSLI" / "run").mkdir(parents=True)
    override = tmp_path / "ctrl"
    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(override))

    assert discovery.runtime_dir() == override
    listener = _listen(override / "control.sock")
    try:
        assert live.discover_socket(dict(os.environ)) == override / "control.sock"
    finally:
        listener.close()


def test_artifacts_dir_is_named_after_the_app(tmp_path, monkeypatch):
    """The artifacts cache follows the same one spelling as the control dir."""
    monkeypatch.delenv("IMGSLI_MCP_ARTIFACTS", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    assert discovery.artifacts_dir() == tmp_path / "cache" / "BlinkTable" / "mcp"


def test_artifacts_dir_falls_back_to_the_pre_rename_cache(tmp_path, monkeypatch):
    """An upgrade keeps reading the captures it already has; nothing is moved."""
    monkeypatch.delenv("IMGSLI_MCP_ARTIFACTS", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    legacy = tmp_path / "cache" / "ImproveImgSLI" / "mcp"
    legacy.mkdir(parents=True)

    assert discovery.artifacts_dir() == legacy
    # ...and the current dir wins the moment it exists.
    (tmp_path / "cache" / "BlinkTable" / "mcp").mkdir(parents=True)
    assert discovery.artifacts_dir() == tmp_path / "cache" / "BlinkTable" / "mcp"


@pytest.mark.parametrize("layout", ["fresh", "legacy-only", "both"])
def test_both_sides_agree_on_the_artifacts_and_data_dirs(
    layout, tmp_path, monkeypatch
):
    """One fallback rule, two implementations — pinned for every disk state.

    The app hands the MCP absolute artifact paths but the MCP also derives the
    dir itself (its own headless captures, the preserved log); two answers for
    one cache would hide a capture the other side just wrote.
    """
    live = _mcp_live()
    backend = _mcp_backend()
    cache, data = tmp_path / "cache", tmp_path / "data"
    monkeypatch.delenv("IMGSLI_MCP_ARTIFACTS", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    if layout in {"legacy-only", "both"}:
        (cache / "ImproveImgSLI" / "mcp").mkdir(parents=True)
        (data / "ImproveImgSLI").mkdir(parents=True)
    if layout in {"fresh", "both"}:
        (cache / "BlinkTable" / "mcp").mkdir(parents=True)
        (data / "BlinkTable").mkdir(parents=True)

    expected_cache = cache / (
        "BlinkTable" if layout in {"fresh", "both"} else "ImproveImgSLI"
    ) / "mcp"
    expected_data = data / (
        "BlinkTable" if layout in {"fresh", "both"} else "ImproveImgSLI"
    )

    assert discovery.artifacts_dir() == expected_cache
    assert backend.default_artifacts_dir() == expected_cache
    assert live.resolved_app_data_dir(dict(os.environ)) == expected_data
    assert backend.app_data_dir() == expected_data
