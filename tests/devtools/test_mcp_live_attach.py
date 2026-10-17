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
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = REPO_ROOT / "mcp-server"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from app.backend import AppBackend  # noqa: E402
from app.live import (  # noqa: E402
    CONTROL_DIR_ENV,
    CONTROL_SOCKET_NAME,
    SOCKET_OVERRIDE_ENV,
    LiveBackend,
    LiveClient,
    LiveError,
    LiveUnavailable,
    discover_socket,
)
from app.protocol import MCPProtocol  # noqa: E402
from app.process_policy import PRESERVED_LOG_NAME  # noqa: E402

#: Handler sentinel: close the connection without answering (transport fault).
CLOSE = object()


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
                    "unexpected": "dropped",
                },
                {
                    "action_id": "image_compare.zoom_fit",
                    "label": "Fit",
                    "owner_tab": "image_compare",
                    "topic": "view",
                    "shortcut": None,
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
            "surfaces": [{"name": "settings", "description": "Settings dialog", "isolated": False}],
        }
    if method == "open_tab":
        return True, {"ran": True, "tab": params.get("tab")}
    if method == "run_action":
        return True, {"ran": True, "action_id": params.get("action_id"), "tab": params.get("tab")}
    if method == "open_folder":
        return True, {"ran": True, "path": params.get("path"), "routed": True}
    if method == "set_theme":
        return True, {"theme": params.get("theme"), "persisted": True, "applies_on": "now"}
    if method == "set_language":
        return True, {"language": params.get("language"), "persisted": True, "applies_on": "now"}
    if method == "capture_live":
        return True, {"surface": params.get("what"), "path": "/live/shot.png", "theme": "dark"}
    if method == "press_keys":
        return True, {"pressed": ["ctrl+shift+p"], "count": 1, "target": "QMainWindow"}
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
        response = {"id": request.get("id"), "ok": bool(ok)}
        if ok:
            response["result"] = payload
        else:
            response["error"] = (payload or {}).get("error", "failed")
            if (payload or {}).get("hint"):
                response["hint"] = payload["hint"]
        conn.sendall(json.dumps(response).encode("utf-8") + b"\n")
        return True


def _write_pointer(directory: Path, *, pid: int, socket_path: Path | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    data = {"pid": pid, "started": "2026-10-17T00:00:00Z", "version": "0.1.0"}
    if socket_path is not None:
        data["socket"] = str(socket_path)
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
    socket_path = FakeControlServer(directory / CONTROL_SOCKET_NAME).start().path
    try:
        # A pid above the kernel's limit never exists: the pointer is stale.
        _write_pointer(directory, pid=2**30, socket_path=socket_path)
        assert discover_socket() is None
    finally:
        (directory / CONTROL_SOCKET_NAME).unlink(missing_ok=True)


def test_discover_socket_uses_the_runtime_dir_when_no_override(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    socket_path = FakeControlServer(runtime / "control.sock").start().path
    try:
        monkeypatch.delenv(SOCKET_OVERRIDE_ENV, raising=False)
        monkeypatch.delenv(CONTROL_DIR_ENV, raising=False)
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
        assert discover_socket() == socket_path
    finally:
        (runtime / "control.sock").unlink(missing_ok=True)


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


# --- adapter: every tool proxied --------------------------------------------


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
                },
                {
                    "action_id": "image_compare.zoom_fit",
                    "label": "Fit",
                    "owner_tab": "image_compare",
                    "topic": "view",
                    "shortcut": None,
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
            "surfaces": [{"name": "settings", "description": "Settings dialog", "isolated": False}],
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
        {"what": "settings", "theme": "light"},
        {
            "surface": "settings",
            "path": "/live/shot.png",
            "theme": "dark",
            "live": True,
            "source": "live",
        },
    ),
    (
        "press_keys",
        {"keys": "ctrl+shift+p"},
        "press_keys",
        {"keys": "ctrl+shift+p"},
        {"pressed": ["ctrl+shift+p"], "count": 1, "target": "QMainWindow", "source": "live"},
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
            }
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
        "source": "live",
    }
    assert ("press_keys", {"keys": "ctrl+shift+p"}) in server.calls


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


def test_press_keys_transport_fault_errors_honestly(tmp_path, monkeypatch):
    """A live instance that dies mid-call leaves ``press_keys`` an honest error."""

    def handler(method, params):
        if method == "press_keys":
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
        result = _call(protocol, "press_keys", {"keys": "ctrl+p"})
        assert result["isError"] is True
        assert "keyboard input needs a running app" in result["content"][0]["text"]
    finally:
        server.stop()


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


def test_adapter_without_attachment_raises_unavailable(tmp_path):
    adapter = LiveBackend(socket_path=tmp_path / "absent.sock")
    with pytest.raises(LiveUnavailable):
        adapter.press_keys(keys="ctrl+p")
    with pytest.raises(LiveUnavailable):
        adapter.list_actions()


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
