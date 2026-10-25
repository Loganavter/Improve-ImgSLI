"""MCP live-attach: control-protocol client, adapter, and fallback wiring.

The fake server below is a **real** ``AF_UNIX`` socket in a tmp dir speaking the
frozen control protocol (one newline-delimited JSON request/response per line,
``{"id", "ok", "result"|"error"}``) — the same wire shape the app's QLocalServer
implements. No real app process is needed, so this suite runs headless and
offline; the one test that talks to a genuine instance is skipped unless
``IMGSLI_MCP_CONTROL_SOCKET`` is set (the supervisor runs that proof once both
lanes land).

Pinned here: discovery order (explicit socket → control dir → runtime dir),
stale-pointer handling, the client's transport-vs-app-error split, every
adapter proxy's normalised result shape, and the backend's live-first /
fallback-on-transport-failure routing.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = REPO_ROOT / "mcp-server"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from app import catalog  # noqa: E402
from app.backend import AppBackend  # noqa: E402
from app.live import (  # noqa: E402
    CONTROL_DIR_ENV,
    CONTROL_SOCKET_NAME,
    INFLIGHT_NOTE_NAME,
    NOT_SENT,
    READ_RETRY_BUDGET,
    SENT_NO_REPLY,
    SOCKET_OVERRIDE_ENV,
    LiveBackend,
    LiveClient,
    LiveError,
    LiveUnavailable,
    control_dirs,
    discover_socket,
    summarize_request_params,
)
from app.protocol import MCPProtocol  # noqa: E402
from app.process_policy import PRESERVED_LOG_NAME, process_report  # noqa: E402

#: Handler sentinel: close the connection without answering (transport fault).
CLOSE = object()

#: Handler sentinel: accept the request but never answer it (read deadline
#: expiry — the caller must time out).
SILENT = object()


# --- fake control server ----------------------------------------------------


def default_handler(method: str, params: dict):
    """Canned answers in the app's own shapes, one branch per protocol method."""
    if method == "ping":
        return True, {}
    if method == "list_actions":
        return True, {
            "count": 2,
            "actions": [
                {
                    "action_id": "platform.settings",
                    "label": "Settings",
                    "owner_tab": None,
                    "topic": "platform",
                    "shortcut": "Ctrl+,",
                    "enabled": True,
                    "reason": None,
                    "unexpected": "dropped",
                },
                {
                    "action_id": "image_compare.zoom_fit",
                    "label": "Fit",
                    "owner_tab": "image_compare",
                    "topic": "view",
                    "shortcut": None,
                    "enabled": False,
                    "reason": "no document is open",
                },
            ],
        }
    if method == "list_sessions":
        return True, {
            "count": 1,
            "sessions": [
                {
                    "id": "s1",
                    "session_type": "image_compare",
                    "title": "Image Compare",
                    "active": True,
                    "extra": "dropped",
                }
            ],
        }
    if method == "get_state":
        return True, {"path": params.get("path"), "state": "dark"}
    if method == "read_log":
        return True, {
            "path": "/live/log.txt",
            "total_lines": 5,
            "returned": 2,
            "lines": [
                {"n": 4, "level": "INFO", "text": "line four"},
                {"n": 5, "level": None, "text": "line five", "extra": "dropped"},
            ],
        }
    if method == "query_trace":
        return True, {
            "path": "/live/trace.jsonl",
            "total_records": 3,
            "returned": 1,
            "records": [{"kind": "render", "trace_id": "t1"}, "not-a-record"],
        }
    if method == "dump_ui_layout":
        return True, {"path": "/live/ui.json", "tab": "image_compare", "windows": 2, "node_count": 7}
    if method == "list_surfaces":
        return True, {
            "count": 1,
            "surfaces": [
                {
                    "name": "settings",
                    "description": "Settings dialog",
                    "isolated": False,
                    "live": False,
                    "capturable": False,
                }
            ],
        }
    if method == "open_tab":
        return True, {"ran": True, "tab": params.get("tab")}
    if method == "run_action":
        return True, {"ran": True, "action_id": params.get("action_id"), "tab": params.get("tab")}
    if method == "open_folder":
        return True, {"ran": True, "path": params.get("path"), "routed": True}
    if method == "open_file":
        return True, {
            "opened": True,
            "path": params.get("path"),
            "tab": params.get("tab") or "image_compare",
            "count": 1,
        }
    if method == "set_theme":
        return True, {"theme": params.get("theme"), "persisted": True, "applies_on": "now"}
    if method == "set_language":
        return True, {"language": params.get("language"), "persisted": True, "applies_on": "now"}
    if method == "capture_live":
        what = params.get("what") or "MainWindow"
        return True, {
            "path": f"/live/{what}.png",
            "what": what,
            "method": "grabWindow",
            "size": [1280, 800],
            "rhi_layers": 1,
        }
    if method == "press_keys":
        return True, {
            "pressed": ["ctrl+shift+p"],
            "count": 1,
            "target": "QMainWindow",
            "activated": True,
            "focus_is_ours": True,
        }
    if method == "ui_elements":
        return True, {
            "count": 2,
            "window_count": 1,
            "elements": [
                {
                    "id": "main.settings.btn",
                    "role": "button",
                    "label": "Settings",
                    "rect": [1, 2, 3, 4],
                    "screen_rect": [10, 20, 30, 40],
                    "window": "main",
                    "owner_tab": None,
                    "action_id": "platform.settings",
                    "enabled": True,
                    "visible": True,
                    "unexpected": "dropped",
                },
                {
                    "id": "gallery.card.menu.row1",
                    "role": "menu-row",
                    "label": "Open",
                    "rect": [5, 6, 7, 8],
                    "screen_rect": [50, 60, 70, 80],
                    "window": "popup",
                    "owner_tab": "image_gallery",
                    "action_id": None,
                    "enabled": True,
                    "visible": True,
                },
            ],
        }
    if method == "ui_click":
        return True, {
            "clicked": True,
            "id": params.get("id"),
            "rect": [1, 2, 3, 4],
            "screen_rect": [10, 20, 30, 40],
            "target": "QPushButton",
            "surface": "main",
        }
    if method == "ui_hover":
        return True, {
            "hovered": True,
            "id": params.get("id"),
            "rect": [1, 2, 3, 4],
            "target": "QPushButton",
        }
    if method == "ui_focus":
        return True, {
            "focused": True,
            "id": params.get("id"),
            "rect": [1, 2, 3, 4],
            "target": "QLineEdit",
            "focus_widget": "QLineEdit",
        }
    if method == "jobs_list":
        return True, {
            "count": 2,
            "jobs": [
                {
                    "id": "pool:image_gallery",
                    "kind": "gallery_pool",
                    "status": "running",
                    "progress": {"done": 2, "total": 6},
                    "elapsed_s": 1.5,
                    "message": "thumbnails 2/6 loaded (1 active, 3 pending)",
                    "unexpected": "dropped",
                },
                {
                    "id": "export:multi_compare:3",
                    "kind": "export",
                    "status": "running",
                    "progress": None,
                    "elapsed_s": None,
                    "message": "export in progress",
                },
            ],
        }
    if method == "jobs_cancel":
        return True, {
            "cancelled": True,
            "id": params.get("id"),
            "kind": "export",
        }
    return False, {"error": f"unknown method {method!r}", "hint": "check the protocol"}


