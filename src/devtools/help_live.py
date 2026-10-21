#!/usr/bin/env python3
"""Live help figures: boot a private app, drive it over the control socket.

Devtool only. The renders of the reproducible devtool surfaces live in
``help_figures.py``; this module covers figures that only exist in a *running*
app (real QRhi canvases, flyouts, session chrome). See
``docs/dev/SCREENSHOTS.md`` § Live figures and the method runbook
``RUNBOOK_LIVE_MCP_VERIFICATION.md`` in the internal-docs repo.

    python src/devtools/help_live.py --list
    python src/devtools/help_live.py --figure help-toolbar
    python src/devtools/help_live.py --all --out /tmp/live-shots

Rules this tool enforces (each one exists because a real capture lied):

* **All four XDG dirs are isolated** (DATA, CACHE, CONFIG, RUNTIME). CONFIG is
  where ``QSettings`` keeps theme/language/window geometry — a recon that
  isolated only three read the host's settings.
* **The profile is seeded before boot** (``improve-imgsli.conf``), so theme,
  language, UI mode and window size are the recipe's, not the host's, and no
  live ``set_theme``/``set_language`` rebuild is needed.
* **A figure installs only after two consecutive captures are byte-identical.**
  Live pixels are not gated in CI (no cross-host promise), but a single frame
  is not evidence: the harness retries the capture until the hash repeats.
* Chapter and verse: never ``:0``, always ``LIBGL_ALWAYS_SOFTWARE=1`` +
  ``QT_QPA_PLATFORM=xcb``; ``capture_live`` reports ``rhi_layers`` and a
  canvas figure with ``rhi_layers == 0`` is refused.

Audit-Meta: pattern=devtool-pipeline size=exempt reason="one live-capture contract: profile seed + app lifecycle + socket client + scenario + stable-capture/crop/install all share the same recipe schema; splitting forks the meaning of a live figure"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from devtools import capture_surface  # noqa: E402  — canonical font/DPI bootstrap
from devtools.help_figures import _free_display_number, xvfb_command  # noqa: E402

RECIPE_PATH = Path(__file__).with_name("help_figures_live.json")
SCHEMA_VERSION = 1
SAMPLE_NAMES = ("sunset", "forest", "ocean", "desert")
#: App boot budget. A blank window is not a capture; the app logs the control
#: socket line when it is ready and the client pings it before any scenario.
BOOT_TIMEOUT_S = 60.0
#: Stable-capture policy: two identical hashes in a row, this many attempts.
STABLE_ATTEMPTS = 14
STABLE_INTERVAL_S = 0.7


class LiveError(RuntimeError):
    """The live app could not be driven or produced no trustworthy frame."""


@dataclass(frozen=True)
class Step:
    """One scenario step, already validated (kind, kwargs)."""

    kind: str
    kwargs: dict


@dataclass(frozen=True)
class LiveFigure:
    id: str
    capture: str
    steps: tuple[Step, ...]
    destination: str
    crop: tuple[int, int, int, int] | None
    locales: tuple[str, ...]
    themes: tuple[str, ...]
    note: str
    min_size: tuple[int, int] | None = None
    crop_element: dict | None = None
    rhi_backend: str = "opengl"
    stable_interval_s: float = STABLE_INTERVAL_S


def _parse_step(raw: dict, figure_id: str) -> Step:
    if not isinstance(raw, dict) or len(raw) != 1:
        raise ValueError(f"{figure_id}: a step is one-key dict, got {raw!r}")
    (kind, value), = raw.items()
    if kind == "open_tab":
        return Step("open_tab", {"tab": str(value)})
    if kind == "open_folder":
        if not isinstance(value, dict):
            raise ValueError(f"{figure_id}: open_folder needs a dict")
        kwargs = {"path": str(value.get("path") or "")}
        if value.get("tab"):
            kwargs["tab"] = str(value["tab"])
        if "slot" in value:
            kwargs["slot"] = int(value["slot"])
        if "side" in value:
            kwargs["side"] = str(value["side"])
        return Step("open_folder", kwargs)
    if kind in ("run_action", "press_keys"):
        return Step(kind, {"action_id" if kind == "run_action" else "keys": str(value)})
    if kind == "sleep":
        return Step("sleep", {"seconds": float(value)})
    if kind == "wait_jobs":
        return Step("wait_jobs", {"timeout_s": float(value)})
    if kind == "ui_click":
        if not isinstance(value, dict):
            raise ValueError(f"{figure_id}: ui_click needs a dict")
        kwargs = {}
        if value.get("role"):
            kwargs["role"] = str(value["role"])
        if value.get("label"):
            kwargs["label"] = str(value["label"])
        if value.get("id"):
            kwargs["id"] = str(value["id"])
        if value.get("element"):
            kwargs["id"] = str(value["element"])
        if not kwargs:
            raise ValueError(f"{figure_id}: ui_click needs element or role/label")
        return Step("ui_click", kwargs)
    raise ValueError(f"{figure_id}: unknown step {kind!r}")


def load_recipes(path: Path = RECIPE_PATH) -> tuple[LiveFigure, ...]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{path}: schema_version != {SCHEMA_VERSION}")
    figures = []
    for entry in raw.get("figures") or []:
        figure_id = str(entry.get("id") or "")
        destination = str(entry.get("destination") or "")
        if not figure_id or not destination:
            raise ValueError(f"{path}: figure needs id + destination")
        crop = entry.get("crop")
        figures.append(
            LiveFigure(
                id=figure_id,
                capture=str(entry.get("capture") or ""),
                steps=tuple(_parse_step(step, figure_id) for step in entry.get("steps") or []),
                destination=destination,
                crop=tuple(int(v) for v in crop) if crop else None,
                locales=tuple(entry.get("locales") or ("en",)),
                themes=tuple(entry.get("themes") or ("dark",)),
                note=str(entry.get("note") or ""),
                min_size=tuple(int(v) for v in entry["min_size"]) if entry.get("min_size") else None,
                crop_element=dict(entry["crop_element"]) if entry.get("crop_element") else None,
                rhi_backend=str(entry.get("rhi_backend") or "opengl"),
                stable_interval_s=float(entry.get("stable_interval_s") or STABLE_INTERVAL_S),
            )
        )
    return tuple(figures)


# --- profile + app lifecycle -------------------------------------------------


def ensure_samples(out_dir: Path) -> Path:
    """Deterministic demo images (same gradients as the devtool surfaces)."""
    samples = out_dir / "_samples"
    samples.mkdir(parents=True, exist_ok=True)
    if all((samples / f"{name}.png").is_file() for name in SAMPLE_NAMES):
        return samples
    from PIL import Image, ImageDraw

    specs = {
        "sunset": ((230, 120, 60), (40, 20, 90)),
        "forest": ((60, 160, 90), (10, 40, 30)),
        "ocean": ((60, 140, 220), (10, 30, 80)),
        "desert": ((230, 200, 120), (120, 80, 40)),
    }
    for name, (top, bottom) in specs.items():
        image = Image.new("RGB", (1280, 800))
        draw = ImageDraw.Draw(image)
        for y in range(800):
            t = y / 799
            draw.line(
                [(0, y), (1280, y)],
                fill=tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3)),
            )
        draw.ellipse([500, 300, 780, 580], fill=(255, 240, 200))
        draw.text((40, 40), name, fill=(255, 255, 255))
        image.save(samples / f"{name}.png")
    three = samples / "three"
    three.mkdir(parents=True, exist_ok=True)
    for name in ("sunset", "forest", "ocean"):
        shutil.copyfile(samples / f"{name}.png", three / f"{name}.png")
    for name in specs:
        single = samples / "singles" / name / f"{name}.png"
        single.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(samples / f"{name}.png", single)
    return samples


def write_profile(
    root: Path,
    *,
    locale: str,
    theme: str,
    width: int,
    height: int,
    rhi_backend: str = "opengl",
) -> Path:
    """Seed QSettings before boot (theme, language, UI mode, window geometry).

    ``QSettings("improve-imgsli", "improve-imgsli")`` writes the INI below
    ``XDG_CONFIG_HOME``. Seeding it is what makes a variant figure possible
    without a live theme/language rebuild (measured: ``set_theme`` /
    ``set_language`` answer ``applied`` but the open window does not repaint).
    """
    profile = root / "config" / "improve-imgsli" / "improve-imgsli.conf"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(
        "[General]\n"
        f"theme={theme}\n"
        f"language={locale}\n"
        "ui_mode=advanced\n"
        "is_first_run=false\n"
        f"window_width={width}\n"
        f"window_height={height}\n"
        "window_x=0\n"
        "window_y=0\n"
        "window_was_maximized=false\n"
        # Neutral, fictional locations: the export dialog shows this string, so
        # a real home directory would put the maintainer's username into a
        # shipped figure (and HOME is sandboxed below for the same reason).
        "export_default_dir=/home/user/Pictures\n"
        f"rhi_backend={rhi_backend}\n",
        encoding="utf-8",
    )
    return profile


class LiveClient:
    """Minimal one-line-JSON client for the app's control socket."""

    def __init__(self, path: Path, timeout: float = 120.0) -> None:
        self.path = Path(path)
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._buffer = b""
        self._counter = 0

    def _connect(self) -> socket.socket:
        if self._sock is not None:
            return self._sock
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(str(self.path))
        self._sock = sock
        return sock

    def call(self, method: str, params: dict | None = None) -> dict:
        sock = self._connect()
        self._counter += 1
        request = {"id": self._counter, "method": method, "params": params or {}}
        sock.sendall(json.dumps(request).encode("utf-8") + b"\n")
        deadline = time.monotonic() + self.timeout
        while True:
            if b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
            else:
                if time.monotonic() > deadline:
                    raise LiveError(f"{method}: timed out waiting for the app")
                chunk = sock.recv(65536)
                if not chunk:
                    raise LiveError(f"{method}: the app closed the socket")
                self._buffer += chunk
                continue
            if not line.strip():
                continue
            message = json.loads(line)
            if message.get("id") != self._counter:
                continue
            if not message.get("ok"):
                raise LiveError(f"{method}: {message.get('error')} ({message.get('hint')})")
            return message.get("result") or {}

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None


