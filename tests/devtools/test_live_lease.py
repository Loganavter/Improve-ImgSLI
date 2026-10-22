"""Live help captures take a lease from the machine's ``live-lease`` tool.

No X server and no app boot here. Two seams make that possible:

* the lease CLI is a fake executable in ``tmp_path`` (the adapter's binary seam
  is ``LIVE_LEASE_BIN``); it implements ``alloc/env/bind/release/list`` and
  records every argv, so the exported env and the lease lifecycle are asserted
  against real subprocess calls, not a mock object;
* the app spawn is a real ``sleep`` child (``help_live.subprocess`` is swapped
  for a shim), so ``pid``/``pgid`` binding and teardown are exercised for real
  while the argv/env the harness *meant* to launch are recorded.

Why a lease at all: the probe in :func:`help_figures._free_display_number` is a
TOCTOU check, not a reservation — two captures that probe before either Xvfb
socket exists pick the same number and the loser times out. The lease pool is
the only allocator that knows what another lane already holds.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from devtools import help_figures, help_live, live_lease

_REAL_SUBPROCESS = subprocess

_FAKE_CLI_BODY = '''
import json
import os
import sys
from pathlib import Path

LEASE_ID = "fake-lease-1"
state = Path(os.environ["FAKE_LEASE_STATE"])
calls = Path(os.environ["FAKE_LEASE_CALLS"])
root = state / "lease"
control = root / "control"

with calls.open("a", encoding="utf-8") as handle:
    print(json.dumps({"argv": sys.argv[1:]}), file=handle)


def exports():
    return {
        "DISPLAY": ":77",
        "XDG_RUNTIME_DIR": str(root / "run"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "IMGSLI_CONTROL_DIR": str(control),
        "IMGSLI_MCP_CONTROL_SOCKET": str(control / "control.sock"),
        "LIVE_LEASE": LEASE_ID,
    }


command = sys.argv[1] if len(sys.argv) > 1 else ""
if command == "alloc":
    for path in (root / "run", root / "data", root / "cache", root / "config", control):
        path.mkdir(parents=True, exist_ok=True)
    (root / "run").chmod(0o700)
    control.chmod(0o700)
    print("lease allocated")
    print(LEASE_ID)
elif command == "env":
    for key, value in exports().items():
        print("export " + key + "=" + value)
elif command in ("bind", "release"):
    pass
elif command == "list":
    print(LEASE_ID)
elif command == "status":
    print(json.dumps({"id": LEASE_ID}))
else:
    print("unknown command: " + command, file=sys.stderr)
    sys.exit(2)
'''


class _FakeCli:
    """The installed fake executable plus its recorded argv log."""

    def __init__(self, script: Path, state: Path) -> None:
        self.script = script
        self.state = state

    @property
    def calls_path(self) -> Path:
        return self.state / "calls.jsonl"

    @property
    def lease_root(self) -> Path:
        return self.state / "lease"

    def calls(self) -> list[list[str]]:
        if not self.calls_path.exists():
            return []
        return [
            json.loads(line)["argv"]
            for line in self.calls_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def commands(self) -> list[str]:
        return [argv[0] for argv in self.calls()]


@pytest.fixture()
def fake_cli(tmp_path, monkeypatch) -> _FakeCli:
    """Install the fake lease CLI and point the adapter's seam at it."""
    script = tmp_path / "live-lease"
    script.write_text("#!" + sys.executable + "\n" + _FAKE_CLI_BODY, encoding="utf-8")
    script.chmod(0o755)
    state = tmp_path / "lease-state"
    state.mkdir()
    monkeypatch.setenv("LIVE_LEASE_BIN", str(script))
    monkeypatch.setenv("FAKE_LEASE_STATE", str(state))
    monkeypatch.setenv("FAKE_LEASE_CALLS", str(state / "calls.jsonl"))
    monkeypatch.delenv("IMGSLI_HELP_LIVE_LEASE", raising=False)
    return _FakeCli(script, state)


@pytest.fixture(autouse=True)
def _reset_legacy_notice(monkeypatch):
    """The "no tool" notice is once per process; isolate every test from it."""
    monkeypatch.setattr(help_live, "_LEGACY_NOTICE_EMITTED", False, raising=False)