class FakeControlServer:
    """A real unix-socket server speaking the frozen control protocol."""

    def __init__(self, path: Path, handler=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handler = handler or default_handler
        self.calls: list[tuple[str, dict]] = []
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._connections: list[socket.socket] = []

    def start(self) -> "FakeControlServer":
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(self.path))
        self._server.listen(8)
        self._server.settimeout(0.2)
        self._thread = threading.Thread(target=self._accept, daemon=True)
        self._thread.start()
        return self

    def die(self) -> None:
        """Simulate a crashed app: stop accepting and remove the socket node.

        A segfault does not run the app's teardown, so the socket node is left
        behind only until the kernel closes the fds — from the client's side the
        connection hits EOF *and* the node stops answering. Closing the listener
        from the serving thread also makes ``accept`` fail, which ends the
        accept loop; the current connection is closed by ``_serve`` when the
        handler returns ``CLOSE``.
        """
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        self.path.unlink(missing_ok=True)

    def stop(self, *, unlink: bool = True) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        for conn in list(self._connections):
            try:
                conn.close()
            except OSError:
                pass
        if self._server is not None:
            self._server.close()
            self._server = None
        if unlink:
            self.path.unlink(missing_ok=True)

    # -- internals ---------------------------------------------------------

    def _accept(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self._connections.append(conn)
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        conn.settimeout(0.2)
        buffer = b""
        try:
            while not self._stop.is_set():
                try:
                    chunk = conn.recv(65536)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if line.strip() and not self._answer(conn, line):
                        return
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _answer(self, conn: socket.socket, line: bytes) -> bool:
        request = json.loads(line.decode("utf-8"))
        method = str(request.get("method"))
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        self.calls.append((method, params))
        ok, payload = self.handler(method, params)
        if payload is CLOSE:
            return False  # transport fault: hang up without answering
        if payload is SILENT:
            return True  # accept the request, never answer (deadline expiry)
        response = {"id": request.get("id"), "ok": bool(ok)}
        if ok:
            response["result"] = payload
        else:
            response["error"] = (payload or {}).get("error", "failed")
            if (payload or {}).get("hint"):
                response["hint"] = payload["hint"]
        conn.sendall(json.dumps(response).encode("utf-8") + b"\n")
        return True


def _write_pointer(
    directory: Path,
    *,
    pid: int,
    socket_path: Path | None = None,
    uid: int | None = None,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    data = {"pid": pid, "started": "2026-10-17T00:00:00Z", "version": "0.1.0"}
    if socket_path is not None:
        data["socket"] = str(socket_path)
    if uid is not None:
        data["uid"] = uid
    pointer = directory / "instance.json"
    pointer.write_text(json.dumps(data), encoding="utf-8")
    return pointer


def _bare_socket(path: Path) -> Path:
    """Create a real socket node with **no** listener (refused connections)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    sock.close()
    return path


#: Real instance provided by the environment (supervisor-run end-to-end proof).
_REAL_SOCKET = os.environ.get(SOCKET_OVERRIDE_ENV)

#: A pid above the kernel's limit: always "not alive" in any namespace.
_UNALLOCATED_PID = 2**30


@pytest.fixture(autouse=True)
def _no_ambient_instance(monkeypatch, tmp_path):
    """Every test is hermetic: no ambient instance unless the test opts in.

    Discovery is pinned at an empty control dir, and the explicit socket
    override is removed, so a real app running on this machine can never leak
    into an assertion.
    """
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(tmp_path / "no-ambient-instance"))


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    """No ambient instance: explicit control dir pointing at an empty tmp dir."""
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(tmp_path / "run"))
    return tmp_path


# --- discovery --------------------------------------------------------------


def test_discover_socket_prefers_the_explicit_override(monkeypatch, tmp_path):
    socket_path = _bare_socket(tmp_path / "run" / "control.sock")
    monkeypatch.setenv(SOCKET_OVERRIDE_ENV, str(socket_path))
    monkeypatch.setenv(CONTROL_DIR_ENV, str(tmp_path / "other"))
    assert discover_socket() == socket_path


def test_discover_socket_override_pointing_nowhere_is_none(monkeypatch, tmp_path):
    monkeypatch.setenv(SOCKET_OVERRIDE_ENV, str(tmp_path / "missing.sock"))
    assert discover_socket() is None

    plain = tmp_path / "not-a-socket.txt"
    plain.write_text("hello", encoding="utf-8")
    monkeypatch.setenv(SOCKET_OVERRIDE_ENV, str(plain))
    assert discover_socket() is None


def test_discover_socket_reads_the_pointer_file(isolated_env):
    directory = isolated_env / "run"
    socket_path = FakeControlServer(directory / "custom.sock").start().path
    try:
        _write_pointer(directory, pid=os.getpid(), socket_path=socket_path)
        assert discover_socket() == socket_path
    finally:
        (directory / "custom.sock").unlink(missing_ok=True)


def test_discover_socket_falls_back_to_sibling_control_sock(isolated_env):
    directory = isolated_env / "run"
    socket_path = FakeControlServer(directory / CONTROL_SOCKET_NAME).start().path
    try:
        _write_pointer(directory, pid=os.getpid())  # no "socket" field
        assert discover_socket() == socket_path
    finally:
        (directory / CONTROL_SOCKET_NAME).unlink(missing_ok=True)


def test_discover_socket_ignores_a_stale_pointer(isolated_env):
    directory = isolated_env / "run"
    # A pid above the kernel's limit never exists, and nothing listens: stale.
    _write_pointer(directory, pid=_UNALLOCATED_PID)
    assert discover_socket() is None


def test_discover_socket_uses_a_pointer_whose_pid_is_unknown_here(isolated_env):
    """A pid that is not visible in this namespace is a hint, not a verdict.

    Flatpak apps run in their own PID namespace: the pointer's ``pid`` is
    sandbox-local, so the host ``kill(pid, 0)`` can say "dead" for a live app.
    The socket answering is the truth — discovery must return it.
    """
    directory = isolated_env / "run"
    socket_path = FakeControlServer(directory / CONTROL_SOCKET_NAME).start().path
    try:
        _write_pointer(directory, pid=_UNALLOCATED_PID, socket_path=socket_path)
        assert discover_socket() == socket_path
    finally:
        (directory / CONTROL_SOCKET_NAME).unlink(missing_ok=True)


def test_discover_socket_ignores_a_socket_nobody_listens_on(isolated_env):
    """A node with no listener is not live even when the pointer is present."""
    directory = isolated_env / "run"
    _bare_socket(directory / CONTROL_SOCKET_NAME)
    _write_pointer(directory, pid=_UNALLOCATED_PID)
    assert discover_socket() is None


def test_dead_pid_alone_never_declares_a_working_pointer_stale(isolated_env, monkeypatch):
    """Regression pin: pid liveness must not override a connectable socket.

    Flatpak sandboxes have their own PID namespace, so ``pid_alive`` can answer
    ``False`` for a live app. A refactor that restores the old pid-only rule
    (``if not pid_alive: stale``) fails this test.
    """
    directory = isolated_env / "run"
    socket_path = FakeControlServer(directory / CONTROL_SOCKET_NAME).start().path
    try:
        _write_pointer(directory, pid=os.getpid(), socket_path=socket_path)
        monkeypatch.setattr("app.live.pid_alive", lambda pid: False)
        assert discover_socket() == socket_path
    finally:
        (directory / CONTROL_SOCKET_NAME).unlink(missing_ok=True)


def test_discover_socket_uses_a_private_runtime_dir(monkeypatch, tmp_path):
    """A private ``$XDG_RUNTIME_DIR`` is the app's first choice, so it is ours.

    The mode is set explicitly: a bare ``mkdir()`` yields ``0755`` under the
    usual umask, which BOTH sides must now refuse (this test used to pin the
    opposite — discovery succeeding in a world-readable dir).
    """
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    os.chmod(runtime, 0o700)
    socket_path = FakeControlServer(runtime / "control.sock").start().path
    try:
        monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
        monkeypatch.delenv(CONTROL_DIR_ENV, raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
        assert discover_socket() == socket_path
    finally:
        (runtime / "control.sock").unlink(missing_ok=True)


def test_discover_socket_refuses_a_shared_runtime_dir(monkeypatch, tmp_path):
    """Symmetric with ``core.control.discovery._is_private_dir``.

    Falsification: with the old ``isdir + W_OK`` rule this returned the socket
    in the ``0755`` dir, while the app refused to publish there — the same
    machine, two different answers for "where is the control socket".
    """
    runtime = tmp_path / "shared"
    runtime.mkdir()
    os.chmod(runtime, 0o755)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(runtime / "control.sock"))
    listener.listen(4)
    try:
        monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
        monkeypatch.delenv(CONTROL_DIR_ENV, raising=False)
        data_home = tmp_path / "share"
        monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
        assert discover_socket() is None

        # And the fallback is the dir the app would publish in, not the shared one.
        assert control_dirs()[0] == data_home / "ImproveImgSLI" / "run"
    finally:
        listener.close()


def test_discover_socket_refuses_a_pointer_from_another_uid(isolated_env):
    """A pointer written by a different user is not a live instance.

    The pointer carries the owning ``uid`` (the app writes it); a client that
    ignored it would hand a foreign socket to the request layer, which the app
    then refuses at ``SO_PEERCRED`` — a confusing refusal instead of "absent".
    """
    directory = isolated_env / "run"
    socket_path = FakeControlServer(directory / CONTROL_SOCKET_NAME).start().path
    try:
        _write_pointer(
            directory,
            pid=os.getpid(),
            socket_path=socket_path,
            uid=os.getuid() + 1,
        )
        assert discover_socket() is None
    finally:
        (directory / CONTROL_SOCKET_NAME).unlink(missing_ok=True)


def test_discover_socket_accepts_a_pointer_without_a_uid(isolated_env):
    """Older pointers (no ``uid`` field) stay usable: absence is not a refusal."""
    directory = isolated_env / "run"
    socket_path = FakeControlServer(directory / CONTROL_SOCKET_NAME).start().path
    try:
        _write_pointer(directory, pid=os.getpid(), socket_path=socket_path)
        assert discover_socket() == socket_path
    finally:
        (directory / CONTROL_SOCKET_NAME).unlink(missing_ok=True)


def test_discover_socket_falls_back_to_the_app_data_run_dir(monkeypatch, tmp_path):
    data_home = tmp_path / "share"
    run_dir = data_home / "ImproveImgSLI" / "run"
    socket_path = FakeControlServer(run_dir / "control.sock").start().path
    try:
        monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
        monkeypatch.delenv(CONTROL_DIR_ENV, raising=False)
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
        assert discover_socket() == socket_path
    finally:
        (run_dir / "control.sock").unlink(missing_ok=True)


def test_discover_socket_returns_none_when_nothing_exists(isolated_env):
    assert discover_socket() is None


# --- client -----------------------------------------------------------------


def test_client_round_trip_and_id_matching(tmp_path):
    server = FakeControlServer(tmp_path / "control.sock").start()
    client = LiveClient(server.path)
    try:
        assert client.alive() is True
        assert client.call("get_state", {"path": "settings.theme"}) == {
            "path": "settings.theme",
            "state": "dark",
        }
        assert [method for method, _ in server.calls] == ["ping", "get_state"]
    finally:
        client.close()
        server.stop()


def test_client_surfaces_app_errors_as_live_error(tmp_path):
    def handler(method, params):
        return False, {"error": "bad key combo", "hint": "use ctrl+shift+p"}

    server = FakeControlServer(tmp_path / "control.sock", handler).start()
    client = LiveClient(server.path)
    try:
        with pytest.raises(LiveError) as excinfo:
            client.call("press_keys", {"keys": "nope"})
        assert excinfo.value.message == "bad key combo"
        assert excinfo.value.hint == "use ctrl+shift+p"
    finally:
        client.close()
        server.stop()


def test_client_missing_socket_is_unavailable(tmp_path):
    client = LiveClient(tmp_path / "absent.sock")
    with pytest.raises(LiveUnavailable):
        client.call("ping")
    assert client.alive() is False


def test_client_dead_socket_node_is_unavailable(tmp_path):
    client = LiveClient(_bare_socket(tmp_path / "dead.sock"))
    with pytest.raises(LiveUnavailable):
        client.call("ping")
    assert client.alive() is False


def test_client_connection_closed_by_the_app_is_unavailable(tmp_path):
    server = FakeControlServer(tmp_path / "control.sock").start()
    client = LiveClient(server.path)
    try:
        assert client.alive() is True
        server.stop(unlink=False)
        with pytest.raises(LiveUnavailable):
            client.call("ping")
    finally:
        client.close()
        server.stop()


class _SilentServer:
    """Accepts connections and never answers — for the client timeout path."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(self.path))
        self._server.listen(2)
        self._held: list[socket.socket] = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while True:
            try:
                conn, _ = self._server.accept()
            except OSError:
                return
            self._held.append(conn)

    def stop(self) -> None:
        self._server.close()
        for conn in self._held:
            try:
                conn.close()
            except OSError:
                pass
        self.path.unlink(missing_ok=True)


def test_client_timeout_is_unavailable(tmp_path):
    server = _SilentServer(tmp_path / "control.sock")
    client = LiveClient(server.path, timeout=0.3)
    try:
        with pytest.raises(LiveUnavailable):
            client.call("ping")
    finally:
        client.close()
        server.stop()


# --- mutation contract taxonomy (plan P2) -----------------------------------
#
# Reads may retry once on a transport timeout; edits never retry, and a
# mutation whose request was already on the wire must say the edit may have
# completed. The two transport failures stay distinguishable in the text:
# "not sent" (nothing left the process) vs "sent, no reply".


def test_client_reports_not_sent_before_the_request_leaves(tmp_path):
    client = LiveClient(tmp_path / "absent.sock", timeout=0.2)
    with pytest.raises(LiveUnavailable) as excinfo:
        client.call("ping")
    assert excinfo.value.sent is False
    assert excinfo.value.timeout is False
    assert excinfo.value.message.startswith(NOT_SENT)


def test_client_reports_sent_no_reply_when_the_deadline_expires(tmp_path):
    server = _SilentServer(tmp_path / "control.sock")
    client = LiveClient(server.path, timeout=0.2)
    try:
        with pytest.raises(LiveUnavailable) as excinfo:
            client.call("ping")
    finally:
        client.close()
        server.stop()
    assert excinfo.value.sent is True
    assert excinfo.value.timeout is True
    assert excinfo.value.message.startswith(SENT_NO_REPLY)
    assert "timed out waiting for the control socket" in excinfo.value.message


def test_read_retries_exactly_once_then_succeeds(tmp_path):
    """A read whose first wire attempt times out wins on the single retry."""
    state = {"list_actions": 0}

    def handler(method, params):
        if method == "list_actions":
            state["list_actions"] += 1
            if state["list_actions"] == 1:
                return True, SILENT  # first attempt never answers
        return default_handler(method, params)

    server = FakeControlServer(tmp_path / "control.sock", handler).start()
    adapter = LiveBackend(client=LiveClient(server.path, timeout=0.2))
    try:
        result = adapter.list_actions()
    finally:
        adapter.close()
        server.stop()
    assert result["source"] == "live"
    assert state["list_actions"] == 1 + READ_RETRY_BUDGET == 2


def test_read_retry_is_bounded_to_one_extra_attempt(tmp_path):
    """A read that times out twice gives up (and the caller falls back)."""
    state = {"list_actions": 0}

    def handler(method, params):
        if method == "list_actions":
            state["list_actions"] += 1
            return True, SILENT
        return default_handler(method, params)

    server = FakeControlServer(tmp_path / "control.sock", handler).start()
    adapter = LiveBackend(client=LiveClient(server.path, timeout=0.2))
    try:
        with pytest.raises(LiveUnavailable):
            adapter.list_actions()
    finally:
        adapter.close()
        server.stop()
    assert state["list_actions"] == 1 + READ_RETRY_BUDGET == 2


def test_mutation_never_retries_after_a_timeout(tmp_path):
    """A mutating tool's first attempt may time out — it is never re-sent."""
    state = {"run_action": 0}

    def handler(method, params):
        if method == "run_action":
            state["run_action"] += 1
            return True, SILENT
        return default_handler(method, params)

    server = FakeControlServer(tmp_path / "control.sock", handler).start()
    adapter = LiveBackend(client=LiveClient(server.path, timeout=0.2))
    try:
        with pytest.raises(LiveUnavailable) as excinfo:
            adapter.run_action(action_id="platform.settings")
    finally:
        adapter.close()
        server.stop()
    assert state["run_action"] == 1, "an edit must never be auto-retried"
    assert excinfo.value.sent is True and excinfo.value.timeout is True
    assert "timed out waiting for the control socket" in excinfo.value.message


def test_list_actions_enabled_and_reason_degrade_when_omitted(tmp_path):
    """A row missing the two keys reads as enabled with no reason — no crash."""

    def handler(method, params):
        if method == "list_actions":
            return True, {"count": 1, "actions": [{"action_id": "a.b", "label": "B"}]}
        return default_handler(method, params)

    server = FakeControlServer(tmp_path / "control.sock", handler).start()
    adapter = LiveBackend(client=LiveClient(server.path))
    try:
        row = adapter.list_actions()["actions"][0]
    finally:
        adapter.close()
        server.stop()
    assert row["enabled"] is True
    assert row["reason"] is None


# --- adapter: every tool proxied --------------------------------------------


_ELEMENTS_LIVE_RESULT = {
    "count": 2,
    "total": 2,
    "window_count": 1,
    "elements": [
        {
            "id": "main.settings.btn",
            "role": "button",
            "label": "Settings",
            "rect": [1, 2, 3, 4],
            "screen_rect": [10, 20, 30, 40],
            "window": "main",
            "owner_tab": None,
            "action_id": "platform.settings",
            "enabled": True,
            "visible": True,
            "properties": {},
        },
        {
            "id": "gallery.card.menu.row1",
            "role": "menu-row",
            "label": "Open",
            "rect": [5, 6, 7, 8],
            "screen_rect": [50, 60, 70, 80],
            "window": "popup",
            "owner_tab": "image_gallery",
            "action_id": None,
            "enabled": True,
            "visible": True,
            "properties": {},
        },
    ],
    "source": "live",
}

_PROXY_CASES = [
    (
        "list_actions",
        {"query": "settings", "owner_tab": "image_compare"},
        "list_actions",
        {"query": "settings", "owner_tab": "image_compare"},
        {
            "count": 2,
            "actions": [
                {
                    "action_id": "platform.settings",
                    "label": "Settings",
                    "owner_tab": None,
                    "topic": "platform",
                    "shortcut": "Ctrl+,",
                    "enabled": True,
                    "reason": None,
                },
                {
                    "action_id": "image_compare.zoom_fit",
                    "label": "Fit",
                    "owner_tab": "image_compare",
                    "topic": "view",
                    "shortcut": None,
                    "enabled": False,
                    "reason": "no document is open",
                },
            ],
            "source": "live",
        },
    ),
    (
        "list_sessions",
        {},
        "list_sessions",
        {},
        {
            "count": 1,
            "sessions": [
                {
                    "id": "s1",
                    "session_type": "image_compare",
                    "title": "Image Compare",
                    "active": True,
                }
            ],
            "source": "live",
        },
    ),
    (
        "get_state",
        {"path": "settings.theme"},
        "get_state",
        {"path": "settings.theme"},
        {"path": "settings.theme", "state": "dark", "source": "live"},
    ),
    (
        "read_log",
        {"n": 50, "level": "WARNING"},
        "read_log",
        {"n": 50, "level": "WARNING"},
        {
            "path": "/live/log.txt",
            "total_lines": 5,
            "returned": 2,
            "lines": [
                {"n": 4, "level": "INFO", "text": "line four"},
                {"n": 5, "level": None, "text": "line five"},
            ],
            "source": "live",
        },
    ),
    (
        "query_trace",
        {"filter": "render", "n": 10},
        "query_trace",
        {"filter": "render", "n": 10},
        {
            "path": "/live/trace.jsonl",
            "total_records": 3,
            "returned": 1,
            "records": [{"kind": "render", "trace_id": "t1"}],
            "source": "live",
        },
    ),
    (
        "dump_ui_layout",
        {"tab": "image_compare"},
        "dump_ui_layout",
        {"tab": "image_compare"},
        {
            "path": "/live/ui.json",
            "tab": "image_compare",
            "windows": 2,
            "node_count": 7,
            "source": "live",
        },
    ),
    (
        "list_surfaces",
        {},
        "list_surfaces",
        {},
        {
            "count": 1,
            "surfaces": [
                {
                    "name": "settings",
                    "description": "Settings dialog",
                    "isolated": False,
                    "live": False,
                    "capturable": False,
                }
            ],
            "source": "live",
        },
    ),
    (
        "open_tab",
        {"tab": "multi_compare"},
        "open_tab",
        {"tab": "multi_compare"},
        {"ran": True, "tab": "multi_compare", "live": True, "source": "live"},
    ),
    (
        "run_action",
        {"action_id": "platform.settings", "tab": "image_compare"},
        "run_action",
        {"action_id": "platform.settings", "tab": "image_compare"},
        {
            "ran": True,
            "action_id": "platform.settings",
            "tab": "image_compare",
            "live": True,
            "source": "live",
        },
    ),
    (
        "open_folder",
        {"path": "/tmp/folder"},
        "open_folder",
        {"path": "/tmp/folder"},
        {"ran": True, "path": "/tmp/folder", "routed": True, "live": True, "source": "live"},
    ),
    (
        "open_folder",
        {"path": "/tmp/folder", "slot": 2},
        "open_folder",
        {"path": "/tmp/folder", "slot": 2},
        {"ran": True, "path": "/tmp/folder", "routed": True, "live": True, "source": "live"},
    ),
    (
        "open_folder",
        {"path": "/tmp/folder", "side": "right"},
        "open_folder",
        {"path": "/tmp/folder", "side": "right"},
        {"ran": True, "path": "/tmp/folder", "routed": True, "live": True, "source": "live"},
    ),
    (
        "open_file",
        {"path": "/img/a.png"},
        "open_file",
        {"path": "/img/a.png"},
        {
            "opened": True,
            "path": "/img/a.png",
            "tab": "image_compare",
            "count": 1,
            "source": "live",
        },
    ),
    (
        "open_file",
        {"path": "/img/a.png", "tab": "image_compare", "slot": 2},
        "open_file",
        {"path": "/img/a.png", "tab": "image_compare", "slot": 2},
        {
            "opened": True,
            "path": "/img/a.png",
            "tab": "image_compare",
            "count": 1,
            "source": "live",
        },
    ),
    (
        "open_file",
        {"path": "/img/a.png", "tab": "multi_compare", "side": "right"},
        "open_file",
        {"path": "/img/a.png", "tab": "multi_compare", "side": "right"},
        {
            "opened": True,
            "path": "/img/a.png",
            "tab": "multi_compare",
            "count": 1,
            "source": "live",
        },
    ),
    (
        "set_theme",
        {"theme": "light"},
        "set_theme",
        {"theme": "light"},
        {"theme": "light", "persisted": True, "applies_on": "now", "live": True, "source": "live"},
    ),
    (
        "set_language",
        {"language": "ru"},
        "set_language",
        {"language": "ru"},
        {
            "language": "ru",
            "persisted": True,
            "applies_on": "now",
            "live": True,
            "source": "live",
        },
    ),
    (
        "capture_surface",
        {"surface": "settings", "theme": "light"},
        "capture_live",
        {"what": "settings"},
        {
            "surface": "settings",
            "what": "settings",
            "path": "/live/settings.png",
            "method": "grabWindow",
            "size": [1280, 800],
            "rhi_layers": 1,
            "theme": None,
            "live": True,
            "source": "live",
            "options_applied": [],
            "unavailable": [],
        },
    ),
    (
        "capture_surface",
        {},
        "capture_live",
        {},
        {
            "surface": "",
            "what": "MainWindow",
            "path": "/live/MainWindow.png",
            "method": "grabWindow",
            "size": [1280, 800],
            "rhi_layers": 1,
            "theme": None,
            "live": True,
            "source": "live",
            "options_applied": [],
            "unavailable": [],
        },
    ),
    (
        "press_keys",
        {"keys": "ctrl+shift+p"},
        "press_keys",
        {"keys": "ctrl+shift+p"},
        {
            "pressed": ["ctrl+shift+p"],
            "count": 1,
            "target": "QMainWindow",
            "activated": True,
            "focus_is_ours": True,
            "source": "live",
        },
    ),
    (
        "ui_elements",
        {},
        "ui_elements",
        {},
        _ELEMENTS_LIVE_RESULT,
    ),
    (
        "ui_elements",
        {"scope": "image_gallery", "include_disabled": True},
        "ui_elements",
        {"scope": "image_gallery", "include_disabled": True},
        _ELEMENTS_LIVE_RESULT,
    ),
    (
        "ui_click",
        {"id": "main.settings.btn"},
        "ui_click",
        {"id": "main.settings.btn"},
        {
            "clicked": True,
            "id": "main.settings.btn",
            "rect": [1, 2, 3, 4],
            "screen_rect": [10, 20, 30, 40],
            "target": "QPushButton",
            "surface": "main",
            "source": "live",
        },
    ),
    (
        "ui_click",
        {"id": "gallery.card.menu.row1", "button": "right", "count": 2},
        "ui_click",
        {"id": "gallery.card.menu.row1", "button": "right", "count": 2},
        {
            "clicked": True,
            "id": "gallery.card.menu.row1",
            "rect": [1, 2, 3, 4],
            "screen_rect": [10, 20, 30, 40],
            "target": "QPushButton",
            "surface": "main",
            "source": "live",
        },
    ),
    (
        "ui_hover",
        {"id": "main.settings.btn"},
        "ui_hover",
        {"id": "main.settings.btn"},
        {
            "hovered": True,
            "id": "main.settings.btn",
            "rect": [1, 2, 3, 4],
            "target": "QPushButton",
            "source": "live",
        },
    ),
    (
        "ui_focus",
        {"id": "main.settings.btn"},
        "ui_focus",
        {"id": "main.settings.btn"},
        {
            "focused": True,
            "id": "main.settings.btn",
            "rect": [1, 2, 3, 4],
            "target": "QLineEdit",
            "focus_widget": "QLineEdit",
            "source": "live",
        },
    ),
    (
        "jobs_list",
        {},
        "jobs_list",
        {},
        {
            "count": 2,
            "jobs": [
                {
                    "id": "pool:image_gallery",
                    "kind": "gallery_pool",
                    "status": "running",
                    "progress": {"done": 2, "total": 6},
                    "elapsed_s": 1.5,
                    "message": "thumbnails 2/6 loaded (1 active, 3 pending)",
                },
                {
                    "id": "export:multi_compare:3",
                    "kind": "export",
                    "status": "running",
                    "progress": None,
                    "elapsed_s": None,
                    "message": "export in progress",
                },
            ],
            "source": "live",
        },
    ),
    (
        "jobs_cancel",
        {"id": "export:multi_compare:3"},
        "jobs_cancel",
        {"id": "export:multi_compare:3"},
        {
            "cancelled": True,
            "id": "export:multi_compare:3",
            "kind": "export",
            "source": "live",
        },
    ),
]


def _wire_calls(server: FakeControlServer) -> list[tuple[str, dict]]:
    """Recorded calls minus the attach probe (``alive`` pings first)."""
    return [call for call in server.calls if call[0] != "ping"]


@pytest.mark.parametrize(
    "proxy,args,wire_method,wire_params,expected",
    _PROXY_CASES,
    ids=[case[0] for case in _PROXY_CASES],
)
def test_every_tool_proxies_and_normalises(tmp_path, proxy, args, wire_method, wire_params, expected):
    server = FakeControlServer(tmp_path / "control.sock").start()
    adapter = LiveBackend(client=LiveClient(server.path))
    try:
        result = getattr(adapter, proxy)(**args)
    finally:
        adapter.close()
        server.stop()
    assert result == expected
    assert _wire_calls(server) == [(wire_method, wire_params)]


def test_capture_without_provenance_reports_nulls_not_inventions(tmp_path):
    """A minimal app answer keeps the shape but never invents method/size/rhi_layers."""

    def handler(method: str, params: dict):
        if method == "ping":
            return True, {}
        if method == "capture_live":
            return True, {"path": "/live/legacy.png"}
        return True, {}

    server = FakeControlServer(tmp_path / "control.sock", handler=handler).start()
    adapter = LiveBackend(client=LiveClient(server.path))
    try:
        result = adapter.capture_surface()
    finally:
        adapter.close()
        server.stop()
    assert result == {
        "surface": "",
        "what": "",
        "path": "/live/legacy.png",
        "method": None,
        "size": None,
        "rhi_layers": None,
        "theme": None,
        "live": True,
        "source": "live",
        "options_applied": [],
        "unavailable": ["what", "method", "size", "rhi_layers"],
    }
    assert _wire_calls(server) == [("capture_live", {})]


def test_adapter_omits_falsy_params_and_keeps_defaults(tmp_path):
    server = FakeControlServer(tmp_path / "control.sock").start()
    adapter = LiveBackend(client=LiveClient(server.path))
    try:
        adapter.list_actions()
        adapter.get_state()
        adapter.read_log()
    finally:
        adapter.close()
        server.stop()
    assert _wire_calls(server) == [
        ("list_actions", {}),
        ("get_state", {}),
        ("read_log", {"n": 200}),
    ]


def test_ui_click_omits_button_and_count_unless_given(tmp_path):
    """``button``/``count`` are sent only when provided (falsy ⇒ omitted)."""
    server = FakeControlServer(tmp_path / "control.sock").start()
    adapter = LiveBackend(client=LiveClient(server.path))
    try:
        adapter.ui_click(id="main.settings.btn")
        adapter.ui_click(id="main.settings.btn", button="right", count=2)
    finally:
        adapter.close()
        server.stop()
    assert _wire_calls(server) == [
        ("ui_click", {"id": "main.settings.btn"}),
        ("ui_click", {"id": "main.settings.btn", "button": "right", "count": 2}),
    ]


def test_ui_elements_omits_optional_params_unless_given(tmp_path):
    server = FakeControlServer(tmp_path / "control.sock").start()
    adapter = LiveBackend(client=LiveClient(server.path))
    try:
        adapter.ui_elements()
    finally:
        adapter.close()
        server.stop()
    assert _wire_calls(server) == [("ui_elements", {})]


def test_ui_elements_forwards_filters_and_keeps_the_properties_bag(tmp_path):
    """Filters travel to the app; the row's properties bag survives normalisation.

    An older app that emits no properties bag still yields ``properties: {}``
    so the advertised element shape never changes under a client.
    """

    def handler(method, params):
        if method == "ui_elements":
            row = {
                "id": "main.gallery.card0",
                "role": "card",
                "label": "card_0.png",
                "rect": [1, 2, 3, 4],
                "screen_rect": [10, 20, 30, 40],
                "window": "main",
                "owner_tab": "image_gallery",
                "action_id": None,
                "enabled": True,
                "visible": True,
                "unexpected": "dropped",
            }
            if params.get("properties") is None:
                return True, {"count": 1, "window_count": 1, "elements": [row]}
            return True, {
                "count": 1,
                "window_count": 1,
                "total": 7,
                "elements": [
                    {**row, "properties": {"gallery_path": "/gallery/card_0.png"}}
                ],
            }
        return default_handler(method, params)

    server = FakeControlServer(tmp_path / "control.sock", handler).start()
    adapter = LiveBackend(client=LiveClient(server.path))
    try:
        unfiltered = adapter.ui_elements()
        narrowed = adapter.ui_elements(
            role="card",
            label="card_0",
            properties={"gallery_path": "/gallery/card_0.png"},
            limit=5,
        )
    finally:
        adapter.close()
        server.stop()

    assert unfiltered["elements"][0]["properties"] == {}, "shape is stable"
    row = narrowed["elements"][0]
    assert row["properties"] == {"gallery_path": "/gallery/card_0.png"}
    assert "unexpected" not in row
    assert narrowed["total"] == 7
    assert _wire_calls(server) == [
        ("ui_elements", {}),
        (
            "ui_elements",
            {
                "role": "card",
                "label": "card_0",
                "properties": {"gallery_path": "/gallery/card_0.png"},
                "limit": 5,
            },
        ),
    ]


def test_list_surfaces_live_keeps_live_and_capturable(tmp_path):
    """The app computes ``live``/``capturable``; the proxy must not drop them.

    ``capturable`` is the distinction a screenshot client needs: a registered
    tab kind is drivable (``live: true``) but only an OPEN page can be grabbed.
    """

    def handler(method, params):
        if method == "list_surfaces":
            return True, {
                "count": 2,
                "surfaces": [
                    {
                        "name": "image_gallery",
                        "description": "Image Gallery",
                        "isolated": False,
                        "live": True,
                        "capturable": True,
                    },
                    {
                        "name": "settings",
                        "description": "Settings",
                        "isolated": True,
                        "live": False,
                        "capturable": False,
                    },
                ],
            }
        return default_handler(method, params)

    server = FakeControlServer(tmp_path / "control.sock", handler).start()
    adapter = LiveBackend(client=LiveClient(server.path))
    try:
        result = adapter.list_surfaces()
    finally:
        adapter.close()
        server.stop()

    rows = {row["name"]: row for row in result["surfaces"]}
    assert rows["image_gallery"]["live"] is True
    assert rows["image_gallery"]["capturable"] is True
    assert rows["settings"]["live"] is False
    assert rows["settings"]["capturable"] is False



def test_read_log_live_normalises_when_the_app_omits_the_path(tmp_path):
    """The app's live ``read_log`` ring has no file path — normalise honestly.

    The canned default handler is more generous than the real app: the in-app
    log ring returns only ``total_lines``/``returned``/``lines`` (no ``path``).
    The adapter must still return the Phase-1 shape, with an empty path rather
    than inventing one.
    """

    def handler(method, params):
        if method == "read_log":
            return True, {
                "total_lines": 3,
                "returned": 1,
                "lines": [{"n": 3, "level": "ERROR", "text": "boom"}],
            }
        return default_handler(method, params)

    server = FakeControlServer(tmp_path / "control.sock", handler).start()
    adapter = LiveBackend(client=LiveClient(server.path))
    try:
        result = adapter.read_log(n=1, level="ERROR")
    finally:
        adapter.close()
        server.stop()
    assert result == {
        "path": "",
        "total_lines": 3,
        "returned": 1,
        "lines": [{"n": 3, "level": "ERROR", "text": "boom"}],
        "source": "live",
    }


# --- adapter: attach lifecycle ----------------------------------------------


def test_try_attach_never_raises_and_finds_the_control_dir(tmp_path, monkeypatch):
    directory = tmp_path / "run"
    socket_path = FakeControlServer(directory / "control.sock").start().path
    _write_pointer(directory, pid=os.getpid(), socket_path=socket_path)
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(directory))
    adapter = LiveBackend()
    try:
        client = adapter.try_attach()
        assert client is not None and client.alive()
        assert adapter.attached is True
    finally:
        adapter.close()
        socket_path.unlink(missing_ok=True)


def test_try_attach_attaches_when_the_pointer_pid_is_not_visible_here(tmp_path, monkeypatch):
    """A pid that this namespace cannot verify must not block a live attach.

    Simulates a host-side server looking at a Flatpak app's pointer: the pid is
    sandbox-local (here an unallocated pid, so ``pid_alive`` is ``False``) but
    the socket exists and answers — the backend must attach and answer live,
    not report "no live instance".
    """
    directory = tmp_path / "run"
    server = FakeControlServer(directory / CONTROL_SOCKET_NAME).start()
    _write_pointer(directory, pid=_UNALLOCATED_PID, socket_path=server.path)
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(directory))
    adapter = LiveBackend(retry_cooldown_s=0.0)
    try:
        client = adapter.try_attach()
        assert client is not None and client.alive()
        assert adapter.list_actions()["source"] == "live"
    finally:
        adapter.close()
        server.stop()