class LiveApp:
    """One private app instance on a private Xvfb with a seeded profile."""

    def __init__(self, *, backend: str, out_dir: Path, locale: str, theme: str,
                 width: int, height: int, rhi_backend: str = "opengl") -> None:
        self.backend = backend
        self.out_dir = Path(out_dir)
        self.locale = locale
        self.theme = theme
        self.width = width
        self.height = height
        self.rhi_backend = rhi_backend
        self.root = self.out_dir / f"profile__{locale}__{theme}"
        for name in ("data", "cache", "config", "run", "artifacts"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        os.chmod(self.root / "run", 0o700)
        self._display_proc: subprocess.Popen | None = None
        self._app_proc: subprocess.Popen | None = None
        self._previous_display: str | None = None
        self.client: LiveClient | None = None

    def __enter__(self) -> "LiveApp":
        write_profile(self.root, locale=self.locale, theme=self.theme,
                      width=self.width, height=self.height,
                      rhi_backend=self.rhi_backend)
        if self.backend == "xvfb":
            if shutil.which("Xvfb") is None:
                raise LiveError("Xvfb not found on PATH")
            number = _free_display_number()
            self._display_proc = subprocess.Popen(
                xvfb_command(number),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            display = f":{number}"
            deadline = time.monotonic() + 10
            while not (Path(f"/tmp/.X11-unix/X{number}").exists()):
                if time.monotonic() > deadline:
                    raise LiveError(f"Xvfb :{number} did not start")
                time.sleep(0.05)
        else:
            display = (os.environ.get("DISPLAY") or "").strip()
            if not display:
                raise LiveError("backend 'native' needs DISPLAY")
        self._previous_display = os.environ.get("DISPLAY")
        os.environ["DISPLAY"] = display
        env = dict(os.environ)
        home = self.root / "home"
        home.mkdir(parents=True, exist_ok=True)
        env.update(
            HOME=str(home),
            QT_QPA_PLATFORM="xcb",
            LIBGL_ALWAYS_SOFTWARE="1",
            XDG_DATA_HOME=str(self.root / "data"),
            XDG_CACHE_HOME=str(self.root / "cache"),
            XDG_CONFIG_HOME=str(self.root / "config"),
            XDG_RUNTIME_DIR=str(self.root / "run"),
            IMGSLI_CONTROL="1",
            IMGSLI_MCP_ARTIFACTS=str(self.root / "artifacts"),
        )
        log = (self.root / "app.log").open("w", encoding="utf-8")
        self._app_proc = subprocess.Popen(
            [sys.executable, "src/__main__.py"],
            cwd=str(REPO_ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        socket_path = self.root / "run" / "control.sock"
        deadline = time.monotonic() + BOOT_TIMEOUT_S
        while True:
            if self._app_proc.poll() is not None:
                raise LiveError(f"app exited during boot (log: {self.root / 'app.log'})")
            if socket_path.exists():
                try:
                    self.client = LiveClient(socket_path)
                    self.client.call("ping")
                    break
                except (OSError, LiveError):
                    self.client = None
            if time.monotonic() > deadline:
                raise LiveError("app did not expose the control socket in time")
            time.sleep(0.2)
        return self

    def __exit__(self, *exc) -> None:
        if self.client is not None:
            self.client.close()
        if self._app_proc is not None and self._app_proc.poll() is None:
            self._app_proc.terminate()
            try:
                self._app_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._app_proc.kill()
                self._app_proc.wait(timeout=5)
        if self._display_proc is not None:
            self._display_proc.terminate()
            try:
                self._display_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._display_proc.kill()
        if self._previous_display is None:
            os.environ.pop("DISPLAY", None)
        else:
            os.environ["DISPLAY"] = self._previous_display


# --- scenario + capture -------------------------------------------------------


def wait_for_active_session(app: LiveClient, kind: str, timeout: float = 20.0) -> None:
    """Wait until a session of *kind* exists and is active (no fixed sleep)."""
    deadline = time.monotonic() + timeout
    while True:
        sessions = app.call("list_sessions").get("sessions") or []
        if any(s.get("session_type") == kind and s.get("active") for s in sessions):
            return
        if time.monotonic() > deadline:
            raise LiveError(f"no active {kind!r} session after {timeout:.0f}s")
        time.sleep(0.2)


def run_steps(app: LiveClient, figure: LiveFigure, samples: Path) -> None:
    for step in figure.steps:
        kwargs = dict(step.kwargs)
        if step.kind == "open_folder":
            kwargs["path"] = kwargs["path"].replace("@samples", str(samples))
        for key, value in list(kwargs.items()):
            if isinstance(value, str) and "@samples" in value:
                kwargs[key] = value.replace("@samples", str(samples))
        if step.kind == "sleep":
            time.sleep(kwargs["seconds"])
            continue
        if step.kind == "wait_jobs":
            deadline = time.monotonic() + kwargs["timeout_s"]
            quiet = 0
            while quiet < 2:
                count = int(app.call("jobs_list").get("count") or 0)
                quiet = quiet + 1 if count == 0 else 0
                if time.monotonic() > deadline:
                    raise LiveError(f"jobs did not settle within {kwargs['timeout_s']:.0f}s")
                time.sleep(0.4)
            continue
        if step.kind == "open_tab":
            app.call("open_tab", kwargs)
            wait_for_active_session(app, kwargs["tab"])
            continue
        if step.kind == "open_folder" and kwargs.get("tab"):
            wait_for_active_session(app, kwargs["tab"])
        app.call(step.kind, kwargs)


def _screen_png(app: LiveClient, out_path: Path) -> Path:
    """Whole-X-screen grab (popups included), for flyout/menu figures.

    ``capture_live`` grabs one window; a toolkit flyout is a separate popup
    window, so it is absent from that grab (measured: the menu is in
    ``ui_elements`` while the window capture shows only chrome). The screen
    image is 1:1 with screen coordinates, which is exactly what an element's
    ``screen_rect`` names.
    """
    tmp = out_path.with_suffix(".xwd")
    subprocess.run(["xwd", "-silent", "-root", "-out", str(tmp)], check=True,
                   env=dict(os.environ))
    subprocess.run(["convert", str(tmp), str(out_path)], check=True,
                   env=dict(os.environ))
    tmp.unlink(missing_ok=True)
    return out_path


def stable_capture(app: LiveClient, what: str, out_path: Path,
                   min_size: tuple[int, int] | None = None,
                   interval_s: float = STABLE_INTERVAL_S) -> Path:
    """Capture until two consecutive frames are byte-identical."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    previous: str | None = None
    for attempt in range(STABLE_ATTEMPTS):
        if what == "@screen":
            source = _screen_png(app, out_path)
            data = source.read_bytes()
            result = {"size": _image_size(source)}
        else:
            result = app.call(
                "capture_live", {} if what == "@window" else {"what": what}
            )
        if min_size is not None:
            width, height = (int(v) for v in result.get("size") or (0, 0))
            if width < min_size[0] or height < min_size[1]:
                raise LiveError(
                    f"{what}: captured {width}x{height}, smaller than the recipe's "
                    f"min_size {min_size[0]}x{min_size[1]} - that is a helper/warning "
                    "window, not the figure"
                )
        if what == "@screen":
            digest = hashlib.sha256(data).hexdigest()
            if digest == previous:
                return out_path
            previous = digest
            time.sleep(interval_s)
            continue
        source = Path(result["path"])
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest == previous:
            out_path.write_bytes(data)
            return out_path
        previous = digest
        time.sleep(interval_s)
    raise LiveError(f"{what}: no two consecutive captures matched in {STABLE_ATTEMPTS} attempts")


def _image_size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def _element_crop(app: LiveClient, spec: dict) -> tuple[int, int, int, int, int]:
    """Read one element's screen rect as ``(pad, x, y, w, h)`` (no crop math)."""
    """Crop box for one live element (menu/flyout), from its screen rect."""
    params = {}
    for key in ("role", "label"):
        if spec.get(key):
            params[key] = str(spec[key])
    if not params:
        raise LiveError("crop_element needs role and/or label")
    elements = app.call("ui_elements", params).get("elements") or []
    if not elements:
        raise LiveError(f"crop_element: no element matched {params!r}")
    rect = elements[0].get("screen_rect") or elements[0].get("rect")
    if not rect or len(rect) != 4:
        raise LiveError(f"crop_element: element has no screen rect ({params!r})")
    pad = int(spec.get("pad", 6))
    x, y, width, height = (int(v) for v in rect)
    return pad, x, y, width, height


def crop_and_install(
    screenshot: Path, destination: Path, crop: tuple[int, int, int, int] | None
) -> Path:
    from PIL import Image

    with Image.open(screenshot) as image:
        if crop is not None:
            x, y, w, h = crop
            image = image.crop((x, y, x + w, y + h))
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.suffix.lower() in (".jpg", ".jpeg"):
            image.convert("RGB").save(destination, format="JPEG", quality=95, subsampling=0)
        else:
            image.save(destination)
    return destination


# --- CLI ----------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture help figures from a live app instance.")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--figure", action="append", metavar="ID")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--out", default=None)
    parser.add_argument("--backend", choices=("xvfb", "native"), default="xvfb")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--manifest", default=str(RECIPE_PATH))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    figures = load_recipes(Path(args.manifest))
    if args.list:
        for figure in figures:
            print(f"{figure.id:28} capture={figure.capture:16} crop={figure.crop} "
                  f"locales={','.join(figure.locales)} themes={','.join(figure.themes)}")
            print(f"    -> {figure.destination}")
        return 0
    selected = figures
    if args.figure:
        known = {f.id for f in figures}
        unknown = [fid for fid in args.figure if fid not in known]
        if unknown:
            print(f"unknown figure: {', '.join(unknown)}", file=sys.stderr)
            return 2
        selected = [f for f in figures if f.id in set(args.figure)]
    elif not args.all:
        print("choose --list, --figure ID or --all", file=sys.stderr)
        return 2
    out_dir = Path(args.out).expanduser() if args.out else Path(tempfile.mkdtemp(prefix="help-live-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    samples = ensure_samples(out_dir)
    failures = 0
    for figure in selected:
        for locale in figure.locales:
            for theme in figure.themes:
                try:
                    with LiveApp(backend=args.backend, out_dir=out_dir, locale=locale,
                                 theme=theme, width=args.width, height=args.height,
                                 rhi_backend=figure.rhi_backend) as live:
                        assert live.client is not None
                        run_steps(live.client, figure, samples)
                        # Read a flyout's rect BEFORE capturing: the element is
                        # alive right after the click, and __exit__ terminates
                        # the app (a lookup after the block is ConnectionRefused).
                        crop = figure.crop
                        rect = None
                        if figure.crop_element is not None:
                            rect = _element_crop(live.client, figure.crop_element)
                        shot = stable_capture(live.client, figure.capture,
                                              out_dir / f"{figure.id}__{locale}__{theme}.png",
                                              figure.min_size,
                                              figure.stable_interval_s)
                        capture_size = _image_size(shot)
                        if rect is not None:
                            pad, x, y, w, h = rect
                            if figure.capture == "@screen":
                                off_x = off_y = 0
                            else:
                                off_x = max(0, (capture_size[0] - live.width) // 2)
                                off_y = max(0, (capture_size[1] - live.height) // 2)
                            crop = (max(0, x + off_x - pad), max(0, y + off_y - pad),
                                    w + 2 * pad, h + 2 * pad)
                    destination = REPO_ROOT / figure.destination
                    crop_and_install(shot, destination, crop)
                    print(f"installed {figure.id} [{locale}/{theme}] -> {figure.destination}")
                except LiveError as exc:
                    failures += 1
                    print(f"FAILED {figure.id} [{locale}/{theme}]: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