class _AppProcesses:
    """Stands in for ``subprocess.Popen`` on the app-spawn path.

    Records the argv/env the harness intended, then starts a real child in its
    own session so ``os.getpgid(pid)`` and the teardown are real as well.
    """

    def __init__(self) -> None:
        self.spawned: list[dict] = []
        self.proc: subprocess.Popen | None = None

    def Popen(self, argv, **kwargs):  # noqa: N802 - the attribute it replaces
        self.spawned.append(
            {
                "argv": list(argv),
                "env": dict(kwargs["env"]),
                "start_new_session": bool(kwargs.get("start_new_session")),
            }
        )
        self.proc = _REAL_SUBPROCESS.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            env=kwargs["env"],
            stdout=_REAL_SUBPROCESS.DEVNULL,
            stderr=_REAL_SUBPROCESS.DEVNULL,
            start_new_session=bool(kwargs.get("start_new_session")),
        )
        return self.proc


class _SubprocessShim:
    """``help_live.subprocess`` with only ``Popen`` replaced, nothing else."""

    def __init__(self, processes: _AppProcesses) -> None:
        self._processes = processes

    @property
    def Popen(self):  # noqa: N802 - mirrors the module attribute
        return self._processes.Popen

    def __getattr__(self, name):
        return getattr(_REAL_SUBPROCESS, name)


class _PingClient:
    """A ``LiveClient`` whose ``ping`` answers without a socket server."""

    instances: list["_PingClient"] = []

    def __init__(self, path) -> None:
        self.path = Path(path)
        self.closed = False
        _PingClient.instances.append(self)

    def call(self, method, params=None):
        assert method == "ping"
        return {}

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def app_seam(monkeypatch):
    """Swap the app spawn + control client; return the recorded spawns."""
    processes = _AppProcesses()
    _PingClient.instances = []
    monkeypatch.setattr(help_live, "subprocess", _SubprocessShim(processes))
    monkeypatch.setattr(help_live, "LiveClient", _PingClient)
    monkeypatch.setattr(help_live, "BOOT_TIMEOUT_S", 5.0)
    return processes


def _live_app(out_dir: Path, *, backend: str = "xvfb", **kwargs) -> help_live.LiveApp:
    return help_live.LiveApp(
        backend=backend,
        out_dir=out_dir,
        locale="en",
        theme="dark",
        width=1280,
        height=800,
        **kwargs,
    )


def _touch_lease_socket(cli: _FakeCli) -> None:
    control = cli.lease_root / "control"
    control.mkdir(parents=True, exist_ok=True)
    (control / "control.sock").touch()


# --- the adapter -------------------------------------------------------------


def test_available_follows_the_binary_seam(fake_cli, tmp_path, monkeypatch):
    assert live_lease.available() is True

    monkeypatch.setenv("LIVE_LEASE_BIN", str(tmp_path / "absent-live-lease"))
    assert live_lease.available() is False


def test_alloc_env_bind_release_round_trip(fake_cli):
    lease = live_lease.alloc("help-live", "figures")

    assert lease.id == "fake-lease-1"
    env = lease.env
    assert env["LIVE_LEASE"] == lease.id
    assert env["DISPLAY"] == ":77"
    assert set(env) >= {
        "XDG_RUNTIME_DIR",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "IMGSLI_CONTROL_DIR",
        "IMGSLI_MCP_CONTROL_SOCKET",
    }

    lease.bind(pid=4242, pgid=4242)
    lease.release()
    # Release is idempotent: a second close must not shell out again.
    lease.release()

    calls = fake_cli.calls()
    assert calls[0] == ["alloc", "--lane", "help-live", "--task", "figures"]
    assert ["bind", lease.id, "--pid", "4242", "--pgid", "4242"] in calls
    assert [argv for argv in calls if argv[0] == "release"] == [["release", lease.id]]