def test_try_attach_is_none_for_garbage_paths(tmp_path, monkeypatch):
    plain = tmp_path / "plain.txt"
    plain.write_text("x", encoding="utf-8")
    monkeypatch.setenv(SOCKET_OVERRIDE_ENV, str(plain))
    assert LiveBackend().try_attach() is None

    monkeypatch.setenv(SOCKET_OVERRIDE_ENV, str(_bare_socket(tmp_path / "dead.sock")))
    assert LiveBackend(socket_path=tmp_path / "dead.sock").try_attach() is None


def test_adapter_cools_down_after_a_transport_failure(tmp_path, monkeypatch):
    directory = tmp_path / "run"
    socket_path = FakeControlServer(directory / CONTROL_SOCKET_NAME).start().path
    _write_pointer(directory, pid=os.getpid(), socket_path=socket_path)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(directory))
    adapter = LiveBackend(retry_cooldown_s=30.0)
    reattaching = LiveBackend(socket_path=socket_path, retry_cooldown_s=0.0)
    try:
        assert adapter.client_if_alive() is not None
        adapter.note_failure()
        assert adapter.attached is False
        assert adapter.client_if_alive() is None, "cooldown must park re-attaching"

        # A zero cooldown re-attaches immediately (what the tests above use).
        assert reattaching.client_if_alive() is not None
    finally:
        adapter.close()
        reattaching.close()
        socket_path.unlink(missing_ok=True)


