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
* **A crop names the thing that was driven.** ``crop_element`` takes an
  inventory/``@action`` reference (the same one ``ui_press`` uses), a union of
  references, or a top-level window; a caption substring is the legacy fallback,
  not the way to point at a control. And a crop is only placed correctly when
  the capture's own origin in screen space is known — ``@screen`` is ``(0, 0)``,
  a window grab is that window's screen position (see :func:`_capture_origin`).
* **A missing target fails the figure.** Cropping a frame that does not contain
  the surface installs a picture of empty background under a caption that
  describes something else; every selector raises instead.
* **A fixture a figure starts is closed with that figure.** A set_clipboard
  step starts an X clipboard owner child *before* the paste happens and (unlike a
  hand-run probe) cannot be left owning the selection when the figure ends, so
  :class:`FigureFixtures` closes it on the normal path and on any exception.
  ``ai_stub`` is the same idea one level up: the local answer server is started
  before boot and closed after the app is gone, and the app profile is seeded
  with its ``base_url`` (never a real endpoint, never a real key).

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
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from devtools import capture_surface  # noqa: E402  — canonical font/DPI bootstrap
from devtools import live_fixtures  # noqa: E402  — deterministic inputs, no import side effect
from devtools.help_figures import _free_display_number, xvfb_command  # noqa: E402

RECIPE_PATH = Path(__file__).with_name("help_figures_live.json")
SCHEMA_VERSION = 1
SAMPLE_NAMES = ("sunset", "forest", "ocean", "desert")

#: QSettings group the Image Gallery's Ask AI surface reads. Read from the app,
#: not invented: ``tabs/image_gallery/services/ai_settings_store.py`` owns
#: ``_QS_GROUP = "image_gallery_ai"`` and the keys seeded in
#: :func:`ai_profile_sections` (``enabled``, ``provider_id``, ``base_url``,
#: ``api_key``, ``model``). Seeding them is what points the running app at the
#: local stub instead of a real endpoint — no key, no network.
AI_SETTINGS_GROUP = "image_gallery_ai"
#: A placeholder credential: the stub ignores the Authorization header and the
#: app only requires the field to be non-empty (the Settings page says the same).
AI_STUB_API_KEY = "stub-key"

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
    #: Steps run *after* the stable capture (a held press is photographed and
    #: only then released). A failure here never discards the frame.
    after_capture: tuple[Step, ...] = ()
    #: ``{"answer": dict | str}`` — serve this fixed chat completion from a
    #: local stub whose ``base_url`` is seeded into the profile before boot.
    ai_stub: dict | None = None


