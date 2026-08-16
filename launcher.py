"""OS-agnostic dev launcher for Improve-ImgSLI.

Python stdlib-only replacement for the old bash launcher (launcher.sh +
common_launcher_funcs.sh). Entry points are thin wrappers — ``launcher.sh``
(POSIX, bash 3.2-safe) and ``launcher.bat`` (Windows) — that locate a
Python 3 interpreter and exec this module.

CLI surface (argparse subparsers):

    Lifecycle:        install | recreate | delete | rm-cache
    Run & develop:    run | test | context
    System:           install-desktop | uninstall-desktop
                      --enable-logging | --disable-logging
    Info:             help [command] | -h | --help

Top-level flags (``--theme``, ``--debug``/``-d``, ``--ui-inspector``,
``--dump-ui-layout``, ``--open-tab``, ``--run-action``) are shorthand for the
same flags on ``run``, preserving the historical bash behavior.

Behavior notes kept from the bash launcher: the venv lives at ``venv/`` and
is invoked directly (no shell ``activate``); a ``.installed`` marker with a
requirements-file mtime compare drives idempotent dependency installs; app /
pytest / cloc exit codes propagate; progress output only renders on a TTY
(``DISABLE_PROGRESS=1`` forces it off).
"""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
APP_MAIN = SCRIPT_DIR / "src" / "__main__.py"
VENV_DIR = SCRIPT_DIR / "venv"
REQUIREMENTS = SCRIPT_DIR / "requirements-gui.txt"
DEV_REQUIREMENTS = SCRIPT_DIR / "requirements-dev.txt"
CONTEXT_SCRIPT = SCRIPT_DIR / "src" / "devtools" / "context_cloc.py"
DESKTOP_TEMPLATE = SCRIPT_DIR / "improve-imgsli.desktop.in"
APP_ICON = SCRIPT_DIR / "src" / "resources" / "icons" / "icon.png"
DESKTOP_MIME_DIR = SCRIPT_DIR / "build" / "linux" / "mime"
DESKTOP_THUMB_BIN = SCRIPT_DIR / "build" / "linux" / "bin" / "improve-imgsli-thumbnailer"
DESKTOP_THUMB_DESKTOP = SCRIPT_DIR / "build" / "linux" / "thumbnailers"
DESKTOP_ICONS_DIR = SCRIPT_DIR / "build" / "linux" / "icons" / "mimetypes"

_RUN_ALIAS_FLAGS = frozenset(
    {
        "--theme",
        "--debug",
        "-d",
        "--ui-inspector",
        "--dump-ui-layout",
        "--open-tab",
        "--run-action",
    }
)
_LOG_FLAGS = ("--enable-logging", "--disable-logging")

_COLOR_RESET = "\033[0m"
_BG_RED = "\033[0;41m"
_BG_GREEN = "\033[0;42m"
_BG_PROGRESS = "\033[48;5;11m"
_TEXT_WHITE = "\033[1;97m"
_TEXT_BLACK = "\033[1;30m"


class UI:
    """Output hooks (info/status/progress) — replaceable in tests."""

    def __init__(self, progress: bool) -> None:
        self.progress_enabled = progress

    def info(self, message: str) -> None:
        print(message)

    def status(self, message: str, ok: bool) -> None:
        if ok:
            print(f"{message} {_BG_GREEN}{_TEXT_WHITE}[OK]{_COLOR_RESET}")
        else:
            print(f"{message} {_BG_RED}{_TEXT_WHITE}[ERROR]{_COLOR_RESET}")

    def progress(self, message: str) -> None:
        if self.progress_enabled:
            print(f"{message} {_BG_PROGRESS}{_TEXT_BLACK}[..%]{_COLOR_RESET}")


def make_ui() -> UI:
    progress = (
        sys.stdout.isatty() and sys.stderr.isatty() and os.environ.get("DISABLE_PROGRESS") != "1"
    )
    return UI(progress=progress)