def test_live_unavailable_is_never_leaked_by_try_attach(tmp_path, monkeypatch):
    monkeypatch.setenv(SOCKET_OVERRIDE_ENV, str(tmp_path / "absent.sock"))
    adapter = LiveBackend()
    assert adapter.client_if_alive() is None
    assert adapter.try_attach() is None


# --- backend: live-first, fallback on transport faults ----------------------


def _snapshot() -> dict:
    return {
        "actions": [
            {
                "action_id": "platform.settings",
                "label": "Settings",
                "owner_tab": None,
                "topic": "platform",
                "shortcut": "Ctrl+,",
                "enabled": True,
                "reason": None,
            },
            {
                "action_id": "platform.quit_app",
                "label": "Quit",
                "owner_tab": None,
                "topic": "platform",
                "shortcut": None,
                "enabled": False,
                "reason": "a modal dialog is open",
            },
        ],
        "state": {"settings": {"theme": "dark", "current_language": "en"}},
        "sessions": [],
        "theme": "dark",
        "language": "en",
        "ui_scale_factor": 1.0,
    }


@pytest.fixture
def live_wired(tmp_path, monkeypatch):
    """A backend whose discovery finds a fake live instance in a tmp dir."""
    directory = tmp_path / "run"
    server = FakeControlServer(directory / "control.sock").start()
    _write_pointer(directory, pid=os.getpid(), socket_path=server.path)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(directory))
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)

    calls: dict[str, list] = {"tabs": [], "launches": [], "settings": []}

    def runner(tab):
        calls["tabs"].append(tab)
        return _snapshot()

    def launcher(args):
        calls["launches"].append(args)
        return os.getpid()

    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        snapshot_runner=runner,
        launcher=launcher,
        settings_writer=lambda key, value: calls["settings"].append((key, value)),
        live_backend=LiveBackend(retry_cooldown_s=0.0),
    )
    yield MCPProtocol(backend), backend, calls, server
    server.stop()