def _parse_ai_stub(raw: object, figure_id: str) -> dict | None:
    """Validate a figure-level ``ai_stub`` block (default off)."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or "answer" not in raw:
        raise ValueError(f"{figure_id}: ai_stub needs an 'answer' (dict or str)")
    answer = raw["answer"]
    if not isinstance(answer, (dict, str)):
        raise ValueError(
            f"{figure_id}: ai_stub 'answer' must be a JSON object or a string, "
            f"got {type(answer).__name__}"
        )
    return {"answer": answer}


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
    if kind == "open_properties":
        # Pass-through to the control verb of the same name: it shows the app's
        # own image-properties dialog for an existing file.
        path = value.get("path") if isinstance(value, dict) else value
        if not path:
            raise ValueError(f"{figure_id}: open_properties needs a path")
        return Step("open_properties", {"path": str(path)})
    if kind in ("run_action", "press_keys"):
        return Step(kind, {"action_id" if kind == "run_action" else "keys": str(value)})
    if kind == "action":
        # Recipe spelling of the same pass-through: ``action`` → ``run_action``.
        return Step("run_action", {"action_id": str(value)})
    if kind == "sleep":
        return Step("sleep", {"seconds": float(value)})
    if kind == "wait_jobs":
        return Step("wait_jobs", {"timeout_s": float(value)})
    if kind == "set_clipboard":
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{figure_id}: set_clipboard needs an image path")
        return Step("set_clipboard", {"path": value})
    if kind == "ui_press":
        if not isinstance(value, dict):
            raise ValueError(f"{figure_id}: ui_press needs a dict")
        if not value.get("id"):
            raise ValueError(f"{figure_id}: ui_press needs an 'id'")
        kwargs = {"id": str(value["id"])}
        if "release" in value:
            if not isinstance(value["release"], bool):
                raise ValueError(
                    f"{figure_id}: ui_press 'release' must be a boolean "
                    "(false parks the press until after_capture releases it)"
                )
            kwargs["release"] = value["release"]
        if "hold_ms" in value:
            kwargs["hold_ms"] = int(value["hold_ms"])
        return Step("ui_press", kwargs)
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
                after_capture=tuple(
                    _parse_step(step, figure_id)
                    for step in entry.get("after_capture") or []
                ),
                ai_stub=_parse_ai_stub(entry.get("ai_stub"), figure_id),
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
    extra_sections: dict[str, dict[str, str]] | None = None,
) -> Path:
    """Seed QSettings before boot (theme, language, UI mode, window geometry).

    ``QSettings("improve-imgsli", "improve-imgsli")`` writes the INI below
    ``XDG_CONFIG_HOME``. Seeding it is what makes a variant figure possible
    without a live theme/language rebuild (measured: ``set_theme`` /
    ``set_language`` answer ``applied`` but the open window does not repaint).

    *extra_sections* appends further INI sections (``{group: {key: value}}``),
    which is how a figure points a QSettings-group setting (the Image Gallery
    Ask AI endpoint) at the local fixture instead of a real host — one write,
    before the app reads it, exactly as a user's own config would arrive.
    """
    profile = root / "config" / "improve-imgsli" / "improve-imgsli.conf"
    profile.parent.mkdir(parents=True, exist_ok=True)
    text = (
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
        f"rhi_backend={rhi_backend}\n"
    )
    for section, values in (extra_sections or {}).items():
        text += f"\n[{section}]\n"
        for key, value in values.items():
            text += f"{key}={value}\n"
    profile.write_text(text, encoding="utf-8")
    return profile


def ai_profile_sections(stub: live_fixtures.AiStub) -> dict[str, dict[str, str]]:
    """QSettings sections that point the app's Ask AI surface at *stub*.

    Keys are the ones ``AiSettingsStore.load`` reads (``enabled``,
    ``provider_id``, ``base_url``, ``api_key``, ``model``). ``provider_id`` is
    ``custom`` because that is the preset whose URL is the user's own — a preset
    id would pin a real vendor URL over the stub's.
    """
    return {
        AI_SETTINGS_GROUP: {
            "enabled": "true",
            "provider_id": "custom",
            "base_url": stub.base_url,
            "api_key": AI_STUB_API_KEY,
            "model": live_fixtures.STUB_MODEL_ID,
        }
    }



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
                 width: int, height: int, rhi_backend: str = "opengl",
                 profile_sections: dict[str, dict[str, str]] | None = None) -> None:
        self.backend = backend
        self.out_dir = Path(out_dir)
        self.locale = locale
        self.theme = theme
        self.width = width
        self.height = height
        self.rhi_backend = rhi_backend
        self.profile_sections = dict(profile_sections or {})
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
                      rhi_backend=self.rhi_backend,
                      extra_sections=self.profile_sections)
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


class FigureFixtures:
    """Fixtures a figure starts by step, closed with (or before) that figure.

    A clipboard owner is a *child process* that keeps the X selection alive: if
    the figure leaves without closing it, the selection outlives the run and the
    next figure pastes the previous figure's image. Every started fixture is
    closed in reverse start order, on the normal path and inside ``__exit__``
    when a later step raises.
    """

    def __init__(self) -> None:
        self._started: list[Any] = []
        #: Close failures, reported (never silently swallowed) by the caller.
        self.errors: list[str] = []

    def track(self, fixture: Any) -> Any:
        """Own *fixture*: it is closed (reverse order) when the scope ends."""
        self._started.append(fixture)
        return fixture

    def start_clipboard(self, path: Path) -> Any:
        return self.track(live_fixtures.set_clipboard_image(Path(path)))

    def close(self) -> None:
        while self._started:
            fixture = self._started.pop()
            closer = getattr(fixture, "close", None)
            if not callable(closer):
                continue
            try:
                closer()
            except Exception as exc:  # noqa: BLE001 - reported, not fatal
                message = f"{type(fixture).__name__}.close(): {exc}"
                self.errors.append(message)
                print(f"WARN fixture not closed: {message}", file=sys.stderr)

    def __enter__(self) -> "FigureFixtures":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _substitute(kwargs: dict, samples: Path) -> dict:
    """Expand ``@samples`` in any string value (paths and stub answers alike)."""
    out = {}
    for key, value in kwargs.items():
        if isinstance(value, str) and "@samples" in value:
            out[key] = value.replace("@samples", str(samples))
        else:
            out[key] = value
    return out


def _run_step(app: LiveClient, step: Step, samples: Path,
              fixtures: FigureFixtures) -> None:
    """Run one validated step against the live app."""
    kwargs = _substitute(dict(step.kwargs), samples)
    if step.kind == "set_clipboard":
        fixtures.start_clipboard(Path(kwargs["path"]))
        return
    if step.kind == "sleep":
        time.sleep(kwargs["seconds"])
        return
    if step.kind == "wait_jobs":
        deadline = time.monotonic() + kwargs["timeout_s"]
        quiet = 0
        while quiet < 2:
            count = int(app.call("jobs_list").get("count") or 0)
            quiet = quiet + 1 if count == 0 else 0
            if time.monotonic() > deadline:
                raise LiveError(f"jobs did not settle within {kwargs['timeout_s']:.0f}s")
            time.sleep(0.4)
        return
    if step.kind == "open_tab":
        app.call("open_tab", kwargs)
        wait_for_active_session(app, kwargs["tab"])
        return
    if step.kind == "open_folder" and kwargs.get("tab"):
        wait_for_active_session(app, kwargs["tab"])
    app.call(step.kind, kwargs)


def run_steps(app: LiveClient, figure: LiveFigure, samples: Path,
              *, fixtures: FigureFixtures | None = None) -> None:
    """Run the figure's scenario steps in order.

    *fixtures* is the figure's fixture scope; without one the steps get a
    private scope that is closed before returning (or raising), so a caller can
    never leak a started clipboard. Post-capture steps are not run here — they
    belong after the frame exists (:func:`run_after_capture`).
    """
    scope = fixtures if fixtures is not None else FigureFixtures()
    owned = fixtures is None
    try:
        for step in figure.steps:
            _run_step(app, step, samples, scope)
    finally:
        if owned:
            scope.close()


def run_after_capture(app: LiveClient, figure: LiveFigure, samples: Path,
                      fixtures: FigureFixtures) -> list[str]:
    """Run ``after_capture`` steps; return their failures instead of raising.

    The frame is already captured and trustworthy at this point, so a cleanup
    step (the release of a held press, a fixture stop) must not throw it away —
    but it must not vanish either: the caller prints every returned message.
    """
    errors: list[str] = []
    for step in figure.after_capture:
        try:
            _run_step(app, step, samples, fixtures)
        except Exception as exc:  # noqa: BLE001 - reported with the frame kept
            errors.append(f"{step.kind} {step.kwargs}: {exc}")
    return errors


def _screen_png(app: LiveClient, out_path: Path) -> Path:
    """Whole-X-screen grab (popups included), for flyout/menu figures.

    ``capture_live`` grabs one window; a toolkit flyout is an in-app
    ``BaseFlyout`` (``Qt.Widget``) child attached to the window's overlay
    layer, and the X ``grabWindow`` path still misses it (measured: the menu is
    in ``ui_elements`` while the window capture shows only the chrome behind
    it; a tab grab never includes a window-level overlay). The screen image is
    1:1 with screen coordinates, which is exactly what an element's
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