def venv_python(venv_dir: Path = VENV_DIR) -> Path:
    win = venv_dir / "Scripts" / "python.exe"
    if win.exists():
        return win
    posix = venv_dir / "bin" / "python"
    if posix.exists():
        return posix
    return win


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_windows() -> bool:
    return os.name == "nt"


# --------------------------------------------------------------------------
# Spinner / pip progress


class _Spinner:
    def __init__(self, ui: UI, message: str) -> None:
        self._ui = ui
        self._message = message
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self._ui.progress_enabled:
            self._ui.info(self._message)
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        spin = r"/-\|"
        i = 0
        while not self._stop.is_set():
            sys.stdout.write(f"\r\033[K{self._message} {spin[i % 4]} ")
            sys.stdout.flush()
            i += 1
            self._stop.wait(0.1)

    def stop(self) -> None:
        if not self._ui.progress_enabled:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()


def run_with_spinner(ui: UI, message: str, fn: Callable[[], bool]) -> bool:
    spinner = _Spinner(ui, message)
    spinner.start()
    try:
        ok = bool(fn())
    finally:
        spinner.stop()
    ui.status(message, ok)
    return ok


def _count_requirements(path: Path) -> int:
    if not path.is_file():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def run_pip_with_inline_progress(
    ui: UI, message: str, command: list[str], requirements: Path, extra_env: dict[str, str] | None = None
) -> bool:
    """Run a pip command, rendering a percentage counter from its output."""
    total = _count_requirements(requirements)

    if not ui.progress_enabled or total == 0:
        ui.info(message)
        env = dict(os.environ)
        if extra_env:
            env.update(extra_env)
        proc = subprocess.run(command, env=env)
        ui.status(message, proc.returncode == 0)
        return proc.returncode == 0

    ui.progress(f"{message} [0%]")
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    assert proc.stderr is not None

    collect_count = 0
    download_count = 0
    COLLECT_WEIGHT = 30
    DOWNLOAD_WEIGHT = 67

    for line in proc.stdout:
        stripped = line.strip()
        if stripped.startswith("Collecting "):
            collect_count += 1
        elif stripped.startswith("Downloading ") or stripped.startswith("Using cached "):
            download_count += 1
        elif stripped.startswith("Requirement already satisfied:"):
            collect_count += 1
            download_count += 1
        elif stripped.startswith("Installing collected packages"):
            collect_count = total
            download_count = total
        percentage = (collect_count * COLLECT_WEIGHT) // total + (
            download_count * DOWNLOAD_WEIGHT
        ) // total
        percentage = min(percentage, 97)
        sys.stdout.write(
            f"\033[A\r\033[K{message} {_BG_PROGRESS}{_TEXT_BLACK}[{percentage}%]{_COLOR_RESET}\n"
        )
        sys.stdout.flush()

    proc.wait()
    stderr_text = proc.stderr.read()
    sys.stdout.write(
        f"\033[A\r\033[K{message} {_BG_PROGRESS}{_TEXT_BLACK}[100%]{_COLOR_RESET}\n"
    )
    sys.stdout.flush()
    if proc.returncode == 0:
        ui.status(message, True)
    else:
        ui.status(message, False)
        if stderr_text:
            sys.stderr.write(stderr_text)
    return proc.returncode == 0


# --------------------------------------------------------------------------
# venv lifecycle


def _is_newer(path_a: Path, path_b: Path) -> bool:
    try:
        return os.path.getmtime(path_a) > os.path.getmtime(path_b)
    except OSError:
        return True


def create_venv(ui: UI, venv_dir: Path) -> bool:
    """Create the venv + upgrade pip (run under the spinner)."""
    if not run_with_spinner(
        ui,
        f"Setting up virtual environment at '{venv_dir}'",
        lambda: subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)]
        ).returncode
        == 0,
    ):
        return False
    py = venv_python(venv_dir)
    if not py.is_file():
        ui.status("Critical error: Failed to create venv", False)
        return False
    return subprocess.run(
        [str(py), "-m", "pip", "install", "--upgrade", "pip", "--disable-pip-version-check", "--quiet"]
    ).returncode == 0