def _call(protocol: MCPProtocol, name: str, arguments: dict | None = None):
    response = protocol.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments or {}}}
    )
    assert "error" not in response, response.get("error")
    return response["result"]


def test_backend_answers_from_the_live_instance(live_wired):
    protocol, _backend, calls, _server = live_wired
    result = _call(protocol, "list_actions")
    assert result["isError"] is False
    assert result["structuredContent"]["source"] == "live"
    assert calls["tabs"] == [], "a live answer must not boot a headless snapshot"


def test_read_log_serves_the_preserved_copy_while_live(live_wired, tmp_path):
    _protocol, backend, _calls, _server = live_wired
    preserved = backend.artifacts_dir / PRESERVED_LOG_NAME
    preserved.parent.mkdir(parents=True, exist_ok=True)
    preserved.write_text("old live line\n", encoding="utf-8")

    result = backend.read_log(n=10)
    assert result["path"] == str(preserved)
    assert result["lines"] == [{"n": 1, "level": None, "text": "old live line"}]
    assert result["source"] == "fallback"


def test_backend_falls_back_when_the_instance_disappears(live_wired):
    protocol, _backend, calls, server = live_wired
    assert _call(protocol, "list_actions")["structuredContent"]["source"] == "live"

    server.stop()  # unlinks the socket: nobody listens any more
    result = _call(protocol, "list_actions")
    assert result["isError"] is False
    assert result["structuredContent"]["source"] == "fallback"
    assert calls["tabs"] == [None], "the fallback must boot exactly one snapshot"