def test_alloc_maps_every_optional_flag_to_argv(fake_cli):
    live_lease.alloc(
        "lane-x",
        "task-y",
        display=":31",
        ttl=120,
        no_xvfb=True,
        wait=8,
        root="/tmp/x",
        geometry="1280x800x24",
    )

    assert fake_cli.calls()[0] == [
        "alloc",
        "--lane",
        "lane-x",
        "--task",
        "task-y",
        "--display",
        ":31",
        "--ttl",
        "120",
        "--no-xvfb",
        "--wait",
        "8",
        "--root",
        "/tmp/x",
        "--geometry",
        "1280x800x24",
    ]


def test_a_missing_binary_is_a_lease_error(tmp_path, monkeypatch):
    monkeypatch.setenv("LIVE_LEASE_BIN", str(tmp_path / "absent-live-lease"))

    with pytest.raises(live_lease.LiveLeaseError, match="not installed"):
        live_lease.alloc("lane", "task")


def test_adapter_never_uses_a_shell():
    source = Path(live_lease.__file__).read_text(encoding="utf-8")

    assert "shell=True" not in source
    assert "shell = True" not in source


# --- the display probe that made a lease necessary ---------------------------


def test_two_probes_pick_the_same_display_before_either_socket_exists(
    monkeypatch,
):
    """The known-bad artefact: ``_free_display_number`` is a check, not a lock."""
    monkeypatch.setattr(help_figures, "_display_exists", lambda _number: False)

    first = help_figures._free_display_number()
    second = help_figures._free_display_number()

    assert first == second == 90


# --- LiveApp: lease mode -----------------------------------------------------


def test_enter_takes_the_lease_and_exports_it_to_the_app(
    tmp_path, fake_cli, app_seam, monkeypatch
):
    _touch_lease_socket(fake_cli)
    live = _live_app(tmp_path / "out")

    with live:
        assert live.lease is not None and live.lease.id == "fake-lease-1"
        env = app_seam.spawned[0]["env"]
        assert app_seam.spawned[0]["argv"] == [sys.executable, "src/__main__.py"]
        assert env["LIVE_LEASE"] == "fake-lease-1"
        assert env["DISPLAY"] == ":77"
        assert env["XDG_CONFIG_HOME"] == str(fake_cli.lease_root / "config")
        assert env["XDG_DATA_HOME"] == str(fake_cli.lease_root / "data")
        assert env["XDG_CACHE_HOME"] == str(fake_cli.lease_root / "cache")
        assert env["XDG_RUNTIME_DIR"] == str(fake_cli.lease_root / "run")
        assert env["IMGSLI_CONTROL_DIR"] == str(fake_cli.lease_root / "control")
        assert env["HOME"] == str(live.root / "home")
        assert env["IMGSLI_CONTROL"] == "1"
        # The client follows the lease's control dir, not the harness's root.
        assert _PingClient.instances[0].path == (
            fake_cli.lease_root / "control" / "control.sock"
        )
        # The app is bound while it runs, not before it exists.
        assert "bind" in fake_cli.commands()

    assert fake_cli.commands() == ["alloc", "env", "bind", "release"]
    assert fake_cli.calls()[0] == [
        "alloc",
        "--lane",
        "help-live",
        "--task",
        "help-figures-live:en/dark",
    ]
    bind = [argv for argv in fake_cli.calls() if argv[0] == "bind"][0]
    assert bind == [
        "bind",
        "fake-lease-1",
        "--pid",
        str(app_seam.proc.pid),
        "--pgid",
        str(app_seam.proc.pid),
    ]
    # The app is gone before the lease is released.
    assert app_seam.proc.poll() is not None
    # Settings live in the lease's config dir, never in the harness root.
    profile = (
        fake_cli.lease_root
        / "config"
        / "improve-imgsli"
        / "improve-imgsli.conf"
    )
    text = profile.read_text(encoding="utf-8")
    assert "theme=dark" in text and "language=en" in text
    assert not (live.root / "config" / "improve-imgsli").exists()


def test_release_runs_when_the_capture_raises(tmp_path, fake_cli, app_seam):
    _touch_lease_socket(fake_cli)
    live = _live_app(tmp_path / "out")

    with pytest.raises(RuntimeError, match="boom"):
        with live:
            raise RuntimeError("boom")

    assert "release" in fake_cli.commands()
    assert app_seam.proc.poll() is not None