def ensure_venv_ready(ui: UI) -> Path | None:
    """Create / repair / update the venv; returns the venv python path."""
    retry_done = False
    while True:
        if not VENV_DIR.is_dir():
            if not create_venv(ui, VENV_DIR):
                ui.status("Critical error: Failed to create venv", False)
                return None
            py = venv_python(VENV_DIR)
            if not run_pip_with_inline_progress(
                ui,
                "Installing dependencies",
                [str(py), "-m", "pip", "install", "-r", str(REQUIREMENTS), "--disable-pip-version-check"],
                REQUIREMENTS,
            ):
                ui.status("Critical error: Failed to install dependencies in new venv", False)
                if _confirm_removal(ui, VENV_DIR, "failed new virtual environment"):
                    shutil.rmtree(VENV_DIR, ignore_errors=True)
                return None
            (VENV_DIR / ".installed").touch()
            return py

        py = venv_python(VENV_DIR)
        if not py.is_file():
            ui.status("Failed to activate existing venv. Considering it corrupted", False)
            if retry_done:
                ui.status("Error: Retry activation also failed", False)
                return None
            if not _confirm_removal(ui, VENV_DIR, "potentially corrupted virtual environment"):
                ui.status("Refusing to remove corrupted venv without confirmation.", False)
                return None
            ui.info("Removing potentially corrupted venv for recreation...")
            shutil.rmtree(VENV_DIR, ignore_errors=True)
            retry_done = True
            continue

        marker = VENV_DIR / ".installed"
        update_needed = not marker.exists() or _is_newer(REQUIREMENTS, marker)
        if update_needed:
            if not run_pip_with_inline_progress(
                ui,
                "Checking/Updating dependencies",
                [str(py), "-m", "pip", "install", "-r", str(REQUIREMENTS), "--disable-pip-version-check"],
                REQUIREMENTS,
            ):
                ui.status("Dependency installation failed. Venv may be corrupted.", False)
                if retry_done:
                    ui.status("Error: Dependency installation failed again", False)
                    return None
                if not _confirm_removal(ui, VENV_DIR, "virtual environment with failed dependencies"):
                    ui.status("Refusing to remove venv without confirmation.", False)
                    return None
                ui.info("Removing venv for recreation...")
                shutil.rmtree(VENV_DIR, ignore_errors=True)
                retry_done = True
                continue
            marker.touch()
        else:
            ui.status("Dependencies are up to date", True)
        return py