def test_backend_falls_back_when_the_socket_drops_mid_call(tmp_path, monkeypatch):
    directory = tmp_path / "run"

    def handler(method, params):
        if method == "list_actions":
            return True, CLOSE
        return default_handler(method, params)

    server = FakeControlServer(directory / "control.sock", handler).start()
    _write_pointer(directory, pid=os.getpid(), socket_path=server.path)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(directory))
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)

    calls: list = []
    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        snapshot_runner=lambda tab: calls.append(tab) or _snapshot(),
        live_backend=LiveBackend(retry_cooldown_s=0.0),
    )
    protocol = MCPProtocol(backend)
    try:
        result = _call(protocol, "list_actions")
        assert result["structuredContent"]["source"] == "fallback"
        assert calls == [None]
    finally:
        server.stop()


def test_backend_surfaces_live_errors_instead_of_falling_back(tmp_path, monkeypatch):
    directory = tmp_path / "run"

    def handler(method, params):
        if method == "run_action":
            return False, {"error": "action platform.quit_app is blocked", "hint": "confirm first"}
        return default_handler(method, params)

    server = FakeControlServer(directory / "control.sock", handler).start()
    _write_pointer(directory, pid=os.getpid(), socket_path=server.path)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(directory))
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)

    calls: list = []
    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        snapshot_runner=lambda tab: calls.append(tab) or _snapshot(),
        live_backend=LiveBackend(retry_cooldown_s=0.0),
    )
    protocol = MCPProtocol(backend)
    try:
        result = _call(protocol, "run_action", {"action_id": "platform.quit_app"})
        assert result["isError"] is True
        assert "is blocked" in result["content"][0]["text"]
        assert "confirm first" in result["content"][0]["text"]
        assert calls == [], "an app-reported error is not a fallback trigger"
    finally:
        server.stop()


def test_press_keys_round_trips_through_the_backend(live_wired):
    protocol, _backend, _calls, server = live_wired
    result = _call(protocol, "press_keys", {"keys": "ctrl+shift+p"})
    assert result["isError"] is False
    assert result["structuredContent"] == {
        "pressed": ["ctrl+shift+p"],
        "count": 1,
        "target": "QMainWindow",
        "activated": True,
        "focus_is_ours": True,
        "source": "live",
    }
    assert ("press_keys", {"keys": "ctrl+shift+p"}) in server.calls


def test_press_keys_reports_activation_and_focus_ownership_unchanged(tmp_path, monkeypatch):
    """The two honest fields must survive the MCP path, including ``false``.

    The app makes the window OS-active before typing and answers ``activated``
    (this call had to bring it forward) and ``focus_is_ours`` (the key went to
    the window holding OS focus). Normalising them to anything but what the app
    said hides exactly the case that matters: a sweep reading ``ok`` for keys
    the window system dropped (complaint mcp-c-015).
    """

    def handler(method, params):
        if method == "press_keys":
            # Already active, and the key went to the window that holds focus.
            return True, {
                "pressed": ["ctrl+p"],
                "count": 1,
                "target": "QCanvasView",
                "activated": False,
                "focus_is_ours": True,
            }
        return default_handler(method, params)

    directory = tmp_path / "run"
    server = FakeControlServer(directory / CONTROL_SOCKET_NAME, handler).start()
    _write_pointer(directory, pid=os.getpid(), socket_path=server.path)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(directory))
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        live_backend=LiveBackend(retry_cooldown_s=0.0),
    )
    protocol = MCPProtocol(backend)
    try:
        result = _call(protocol, "press_keys", {"keys": "ctrl+p", "target": "main.canvas"})
        assert result["isError"] is False
        structured = result["structuredContent"]
        assert structured["activated"] is False
        assert structured["focus_is_ours"] is True
        assert structured["pressed"] == ["ctrl+p"]
        assert structured["source"] == "live"
    finally:
        server.stop()


def _schema_accepts(schema: dict, value: object) -> bool:
    """Minimal JSON-Schema check for the keywords the catalog uses.

    Deliberately small: this pins *which shapes a strict host may see*, it is
    not a general validator. ``anyOf`` is the one non-trivial keyword — a live
    tool's declared output is its normal result OR the transport's early
    answer. A keyword this helper does not understand fails loudly instead of
    passing silently, so the checker cannot become a no-op.
    """
    if not isinstance(schema, dict) or not schema:
        return True
    branches = schema.get("anyOf")
    if branches is not None and not any(
        _schema_accepts(branch, value) for branch in branches
    ):
        return False
    if "const" in schema and value != schema["const"]:
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    expected = schema.get("type")
    if expected is not None:
        options = list(expected) if isinstance(expected, list) else [expected]
        checks = {
            "object": lambda item: isinstance(item, dict),
            "array": lambda item: isinstance(item, list),
            "string": lambda item: isinstance(item, str),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
            "boolean": lambda item: isinstance(item, bool),
            "null": lambda item: item is None,
        }
        unknown = set(options) - set(checks)
        assert not unknown, f"schema type(s) this helper does not understand: {unknown}"
        if not any(checks[option](value) for option in options):
            return False
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        for name in schema.get("required") or ():
            if name not in value:
                return False
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            return False
        for name, sub in properties.items():
            if name in value and not _schema_accepts(sub, value[name]):
                return False
    if isinstance(value, list) and "items" in schema:
        return all(_schema_accepts(schema["items"], item) for item in value)
    return True


def test_press_keys_schema_accepts_the_normal_and_the_early_answer():
    """A strict host must not flag either frame the transport can put on the wire.

    The control channel answers on its own behalf when a handler overruns its
    budget (``server._arm_early_answer``): ``ok: true`` with ``accepted /
    answered_early / still_running / modal_open / method / budget_ms`` and none
    of the tool's own fields — a chord that opened a modal dialog is the case.
    A schema that declares only the normal result would report a mismatch for a
    call that worked.
    """
    tool = next(entry for entry in catalog.TOOLS if entry["name"] == "press_keys")
    schema = tool["outputSchema"]

    normal = {
        "pressed": ["ctrl+shift+p"],
        "count": 1,
        "target": "QMainWindow",
        "activated": True,
        "focus_is_ours": True,
        "source": "live",
    }
    early = {
        "accepted": True,
        "answered_early": True,
        "still_running": True,
        "modal_open": True,
        "method": "press_keys",
        "budget_ms": 2000,
    }

    assert _schema_accepts(schema, normal) is True
    assert _schema_accepts(schema, early) is True
    # Falsification: the checker really rejects frames the schema does not declare.
    assert _schema_accepts(schema, {**normal, "invented": 1}) is False
    assert _schema_accepts(schema, {"accepted": True}) is False


def test_element_tools_round_trip_through_the_backend(live_wired):
    protocol, _backend, _calls, server = live_wired
    elements = _call(protocol, "ui_elements", {"scope": "main"})
    assert elements["isError"] is False
    assert elements["structuredContent"]["count"] == 2
    assert elements["structuredContent"]["source"] == "live"

    clicked = _call(protocol, "ui_click", {"id": "main.settings.btn", "button": "right"})
    assert clicked["structuredContent"]["clicked"] is True
    assert clicked["structuredContent"]["source"] == "live"

    hovered = _call(protocol, "ui_hover", {"id": "main.settings.btn"})
    assert hovered["structuredContent"]["hovered"] is True

    focused = _call(protocol, "ui_focus", {"id": "main.settings.btn"})
    assert focused["structuredContent"]["focus_widget"] == "QLineEdit"

    assert ("ui_elements", {"scope": "main"}) in server.calls
    assert ("ui_click", {"id": "main.settings.btn", "button": "right"}) in server.calls
    assert ("ui_hover", {"id": "main.settings.btn"}) in server.calls
    assert ("ui_focus", {"id": "main.settings.btn"}) in server.calls