#: Margin around a cropped target, in screen px. Wide enough that a press ring
#: (and the neighbouring control in a union crop) is not clipped at the edge.
DEFAULT_CROP_PAD = 6


def _layout_dump(app: LiveClient) -> dict:
    """The app's own widget-tree dump (``dump_ui_layout``), parsed.

    The one place that names a *window* rather than an element: a dialog or an
    in-window overlay has no interactive row to point at, but the dump lists
    every top-level widget with its screen geometry and its ``visible`` flag.
    """
    result = app.call("dump_ui_layout", {})
    path = Path(str(result.get("path") or ""))
    if not path.is_file():
        raise LiveError(f"dump_ui_layout wrote no readable file ({path})")
    return json.loads(path.read_text(encoding="utf-8"))


def _window_node(data: dict, name: str) -> dict | None:
    """The visible top-level window whose class or object name is *name*."""
    matches = [
        node
        for node in data.get("windows") or []
        if isinstance(node, dict)
        and node.get("visible")
        and name in (str(node.get("class") or ""), str(node.get("object_name") or ""))
    ]
    if not matches:
        return None
    # A dialog family can be instantiated twice; the active one is the one a
    # reader is looking at, and it is the only one a still frame can show.
    for node in matches:
        if node.get("is_active_window"):
            return node
    return matches[0]


def _rect_of(rect: object, what: str) -> tuple[int, int, int, int]:
    """``[x, y, w, h]`` → an int tuple, refusing a degenerate/absent rect."""
    if not rect or not isinstance(rect, (list, tuple)) or len(rect) != 4:
        raise LiveError(f"crop_element: {what} has no usable rect ({rect!r})")
    x, y, width, height = (int(v) for v in rect)
    if width <= 0 or height <= 0:
        raise LiveError(f"crop_element: {what} is collapsed ({width}x{height})")
    return x, y, width, height