def test_an_injected_lease_is_used_without_allocating(tmp_path, fake_cli, app_seam):
    _touch_lease_socket(fake_cli)
    control = fake_cli.lease_root / "control"

    class _Injected:
        id = "injected-1"

        def __init__(self) -> None:
            self.bound: list[tuple] = []
            self.released = 0

        @property
        def env(self):
            return {
                "DISPLAY": ":88",
                "XDG_RUNTIME_DIR": str(fake_cli.lease_root / "run"),
                "XDG_DATA_HOME": str(fake_cli.lease_root / "data"),
                "XDG_CACHE_HOME": str(fake_cli.lease_root / "cache"),
                "XDG_CONFIG_HOME": str(fake_cli.lease_root / "config"),
                "IMGSLI_CONTROL_DIR": str(control),
                "IMGSLI_MCP_CONTROL_SOCKET": str(control / "control.sock"),
                "LIVE_LEASE": "injected-1",
            }

        def bind(self, pid=None, pgid=None):
            self.bound.append((pid, pgid))

        def release(self) -> None:
            self.released += 1

    lease = _Injected()
    live = _live_app(tmp_path / "out", lease=lease)

    with live:
        assert app_seam.spawned[0]["env"]["DISPLAY"] == ":88"

    assert "alloc" not in fake_cli.commands()
    assert lease.bound == [(app_seam.proc.pid, app_seam.proc.pid)]
    assert lease.released == 1


# --- LiveApp: no tool installed ---------------------------------------------


def test_without_the_tool_the_old_isolation_stays_and_the_downgrade_is_named_once(
    tmp_path, app_seam, monkeypatch, capsys
):
    monkeypatch.setenv("LIVE_LEASE_BIN", str(tmp_path / "absent-live-lease"))
    monkeypatch.setenv("DISPLAY", ":42")

    apps = []
    for index in range(2):
        live = _live_app(tmp_path / f"run-{index}", backend="native")
        (live.root / "run" / "control.sock").touch()
        with live:
            assert live.lease is None
        apps.append(live)

    stderr = capsys.readouterr().err
    assert stderr.count("live-lease") == 1
    assert "in-process isolation" in stderr

    env = app_seam.spawned[0]["env"]
    live = apps[0]
    assert env["DISPLAY"] == ":42"
    assert "LIVE_LEASE" not in env
    assert env["XDG_CONFIG_HOME"] == str(live.root / "config")
    assert env["XDG_DATA_HOME"] == str(live.root / "data")
    assert env["XDG_CACHE_HOME"] == str(live.root / "cache")
    assert env["XDG_RUNTIME_DIR"] == str(live.root / "run")
    assert env["HOME"] == str(live.root / "home")
    # The fallback still writes the seeded profile where the app reads it.
    assert (live.root / "config" / "improve-imgsli" / "improve-imgsli.conf").is_file()


def test_override_zero_forces_the_legacy_path_even_with_the_tool(
    tmp_path, fake_cli, app_seam, monkeypatch, capsys
):
    monkeypatch.setenv("IMGSLI_HELP_LIVE_LEASE", "0")
    monkeypatch.setenv("DISPLAY", ":42")
    live = _live_app(tmp_path / "out", backend="native")
    (live.root / "run" / "control.sock").touch()

    with live:
        assert live.lease is None

    assert "alloc" not in fake_cli.commands()
    assert "live-lease" in capsys.readouterr().err


def test_override_one_without_the_tool_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setenv("LIVE_LEASE_BIN", str(tmp_path / "absent-live-lease"))
    monkeypatch.setenv("IMGSLI_HELP_LIVE_LEASE", "1")

    with pytest.raises(help_live.LiveError, match="live-lease"):
        with _live_app(tmp_path / "out"):
            pass


def test_a_non_boolean_override_is_an_error(tmp_path, fake_cli, monkeypatch):
    monkeypatch.setenv("IMGSLI_HELP_LIVE_LEASE", "maybe")

    with pytest.raises(help_live.LiveError, match="IMGSLI_HELP_LIVE_LEASE"):
        with _live_app(tmp_path / "out"):
            pass