def test_ui_click_transport_fault_names_the_request_and_the_broken_channel(
    tmp_path, monkeypatch
):
    """A mid-``ui_click`` drop names the request instead of "no live instance".

    This fake server keeps *listening* (only the one connection is dropped), so
    the honest verdict here is "the channel broke, the process still answers",
    and the request that was in flight is named. The death wording is pinned by
    the ``press_keys`` test, where the socket node goes away too.
    """

    def handler(method, params):
        if method == "ui_click":
            return True, CLOSE  # hang up without answering
        return default_handler(method, params)

    directory = tmp_path / "run"
    server = FakeControlServer(directory / CONTROL_SOCKET_NAME, handler).start()
    _write_pointer(directory, pid=os.getpid(), socket_path=server.path)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(directory))
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        live_backend=LiveBackend(retry_cooldown_s=0.0),
    )
    protocol = MCPProtocol(backend)
    try:
        result = _call(protocol, "ui_click", {"id": "main.settings.btn"})
        assert result["isError"] is True
        text = result["content"][0]["text"]
        assert "ui_click" in text
        assert "id='main.settings.btn'" in text
        assert "still answers" in text
        assert "the app's process is still running" in text
        assert "no live instance" not in text
        assert "element targeting needs a running app" not in text
    finally:
        server.stop()


def test_ui_focus_live_app_error_keeps_the_apps_hint(tmp_path, monkeypatch):
    """An app-reported element failure is surfaced with the app's own hint."""

    def handler(method, params):
        if method == "ui_focus":
            return False, {"error": "no element id 'ghost'", "hint": "did you mean: main.settings.btn?"}
        return default_handler(method, params)

    directory = tmp_path / "run"
    server = FakeControlServer(directory / CONTROL_SOCKET_NAME, handler).start()
    _write_pointer(directory, pid=os.getpid(), socket_path=server.path)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(directory))
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        live_backend=LiveBackend(retry_cooldown_s=0.0),
    )
    protocol = MCPProtocol(backend)
    try:
        result = _call(protocol, "ui_focus", {"id": "ghost"})
        assert result["isError"] is True
        text = result["content"][0]["text"]
        assert "no element id 'ghost'" in text
        assert "did you mean: main.settings.btn?" in text
    finally:
        server.stop()


def test_backend_falls_back_when_the_socket_refuses(tmp_path, monkeypatch):
    """A socket node nobody listens on (ECONNREFUSED) is "no live instance".

    Refusal must send the call down the fallback path — never crash and never
    surface as a user-visible error.
    """
    directory = tmp_path / "run"
    directory.mkdir(parents=True)
    socket_path = _bare_socket(directory / CONTROL_SOCKET_NAME)  # bound, then closed
    _write_pointer(directory, pid=os.getpid(), socket_path=socket_path)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(directory))
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)

    calls: list = []
    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        snapshot_runner=lambda tab: calls.append(tab) or _snapshot(),
        live_backend=LiveBackend(retry_cooldown_s=0.0),
    )
    protocol = MCPProtocol(backend)
    result = _call(protocol, "list_actions")
    assert result["isError"] is False
    assert result["structuredContent"]["source"] == "fallback"
    assert calls == [None]


def test_press_keys_mid_call_death_reports_the_signal_and_last_request(tmp_path, monkeypatch):
    """A live instance that dies mid-call must report *the death*, not "no live instance".

    The app's control socket closing under a request is the only witness a
    sibling process has of a crash: the request was sent and the process is
    gone. Pinned before this test: the backend answered "no live instance;
    keyboard input needs a running app" — true of a missing app, a lie about a
    dead one, and silent about the request that was on the wire.

    The fake server drops the connection *and* removes its socket node (what a
    crashed app leaves behind) and the pointer pid is unallocated, so the report
    has a process to describe.
    """
    holder: dict = {}

    def handler(method, params):
        if method == "press_keys":
            holder["server"].die()  # the crash: connection + socket node go
            return True, CLOSE  # hang up without answering
        return default_handler(method, params)

    directory = tmp_path / "run"
    server = holder["server"] = FakeControlServer(
        directory / CONTROL_SOCKET_NAME, handler
    ).start()
    _write_pointer(directory, pid=_UNALLOCATED_PID, socket_path=server.path)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(directory))
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        live_backend=LiveBackend(retry_cooldown_s=0.0),
    )
    protocol = MCPProtocol(backend)
    try:
        result = _call(protocol, "press_keys", {"keys": "ctrl+p"})
    finally:
        server.stop()
    assert result["isError"] is True
    text = result["content"][0]["text"]
    # The death itself, with the request that was in flight ...
    assert "the app died" in text
    assert "press_keys" in text
    assert "keys='ctrl+p'" in text
    # ... and what can honestly be said about the process: it is gone, and a
    # sibling cannot reap its exit status/signal.
    assert "is gone" in text
    assert "not observable" in text
    # The old, false half of the message must be gone.
    assert "keyboard input needs a running app" not in text


def test_press_keys_without_an_instance_repeats_the_recorded_death(
    tmp_path, monkeypatch
):
    """A dead app is not a missing one: the app's own in-flight note survives it.

    Nothing listens any more (the socket is gone with the process), so the
    backend cannot see a mid-call EOF. The app recorded the request it was
    handling in ``inflight.json``; that note is what turns a bare "no live
    instance" into "it died while handling press_keys".
    """
    directory = tmp_path / "run"
    directory.mkdir(parents=True)
    _write_pointer(
        directory, pid=_UNALLOCATED_PID, socket_path=directory / CONTROL_SOCKET_NAME
    )
    # Time the app's own control server stamped into the note it left behind.
    (directory / INFLIGHT_NOTE_NAME).write_text(
        json.dumps(
            {
                "method": "press_keys",
                "summary": "keys='ctrl+p'",
                "request_id": 7,
                "pid": _UNALLOCATED_PID,
                "at": "2026-10-21T18:22:03+00:00",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(CONTROL_DIR_ENV, str(directory))
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        live_backend=LiveBackend(retry_cooldown_s=0.0),
    )
    protocol = MCPProtocol(backend)
    result = _call(protocol, "press_keys", {"keys": "ctrl+p"})
    assert result["isError"] is True
    text = result["content"][0]["text"]
    # The old contract still holds — there is no app to type into ...
    assert "no live instance" in text
    assert "keyboard input needs a running app" in text
    # ... but it now says *why*: the app died inside this request.
    assert "the app died while handling request 'press_keys'" in text
    assert "keys='ctrl+p'" in text
    assert "2026-10-21T18:22:03+00:00" in text


def test_death_report_names_the_request_without_echoing_secrets(tmp_path):
    """The request digest must identify the call and never leak a secret value.

    ``set_setting``/``run_action`` carry free-form values, so a token can sit in
    the params of the very request that killed the app.
    """
    holder: dict = {}

    def handler(method, params):
        if method == "set_setting":
            holder["server"].die()
            return True, CLOSE
        return default_handler(method, params)

    server = holder["server"] = FakeControlServer(
        tmp_path / CONTROL_SOCKET_NAME, handler
    ).start()
    client = LiveClient(server.path, timeout=0.5)
    try:
        with pytest.raises(LiveUnavailable) as excinfo:
            client.call(
                "set_setting",
                {"key": "theme", "value": "sk-or-v1-di0dbeefdi0dbeef"},
            )
    finally:
        client.close()
        server.stop()
    message = excinfo.value.message
    assert server.calls == [("set_setting", {"key": "theme", "value": "sk-or-v1-di0dbeefdi0dbeef"})]
    assert "set_setting" in message
    assert "the app died" in message
    assert "<redacted>" in message
    assert "di0dbeef" not in message
    assert "sk-or-v1" not in message


def test_request_digest_redacts_secret_names_and_token_shaped_values():
    """The digest identifies the call without ever echoing what it carried."""
    summary = summarize_request_params(
        {
            "action_id": "image_compare.export",
            "api_key": "abc123",
            "token": "def456",
            "value": "sk-or-v1-di0dbeef",
            "n": 3,
            "nested": {"a": 1, "b": 2},
            "keys": "ctrl+p",
        }
    )
    for secret in ("abc123", "def456", "di0dbeef"):
        assert secret not in summary
    assert "<redacted>" in summary
    assert "action_id='image_compare.export'" in summary
    assert "keys='ctrl+p'" in summary
    assert "n=3" in summary
    assert "nested={2 keys}" in summary


@pytest.mark.skipif(not Path("/proc/self/stat").exists(), reason="needs procfs")
def test_process_report_reads_a_zombies_signal_then_admits_it_is_gone():
    """A signal is reported when ``/proc`` still has it, and never invented after."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        child.kill()  # SIGKILL: unreaped, so /proc still carries the wait status
        deadline = time.monotonic() + 5.0
        report = process_report(child.pid)
        while report["state"] != "zombie" and time.monotonic() < deadline:
            time.sleep(0.02)
            report = process_report(child.pid)
        assert report["state"] == "zombie"
        assert report["observable"] is True
        assert report["signal"] == int(signal.SIGKILL)
        assert "SIGKILL" in report["detail"]
    finally:
        child.wait()
    # Reaped: a sibling can no longer read the status, and must not guess one.
    gone = process_report(child.pid)
    assert gone["state"] == "gone"
    assert gone["observable"] is False
    assert gone["signal"] is None
    assert "not observable" in gone["detail"]


def test_process_report_without_a_pid_does_not_guess():
    report = process_report(None)
    assert report["state"] == "no-pid"
    assert report["observable"] is False
    assert "not observable" in report["detail"]


def test_press_keys_live_app_error_keeps_the_apps_hint(tmp_path, monkeypatch):
    """An app-reported key failure is surfaced with the app's own hint."""

    def handler(method, params):
        if method == "press_keys":
            return False, {"error": "unknown key 'nope'", "hint": "valid names: enter, tab"}
        return default_handler(method, params)

    directory = tmp_path / "run"
    server = FakeControlServer(directory / CONTROL_SOCKET_NAME, handler).start()
    _write_pointer(directory, pid=os.getpid(), socket_path=server.path)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(directory))
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        live_backend=LiveBackend(retry_cooldown_s=0.0),
    )
    protocol = MCPProtocol(backend)
    try:
        result = _call(protocol, "press_keys", {"keys": "nope"})
        assert result["isError"] is True
        text = result["content"][0]["text"]
        assert "unknown key 'nope'" in text
        assert "valid names: enter, tab" in text
    finally:
        server.stop()