def _element_rows(app: LiveClient) -> dict[str, dict]:
    """Inventory rows by full id *and* by ``@<action id>``.

    ``include_disabled`` is on purpose: a control can be present and visible but
    disabled (``clear list`` with nothing to clear), and a pressed neighbour is
    still part of the picture. A hidden row is filtered by the caller instead of
    here, so the failure can name *why* it is unusable.
    """
    rows = app.call("ui_elements", {"include_disabled": True}).get("elements") or []
    index: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        element_id = str(row.get("id") or "")
        if element_id:
            index.setdefault(element_id, row)
            # The ``@<action id>`` suffix is how ``ui_press``/``ui_click`` name
            # a control too, so both spellings must reach the same row.
            if "@" in element_id:
                index.setdefault("@" + element_id.rsplit("@", 1)[-1], row)
        action_id = row.get("action_id")
        if action_id:
            index.setdefault(f"@{action_id}", row)
    return index


def _element_crop(app: LiveClient, spec: dict) -> tuple[int, int, int, int, int]:
    """Crop box ``(pad, x, y, w, h)`` in screen px for one live target.

    Three selectors, each the smallest surface that can name the region:

    * ``id`` / ``ids`` — inventory references, ``@<action id>`` included, i.e.
      the *same* reference ``ui_press``/``ui_click`` drives. Photographing by
      reference is what keeps a figure from cropping a different widget than the
      one it pressed (measured 2026-10-21: the long-press recipe named its
      button by ``role``+``label`` and a label lookup is a *substring scan* over
      every window, so the crop followed the caption, not the control). Several
      ids crop their union — the two adjacent long-press list buttons are one
      figure.
    * ``window`` — a top-level window's own rect (see :func:`_window_node`): the
      video-editor export dialog is a separate top-level, and the paste direction
      picker paints its targets in one ``paintEvent``, so neither owns an
      element row to crop by.
    * ``role`` / ``label`` — the guarded legacy form, kept for the flyout figure.

    A target that is not on screen raises instead of cropping nothing: a missing
    overlay must fail the figure, never install a frame of empty background.
    """
    pad = int(spec.get("pad", DEFAULT_CROP_PAD))
    name = spec.get("window")
    if name:
        node = _window_node(_layout_dump(app), str(name))
        if node is None:
            raise LiveError(
                f"crop_element: no visible window {str(name)!r} at capture time - "
                "that surface is not on screen (its class is what dump_ui_layout "
                "reports for a top-level)"
            )
        x, y, width, height = _rect_of(node.get("geometry"), f"window {str(name)!r}")
        return pad, x, y, width, height
    ids = spec.get("ids") or ([spec["id"]] if spec.get("id") else [])
    if ids:
        index = _element_rows(app)
        rects = []
        for needle in ids:
            row = index.get(str(needle))
            if row is None:
                raise LiveError(
                    f"crop_element: no live element {str(needle)!r} - use an "
                    "inventory id or @action id (ui_elements rows carry both)"
                )
            if not row.get("visible"):
                raise LiveError(
                    f"crop_element: element {str(needle)!r} is not visible, so it "
                    "has no pixels to crop"
                )
            rects.append(_rect_of(row.get("screen_rect") or row.get("rect"), str(needle)))
        left = min(rect[0] for rect in rects)
        top = min(rect[1] for rect in rects)
        right = max(rect[0] + rect[2] for rect in rects)
        bottom = max(rect[1] + rect[3] for rect in rects)
        return pad, left, top, right - left, bottom - top
    params = {}
    for key in ("role", "label"):
        if spec.get(key):
            params[key] = str(spec[key])
    if not params:
        raise LiveError("crop_element needs id/ids, window or role/label")
    elements = app.call("ui_elements", params).get("elements") or []
    if not elements:
        raise LiveError(f"crop_element: no element matched {params!r}")
    x, y, width, height = _rect_of(
        elements[0].get("screen_rect") or elements[0].get("rect"), repr(params)
    )
    return pad, x, y, width, height


