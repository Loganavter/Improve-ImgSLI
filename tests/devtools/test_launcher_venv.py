"""venv-lifecycle tests for the launcher (no real venvs, no network).

Covers the decisions in ensure_venv_ready / cleanup_python_cache /
remove_venv_dir with fake directories and monkeypatched subprocess/venv
creation, plus the .installed marker mtime semantics.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import pytest
from types import SimpleNamespace

import launcher


def _quiet_ui():
    return launcher.UI(progress=False)


def test_venv_python_resolves_posix_then_windows(tmp_path):
    posix = tmp_path / "bin" / "python"
    posix.parent.mkdir()
    posix.touch()
    assert launcher.venv_python(tmp_path) == posix

    win_only = tmp_path / "winvenv"
    (win_only / "Scripts").mkdir(parents=True)
    (win_only / "Scripts" / "python.exe").touch()
    assert launcher.venv_python(win_only) == win_only / "Scripts" / "python.exe"


def test_ensure_venv_ready_creates_missing_venv(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "VENV_DIR", tmp_path / "venv")
    reqs = tmp_path / "requirements-gui.txt"
    reqs.write_text("pyvips\n")
    monkeypatch.setattr(launcher, "REQUIREMENTS", reqs)

    calls = []

    def fake_create(ui, venv_dir):
        calls.append("create")
        (venv_dir / "bin").mkdir(parents=True)
        (venv_dir / "bin" / "python").touch()
        return True

    def fake_pip(ui, message, command, requirements, extra_env=None):
        calls.append("pip:" + message)
        return True

    monkeypatch.setattr(launcher, "create_venv", fake_create)
    monkeypatch.setattr(launcher, "run_pip_with_inline_progress", fake_pip)

    py = launcher.ensure_venv_ready(_quiet_ui())
    assert py is not None
    assert py.name == "python"
    assert (tmp_path / "venv" / ".installed").exists()
    assert calls == ["create", "pip:Installing dependencies"]


def test_ensure_venv_ready_skips_install_when_marker_fresh(tmp_path, monkeypatch):
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").touch()
    reqs = tmp_path / "requirements-gui.txt"
    reqs.write_text("pyvips\n")
    marker = venv / ".installed"
    marker.write_text("installed")
    time.sleep(0.01)
    os.utime(marker, None)

    monkeypatch.setattr(launcher, "VENV_DIR", venv)
    monkeypatch.setattr(launcher, "REQUIREMENTS", reqs)
    calls = []
    monkeypatch.setattr(
        launcher, "run_pip_with_inline_progress",
        lambda ui, m, c, r, extra_env=None: calls.append(m) or True,
    )

    py = launcher.ensure_venv_ready(_quiet_ui())
    assert py is not None
    assert calls == []


def test_ensure_venv_ready_reinstalls_when_requirements_newer(tmp_path, monkeypatch):
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").touch()
    marker = venv / ".installed"
    marker.write_text("installed")
    old = time.time() - 1000
    os.utime(marker, (old, old))

    reqs = tmp_path / "requirements-gui.txt"
    reqs.write_text("pyvips\n")

    monkeypatch.setattr(launcher, "VENV_DIR", venv)
    monkeypatch.setattr(launcher, "REQUIREMENTS", reqs)
    calls = []
    monkeypatch.setattr(
        launcher, "run_pip_with_inline_progress",
        lambda ui, m, c, r, extra_env=None: calls.append(m) or True,
    )

    launcher.ensure_venv_ready(_quiet_ui())
    assert calls == ["Checking/Updating dependencies"]


def test_ensure_venv_ready_recovers_from_corrupt_venv(tmp_path, monkeypatch):
    # safety confirmation (post-recovery addition) is bypassed for headless
    monkeypatch.setenv("IMGSLI_REMOVE_VENV_YES", "1")
    venv = tmp_path / "venv"
    venv.mkdir()  # exists but has no python

    monkeypatch.setattr(launcher, "VENV_DIR", venv)
    reqs = tmp_path / "requirements-gui.txt"
    reqs.write_text("pyvips\n")
    monkeypatch.setattr(launcher, "REQUIREMENTS", reqs)

    def fake_create(ui, venv_dir):
        (venv_dir / "bin").mkdir(parents=True, exist_ok=True)
        (venv_dir / "bin" / "python").touch()
        return True

    monkeypatch.setattr(launcher, "create_venv", fake_create)
    monkeypatch.setattr(launcher, "run_pip_with_inline_progress", lambda *a, **k: True)

    py = launcher.ensure_venv_ready(_quiet_ui())
    assert py is not None
    assert py.is_file()


def test_remove_venv_dir_refuses_invalid_path(tmp_path):
    ui = _quiet_ui()
    assert not launcher.remove_venv_dir(ui, Path("."), "virtual environment")
    assert not launcher.remove_venv_dir(ui, Path("/"), "virtual environment")


def test_remove_venv_dir_deletes(tmp_path, monkeypatch):
    # safety confirmation (post-recovery addition) is bypassed for headless
    monkeypatch.setenv("IMGSLI_REMOVE_VENV_YES", "1")
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "bin").mkdir()
    assert launcher.remove_venv_dir(_quiet_ui(), venv, "virtual environment")
    assert not venv.exists()


def test_cleanup_python_cache_prunes_pycache_and_skips_exclude(tmp_path):
    (tmp_path / "src" / "mod" / "__pycache__").mkdir(parents=True)
    (tmp_path / "src" / "mod" / "__pycache__" / "x.cpython-314.pyc").touch()
    (tmp_path / "venv" / "lib" / "__pycache__").mkdir(parents=True)
    (tmp_path / "venv" / "lib" / "__pycache__" / "y.pyc").touch()

    assert launcher.cleanup_python_cache(_quiet_ui(), tmp_path, exclude=tmp_path / "venv")
    assert not (tmp_path / "src" / "mod" / "__pycache__").exists()
    assert (tmp_path / "venv" / "lib" / "__pycache__").exists()


def test_app_env_sets_pythonpath(monkeypatch):
    env = launcher._app_env()
    assert str(launcher.SCRIPT_DIR / "src") in env["PYTHONPATH"].split(os.pathsep)


def test_run_action_assembles_argv_and_propagates_exit(monkeypatch, tmp_path):
    class FakeArgs:
        debug = True
        ui_inspector = True
        theme = "dark"

    launched = {}

    def fake_ensure(ui):
        return tmp_path / "python"

    def fake_popen(command, env=None):
        launched["command"] = command
        launched["env"] = env
        return SimpleNamespace(wait=lambda: 3)

    monkeypatch.setattr(launcher, "ensure_venv_ready", fake_ensure)
    monkeypatch.setattr(launcher, "venv_python", lambda: tmp_path / "python")
    monkeypatch.setattr(launcher, "desktop_integration", lambda ui, mode: True)
    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)

    code = launcher.run_action(FakeArgs(), ["--dump-ui-layout", "/tmp/x.json"], _quiet_ui())
    assert code == 3
    command = launched["command"]
    assert command[0] == str(tmp_path / "python")
    assert command[1] == str(launcher.APP_MAIN)
    assert set(command[2:4]) == {"--ui-inspector", "--debug"}
    assert command[4:] == ["--dump-ui-layout", "/tmp/x.json"]
    assert launched["env"]["APP_THEME"] == "dark"


def test_install_action_returns_zero_on_ready(monkeypatch):
    monkeypatch.setattr(launcher, "ensure_venv_ready", lambda ui: Path("/x/python"))
    code = launcher.install_action(None, [], _quiet_ui())
    assert code == 0


# --------------------------------------------------------------------------
# pip isolation (dead host index) + relative editable resolution


def test_pip_env_overrides_disables_pip_config_file():
    assert launcher._pip_env_overrides() == {"PIP_CONFIG_FILE": os.devnull}


def test_resolve_requirements_resolves_editable_sibling(tmp_path, monkeypatch):
    repo = tmp_path / "Improve-ImgSLI"
    repo.mkdir()
    sibling = tmp_path / "sli-ui-toolkit"
    sibling.mkdir()
    monkeypatch.setattr(launcher, "SCRIPT_DIR", repo)
    monkeypatch.delenv("SLI_TOOLKIT_DIR", raising=False)

    reqs = tmp_path / "requirements-gui.txt"
    reqs.write_text("pyvips\n-e ../sli-ui-toolkit\nMarkdown==3.8\n")

    resolved = launcher.resolve_requirements(reqs, tmp_path)
    text = resolved.read_text(encoding="utf-8")
    assert f"-e {sibling.resolve()}" in text
    assert "pyvips" in text
    assert "Markdown==3.8" in text


def test_resolve_requirements_drops_unresolved_editable(tmp_path, monkeypatch):
    repo = tmp_path / "Improve-ImgSLI"
    repo.mkdir()
    monkeypatch.setattr(launcher, "SCRIPT_DIR", repo)
    monkeypatch.delenv("SLI_TOOLKIT_DIR", raising=False)

    reqs = tmp_path / "requirements-gui.txt"
    reqs.write_text("pyvips\n-e ../missing-toolkit\n")

    resolved = launcher.resolve_requirements(reqs, tmp_path)
    active = [
        line
        for line in resolved.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert all("missing-toolkit" not in line for line in active)
    assert "dropped unresolved editable requirement" in resolved.read_text(encoding="utf-8")


def test_resolve_requirements_uses_env_toolkit_dir(tmp_path, monkeypatch):
    repo = tmp_path / "Improve-ImgSLI"
    repo.mkdir()
    env_dir = tmp_path / "elsewhere" / "sli-ui-toolkit"
    env_dir.mkdir(parents=True)
    monkeypatch.setattr(launcher, "SCRIPT_DIR", repo)
    monkeypatch.setenv("SLI_TOOLKIT_DIR", str(env_dir))

    reqs = tmp_path / "requirements-gui.txt"
    reqs.write_text("-e ../sli-ui-toolkit\n")

    resolved = launcher.resolve_requirements(reqs, tmp_path)
    assert f"-e {env_dir.resolve()}" in resolved.read_text(encoding="utf-8")


def test_ensure_venv_ready_isolates_pip_and_resolves_reqs(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "VENV_DIR", tmp_path / "venv")
    monkeypatch.setattr(launcher, "SCRIPT_DIR", tmp_path)
    monkeypatch.delenv("SLI_TOOLKIT_DIR", raising=False)
    reqs = tmp_path / "requirements-gui.txt"
    reqs.write_text("-e ../nonexistent-toolkit\npyvips\n")
    monkeypatch.setattr(launcher, "REQUIREMENTS", reqs)

    captured = {}

    def fake_create(ui, venv_dir):
        (venv_dir / "bin").mkdir(parents=True)
        (venv_dir / "bin" / "python").touch()
        return True

    def fake_pip(ui, message, command, requirements, extra_env=None):
        captured["requirements"] = requirements
        captured["extra_env"] = extra_env or {}
        return True

    monkeypatch.setattr(launcher, "create_venv", fake_create)
    monkeypatch.setattr(launcher, "run_pip_with_inline_progress", fake_pip)

    assert launcher.ensure_venv_ready(_quiet_ui()) is not None
    assert captured["extra_env"].get("PIP_CONFIG_FILE") == os.devnull
    assert captured["requirements"].name.endswith(".launcher-resolved.txt")