def test_open_folder_routes_on_the_live_instance(live_wired, tmp_path):
    protocol, _backend, _calls, _server = live_wired
    result = _call(protocol, "open_folder", {"path": str(tmp_path)})
    assert result["structuredContent"]["routed"] is True
    assert result["structuredContent"]["live"] is True


def test_open_folder_forwards_its_tab_to_the_live_instance(live_wired, tmp_path):
    """A targeted folder must reach the app *targeted* (complaint mcp-c-014).

    Falsification: the adapter always carried ``tab``; the backend dropped it,
    so the app answered from its untargeted branch ("no live tab accepted the
    folder") while the identical params on the control socket route fine.
    """
    protocol, _backend, _calls, server = live_wired
    result = _call(
        protocol,
        "open_folder",
        {"path": str(tmp_path), "tab": "image_compare", "slot": 1},
    )

    assert result["isError"] is False
    assert result["structuredContent"]["routed"] is True
    assert _wire_calls(server)[-1] == (
        "open_folder",
        {"path": str(tmp_path), "tab": "image_compare", "slot": 1},
    ), "tab travels with the call, next to slot/side"


def test_open_file_forwards_its_slot_hint_to_the_live_instance(live_wired):
    """A slot hint must reach the app, not stop at the schema (wave-1 finding).

    Falsification: the schema accepted ``slot`` while the live proxy put only
    ``{path, tab}`` on the wire, so the app routed the file to slot 1; a second
    ``open_file`` replaced it and ``image_compare.save`` answered "Please load
    and select images in both slots first". The wire assertion below fails on
    that implementation, and on one that drops the hint before the request.
    """
    protocol, _backend, _calls, server = live_wired
    result = _call(
        protocol,
        "open_file",
        {"path": "/img/right.png", "tab": "image_compare", "slot": 2},
    )

    assert result["isError"] is False
    assert result["structuredContent"]["opened"] is True
    assert _wire_calls(server)[-1] == (
        "open_file",
        {"path": "/img/right.png", "tab": "image_compare", "slot": 2},
    ), "the slot hint travels with the call"


def test_open_folder_reports_an_unknown_tab_as_an_unknown_tab(tmp_path, monkeypatch):
    """A named-but-unknown kind is the app's own error, not "nothing accepted"."""
    launches: list = []
    known = ("image_compare", "image_gallery", "multi_compare")

    def handler(method: str, params: dict):
        if method == "open_folder":
            tab = params.get("tab")
            if not tab:
                # What the real app answers when nothing targeted was asked
                # for (handlers.open_folder, untargeted branch).
                return False, {
                    "error": "no live tab accepted the folder",
                    "hint": "open a gallery-like tab once, then retry open_folder",
                }
            if tab not in known:
                return False, {
                    "error": f"unknown tab kind {tab!r}",
                    "hint": "known kinds: image_compare, image_gallery",
                }
            return True, {"routed": True, "path": params["path"], "tab": tab}
        return default_handler(method, params)

    directory = tmp_path / "run"
    server = FakeControlServer(directory / CONTROL_SOCKET_NAME, handler).start()
    _write_pointer(directory, pid=os.getpid(), socket_path=server.path)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(directory))
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        launcher=lambda args: launches.append(args) or os.getpid(),
        live_backend=LiveBackend(retry_cooldown_s=0.0),
    )
    protocol = MCPProtocol(backend)
    try:
        result = _call(
            protocol, "open_folder", {"path": str(tmp_path), "tab": "wibble"}
        )

        assert result["isError"] is True
        text = result["content"][0]["text"]
        assert "unknown tab kind 'wibble'" in text
        assert "known kinds: image_compare" in text, "the app's hint survives"
        assert "no live tab accepted the folder" not in text
        assert launches == [], "a rejected kind never starts a headless boot"
    finally:
        server.stop()


def test_adapter_without_attachment_raises_unavailable(tmp_path):
    adapter = LiveBackend(socket_path=tmp_path / "absent.sock")
    with pytest.raises(LiveUnavailable):
        adapter.press_keys(keys="ctrl+p")
    with pytest.raises(LiveUnavailable):
        adapter.list_actions()
    with pytest.raises(LiveUnavailable):
        adapter.ui_elements()
    with pytest.raises(LiveUnavailable):
        adapter.ui_click(id="main.settings.btn")


# --- mutation contract taxonomy through the backend (plan P2) ---------------


def _silent_live_protocol(tmp_path, monkeypatch, *, silent_method: str):
    """A wired backend whose ``silent_method`` accepts and never answers."""

    def handler(method, params):
        if method == silent_method:
            return True, SILENT
        return default_handler(method, params)

    directory = tmp_path / "run"
    server = FakeControlServer(directory / CONTROL_SOCKET_NAME, handler).start()
    _write_pointer(directory, pid=os.getpid(), socket_path=server.path)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(directory))
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)

    calls: list = []
    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        snapshot_runner=lambda tab: calls.append(tab) or _snapshot(),
        live_backend=LiveBackend(retry_cooldown_s=0.0, timeout=0.2),
    )
    return MCPProtocol(backend), calls, server


def test_mutating_tool_timeout_says_the_operation_may_have_completed(tmp_path, monkeypatch):
    """A sent-but-unanswered edit errors honestly instead of falling back."""
    protocol, calls, server = _silent_live_protocol(tmp_path, monkeypatch, silent_method="run_action")
    try:
        result = _call(protocol, "run_action", {"action_id": "platform.settings"})
        assert result["isError"] is True
        text = result["content"][0]["text"]
        assert "may have completed" in text
        assert "timed out waiting for the control socket" in text
        assert calls == [], "a sent edit must not fall back to a fresh process"
    finally:
        server.stop()


def test_live_only_mutation_timeout_says_the_operation_may_have_completed(tmp_path, monkeypatch):
    """``press_keys`` (live-only) reports a timed-out edit as possibly applied."""
    protocol, calls, server = _silent_live_protocol(tmp_path, monkeypatch, silent_method="press_keys")
    try:
        result = _call(protocol, "press_keys", {"keys": "ctrl+p"})
        assert result["isError"] is True
        text = result["content"][0]["text"]
        assert "may have completed" in text
        assert "timed out waiting for the control socket" in text
    finally:
        server.stop()


def test_read_timeout_falls_back_without_a_completed_edit_claim(tmp_path, monkeypatch):
    """Reads retry, then fall back quietly — never the mutation wording."""
    protocol, calls, server = _silent_live_protocol(tmp_path, monkeypatch, silent_method="list_actions")
    try:
        result = _call(protocol, "list_actions")
        assert result["isError"] is False
        assert result["structuredContent"]["source"] == "fallback"
        assert "may have completed" not in result["content"][0]["text"]
        assert calls == [None]
    finally:
        server.stop()


def test_fallback_list_actions_carries_enabled_and_reason(tmp_path, monkeypatch):
    """The Phase-1 fallback passes ``enabled``/``reason`` through from the snapshot."""
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(tmp_path / "no-instance"))
    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        snapshot_runner=lambda tab: _snapshot(),
    )
    rows = {row["action_id"]: row for row in backend.list_actions()["actions"]}
    assert rows["platform.settings"]["enabled"] is True
    assert rows["platform.settings"]["reason"] is None
    assert rows["platform.quit_app"]["enabled"] is False
    assert rows["platform.quit_app"]["reason"] == "a modal dialog is open"


def test_fallback_list_actions_degrades_missing_enabled_and_reason(tmp_path, monkeypatch):
    """A snapshot row without the two keys degrades to enabled/null, not a crash."""
    monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
    monkeypatch.setenv(CONTROL_DIR_ENV, str(tmp_path / "no-instance"))
    snapshot = {"actions": [{"action_id": "a.b", "label": "B"}], "state": {}, "sessions": []}
    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        snapshot_runner=lambda tab: snapshot,
    )
    row = backend.list_actions()["actions"][0]
    assert row["enabled"] is True
    assert row["reason"] is None


# --- real instance (only when the environment provides one) ------------------


@pytest.mark.skipif(
    not _REAL_SOCKET,
    reason="set IMGSLI_MCP_CONTROL_SOCKET to prove the real app-side socket",
)
def test_real_instance_round_trip_when_provided():
    """End-to-end proof against a genuine app instance (supervisor-run)."""
    env = {SOCKET_OVERRIDE_ENV: _REAL_SOCKET}
    path = discover_socket(env)
    assert path is not None, "IMGSLI_MCP_CONTROL_SOCKET is set but discovery found nothing"
    client = LiveClient(path)
    try:
        assert client.alive() is True
        adapter = LiveBackend(client=client)
        actions = adapter.list_actions()
        assert actions["source"] == "live"
        assert actions["count"] == len(actions["actions"])
    finally:
        client.close()


def test_timeout_is_configurable(tmp_path):
    client = LiveClient(tmp_path / "absent.sock", timeout=0.25)
    assert client.timeout == pytest.approx(0.25)