def _capture_origin(
    app: LiveClient, what: str, capture_size: tuple[int, int]
) -> tuple[int, int]:
    """Screen origin of a captured image, for mapping ``screen_rect`` onto it.

    ``screen_rect`` is absolute screen space, so a crop must subtract the image's
    own origin. ``@screen`` is the X root, i.e. ``(0, 0)`` — the 1:1 mapping the
    live-capture docs promise. A window grab starts at that window's own screen
    position, which the layout dump names; guessing it from the seeded window
    size is what shipped a shifted crop once (measured 2026-10-21: the guess
    centred the 16 px CSD shadow on both sides and re-added it, so a 36x36
    button was clipped on two edges inside its own 48x48 crop).

    A grab that was clipped (window partly off screen, DPR-scaled pixels) has an
    origin this cannot name: that raises, with the ``@screen`` form as the hint,
    instead of cropping a shifted region.
    """
    if what == "@screen":
        return 0, 0
    data = _layout_dump(app)
    # ``dump_ui_layout`` names the active window as "Class:objectName" — the same
    # window ``capture_live`` grabs when no ``what`` is given.
    active_class, _, active_object = str(data.get("active_window") or "").partition(":")
    node = None
    for candidate in data.get("windows") or []:
        if not isinstance(candidate, dict):
            continue
        identity = (
            str(candidate.get("class") or ""),
            str(candidate.get("object_name") or ""),
        )
        if active_class and identity == (active_class, active_object):
            node = candidate
            break
    if node is None:
        raise LiveError(
            f"{what}: the grabbed window is not in the layout dump (active_window="
            f"{data.get('active_window') or 'none'!r}), so a screen-rect crop cannot "
            "be placed - capture @screen for a crop_element figure"
        )
    x, y, width, height = _rect_of(node.get("geometry"), "the captured window")
    if (width, height) != tuple(capture_size):
        raise LiveError(
            f"{what}: grabbed {capture_size[0]}x{capture_size[1]} but the window is "
            f"{width}x{height} (clipped or scaled grab), so the image origin is "
            "unknown - capture @screen for a crop_element figure"
        )
    return x, y


def crop_and_install(
    screenshot: Path, destination: Path, crop: tuple[int, int, int, int] | None
) -> Path:
    from PIL import Image

    with Image.open(screenshot) as image:
        if crop is not None:
            x, y, w, h = (int(v) for v in crop)
            left = max(0, min(x, image.width))
            top = max(0, min(y, image.height))
            right = max(left, min(x + w, image.width))
            bottom = max(top, min(y + h, image.height))
            if right <= left or bottom <= top:
                raise LiveError(
                    f"crop {tuple(crop)} falls outside the {image.width}x{image.height} "
                    "capture - the target moved or the capture does not cover it"
                )
            # Clamped, never padded: PIL pads an out-of-bounds crop with black,
            # which reads as a rendering defect in the shipped figure.
            image = image.crop((left, top, right, bottom))
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
            crop = f"crop={figure.crop}"
            if figure.crop_element is not None:
                crop += " crop_element=" + json.dumps(figure.crop_element, sort_keys=True)
            print(f"{figure.id:28} capture={figure.capture:16} {crop} "
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
                label = f"{figure.id} [{locale}/{theme}]"
                stub: live_fixtures.AiStub | None = None
                try:
                    sections: dict[str, dict[str, str]] = {}
                    if figure.ai_stub is not None:
                        # Before boot, never after: the app reads QSettings once
                        # at startup and an endpoint edited later would need the
                        # settings page to re-read it.
                        answer = figure.ai_stub["answer"]
                        if isinstance(answer, str) and "@samples" in answer:
                            answer = answer.replace("@samples", str(samples))
                        stub = live_fixtures.ai_stub_server(answer)
                        sections = ai_profile_sections(stub)
                    with LiveApp(backend=args.backend, out_dir=out_dir, locale=locale,
                                 theme=theme, width=args.width, height=args.height,
                                 rhi_backend=figure.rhi_backend,
                                 profile_sections=sections) as live:
                        assert live.client is not None
                        with FigureFixtures() as fixtures:
                            run_steps(live.client, figure, samples, fixtures=fixtures)
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
                                origin_x, origin_y = _capture_origin(
                                    live.client, figure.capture, capture_size
                                )
                                crop = (x - origin_x - pad, y - origin_y - pad,
                                        w + 2 * pad, h + 2 * pad)
                            for message in run_after_capture(live.client, figure, samples, fixtures):
                                print(f"WARN {label} after_capture: {message}", file=sys.stderr)
                            for message in fixtures.errors:
                                print(f"WARN {label} fixture: {message}", file=sys.stderr)
                    destination = REPO_ROOT / figure.destination
                    crop_and_install(shot, destination, crop)
                    print(f"installed {figure.id} [{locale}/{theme}] -> {figure.destination}")
                except LiveError as exc:
                    failures += 1
                    print(f"FAILED {label}: {exc}", file=sys.stderr)
                finally:
                    if stub is not None:
                        stub.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