def _confirm_removal(ui: UI, target: Path, description: str) -> bool:
    """Show exactly what will be removed and require explicit Y/n consent.

    Refuses when stdin is not interactive (CI, scripts, tests) or the answer
    is not y/Y. IMGSLI_REMOVE_VENV_YES=1 opts in for headless flows.
    """
    try:
        resolved = target.resolve()
    except OSError:
        resolved = target
    ui.info(f"About to remove {description}: {resolved}")
    if os.environ.get("IMGSLI_REMOVE_VENV_YES") == "1":
        return True
    if not sys.stdin.isatty():
        ui.status("Non-interactive session: refusing to remove without confirmation.", False)
        return False
    try:
        answer = input(f"Remove {description} at '{resolved}'? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def remove_venv_dir(ui: UI, venv_dir: Path, description: str) -> bool:
    # Defense in depth: Path("") is truthy and equal to Path("."), and
    # Path("").is_dir() is True — both would let shutil.rmtree wipe the CWD
    # (this is exactly how the whole repo was deleted on 16.08.2026).
    # Require an absolute path with at least one name component.
    if (
        not venv_dir
        or not venv_dir.is_absolute()
        or len(venv_dir.parts) < 2
        or venv_dir == venv_dir.anchor
    ):
        ui.status("Venv path is invalid. Refusing to remove.", False)
        return False
    # Resolve ONCE and operate on the resolved path: the displayed target and
    # the deleted target are then literally the same object (symlinks can
    # otherwise make the shown path differ from the removed one).
    try:
        venv_dir = venv_dir.resolve()
    except OSError:
        ui.status("Venv path cannot be resolved. Refusing to remove.", False)
        return False
    if not venv_dir.is_dir():
        ui.status(f"{description.capitalize()} not found.", False)
        return False
    if not _confirm_removal(ui, venv_dir, description):
        ui.status(f"Removal of {description} cancelled.", False)
        return False
    ui.info(f"Removing {description} in '{venv_dir}'...")
    try:
        shutil.rmtree(venv_dir)
    except OSError:
        ui.status(f"Failed to remove {description}. Remove manually: {venv_dir}", False)
        return False
    ui.status(f"{description.capitalize()} removed", True)
    return True


def cleanup_python_cache(ui: UI, root: Path, exclude: Path | None = None) -> bool:
    if not root.is_dir():
        ui.status(f"Cache cleanup root does not exist: {root}", False)
        return False
    ui.info(f"Removing Python cache files in '{root}'...")
    removed_dirs = 0
    removed_files = 0
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        if exclude is not None and current_path.resolve() == exclude.resolve():
            dirs[:] = []
            continue
        if "__pycache__" in dirs:
            target = current_path / "__pycache__"
            shutil.rmtree(target, ignore_errors=True)
            removed_dirs += 1
        for name in files:
            if name.endswith((".pyc", ".pyo")):
                try:
                    (current_path / name).unlink()
                    removed_files += 1
                except OSError:
                    pass
    ok = True
    ui.status("Python caches removed" if removed_dirs or removed_files else "No Python caches found", ok)
    return ok


# --------------------------------------------------------------------------
# Desktop integration (Linux-only)


def _write_if_changed(path: Path, content: bytes, mode: int | None = None) -> bool:
    try:
        existing = path.read_bytes()
    except OSError:
        existing = None
    if existing == content:
        return False
    path.write_bytes(content)
    if mode is not None:
        path.chmod(mode)
    return True


def _copy_if_changed(src: Path, dst: Path, mode: int | None = None) -> bool:
    if src.is_file() and dst.is_file() and filecmp.cmp(src, dst, shallow=False):
        return False
    shutil.copy2(src, dst)
    if mode is not None:
        dst.chmod(mode)
    return True


def _run_tool(tool: str, args: list[str]) -> None:
    if shutil.which(tool) is None:
        return
    subprocess.run([tool, *args], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def desktop_integration(ui: UI, mode: str = "quiet") -> bool:
    """Idempotent Linux .desktop / MIME / thumbnailer install (quiet sync)."""
    if not is_linux():
        if mode == "verbose":
            ui.info("Desktop integration is Linux-only; skipping.")
        return True

    home = Path.home()
    target = home / ".local" / "share" / "applications" / "improve-imgsli.desktop"
    mime_dst = home / ".local" / "share" / "mime" / "packages" / "application-x-improve-imgsli.xml"
    thumb_bin_dst = home / ".local" / "bin" / "improve-imgsli-thumbnailer"
    thumb_desktop_dst = home / ".local" / "share" / "thumbnailers" / "improve-imgsli.thumbnailer"
    mark_dst = home / ".local" / "share" / "improve-imgsli" / "mark.png"
    mime_src = DESKTOP_MIME_DIR / "application-x-improve-imgsli.xml"
    thumb_desktop_src = DESKTOP_THUMB_DESKTOP / "improve-imgsli.thumbnailer"

    if not DESKTOP_TEMPLATE.is_file():
        return False

    desktop_changed = 0
    mime_changed = 0
    thumb_changed = 0
    icons_changed = 0

    template = DESKTOP_TEMPLATE.read_text(encoding="utf-8")
    content = (
        template.replace("@LAUNCHER_PATH@", str(SCRIPT_DIR / "launcher.sh"))
        .replace("@ICON_PATH@", str(APP_ICON))
        .encode("utf-8")
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if _write_if_changed(target, content):
        target.chmod(0o755)
        desktop_changed = 1

    if mime_src.is_file():
        mime_dst.parent.mkdir(parents=True, exist_ok=True)
        if _copy_if_changed(mime_src, mime_dst):
            mime_changed = 1

    if DESKTOP_THUMB_BIN.is_file() and thumb_desktop_src.is_file():
        thumb_bin_dst.parent.mkdir(parents=True, exist_ok=True)
        thumb_desktop_dst.parent.mkdir(parents=True, exist_ok=True)
        mark_dst.parent.mkdir(parents=True, exist_ok=True)
        if _copy_if_changed(DESKTOP_THUMB_BIN, thumb_bin_dst, mode=0o755):
            thumb_changed = 1
        if _copy_if_changed(thumb_desktop_src, thumb_desktop_dst):
            thumb_changed = 1
        if APP_ICON.is_file() and _copy_if_changed(APP_ICON, mark_dst):
            thumb_changed = 1

    if DESKTOP_ICONS_DIR.is_dir():
        for size in ("16", "22", "32", "48", "64", "128", "256"):
            icon_src = DESKTOP_ICONS_DIR / f"application-x-improve-imgsli-{size}.png"
            if not icon_src.is_file():
                continue
            icon_dst = (
                home
                / ".local"
                / "share"
                / "icons"
                / "hicolor"
                / f"{size}x{size}"
                / "mimetypes"
                / "application-x-improve-imgsli.png"
            )
            icon_dst.parent.mkdir(parents=True, exist_ok=True)
            if _copy_if_changed(icon_src, icon_dst):
                icons_changed = 1

    if desktop_changed:
        _run_tool("update-desktop-database", [str(home / ".local" / "share" / "applications")])
        ui.info(f"Desktop entry updated: {target}")
    elif mode == "verbose":
        ui.info(f"Desktop entry already up to date: {target}")

    if mime_changed or icons_changed:
        _run_tool("update-mime-database", [str(home / ".local" / "share" / "mime")])
        _run_tool("xdg-mime", ["default", "improve-imgsli.desktop", "application/x-improve-imgsli"])
        if icons_changed:
            _run_tool(
                "gtk-update-icon-cache",
                ["-f", "-t", str(home / ".local" / "share" / "icons" / "hicolor")],
            )
            _run_tool("xdg-icon-resource", ["forceupdate", "--theme", "hicolor"])
        _run_tool("kbuildsycoca6", ["--noincremental"])
        _run_tool("kbuildsycoca5", ["--noincremental"])
        if mime_changed:
            ui.info("MIME type installed/updated (application/x-improve-imgsli).")
        if icons_changed:
            ui.info("MIME icons installed (document + mark + IMGSLI).")
        if mode == "verbose":
            ui.info("If Dolphin still shows Zip/old icon: killall dolphin; clear ~/.cache/thumbnails.")
    elif mode == "verbose":
        ui.info("MIME type / icons already up to date (application/x-improve-imgsli).")
        _run_tool("xdg-mime", ["default", "improve-imgsli.desktop", "application/x-improve-imgsli"])

    if thumb_changed:
        ui.info("Thumbnailer installed/updated (document-framed preview.png).")
        if f"{home / '.local' / 'bin'}" not in os.environ.get("PATH", ""):
            ui.info("Note: ensure ~/.local/bin is on PATH so the thumbnailer is found.")
    elif mode == "verbose":
        ui.info("Thumbnailer already up to date.")

    return True


def desktop_uninstall(ui: UI) -> bool:
    if not is_linux():
        ui.info("Desktop integration is Linux-only; skipping.")
        return True

    home = Path.home()
    target = home / ".local" / "share" / "applications" / "improve-imgsli.desktop"
    mime_xml = home / ".local" / "share" / "mime" / "packages" / "application-x-improve-imgsli.xml"
    thumb_bin = home / ".local" / "bin" / "improve-imgsli-thumbnailer"
    thumb_desktop = home / ".local" / "share" / "thumbnailers" / "improve-imgsli.thumbnailer"
    mark_dst = home / ".local" / "share" / "improve-imgsli" / "mark.png"

    if target.is_file():
        target.unlink()
        _run_tool("update-desktop-database", [str(home / ".local" / "share" / "applications")])
        ui.status("Desktop entry removed", True)
    else:
        ui.info("Desktop entry not found, nothing to remove.")

    if mime_xml.is_file():
        mime_xml.unlink()
        _run_tool("update-mime-database", [str(home / ".local" / "share" / "mime")])
        ui.info("MIME type removed.")

    for size in ("16", "22", "32", "48", "64", "128", "256"):
        icon_dst = (
            home
            / ".local"
            / "share"
            / "icons"
            / "hicolor"
            / f"{size}x{size}"
            / "mimetypes"
            / "application-x-improve-imgsli.png"
        )
        icon_dst.unlink(missing_ok=True)
    _run_tool("gtk-update-icon-cache", ["-f", "-t", str(home / ".local" / "share" / "icons" / "hicolor")])

    for path in (thumb_bin, thumb_desktop, mark_dst):
        path.unlink(missing_ok=True)
    return True


# --------------------------------------------------------------------------
# Actions


def _app_env() -> dict[str, str]:
    env = dict(os.environ)
    src_path = str(SCRIPT_DIR / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return env


def run_action(args: argparse.Namespace, extras: list[str], ui: UI) -> int:
    py = ensure_venv_ready(ui)
    if py is None:
        ui.status("Failed to prepare environment. Aborting.", False)
        return 1
    if is_linux():
        desktop_integration(ui, mode="quiet")

    ui.info("Starting Improve ImgSLI...")
    gui_args: list[str] = []
    if args.ui_inspector:
        gui_args.append("--ui-inspector")
    if args.debug:
        gui_args.append("--debug")
    gui_args.extend(extras)

    env = _app_env()
    if args.theme is not None:
        env["APP_THEME"] = args.theme

    command = [str(py), str(APP_MAIN), *gui_args]
    try:
        proc = subprocess.Popen(command, env=env)
        returncode = proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        returncode = 130
    ui.info(f"Application completed with exit code: {returncode}")
    return returncode


def test_action(args: argparse.Namespace, extras: list[str], ui: UI) -> int:
    py = ensure_venv_ready(ui)
    if py is None:
        ui.status("Failed to prepare environment. Aborting.", False)
        return 1

    has_tests_deps = (
        subprocess.run(
            [str(py), "-c", "import pytest, pytest_sugar"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )
    if not has_tests_deps:
        if not run_pip_with_inline_progress(
            ui,
            "Installing test dependencies",
            [str(py), "-m", "pip", "install", "-r", str(DEV_REQUIREMENTS)],
            DEV_REQUIREMENTS,
        ):
            return 1

    ui.info("Running test suite...")
    proc = subprocess.run([str(py), "-m", "pytest", *extras], cwd=SCRIPT_DIR)
    ui.info(f"Tests completed with exit code: {proc.returncode}")
    return proc.returncode


def context_action(args: argparse.Namespace, extras: list[str], ui: UI) -> int:
    if not CONTEXT_SCRIPT.is_file():
        ui.status(f"Context script not found: {CONTEXT_SCRIPT}", False)
        return 1
    ui.info("Running context bundle...")
    proc = subprocess.run(
        [sys.executable, str(CONTEXT_SCRIPT), *extras],
        cwd=SCRIPT_DIR,
    )
    return proc.returncode


def install_action(args: argparse.Namespace, extras: list[str], ui: UI) -> int:
    if ensure_venv_ready(ui) is None:
        ui.status("Failed to set up environment.", False)
        return 1
    return 0


def recreate_action(args: argparse.Namespace, extras: list[str], ui: UI) -> int:
    ui.info("Recreating virtual environment...")
    if not remove_venv_dir(ui, VENV_DIR, "existing virtual environment"):
        return 1
    if ensure_venv_ready(ui) is None:
        ui.status("Failed to recreate environment.", False)
        return 1
    return 0


def delete_action(args: argparse.Namespace, extras: list[str], ui: UI) -> int:
    ui.info("Starting cleanup...")
    if not remove_venv_dir(ui, VENV_DIR, "virtual environment"):
        return 1
    cleanup_python_cache(ui, SCRIPT_DIR, exclude=VENV_DIR)
    ui.info("Cleanup completed.")
    return 0


def rm_cache_action(args: argparse.Namespace, extras: list[str], ui: UI) -> int:
    cleanup_python_cache(ui, SCRIPT_DIR, exclude=VENV_DIR)
    return 0


def logging_action(enable: bool, ui: UI) -> int:
    flag = "--enable-logging" if enable else "--disable-logging"
    ui.info(f"Attempting to {flag.lstrip('-').replace('-', ' ')}...")
    py = ensure_venv_ready(ui)
    if py is None:
        ui.status("Failed to prepare environment. Aborting.", False)
        return 1
    proc = subprocess.run([str(py), str(APP_MAIN), flag], env=_app_env())
    ui.status("Logging settings updated", proc.returncode == 0)
    return proc.returncode


# --------------------------------------------------------------------------
# CLI


TOP_HELP = """\
usage: launcher.sh [run flags] <command> [args...]
       launcher.sh run [flags] [app args...]

Improve-ImgSLI dev launcher: venv bootstrap, app run, tests, cloc context,
and Linux desktop integration.

Commands:
  Lifecycle:
    install             Create the virtual environment and/or install dependencies
    recreate            Recreate the virtual environment from scratch
    delete              Delete the virtual environment and Python caches
    rm-cache            Remove Python caches without deleting the venv
  Run & develop:
    run                 Run the application (GUI)
    test                Run the test suite (pytest); extra args pass through
    context             cloc report for app + sli-ui-toolkit
  System:
    install-desktop     Install .desktop / .imgsli MIME / thumbnailer (Linux only)
    uninstall-desktop   Remove .desktop / MIME / thumbnailer (Linux only)
    --enable-logging    Permanently enable debug logging
    --disable-logging   Permanently disable debug logging
  Info:
    help [command]      Show help for a command
    -h, --help          Show this help

Top-level flags are shorthand for 'run':
  --theme dark|light    Force a specific theme for this session
  --debug, -d           Debug logging for this session only
  --ui-inspector        Enable the developer UI inspector (implies --debug)
  --dump-ui-layout PATH Dump widget tree + geometry + Find Action ids to PATH, then exit
  --open-tab KIND       Create and switch to that tab kind on startup
  --run-action ID       Run this Find Action id on startup (repeatable)

Examples:
  ./launcher.sh run                          Start the app
  ./launcher.sh run --theme dark --debug     Dark theme + debug session
  ./launcher.sh test tests/runtime -k gesture
  ./launcher.sh context --cloc-only          cloc tables only → cloc.txt
  ./launcher.sh help run                     Full details for 'run'
"""


class _TopHelpFormatter(argparse.RawDescriptionHelpFormatter):
    def format_help(self) -> str:
        return TOP_HELP + "\n"


def build_parser() -> tuple[argparse.ArgumentParser, dict[str, argparse.ArgumentParser]]:
    parser = argparse.ArgumentParser(
        prog="launcher.sh",
        add_help=False,
        formatter_class=_TopHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        dest="command", metavar="<command>", prog="launcher.sh"
    )
    commands: dict[str, argparse.ArgumentParser] = {}

    run = subparsers.add_parser(
        "run",
        help="Run the application (GUI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""\
Run the application (GUI).

Launcher-owned flags (--theme, --debug/-d, --ui-inspector) are consumed by
the launcher; every other argument passes through to the app verbatim, e.g.:

  ./launcher.sh run --theme dark --open-tab image_compare --dump-ui-layout /tmp/layout.json
  ./launcher.sh run --run-action platform.settings --dump-ui-layout /tmp/layout.json

--ui-inspector implies --debug. On Linux, 'run' also syncs the .desktop /
.imgsli MIME / thumbnailer when outdated.
""",
    )
    run.add_argument("--theme", choices=("dark", "light"), help="force a specific theme")
    run.add_argument("--debug", "-d", action="store_true", help="debug logging for this session only")
    run.add_argument("--ui-inspector", action="store_true", help="enable the developer UI inspector (implies --debug)")

    test = subparsers.add_parser(
        "test",
        help="Run the test suite (pytest)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""\
Run the test suite (pytest). Extra args pass through, e.g.:

  ./launcher.sh test tests/runtime -k gesture
  ./launcher.sh test tests/plugins/test_help_plugin.py -q
""",
    )

    context = subparsers.add_parser(
        "context",
        help="cloc report for app + sli-ui-toolkit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""\
cloc report for Improve-ImgSLI and the external sli-ui-toolkit.

  ./launcher.sh context --cloc-only   cloc tables only → cloc.txt

See 'src/devtools/context_cloc.py --help' for the full option set.
""",
    )

    install = subparsers.add_parser(
        "install",
        help="Create the venv and/or install dependencies",
        description="Create the virtual environment and/or install dependencies.",
    )
    recreate = subparsers.add_parser(
        "recreate",
        help="Recreate the virtual environment from scratch",
        description="Forcibly recreate the virtual environment.",
    )
    delete = subparsers.add_parser(
        "delete",
        help="Delete the virtual environment and Python caches",
        description="Delete the virtual environment and Python caches.",
    )
    rm_cache = subparsers.add_parser(
        "rm-cache",
        help="Remove Python caches without deleting the venv",
        description="Remove Python caches without deleting the virtual environment.",
    )
    install_desktop = subparsers.add_parser(
        "install-desktop",
        help="Install .desktop / .imgsli MIME / thumbnailer (Linux)",
        description="Install .desktop, .imgsli MIME type, and thumbnailer (Linux only).",
    )
    uninstall_desktop = subparsers.add_parser(
        "uninstall-desktop",
        help="Remove .desktop / MIME / thumbnailer (Linux)",
        description="Remove .desktop / MIME / thumbnailer (Linux only).",
    )
    help_cmd = subparsers.add_parser(
        "help",
        help="Show help for a command",
        description="Show help for a command (or the top-level help).",
    )
    help_cmd.add_argument("topic", nargs="?", default=None, metavar="command")

    for name, sp in (
        ("run", run),
        ("test", test),
        ("context", context),
        ("install", install),
        ("recreate", recreate),
        ("delete", delete),
        ("rm-cache", rm_cache),
        ("install-desktop", install_desktop),
        ("uninstall-desktop", uninstall_desktop),
        ("help", help_cmd),
    ):
        commands[name] = sp
    return parser, commands


DISPATCH = {
    "run": run_action,
    "test": test_action,
    "context": context_action,
    "install": install_action,
    "recreate": recreate_action,
    "delete": delete_action,
    "rm-cache": rm_cache_action,
    "install-desktop": lambda a, e, ui: (0 if desktop_integration(ui, mode="verbose") else 1),
    "uninstall-desktop": lambda a, e, ui: (0 if desktop_uninstall(ui) else 1),
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        print(TOP_HELP)
        return 0

    if argv[0] in _LOG_FLAGS:
        return logging_action(argv[0] == "--enable-logging", make_ui())

    if argv[0] in _RUN_ALIAS_FLAGS:
        argv.insert(0, "run")

    parser, commands = build_parser()
    args, extras = parser.parse_known_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "help":
        topic = extras[0] if extras else args.topic
        if topic is None:
            parser.print_help()
            return 0
        target = commands.get(topic)
        if target is None:
            print(f"Error: unknown help topic '{topic}'")
            return 2
        target.print_help()
        return 0

    handler = DISPATCH[args.command]
    return handler(args, extras, make_ui())


if __name__ == "__main__":
    raise SystemExit(main())
